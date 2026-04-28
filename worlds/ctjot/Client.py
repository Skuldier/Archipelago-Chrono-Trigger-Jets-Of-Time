import json
import logging

from NetUtils import ClientStatus, NetworkItem

from worlds.AutoSNIClient import SNIClient

snes_logger = logging.getLogger("SNES")

# FXPAK Pro protocol memory mapping used by SNI
ROM_START = 0x000000
WRAM_START = 0xF50000
WRAM_SIZE = 0x20000
SRAM_START = 0xE00000

# CTJoT addresses/constants
# TODO: Unify the address scheme.  These use the SNES addresses,
#       but SNI maps things a little differently.
#       For now I'm just converting on the fly when they are used.
EVENT_BLOCK_SIZE = 0x200
EVENT_BASE_ADDR = 0x7F0000
TREASURE_BASE_ADDR = 0x7F0001
# --- AP receive queue (Phase A architecture) ---
#
# Items inbound from other slots queue up in WRAM at 0x7E2900+, a
# region inside the "Appears to be unused space (included in SRAM)"
# block (0x7E2880-0x7E297F) in the Chrono Compendium memory map.
# The receive hook drains up to AP_QUEUE_CAPACITY items per map
# transition.
#
# Layout (must mirror patches.py:AP_QUEUE_*):
#   0x7E2900..0x7E2903   queue slots (item byte per slot)
#   0x7E2904             queue count (0..AP_QUEUE_CAPACITY)
#   0x7E2905             total received counter (1 byte)
#
# Why a queue: in the previous single-byte design, if items arrived
# faster than the hook drained or if the byte got clobbered between
# SNI write and hook fire, items silently vanished. With a 4-slot
# queue plus read-back verification below, individual write drops
# recover and rapid-fire arrivals stack up without overwriting
# each other.
#
# Why 0x7E2900+ specifically: an earlier Phase A attempt put the
# queue at flag-memory 0x7F01F0+ -- "Location storyline flags"
# (ferry departures); writing there triggered the boat cutscene
# every map exit. v1.4.1 moved to 0x7E2880+ thinking that was
# unused. v1.4.4 moved again to 0x7E2900+ because cjot-beta's
# patch_timegauge (basepatch.py:262) repurposes 0x7E2881-0x7E288D
# as the Epoch time-period table -- our queue/counter writes were
# corrupting the dial after the first item delivery. 0x7E2900+ is
# clear of that table and still inside the documented unused-but-
# saved range.
AP_QUEUE_BASE_ADDR = 0x7E2900
AP_QUEUE_COUNT_ADDR = 0x7E2904
AP_QUEUE_CAPACITY = 4
RECEIVED_ITEM_COUNT_ADDR = 0x7E2905

# --- Rock pickup completion bytes (Rocksanity) ---
#
# The script-treasure rocks (Denadoro/Laruba/Kajar) live at LocIDs
# whose vanilla CT scripts use the storyline counter, not bit flags,
# to track event completion -- so there's no per-rock event flag we
# can watch in the standard 0x7F0000-0x7F01FF flag-memory region.
#
# patches.py:install_rock_pickup_flags injects a tiny "write 1 to
# WRAM byte" command after the add-item in each rock's pickup
# script. We read those bytes each tick. Non-zero = pickup occurred.
#
# Black Omen Terra Rock is a ChestTreasure (chest_id 0xCE) -- it's
# already covered by the existing data-driven chest-flag mechanism
# (chest 0xCE -> byte offset 0x19, bit mask 0x40), see
# _locations_treasure_chests below.
ROCK_PICKUP_BASE_ADDR = 0x7E2906  # 3 bytes follow, one per script-treasure rock
ROCK_PICKUP_NUM_BYTES = 3
VICTORY_ADDRESS = 0x7F0020
LOCATION_ADDRESS = 0xF50100  # already in SNI addressing

# These are already in SNI addressing
# NOTE: SNI with RetroArch can't read past 4MB in the ROM
#       Validation data must be before 4MB or the client can't validate/connect to the game
VALIDATION_ADDR = ROM_START + 0x3F8C03
VALIDATION_SIZE = 32

# Item and location ID offsets
LOCATION_ID_START = 5100000
ITEM_ID_START = 5100000
MAX_IN_GAME_ITEM_ID = 255

# Don't track on the Load Screen(0x00) or Title Screen(0x1B1)
INVALID_TRACKING_LOCATIONS = [0x00, 0x1B1]
MAX_MAP_ID = 0x1FF


# These are the event flag locations for the baseline (non chronosanity) checks
_locations_baseline_key_items = {
    # ##########
    # Prehistory
    # ##########
    "Reptite Lair Key": (0x7F0105, 0x20),

    # ##########
    # Dark Ages
    # ##########
    "Mt Woe Key": (0x7F0100, 0x20),

    # ##########
    # 600 AD
    # ##########
    # NOTE: Giant's Claw Key is triggered on warping out of the cave,
    #       not immediately on picking up the key item from the shell.
    "Giants Claw Key": (0x7F00A9, 0x80),
    "Zenan Bridge Key": (0x7F0101, 0x02),
    "Denadoro Mts Key": (0x7F0102, 0x02),
    "Frogs Burrow Left": (0x7F0106, 0x04),

    # This only applies in vanilla rando mode
    "Cyrus Grave Key": (0x7F01A3, 0x40),

    # Beta ADD_OZZIE_SPOT: pickup runs inline with the Ozzie defeat script
    # (OZZIES_FORT_THRONE_INCOMPETENCE, obj 8, fn 2). The beta's
    # vanillarando.add_check_to_ozzies_fort_script() now sets bit 0x02 on
    # the Ozzie's Fort state byte; other bits on this byte: 0x01 = met,
    # 0x04 = Flea+ defeated, 0x08 = Super Slash defeated.
    "Ozzies Fort Key": (0x7F01A1, 0x02),

    # ##########
    # 1000 AD
    # ##########
    "Fiona Key": (0x7F007C, 0x80),
    "Kings Trial Key": (0x7F00A2, 0x80),
    "Snail Stop Key": (0x7F01D0, 0x10),
    "Lazy Carpenter": (0x7F019E, 0x80),
    "Taban Key": (0x7F007A, 0x01),
    "Melchior Key": (0x7F001F, 0x80),

    # This only applies in vanilla rando mode
    "Bekkler Key": (0x7F007C, 0x01),

    # ##########
    # 2300 AD
    # ##########
    "Arris Dome Key": (0x7F00A4, 0x01),
    # Beta SPLIT_ARRIS_DOME: corpse gives Seed KI; flag set explicitly
    # in vanillarando.add_arris_food_locker_check() via
    # EC.set_bit(0x7F00A4, 0x02) -- sibling bit of Arris Dome Key.
    "Arris Dome Food Locker Key": (0x7F00A4, 0x02),
    "Sun Palace Key": (0x7F013A, 0x02),
    # Beta ADD_SUNKEEP_SPOT: Sunstone KI pickup; flag set explicitly in
    # vanillarando.split_sunstone_quest() via EC.set_bit(0x7F013A, 0x40).
    "Sun Keep 2300": (0x7F013A, 0x40),
    "Geno Dome Key": (0x7F013B, 0x10)
}

# These are things like sealed chests and the chests
# at the Northern Ruins that aren't treated like normal
# treasure chests.  These are handled in event code.
_locations_event_treasures = {
    "Northern Ruins Antechamber Left 600": (0x7F01AC, 0x08),
    "Northern Ruins Antechamber Sealed 600": (0x7F01A9, 0x20),
    "Northern Ruins Antechamber Left 1000": (0x7F01AC, 0x04),
    "Northern Ruins Antechamber Sealed 1000": (0x7F01A6, 0x01),
    "Northern Ruins Back Left Sealed 600": (0x7F01A9, 0x40),
    "Northern Ruins Back Right Sealed 600": (0x7F01A9, 0x80),
    "Northern Ruins Back Left Sealed 1000": (0x7F01A6, 0x02),
    "Northern Ruins Back Right Sealed 1000": (0x7F01A6, 0x04),
    "Northern Ruins Basement 600": (0x7F01AC, 0x02),
    "Northern Ruins Basement 1000": (0x7F01AC, 0x01),
    "Truce Inn Sealed 600": (0x7F014A, 0x80),
    "Porre Elder Sealed 1": (0x7F01D3, 0x10),
    "Porre Elder Sealed 2": (0x7F01D3, 0x20),
    "Guardia Castle Sealed 600": (0x7F00D9, 0x02),
    "Guardia Forest Sealed 600": (0x7F01D2, 0x80),
    "Truce Inn Sealed 1000": (0x7F014A, 0x20),
    "Porre Mayor Sealed 1": (0x7F01D1, 0x40),
    "Porre Mayor Sealed 2": (0x7F01D1, 0x80),
    "Guardia Forest Sealed 1000": (0x7F01D1, 0x20),
    "Guardia Castle Sealed 1000": (0x7F00D9, 0x04),
    "Heckran Sealed 1": (0x7F01A0, 0x04),
    "Heckran Sealed 2": (0x7F01A0, 0x04),
    "Magic Cave Sealed": (0x7F0079, 0x01),

    # The pyramid chests share a flag.  Opening one will cause the other to vanish.
    # In the normal randomizer the player could only get one of these, but in multiworld
    # we will send items for both chests when the flag is cleared.
    "Pyramid Left": (0x7F01A0, 0x01),
    "Pyramid Right": (0x7F01A0, 0x01),

}

# Not currently used for item randomization
_locations_tab_events = {
    "Guardia Forest Power Tab 600": 192,
    "Guardia Forest Power Tab 1000": 193,
    "Manoria Confinement Power Tab": 194,
    "Porre Market 600 Power Tab": 195,
    "Denadoro Mts Speed Tab": 196,
    "Tomas Grave Speed Tab": 197,
    "Giants Claw Caverns Power Tab": 198,
    "Giants Claw Entrance Power Tab": 199,
    "Giants Claw Traps Power Tab": 200,
    "Sun Keep 600 Power Tab": 201,
    "Medina Elder Speed Tab": 202,
    "Medina Elder Magic Tab": 203,
    "Magus Castle Flea Magic Tab": 204,
    "Magus Castle Dungeons Magic Tab": 205,
    "Trann Dome Sealed Magic Tab": 206,
    "Arris Dome Sealed Power Tab": 207,
    "Death Peak Power Tab": 208,
}

# Location IDs for miscellaneous events.
#
# WARNING: this dict is currently NOT iterated by _track_locations,
# so any location that lives ONLY here is silently un-tracked. The
# original author left these as placeholder integer values pending a
# watch implementation that never landed. The four rock spots that
# used to live here have been moved -- Giants Claw and Black Omen
# Terra Rock to _locations_treasure_chests (chest-flag tracking),
# Denadoro/Laruba/Kajar Rock to _locations_wram_rock_pickups (WRAM
# pickup-byte tracking, see patches.py:install_rock_pickup_flags).
# The remaining entries (Taban/Trading Post/Jerky) are still
# unwatched -- a future fix should give them proper trackable
# event-flag tuples.
_locations_misc_events = {
    "Taban Gift Weapon": 300,
    "Taban Gift Helm": 301,
    "Trading Post Ranged Weapon": 302,
    "Trading Post Accessory": 303,
    "Trading Post Tab": 304,
    "Trading Post Melee Weapon": 305,
    "Trading Post Armor": 306,
    "Trading Post Helm": 307,
    "Jerky Gift": 308,
}

# Rocksanity rock pickups for the three ScriptTreasure rocks. Watched
# via WRAM bytes that patches.py:install_rock_pickup_flags injects
# into the rock pickup scripts. Each rock writes 1 to its own byte;
# non-zero on the watcher side reports the location check.
_locations_wram_rock_pickups = {
    "Denadoro Rock": ROCK_PICKUP_BASE_ADDR + 0,  # 0x7E2906
    "Laruba Rock":   ROCK_PICKUP_BASE_ADDR + 1,  # 0x7E2907
    "Kajar Rock":    ROCK_PICKUP_BASE_ADDR + 2,  # 0x7E2908
}

# These are treasure chests that are not considered in logic for
# key items.  Some may still hold bucket fragments.
_locations_treasure_chests_not_in_logic = {
    "Guardia Jail Fritz Storage": (0x01, 0x02),
    "Guardia Jail Cell": (0x02, 0x01),
    "Guardia Jail Omnicrone 1": (0x02, 0x02),
    "Guardia Jail Omnicrone 2": (0x02, 0x04),
    "Guardia Jail Omnicrone 3": (0x02, 0x08),
    "Guardia Jail Hole 1": (0x02, 0x10),
    "Guardia Jail Hole 2": (0x02, 0x20),
    "Guardia Jail Outer Wall": (0x02, 0x40),
    "Guardia Jail Omnicrone 4": (0x02, 0x80),
    "Guardia Jail Fritz": (0x03, 0x01),
    "Sunken Desert B1 Nw": (0x08, 0x01),
    "Sunken Desert B1 Ne": (0x08, 0x02),
    "Sunken Desert B1 Se": (0x08, 0x04),
    "Sunken Desert B1 Sw": (0x08, 0x08),
    "Sunken Desert B2 Nw": (0x08, 0x10),
    "Sunken Desert B2 N": (0x08, 0x20),
    "Sunken Desert B2 W": (0x09, 0x02),
    "Sunken Desert B2 Sw": (0x09, 0x01),
    "Sunken Desert B2 Se": (0x08, 0x80),
    "Sunken Desert B2 E": (0x08, 0x40),
    "Sunken Desert B2 Center": (0x09, 0x04),
    "Magus Castle Right Hall": 219,
    "Magus Castle Guillotine 1": 231,
    "Magus Castle Guillotine 2": 232,
    "Magus Castle Slash Room 1": 233,
    "Magus Castle Slash Room 2": 234,
    "Magus Castle Statue Hall": 235,
    "Magus Castle Four Kids": 236,
    "Magus Castle Ozzie 1": 237,
    "Magus Castle Ozzie 2": 238,
    "Magus Castle Enemy Elevator": 239,
    "Reptite Lair Secret B2 Ne Right": 240,
    "Death Peak South Face Krakker": 243,
    "Death Peak South Face Spawn Save": 244,
    "Death Peak South Face Summit": 245,
    "Death Peak Field": 246,
    "Death Peak Krakker Parade": 247,
    "Death Peak Caves Left": 248,
    "Death Peak Caves Center": 249,
    "Death Peak Caves Right": 250,
    "Reptite Lair Secret B1 Sw": 251,
    "Reptite Lair Secret B1 Ne": (0x15, 0x01),
    "Reptite Lair Secret B1 Se": 253,
    "Reptite Lair Secret B2 Se Right": 254,
    "Reptite Lair Secret B2 Ne Or Se Left": (0x15, 0x08),
    "Reptite Lair Secret B2 Sw": 256,
    "Giants Claw Throne 1": 257,
    "Giants Claw Throne 2": 258,
    "Tyrano Lair Trapdoor": 259,
    "Tyrano Lair Kino Cell": 260,
    "Tyrano Lair Maze 1": 261,
    "Tyrano Lair Maze 2": 262,
    "Tyrano Lair Maze 3": 263,
    "Tyrano Lair Maze 4": 264,
    "Black Omen Aux Command Mid": 265,
    "Black Omen Aux Command Ne": 266,
    "Black Omen Grand Hall": 267,
    "Black Omen Nu Hall Nw": 268,
    "Black Omen Nu Hall W": 269,
    "Black Omen Nu Hall Sw": 270,
    "Black Omen Nu Hall Ne": 271,
    "Black Omen Nu Hall E": 272,
    "Black Omen Nu Hall Se": 273,
    "Black Omen Royal Path": 274,
    "Black Omen Ruminator Parade": 275,
    "Black Omen Eyeball Hall": 276,
    "Black Omen Tubster Fly": 277,
    "Black Omen Martello": 278,
    "Black Omen Alien Sw": 279,
    "Black Omen Alien Ne": 280,
    "Black Omen Alien Nw": 281,
    "Black Omen Terra W": 282,
    "Black Omen Terra Ne": 284,
    "Ocean Palace Main S": 285,
    "Ocean Palace Main N": 286,
    "Ocean Palace E Room": 287,
    "Ocean Palace W Room": 288,
    "Ocean Palace Switch Nw": 289,
    "Ocean Palace Switch Sw": 290,
    "Ocean Palace Switch Ne": 291,
    "Ocean Palace Switch Secret": 292,
    "Ocean Palace Final": 293,
    "Magus Castle Left Hall": 294,
    "Magus Castle Unskippables": 295,
    "Magus Castle Pit E": 296,
    "Magus Castle Pit Ne": 297,
    "Magus Castle Pit Nw": 298,
    "Magus Castle Pit W": 299,
}

# Treasure locations with offset from treasure base addr and a bit flag
_locations_treasure_chests = {
    "Mt Woe 1St Screen": (0x1B, 0x08),
    "Mt Woe 2Nd Screen 1": (0x1A, 0x02),
    "Mt Woe 2Nd Screen 2": (0x1A, 0x04),
    "Mt Woe 2Nd Screen 3": (0x1A, 0x08),
    "Mt Woe 2Nd Screen 4": (0x1A, 0x10),
    "Mt Woe 2Nd Screen 5": (0x1A, 0x20),
    "Mt Woe 3Rd Screen 1": (0x1A, 0x40),
    "Mt Woe 3Rd Screen 2": (0x1A, 0x80),
    "Mt Woe 3Rd Screen 3": (0x1B, 0x01),
    "Mt Woe 3Rd Screen 4": (0x1B, 0x02),
    "Mt Woe 3Rd Screen 5": (0x1B, 0x04),
    "Mt Woe Final 1": (0x1B, 0x10),
    "Mt Woe Final 2": (0x1B, 0x20),
    "Arris Dome Rats": (0x0E, 0x02),
    "Arris Dome Food Store": (0x1A, 0x01),
    "Sewers 1": (0x10, 0x10),
    "Sewers 2": (0x10, 0x20),
    "Sewers 3": (0x10, 0x40),
    "Lab 16 1": (0x0D, 0x20),
    "Lab 16 2": (0x0D, 0x40),
    "Lab 16 3": (0x0D, 0x80),
    "Lab 16 4": (0x0E, 0x01),
    "Lab 32 1": (0x0E, 0x80),
    # Lab 32 Race Log = ChestTreasure(0x78) -> 0x78 // 8 = 0x0F, 1 << (0x78 % 8) = 0x01
    "Lab 32 Race Log": (0x0F, 0x01),
    "Prison Tower 1000": (0x1E, 0x40),
    "Geno Dome 1F 1": (0x11, 0x08),
    "Geno Dome 1F 2": (0x11, 0x10),
    "Geno Dome 1F 3": (0x11, 0x20),
    "Geno Dome 1F 4": (0x11, 0x40),
    "Geno Dome Room 1": (0x11, 0x80),
    "Geno Dome Room 2": (0x12, 0x01),
    "Geno Dome Proto4 1": (0x12, 0x02),
    "Geno Dome Proto4 2": (0x12, 0x04),
    "Geno Dome 2F 1": (0x13, 0x02),
    "Geno Dome 2F 2": (0x13, 0x04),
    "Geno Dome 2F 3": (0x13, 0x08),
    "Geno Dome 2F 4": (0x13, 0x10),
    "Factory Left Aux Console": (0x0F, 0x02),
    "Factory Left Security Right": (0x0F, 0x04),
    "Factory Left Security Left": (0x0F, 0x08),
    "Factory Right Data Core 1": (0x12, 0x08),
    "Factory Right Data Core 2": (0x12, 0x10),
    "Factory Right Floor Top": (0x0F, 0x10),
    "Factory Right Floor Left": (0x0F, 0x20),
    "Factory Right Floor Bottom": (0x0F, 0x40),
    "Factory Right Floor Secret": (0x0F, 0x80),
    "Factory Right Crane Lower": (0x10, 0x02),
    "Factory Right Crane Upper": (0x10, 0x01),
    "Factory Right Info Archive": (0x10, 0x04),
    "Giants Claw Kino Cell": (0x03, 0x02),
    "Giants Claw Traps": (0x03, 0x04),
    "Giants Claw Caves 1": (0x0B, 0x04),
    "Giants Claw Caves 2": (0x0B, 0x08),
    "Giants Claw Caves 3": (0x0B, 0x10),
    "Giants Claw Caves 4": (0x0B, 0x20),
    "Giants Claw Caves 5": (0x0B, 0x80),
    # Rocksanity ChestTreasure rocks (data-driven, chest-flag tracked).
    # Giants Claw Rock = ChestTreasure(0x5E) -> 0x5E // 8 = 0x0B, 1 << (0x5E % 8) = 0x40
    # Black Omen Terra Rock = ChestTreasure(0xCE) -> 0xCE // 8 = 0x19, 1 << (0xCE % 8) = 0x40
    "Giants Claw Rock":      (0x0B, 0x40),
    "Black Omen Terra Rock": (0x19, 0x40),
    "Guardia Basement 1": (0x00, 0x40),
    "Guardia Basement 2": (0x00, 0x80),
    "Guardia Basement 3": (0x01, 0x01),
    "Guardia Treasury 1": (0x1D, 0x01),
    "Guardia Treasury 2": (0x1D, 0x02),
    "Guardia Treasury 3": (0x1D, 0x04),
    "Ozzies Fort Guillotines 1": (0x0A, 0x10),
    "Ozzies Fort Guillotines 2": (0x0A, 0x20),
    "Ozzies Fort Guillotines 3": (0x0A, 0x40),
    "Ozzies Fort Guillotines 4": (0x0A, 0x80),
    "Ozzies Fort Final 1": (0x0B, 0x01),
    "Ozzies Fort Final 2": (0x0B, 0x02),
    "Truce Mayor 1F": (0x00, 0x04),
    "Truce Mayor 2F": (0x00, 0x08),
    "Forest Ruins": (0x01, 0x04),
    "Porre Mayor 2F": (0x01, 0x80),
    "Truce Canyon 1": (0x03, 0x08),
    "Truce Canyon 2": (0x03, 0x10),
    "Fionas House 1": (0x07, 0x40),
    "Fionas House 2": (0x07, 0x80),
    "Cursed Woods 1": (0x05, 0x01),
    "Cursed Woods 2": (0x05, 0x02),
    "Frogs Burrow Right": (0x05, 0x04),
    "Heckran Cave Sidetrack": (0x01, 0x08),
    "Heckran Cave Entrance": (0x01, 0x10),
    "Heckran Cave 1": (0x01, 0x20),
    "Heckran Cave 2": (0x01, 0x40),
    "Kings Room 1000": (0x00, 0x10),
    "Queens Room 1000": (0x00, 0x20),
    "Kings Room 600": (0x03, 0x20),
    "Queens Room 600": (0x03, 0x40),
    "Royal Kitchen": (0x03, 0x80),
    "Queens Tower 600": (0x1D, 0x08),
    "Kings Tower 600": (0x1E, 0x04),
    "Kings Tower 1000": (0x1E, 0x08),
    "Queens Tower 1000": (0x1E, 0x10),
    "Guardia Court Tower": (0x1E, 0x20),
    "Manoria Cathedral 1": (0x04, 0x02),
    "Manoria Cathedral 2": (0x04, 0x04),
    "Manoria Cathedral 3": (0x04, 0x08),
    "Manoria Interior 1": (0x04, 0x10),
    "Manoria Interior 2": (0x04, 0x20),
    "Manoria Interior 3": (0x04, 0x40),
    "Manoria Interior 4": (0x04, 0x80),
    "Manoria Shrine Sideroom 1": (0x0C, 0x02),
    "Manoria Shrine Sideroom 2": (0x0C, 0x04),
    "Manoria Bromide 1": (0x0C, 0x08),
    "Manoria Bromide 2": (0x0C, 0x10),
    "Manoria Bromide 3": (0x0C, 0x20),
    "Manoria Shrine Magus 1": (0x0C, 0x40),
    "Manoria Shrine Magus 2": (0x0C, 0x80),
    "Yakras Room": (0x0C, 0x01),
    "Denadoro Mts Screen2 1": (0x05, 0x08),
    "Denadoro Mts Screen2 2": (0x05, 0x10),
    "Denadoro Mts Screen2 3": (0x05, 0x20),
    "Denadoro Mts Final 1": (0x05, 0x40),
    "Denadoro Mts Final 2": (0x05, 0x80),
    "Denadoro Mts Final 3": (0x06, 0x01),
    "Denadoro Mts Waterfall Top 1": (0x06, 0x02),
    "Denadoro Mts Waterfall Top 2": (0x06, 0x04),
    "Denadoro Mts Waterfall Top 3": (0x06, 0x08),
    "Denadoro Mts Waterfall Top 4": (0x06, 0x10),
    "Denadoro Mts Waterfall Top 5": (0x06, 0x20),
    "Denadoro Mts Entrance 1": (0x06, 0x40),
    "Denadoro Mts Entrance 2": (0x06, 0x80),
    "Denadoro Mts Screen3 1": (0x07, 0x01),
    "Denadoro Mts Screen3 2": (0x07, 0x02),
    "Denadoro Mts Screen3 3": (0x07, 0x04),
    "Denadoro Mts Screen3 4": (0x07, 0x08),
    "Denadoro Mts Ambush": (0x07, 0x10),
    "Denadoro Mts Save Pt": (0x07, 0x20),
    "Bangor Dome Seal 1": (0x0D, 0x01),
    "Bangor Dome Seal 2": (0x0D, 0x02),
    "Bangor Dome Seal 3": (0x0D, 0x04),
    "Trann Dome Seal 1": (0x0D, 0x08),
    "Trann Dome Seal 2": (0x0D, 0x10),
    "Arris Dome Seal 1": (0x0E, 0x04),
    "Arris Dome Seal 2": (0x0E, 0x08),
    "Arris Dome Seal 3": (0x0E, 0x10),
    "Arris Dome Seal 4": (0x0E, 0x20),
    "Mystic Mt Stream": (0x13, 0x20),
    "Forest Maze 1": (0x13, 0x40),
    "Forest Maze 2": (0x13, 0x80),
    "Forest Maze 3": (0x14, 0x01),
    "Forest Maze 4": (0x14, 0x10),
    "Forest Maze 5": (0x14, 0x04),
    "Forest Maze 6": (0x14, 0x08),
    "Forest Maze 7": (0x14, 0x02),
    "Forest Maze 8": (0x14, 0x20),
    "Forest Maze 9": (0x14, 0x40),  # TODO: Verify this with maze 3 (both rolled Full Tonic)
    "Reptite Lair Reptites 1": (0x15, 0x20),
    "Reptite Lair Reptites 2": (0x15, 0x40),
    "Dactyl Nest 1": (0x15, 0x80),
    "Dactyl Nest 2": (0x16, 0x01),
    "Dactyl Nest 3": (0x16, 0x02),
    "Factory Ruins Generator": (0x10, 0x08),
}

# Maps location names to IDs.  Populated by client init.
_location_name_to_id = {}


class CTJoTSNIClient(SNIClient):
    """
    Game client for Chrono Trigger Jets of Time.
    """

    game = "Chrono Trigger Jets of Time"
    patch_suffix = ".apctjot"

    def __init__(self):
        super().__init__()
        import pkgutil
        locations = json.loads(pkgutil.get_data(__name__, "data/location_data.json").decode())
        for key, value in locations.items():
            _location_name_to_id[key] = LOCATION_ID_START + value
        # Per-slot settings, populated lazily from the AP `Connected`
        # packet's slot_data. Default-safe values mirror the legacy
        # behavior (track everything) so older patched ROMs that don't
        # ship slot_data still work.
        self.slot_data: dict = {}
        self._slot_data_received = False
        # Set of ctx ids whose on_package we've already wrapped, so we
        # don't double-wrap if validate_rom is called multiple times.
        self._slot_data_patched_ctxs: set = set()

    @property
    def chronosanity(self) -> bool:
        return bool(self.slot_data.get("chronosanity", True))

    @property
    def rocksanity(self) -> bool:
        return bool(self.slot_data.get("rocksanity", False))

    def _install_slot_data_capture(self, ctx) -> None:
        """Wrap ctx.on_package so we can stash slot_data on Connected.

        SNIContext doesn't expose slot_data as a public attribute, so
        we wrap its on_package method to peek at the Connected packet.
        Idempotent per ctx instance (guarded via _slot_data_patched_ctxs).
        """
        if id(ctx) in self._slot_data_patched_ctxs:
            return
        self._slot_data_patched_ctxs.add(id(ctx))
        original_on_package = ctx.on_package
        client_self = self

        def patched_on_package(cmd, args):
            if cmd == "Connected":
                client_self.slot_data = args.get("slot_data") or {}
                client_self._slot_data_received = True
                client_self._log_connection_banner()
            return original_on_package(cmd, args)

        ctx.on_package = patched_on_package

    def _log_connection_banner(self) -> None:
        """Print a one-line summary of this slot's relevant YAML settings."""
        sd = self.slot_data
        if not sd:
            snes_logger.info(
                "CTJoT connected (no slot_data; older patched ROM -- "
                "tracking everything as fallback)"
            )
            return
        mode = sd.get("game_mode", "Standard")
        chrono = "on" if sd.get("chronosanity") else "off"
        rocks = "on" if sd.get("rocksanity") else "off"
        extras = sd.get("active_ki_flags") or []
        extras_str = f", flag-KIs={','.join(extras)}" if extras else ""
        snes_logger.info(
            f"CTJoT connected: mode={mode}, chronosanity={chrono}, "
            f"rocksanity={rocks}{extras_str}"
        )

    @staticmethod
    def _convert_to_sni_addressing(address: int):
        """
        Convert from SNES address mapping to the SNI address mapping.

        :param address: SNES address to convert to SNI mapping
        :return: SNI address corresponding to this SNES address
        """
        return (address - 0x7E0000) + WRAM_START

    @staticmethod
    def _check_event_location(address: int, flag: int, data: bytes) -> bool:
        """
        Check if an event location has been checked by the runner.

        :param address: Event memory address of this location flag
        :param flag: Bit flag for this specific location
        :param data: Event data block from SNES RAM
        :return: True if the check has been completed, false if not
        """
        offset = address - EVENT_BASE_ADDR
        return (data[offset] & flag) > 0

    @staticmethod
    def _check_treasure_location(offset: int, flag: int, data: bytes) -> bool:
        """
        Check if a treasure chest has been opened by the runner.

        :param offset: Offset into treasure memory
        :param flag: Bit flag for this specific treasure chest
        :param data: Event data block from SNES RAM
        :return: True if the chest has been opened, false if not
        """
        # Adjust offset.  It's based on 0x7F0001 (treasure data start)
        # but the data block starts at 0x7F0000 (event data start)
        return (data[offset + 1] & flag) > 0

    @staticmethod
    def _check_victory_condition(data: bytes) -> bool:
        """
        Check if the player has beaten the game.

        The multiworld code adds a new flag to the ending selector scene to reliably
        verify that the player has beaten the game.  This should work with all  the
        different game modes and endings.

        :param data: Event data to check for victory condition
        :return: True if the player has beaten the game, false if not
        """
        return (data[VICTORY_ADDRESS - EVENT_BASE_ADDR]) & 0x01 > 0

    @classmethod
    async def _deliver_next_item(cls, ctx, items: list[NetworkItem]):
        """
        Enqueue the next pending item into the in-game receive queue.

        Phase A architecture: the in-game receive hook (see
        worlds/ctjot/patches.py:_build_receive_block) drains a
        4-slot FIFO at AP_QUEUE_BASE_ADDR each map transition. This
        method is called every game-watcher tick (~10Hz) and:

          1. Reads the total-received counter at RECEIVED_ITEM_COUNT_ADDR.
          2. Reads the queue count at AP_QUEUE_COUNT_ADDR.
          3. If we have a pending item AND the queue isn't full,
             writes the next item byte to slot[queue_count],
             verifies the byte landed via read-back, and only then
             increments both the counter and the queue count.

        Read-back verification means a dropped SNI write (e.g.,
        FXPak USB hiccup) results in a retry on the next tick rather
        than a silently-lost item with the counter advancing past it.

        :param ctx: SNIContext used to communicate with the SNES/Emulator
        :param items: items_received list from the AP server
        """
        from SNIClient import snes_read, snes_buffered_write, snes_flush_writes

        # 1. Total-received counter (how many items the in-game state
        #    has already accepted from us).
        counter_data = await snes_read(
            ctx, cls._convert_to_sni_addressing(RECEIVED_ITEM_COUNT_ADDR), 1)
        if counter_data is None:
            return
        num_items_delivered = counter_data[0]

        # Nothing pending? Done.
        if len(items) <= num_items_delivered:
            return

        # 2. Queue count -- how many items the hook hasn't drained yet.
        queue_count_data = await snes_read(
            ctx, cls._convert_to_sni_addressing(AP_QUEUE_COUNT_ADDR), 1)
        if queue_count_data is None:
            return
        queue_count = queue_count_data[0]

        # Queue full? Wait for the hook to drain (next map transition).
        if queue_count >= AP_QUEUE_CAPACITY:
            return

        # 3. Compute the in-game item byte. Items above the in-game
        #    range (notably character-pickup events at >= 256) are
        #    not real CT items; we skip the queue write but still
        #    advance the counter so we don't re-attempt forever.
        item = ctx.items_received[num_items_delivered]
        in_game_id = item.item - ITEM_ID_START
        target_slot_addr = AP_QUEUE_BASE_ADDR + queue_count

        if 0 < in_game_id <= MAX_IN_GAME_ITEM_ID:
            # 3a. Write item byte to the next free slot.
            snes_buffered_write(
                ctx,
                cls._convert_to_sni_addressing(target_slot_addr),
                bytes([in_game_id]))
            # 3b. Bump the queue count so the hook sees a new item.
            snes_buffered_write(
                ctx,
                cls._convert_to_sni_addressing(AP_QUEUE_COUNT_ADDR),
                bytes([queue_count + 1]))
            await snes_flush_writes(ctx)

            # 3c. Verify both writes landed before advancing the
            #     counter. A dropped write here would otherwise lose
            #     the item silently -- the bug Phase A is built to
            #     prevent. If verify fails we return without bumping
            #     the counter; next tick will retry.
            verify_slot = await snes_read(
                ctx, cls._convert_to_sni_addressing(target_slot_addr), 1)
            verify_count = await snes_read(
                ctx, cls._convert_to_sni_addressing(AP_QUEUE_COUNT_ADDR), 1)
            if (verify_slot is None or verify_slot[0] != in_game_id or
                    verify_count is None or verify_count[0] != queue_count + 1):
                return

        # 4. Advance the total-received counter. Done unconditionally
        #    once we've verified the queue write (or determined the
        #    item was an out-of-range event item we're skipping) so
        #    items_received and the in-game counter stay in sync.
        snes_buffered_write(
            ctx,
            cls._convert_to_sni_addressing(RECEIVED_ITEM_COUNT_ADDR),
            bytes([num_items_delivered + 1]))
        await snes_flush_writes(ctx)

    async def _track_locations(self, ctx) -> bool:
        """
        Track the locations checked by the player.

        :param ctx: SNIContext for this SNI connection
        """
        from SNIClient import snes_read

        if not ctx.allow_collect or ctx.server is None or ctx.slot is None:
            # We're not fully connected yet, to the server or emulator/hardware
            return False

        # Read the player's in-game location and then do one big read to get all event and treasure flags.
        # NOTE: There is a potential race condition here where the location read happens in a good location
        #       but the event data read occurs in an invalid location for tracking.
        location_data = await snes_read(ctx, LOCATION_ADDRESS, 2)
        event_data = await snes_read(ctx, self._convert_to_sni_addressing(EVENT_BASE_ADDR), EVENT_BLOCK_SIZE)
        if event_data is None or location_data is None:
            return False

        # NOTE: Travelling through a time gate puts the game into a mode 7 scene that overwrites
        # event memory. It always uses a predictable pattern starting at 7F0000, so we can use that
        # to detect when gate travel is occurring and skip item tracking for the duration.
        if event_data[0:4] == b"@ABC":
            return False

        # Check the player's current location and don't track if they are
        # on either the title screen or the load screen.
        # Current location is stored in two bytes starting at 0x7F0100
        map_id = int.from_bytes(location_data, "little")
        if map_id in INVALID_TRACKING_LOCATIONS:
            return False

        # Sanity check to make sure the map actually exists before tracking
        # This can catch an issue where the hardware/emulator fills RAM with invalid values before the game loads
        #
        # This check is a bit naive, since some maps under this value are also invalid, but it should
        # work to stop the but where the game auto-completes on connect
        if map_id >  MAX_MAP_ID:
            return False

        # Normal locations (standard randomizer checks)
        new_locations: list[int] = []
        for name, (address, flag) in _locations_baseline_key_items.items():
            loc_id = _location_name_to_id[name]
            if loc_id not in ctx.checked_locations and loc_id not in new_locations:
                if self._check_event_location(address, flag, event_data):
                    # This location has been checked
                    new_locations.append(loc_id)

        # Treasure chest locations -- only meaningful when chronosanity
        # is on. With chronosanity off chests aren't AP locations, so
        # any LocationChecks we send for chest IDs are dropped server-
        # side as noise. Skip the loop entirely in that case.
        if self.chronosanity:
            for name, (offset, flag) in _locations_treasure_chests.items():
                loc_id = _location_name_to_id[name]
                if loc_id not in ctx.checked_locations and loc_id not in new_locations:
                    if self._check_treasure_location(offset, flag, event_data):
                        # This location has been checked
                        new_locations.append(loc_id)

        # Sealed chests and event chest locations
        for name, (address, flag) in _locations_event_treasures.items():
            loc_id = _location_name_to_id[name]
            if loc_id not in ctx.checked_locations and loc_id not in new_locations:
                if self._check_event_location(address, flag, event_data):
                    # This location has been checked
                    new_locations.append(loc_id)

        # Rocksanity ScriptTreasure rock pickups (Denadoro/Laruba/
        # Kajar). These don't have native event flags -- the apworld
        # injects "write 1 to WRAM byte" commands into each rock's
        # pickup script via patches.py:install_rock_pickup_flags. We
        # do a small additional snes_read here for those bytes -- but
        # only when rocksanity is on; otherwise the bytes are always
        # zero (no rock pickup script is patched) and the read just
        # wastes a SNI round-trip every tick.
        if self.rocksanity:
            rock_data = await snes_read(
                ctx,
                self._convert_to_sni_addressing(ROCK_PICKUP_BASE_ADDR),
                ROCK_PICKUP_NUM_BYTES,
            )
            if rock_data is not None:
                for name, addr in _locations_wram_rock_pickups.items():
                    loc_id = _location_name_to_id[name]
                    if loc_id in ctx.checked_locations or loc_id in new_locations:
                        continue
                    offset = addr - ROCK_PICKUP_BASE_ADDR
                    if rock_data[offset] != 0:
                        new_locations.append(loc_id)

        # Send the list of newly checked locations to the server
        if len(new_locations) > 0:
            await ctx.send_msgs([{"cmd": 'LocationChecks', "locations": new_locations}])

        # Check to see if the player has beaten the game
        if self._check_victory_condition(event_data):
            if not ctx.finished_game:
                await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
                ctx.finished_game = True

        return True

    async def validate_rom(self, ctx) -> bool:
        # Format is: APxyzPlayer_name
        # Where:
        #   AP is a string literal
        #   xyz are a three byte version number
        #   Player_name can be up to 16 characters
        #
        # TODO: Do something with version info
        # TODO: This identifies the player, but not necessarily the AP seed.
        #       Need to expand on this a bit.
        from SNIClient import snes_read
        data = await snes_read(ctx, VALIDATION_ADDR, VALIDATION_SIZE)
        if data is None or data[0:2] != b"AP":
            return False

        name_end = min(data[5:22].find(b'\00'), 16) + 5
        name = data[5:name_end]
        ctx.game = self.game
        # Bit 0 (remote items): receive items other slots send to us.
        # Bit 1 (own items): would echo our own items back when we find
        # them in our own world. We deliberately leave bit 1 OFF: the
        # patched ROM hands the player their own items locally
        # (selective placement at generate_output time), so an echo
        # would deliver each own-item twice. Bit 2 unused for ctjot.
        ctx.items_handling = 0b001
        ctx.rom = name
        ctx.allow_collect = True
        # Install slot_data capture before AP fires its Connected packet.
        self._install_slot_data_capture(ctx)
        return True

    async def game_watcher(self, ctx) -> None:
        # Send newly checked locations to the server.
        tracking_succeeded = await self._track_locations(ctx)

        # Deliver the next item to the player if there are items to give.
        # Don't try to deliver items if something went wrong with tracking.
        if tracking_succeeded:
            await self._deliver_next_item(ctx, ctx.items_received)

    async def deathlink_kill_player(self, ctx) -> None:
        """
        Not implemented for Jets of Time
        """
        pass
