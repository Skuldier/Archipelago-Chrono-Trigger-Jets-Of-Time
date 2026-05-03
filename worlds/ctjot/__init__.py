import logging
import threading
import typing
from typing import Callable

import settings

from BaseClasses import Item, Location, MultiWorld, Tutorial, Region, CollectionState, ItemClassification
from ..AutoWorld import World, WebWorld

from .Client import CTJoTSNIClient
from .Items import CTJoTItemManager
from .Locations import CTJoTLocationManager
from .Options import CTJoTOptions
from .Rom import CTJoTProcedurePatch

# Apworld version.
#   1.0.0 -- first release of the procedure-patch / romless
#            generation architecture: generator emits JSON-only
#            .apctjot, players apply against their own ROM via the
#            bundled cjot-beta snapshot at worlds/ctjot/_beta/. See
#            _beta/SNAPSHOT.txt for the cjot-beta source identity.
#   1.1.0 -- per-classification chest placeholders. Cross-slot
#            chests now display "Got 1 AP Trap" / "Got 1 AP Key" /
#            "Got 1 AP Useful" / "Got 1 AP Filler" instead of a
#            single "AP Item" label, so the player can see at a
#            glance what kind of item they sent. Patch-zip schema
#            is unchanged; older patches still apply, but the
#            classification labels need a 1.1.0+ apworld at apply
#            time to render.
#   1.1.1 -- fix: 1.1.0 picked placeholder bytes 0xFC-0xFF, which
#            are EnemyID members but NOT ItemID members. The
#            attribute lookup fell through to ItemID.MOP at apply
#            time and every cross-slot chest displayed "Got 1 Mop".
#            Switched placeholder bytes to 0xEA-0xED (real ItemID
#            UNUSED slots).
#   1.2.0 -- conditional chest verb. Cross-slot chest pickups now
#            display "You Sent 1 AP Trap!" (etc.) instead of
#            "Got 1 AP Trap!"; own-slot pickups still read "Got 1
#            X!". Implemented as an ASM substitution-symbol handler
#            in bank 0x02 (see install_conditional_chest_verb in
#            patches.py); handler reads the chest's item byte at
#            0x7F0200 and emits the right verb prefix.
#   1.2.1 -- fix: 1.2.0 hit "handler must live in bank 0x02" at
#            apply time because the freshly-opened cjot-beta ROM
#            has an empty freespace ledger -- the space_manager
#            hint to bank 0x02 fell back to bank 0x41 (where
#            _grant_freespace had marked space) and the assertion
#            tripped.
#   1.2.2 -- fix: 1.2.1's bank-0x02 scan didn't help because
#            cjot-beta has consumed the documented bank-0x02 free
#            blocks for its own ASM and string tables; only ~50
#            bytes of FF/00 remain across the entire bank, none
#            large enough for our ~70-byte handler. Switched to a
#            trampoline pattern: real handler lives in bank
#            0x40-0x5F freespace, a 4-byte JML trampoline at a
#            small bank-0x02 FF run forwards the substitution-jump
#            indirection out to it.
#   1.2.3 -- fix: 1.2.2 patched cleanly and the verb showed up
#            correct on first render, but ~0.5s after the textbox
#            finished typing it would re-render itself layered on
#            top of the first pass. Cause: the chest-string ending
#            bytes `de 02 00` triggered a re-traversal in CT's
#            text engine (vanilla uses `1f 02 00`; cjot-beta's
#            chesttext-hack uses `de 06 01 00`; ours matched
#            neither). Rewrote the chest string to end at the
#            first NUL after `!` and pad to 12 bytes with NULs so
#            any engine over-read also terminates immediately.
#   1.2.4 -- fix: 1.2.3's chest string ended at the first NUL
#            after `!`, which also dropped the `06 01` trailing
#            sequence that cjot-beta's chesttext-hack uses to
#            display the item description (stats line) below the
#            pickup text. Restored the `06 01 00` tail when the
#            original bytes show chesttext-hack is active, so own-
#            slot pickups regain their stats line. Cross-slot
#            placeholders (UNUSED_EA-ED) have empty descriptions
#            so they render the same blank space as before.
#   1.3.0 -- dropped the seed_share_link option. The webapp no
#            longer emits it, the Options.py SeedShareLink class
#            is gone, and generate_early()'s share-link-marker
#            validator + InvalidYamlException are gone with it.
#            Existing YAMLs with seed_share_link still load (AP
#            ignores unknown keys); new YAMLs are simpler and
#            don't carry a generator-origin stamp.
#   1.4.0 -- Phase A receive-hook overhaul. The single-byte receive
#            slot at flag-memory 0x7F01FE is replaced by a 4-slot
#            FIFO at 0x7F01F0..0x7F01F3 + count at 0x7F01F4. The
#            in-game hook drains up to 4 items per map transition
#            instead of one, so rapid-fire item arrivals no longer
#            block on a single-byte gate. The total-received
#            counter moves from WRAM 0x7E287C to flag-memory
#            0x7F01FD, eliminating the WRAM-counter save-reload
#            desync and the "Writing this value back manually for
#            now" SNI kludge. Client.py also adds read-back
#            verification on every queue write so dropped SNI
#            writes (FXPak USB hiccups) retry instead of silently
#            losing items + advancing the counter past them.
#            Together these address the "items vanished even
#            though the counter advanced" bug class.
#   1.4.1 -- fix: 1.4.0's queue at 0x7F01F0+ was placed inside the
#            "Location storyline flags" range (Memory Locations.txt
#            line 332). Writing item bytes there set the
#            ferry-departure bits; every map exit triggered the
#            "riding the boat" cutscene until SNI was disconnected.
#            Moved the queue + counter to WRAM 0x7E2880-0x7E2885,
#            documented as "Appears to be unused space (included
#            in SRAM)" -- genuinely safe for arbitrary writes and
#            still save-persistent. Hook updated to use WRAM<->
#            script-memory bounce ops since if_mem_op_value can't
#            check WRAM directly.
#   1.4.2 -- fix: Rocksanity rock pickups at the four rock-spot
#            locations were silently un-tracked by the SNI client.
#            The original Client.py left the rock entries in a
#            never-iterated _locations_misc_events dict with
#            placeholder integer values -- so when a Denadoro,
#            Laruba, Kajar, Giants Claw, or Black Omen Terra rock
#            was placed at one of those spots in another player's
#            world and they opened it, AP server never heard about
#            the location check and the rock never routed to its
#            destination slot. Fix: Giants Claw and Black Omen
#            Terra Rock are ChestTreasures, so they slot into
#            _locations_treasure_chests via the chest-flag formula
#            (chest_id // 8, 1 << (chest_id % 8)). The three
#            ScriptTreasure rocks (Denadoro/Laruba/Kajar) have no
#            native event flag -- patches.py now injects a
#            "write 1 to a unique WRAM byte" command after the
#            add-item in each rock's pickup script
#            (install_rock_pickup_flags), and Client.py reads those
#            bytes each tick.
#   1.4.3 -- fix: Lab 32 Race Log (the ADD_RACELOG_SPOT key item) was
#            silently un-tracked. cjot-beta defines it as
#            ChestTreasure(0x78), but Client.py's
#            _locations_treasure_chests_not_in_logic dict (which is
#            never iterated by _track_locations) had it as a stale
#            integer placeholder. Moved to _locations_treasure_chests
#            with the chest-flag tuple (0x0F, 0x01) so it's now
#            tracked alongside the other ChestTreasure key items.
#   1.4.4 -- fix: receive queue / counter / rock-pickup flags moved
#            from 0x7E2880-0x7E2888 to 0x7E2900-0x7E2908. cjot-beta's
#            base/basepatch.py:patch_timegauge repurposes
#            0x7E2881-0x7E288D as the Epoch time-period table
#            (asm CMP loop walks 14 bytes from 0x7E2881). Our
#            queue/counter writes were corrupting that table -- the
#            dial worked at game start (table all zero == no items
#            received yet) but spun forever after the first item
#            delivery (counter at 0x7E2885 incrementing leaked
#            garbage map IDs into the gauge's lookup). 0x7E2900 is
#            past cjot-beta's last reference at 0x7E288D and still
#            inside the documented unused-but-SRAM-persistent block
#            (0x7E2880-0x7E297F). Memory Locations.txt's "Appears to
#            be unused" annotation is vanilla -- cjot-beta hijacks
#            part of that range. Lesson logged in
#            ct_text_engine_gotchas.md.
#   1.4.5 -- behavior: chronosanity OFF now means chests are truly
#            local. Previously the apworld's add_filler_locations
#            registered every chest as an AP location with a
#            filler-only item rule, which still routed chest contents
#            through the multiworld -- a chest in your game could
#            send an item to another player even though you turned
#            chronosanity off. Now: when chronosanity is off,
#            create_regions skips add_filler_locations entirely, and
#            create_items skips the chest-filler item-pool padding.
#            Chests retain cjot-beta's native randomized contents and
#            never enter the multiworld. Chronosanity ON behavior is
#            unchanged.
#   1.4.6 -- feature: slot_data plumbing. CTJoTWorld.fill_slot_data
#            now emits per-slot YAML settings (chronosanity,
#            rocksanity, game_mode, early_pendant, unlocked_magic,
#            ap_classification_markers, active_ki_flags) on the AP
#            wire. The SNI Client wraps ctx.on_package on validate_rom
#            to capture slot_data on Connected, then gates the
#            chest-tracking loop on chronosanity and the rock-pickup
#            WRAM read on rocksanity -- eliminating dead-packet noise
#            for chronosanity-off seeds and a redundant SNI round-
#            trip per tick for non-rocksanity seeds. Connection
#            banner now prints mode + flags. Default-safe fallbacks
#            (chronosanity=on, rocksanity=off) keep older patched
#            ROMs without slot_data working. Foundation for upcoming
#            DeathLink, trap items, hint-NPC features. Also fixes
#            pre-existing None-check bug in _track_locations where
#            location_data could be passed unguarded to
#            int.from_bytes.
#   1.4.7 -- fix: AP fill error "more locations than items" when
#            chronosanity is OFF and any of the location-only flag-
#            gated KI spots are enabled (add_bekkler_spot,
#            add_cyrus_grave_spot, add_ozzie_fort_spot,
#            add_sun_keep_spot). These flags add a LOCATION to the
#            YAML's region_list but reuse existing KI items in
#            cjot-beta -- they don't define new KI item types like
#            Tools/JetsOfTime/Race Log/Bike Key/Seed do. v1.4.5's
#            chronosanity-off branch skipped all item-pool padding,
#            leaving these locations unfillable. Now: when
#            chronosanity is off, count YAML region_list locations
#            and top up with filler items so item count matches
#            location count. Char/victory events excluded from the
#            count (they have locked items). Reproduced with the
#            user's YAML at: bekkler+cyrus+rocksanity, fill failed
#            on slot Skuldier_CT (22 locations, 21 items).
#   1.4.8 -- fix: fragments missing from AP item pool with bucket_list +
#            chronosanity on. cjot-beta's bucketlist.py:208-212 places
#            fragments at chests via write_fragments_to_config when a
#            CollectNFragmentsObjective is selected, but our
#            apply_selective_placement overrides those chests with AP
#            placements -- the fragments vanish from the multiworld
#            and the bucket objective is unreachable. Now: when
#            bucket_list + chronosanity are both on, parse
#            bucket_objective_hints for collect_N_fragments_M patterns
#            and add MAX(M) Fragment items to the AP pool. Other
#            players' chests can then deliver fragments back via the
#            receive queue. Reproduced 2026-04-29 in a 12-player
#            multiworld: zero fragments collected despite having
#            fragment bucket objectives.
#   1.4.9 -- fix: rock bucket-list objective false-completes under
#            chronosanity. cjot-beta's ObtainNRocksObjective installed
#            chest-id box-checks on rock-bearing chests; with AP
#            routing chest contents, those box-checks fired on
#            chest-open regardless of whether the AP-delivered item
#            was actually a rock. Result (reported 2026-04-29):
#            "Collect 4 Rocks" objective completed with 0 rocks in
#            inventory after the player opened 4 chests that
#            cjot-beta had originally placed rocks at.
#            Replacement (Option 3 from analysis):
#            - cjot-beta side: ObtainNRocksObjective.
#              add_objective_check_to_ctrom rewritten to install a
#              polling watchdog at End of Time obj 0 that checks
#              0x7F003D >= num_rocks_needed and fires the
#              obj-complete chain. One-shot flag at 0x7F003E
#              prevents re-firing on EoT re-entry.
#            - Client side: each game_watcher tick, count rock items
#              (IDs 0xAE-0xB2) in inventory at 0x7E2400 and write the
#              count to 0x7F003D via SNI. Watchdog now fires exactly
#              when the player has actually collected the target
#              number of rocks regardless of source (vanilla pickup,
#              local AP placement, or cross-slot AP queue delivery).
#   1.4.10 -- refinement of v1.4.8 fragment fix: pre-roll the
#             bucket-list hint distribution to specific categories
#             before deciding whether to add fragments to the AP item
#             pool. v1.4.8 was over-conservative -- it added fragments
#             whenever a fragment objective was POSSIBLE in any hint
#             slot, even if no slot ended up rolling one. Result
#             (reported 2026-04-29): user had Fragment items cluttering
#             inventory in seeds where no fragment objective was
#             actually selected.
#             Now: _pre_roll_bucket_hints uses self.multiworld.random
#             (seed-deterministic) to resolve each weighted hint
#             string to one literal category. The resolved literals
#             are mutated back into the option, so cjot-beta reads
#             them at apply time and agrees with our roll. Fragments
#             are added only if a collect_*_fragments_* objective is
#             in the rolled list.
#   1.4.11 -- feature: optional item-arrival textbox. New ItemArrivalTextbox
#             toggle (default OFF, matches pre-1.4.11 silent delivery).
#             When ON, the receive hook injects a personal-textbox
#             command (0xBB) after each 0xC7 add-item, displaying
#             "* AP Item Received *" in-game. Implementation:
#             - Options.py: new ItemArrivalTextbox toggle in dataclass
#             - __init__.py generate_output: writes
#               item_arrival_textbox_enabled into ap_metadata.json
#             - patches.py: install_receive_hook gains a show_textbox
#               kwarg; when True, builds the receive block per-script
#               (so each script's added string ID can be baked into the
#               textbox command). When False, keeps the cheap shared-
#               bytes path identical to 1.4.10. Static message string
#               for v1; item-name substitution deferred to a v2.
#   1.4.12 -- v2 of the item-arrival textbox: now displays the actual
#             item name. New install_item_name_substitution pass claims
#             chest text engine substitution sym 0x05 (jump table at
#             0x025903 + 2*0x05). Handler reads the staged item ID from
#             SCRIPT_STAGING_ADDR (0x7F03FC), multiplies by
#             ITEM_NAME_SIZE (11), adds ITEM_NAMES_OFFSET base
#             (0x0C0B5E), and tail-jumps to the engine's substring
#             render continuation at 0xC25BF5. Uses the same
#             trampoline pattern as install_conditional_chest_verb
#             (real handler in bank 0x40-0x5F freespace + 4-byte JML
#             trampoline at a small bank-0x02 free run + jump-table
#             entry pointing at the trampoline).
#             Receive hook string changed from static
#             "* AP Item Received *" to raw bytes
#             "Got <sym 0x05>!" so the player sees e.g. "Got Pendant!"
#             when an AP item arrives. Caveat: claims sym 0x05 which
#             is the encoder keyword `{linebreak+0}` -- any cjot-beta
#             script that uses that keyword now invokes our handler
#             instead. The more common `{line break}` (byte 0x06) is
#             unaffected.
__version__ = "1.4.12"

ctjot_logger = logging.getLogger("Jets of Time")


class CTJoTSettings(settings.Group):
    """Settings for Chrono Trigger Jets of Time.

    Used only when applying a .apctjot patch on this machine.

      - rom_file:       your vanilla Chrono Trigger (US) ROM.
      - cjot_beta_path: optional. Leave blank unless you want the
                        patcher to use a separate cjot-beta
                        checkout instead of the one bundled with
                        this apworld.
    """

    class RomFile(settings.SNESRomPath):
        """File name of the Chrono Trigger (US) ROM"""
        description = "Chrono Trigger (US) ROM File"
        copy_to = "Chrono Trigger (USA).sfc"
        md5s = [CTJoTProcedurePatch.hash]

    class CjotBetaPath(settings.OptionalUserFolderPath):
        """Optional override for the cjot-beta randomizer source.

        Leave blank to use the bundled cjot-beta. Set only if you
        want the patcher to use a separate cjot-beta checkout.
        """
        description = "cjot-beta randomizer source (optional override)"

    rom_file: RomFile = RomFile(RomFile.copy_to)
    cjot_beta_path: CjotBetaPath = CjotBetaPath("")


class CTJoTWebWorld(WebWorld):
    settings_page = "https://multiworld.ctjot.com/"
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "A guide to playing Jets of Time multiworld.",
        "English",
        "multiworld_en.md",
        "multiworld/en",
        ["Anguirel"]
    )]


class CTJoTWorld(World):
    """
    Jet of Time is an open world randomizer for the iconic JRPG Chrono Trigger.

    Players start with two characters and the winged Epoch and must journey through time finding
    additional characters and key items to save the world from the evil Lavos.
    """

    _item_manager = CTJoTItemManager()
    _location_manager = CTJoTLocationManager()

    game = "Chrono Trigger Jets of Time"
    options: CTJoTOptions
    options_dataclass = CTJoTOptions

    settings: typing.ClassVar[CTJoTSettings]

    item_name_to_id = _item_manager.get_item_name_to_id_mapping()
    location_name_to_id = _location_manager.get_location_name_to_id_mapping()

    web = CTJoTWebWorld()

    def __init__(self, world: MultiWorld, player: int):
        super().__init__(world, player)
        self.rom_name_available_event = threading.Event()

    def create_item(self, name: str) -> Item:
        """
        Create a CTJoT multiworld item.

        Overridden from World
        """
        return self._item_manager.create_item_by_name(name, self.player)

    def create_items(self) -> None:
        """
        Create items for the player from the passed in
        config data and append them to the multiworld item pool.

        Overridden from World
        """
        items_from_config = self.options.items.value
        bucket_fragments = self.options.bucket_fragments.value
        fragment_count = self.options.fragment_count.value
        bucket_list = self.options.bucket_list.value
        game_mode = self.options.game_mode.value
        difficulty = self.options.item_difficulty.value
        tab_treasures = self.options.tab_treasures.value
        char_locations = self.options.char_locations.value

        items = []

        # Add the key items from the yaml
        for item in items_from_config:
            items.append(self._item_manager.create_item_by_id(item["id"], self.player))

        # Add fragments only when bucket_fragments is the chosen go mode.
        # The beta-branch bucket_list option supersedes fragments: when it is
        # enabled, the web generator encodes the bucket-list victory condition
        # directly in the `victory` rules and no fragment items are placed.
        if bucket_fragments and not bucket_list and game_mode != "Lost worlds":
            for i in range(fragment_count):
                items.append(self.create_item("Fragment"))

        # bucket_list mode + chronosanity ON: cjot-beta places fragments at
        # chests via bucketlist.py:write_fragments_to_config(), but with
        # chronosanity our apply_selective_placement overrides those chests
        # with AP-routed items. Fragments need to be in the AP item pool
        # so AP fill distributes them across the multiworld and other
        # players opening chests routes them back to us via the receive
        # queue.
        #
        # v1.4.10 refinement of v1.4.8: pre-roll the bucket-list hint
        # distribution to specific categories using self.multiworld.random
        # (seed-deterministic), then add fragments ONLY if a fragment
        # objective was actually selected. Mutate the option value so
        # cjot-beta sees the same literal selections at apply time
        # (otherwise cjot-beta would re-roll with its own random and
        # disagree with our fragment-add decision -- could leave fragments
        # in the pool with no fragment objective, or vice-versa).
        if (
            bucket_list
            and bool(self.options.chronosanity.value)
            and game_mode != "Lost worlds"
        ):
            self._pre_roll_bucket_hints()

            import re as _re_frag
            rolled_hints = self.options.bucket_objective_hints.value or []
            max_fragments = 0
            for hint in rolled_hints:
                m = _re_frag.match(
                    r'collect_(\d+)_fragments_(\d+)', str(hint).strip()
                )
                if m:
                    total = int(m.group(2))
                    if total > max_fragments:
                        max_fragments = total
            for _ in range(max_fragments):
                items.append(self.create_item("Fragment"))

        # If this is a Lost Worlds seed we may need to add some character specific items
        # Add these items as "useful" so they try to take up progression locations in
        # non chronosanity games
        if game_mode == "Lost worlds":
            for location in char_locations:
                if location["character"] == "Frog":
                    grand_leon = self._item_manager.get_item_data_by_name("Grand Leon")
                    hero_medal = self._item_manager.get_item_data_by_name("Hero Medal")

                    items.append(
                        self._item_manager.create_custom_item(
                            grand_leon.name, grand_leon.code, ItemClassification.useful, self.player))
                    items.append(
                        self._item_manager.create_custom_item(
                            hero_medal.name, hero_medal.code, ItemClassification.useful, self.player))
                elif location["character"] == "Robo":
                    robo_rbn = self._item_manager.get_item_data_by_name("Robo's Rbn")
                    items.append(
                        self._item_manager.create_custom_item(
                            robo_rbn.name, robo_rbn.code, ItemClassification.useful, self.player))

        chronosanity_on = bool(self.options.chronosanity.value)

        if chronosanity_on:
            # Chronosanity ON: every chest in the game mode's pool becomes an
            # AP location. Pad the item pool with filler so item count matches
            # location count, and top up for experimental-flag KI spots whose
            # locations sit outside the standard chronosanity pool.
            all_locations = self._location_manager.get_location_ids(game_mode)
            self.multiworld.random.shuffle(all_locations)

            # Beta experimental-flag KI spots (Bekkler Key, Cyrus Grave Key,
            # Ozzies Fort Key, Sun Keep 2300, Arris Dome Food Locker Key, Lab
            # 32 Race Log, rocksanity rocks) can appear in the YAML
            # region_list even though the mode's chronosanity pool does not
            # list them. Each such "extra" location still becomes an AP
            # Location, so the item pool must grow to match or Fill fails
            # with item-count < location-count.
            regions_from_config = self.options.region_list.value
            name_to_id = self._location_manager.get_location_name_to_id_mapping()
            pool_set = set(all_locations)
            extra_flag_ki_count = 0
            for _region_name, location_list in regions_from_config.items():
                for location_name in location_list:
                    internal_id = name_to_id.get(location_name)
                    if internal_id is None:
                        continue
                    mapped = internal_id - self._location_manager._LOCATION_ID_START
                    if mapped not in pool_set:
                        extra_flag_ki_count += 1

            num_items_to_place = len(all_locations) - len(items)
            for i in range(num_items_to_place):
                item = self._item_manager.get_random_item_for_location(
                    all_locations[i], difficulty, tab_treasures, self.multiworld, self.player)
                items.append(item)

            # Top up the item pool with filler items for each extra beta KI spot.
            for _ in range(extra_flag_ki_count):
                tier_loc = self.multiworld.random.choice(all_locations)
                items.append(self._item_manager.get_random_item_for_location(
                    tier_loc, difficulty, tab_treasures, self.multiworld, self.player))
        else:
            # Chronosanity OFF: chests stay local (no chest-filler padding
            # needed). But flag-gated KI locations like Bekkler / Cyrus /
            # Ozzie / Sun Keep add LOCATIONS to region_list without adding
            # corresponding items to the items pool (cjot-beta treats those
            # spots as new chests for existing KIs, not as new KI types).
            # Without balancing here, AP fill errors with
            # "more locations than items".
            #
            # Count YAML region_list locations and top up with filler items
            # to match. Char/victory event locations have locked items and
            # don't count toward fillable locations.
            regions_from_config = self.options.region_list.value
            yaml_loc_count = sum(
                len(locs) for locs in regions_from_config.values())
            items_short = yaml_loc_count - len(items)
            for _ in range(max(0, items_short)):
                items.append(self.create_item(self.get_filler_item_name()))

        # Add the selected items to the multiworld item pool
        self.multiworld.itempool += items

    def create_regions(self) -> None:
        """
        Set up the locations and rules for this player.

        Region/location data is defined in the yaml to match the chosen flag set
        Pull this data from the yaml and set up the associated AP structures

        Overridden from World
        """
        # Get region/location data from the yaml
        regions_from_config = self.options.region_list.value
        char_locations_from_config = self.options.char_locations.value
        victory_rules_from_config = self.options.victory.value
        rules_from_config = self.options.rules.value
        game_mode = self.options.game_mode.value
        menu_region = Region("Menu", self.player, self.multiworld)

        # For now just shove all locations into the menu region
        # TODO: Add separate regions?
        for region_name, location_list in regions_from_config.items():
            access_rule = self._get_access_rule(rules_from_config[region_name])
            for location_name in location_list:
                location = self._location_manager.get_location(self.player, location_name, menu_region)
                location.access_rule = access_rule
                menu_region.locations.append(location)

        # Handle event locations for character pickups
        for char_location in char_locations_from_config:
            location_name = char_location["name"]
            character_name = char_location["character"]
            location = Location(self.player, location_name, None, menu_region)
            location.event = True
            # Add character here as a locked item.
            location.place_locked_item(
                self._item_manager.create_event_item(character_name, self.player))
            location.access_rule = self._get_access_rule(rules_from_config[location_name])
            menu_region.locations.append(location)

        # Chronosanity ON: register every chest in the mode's pool as an AP
        # location (gated to filler/useful/trap items only -- no KI). This
        # is a no-op when the YAML region_list already covers the full pool.
        # Chronosanity OFF: chests stay local. cjot-beta's own treasure
        # randomizer fills them with native items; they never become AP
        # locations and items opened from chests stay in the player's slot.
        if self.options.chronosanity.value:
            self._location_manager.add_filler_locations(
                regions_from_config, game_mode, self.player, menu_region)

        # Add victory condition event
        victory_location = Location(self.player, "Victory", None, menu_region)
        victory_location.event = True
        victory_location.access_rule = self._get_access_rule(victory_rules_from_config)
        victory_location.place_locked_item(self._item_manager.create_event_item("Victory", self.player))
        menu_region.locations.append(victory_location)

        self.multiworld.completion_condition[self.player] = lambda state: state.has("Victory", self.player)

        self.multiworld.regions += [menu_region]

    def get_filler_item_name(self) -> str:
        """
        Get a random filler item.

        Overridden from World
        """
        return self.multiworld.random.choice(self._item_manager.get_junk_fill_items())

    def _pre_roll_bucket_hints(self) -> None:
        """Resolve weighted bucket-list hint distributions to literal categories.

        cjot-beta accepts both weighted strings (e.g.,
        ``"30:quest_gated, 50:boss_any"``) AND literal category names
        (e.g., ``"quest_gated"``, ``"collect_10_fragments_20"``). When given
        a weighted string, cjot-beta picks one entry using its OWN random
        at apply time -- but we need to know the selection at create_items
        time to decide whether fragments need to be added to the AP item
        pool.

        Solution: pre-roll using ``self.multiworld.random`` (seeded by AP)
        and replace each weighted hint with the literal category we picked.
        We mutate ``self.options.bucket_objective_hints.value`` so the
        change persists into ``generate_output``, where
        ``options_to_cli_args`` reads it and packs the resolved literals
        into the .apctjot patch. cjot-beta then reads literals at apply
        time and uses them as-is, agreeing with our pre-roll.

        Hints without a ``:`` (e.g., the user picked a specific objective
        like "Forge the Masamune") are left unchanged -- no roll needed.
        """
        raw = self.options.bucket_objective_hints.value or []
        rolled: list[str] = []
        rng = self.multiworld.random
        for hint in raw:
            text = str(hint).strip()
            if ':' not in text:
                rolled.append(text)
                continue
            parts = [p.strip() for p in text.split(',') if p.strip()]
            weights: list[int] = []
            categories: list[str] = []
            for p in parts:
                if ':' in p:
                    weight_s, category = p.split(':', 1)
                    try:
                        w = int(weight_s.strip())
                    except ValueError:
                        continue
                    if w <= 0:
                        continue
                    weights.append(w)
                    categories.append(category.strip())
                elif p:
                    weights.append(1)
                    categories.append(p)
            if categories:
                rolled.append(rng.choices(categories, weights=weights, k=1)[0])
            else:
                rolled.append(text)
        self.options.bucket_objective_hints.value = rolled

    def fill_slot_data(self) -> dict:
        """Send per-slot YAML settings to the SNI Client over the AP wire.

        Read by the Client on `Connected` so it can:
          - skip iterating chest-flag tracking when chronosanity is off
            (otherwise we send LocationChecks the server drops)
          - skip the rock-pickup WRAM read when rocksanity is off
          - log a meaningful connection banner with the player's mode

        Schema versioned via "version" so Client can branch if we add
        keys later. Missing keys must default-safely on the Client side
        (treat-as-on) so older patched ROMs / older Clients keep working.
        """
        active_ki_flags = [
            f for f in (
                "add_bekkler_spot", "add_cyrus_grave_spot",
                "add_ozzie_fort_spot", "add_race_log_spot",
                "add_sun_keep_spot", "split_arris_dome",
            )
            if bool(getattr(self.options, f).value)
        ]
        return {
            "version": 1,
            "chronosanity": bool(self.options.chronosanity.value),
            "rocksanity":   bool(self.options.rocksanity.value),
            "game_mode":    str(self.options.game_mode.value),
            "early_pendant":  bool(self.options.early_pendant.value),
            "unlocked_magic": bool(self.options.unlocked_magic.value),
            "ap_classification_markers":
                bool(self.options.ap_classification_markers.value),
            "active_ki_flags": active_ki_flags,
        }

    def generate_output(self, output_directory: str) -> None:
        """Produce the per-player .apctjot patch (no ROM I/O).

        The generator's job is pure data assembly: gather everything
        the apply-time procedure handlers need to reproduce the
        player's randomized ROM, then write those inputs into the
        patch zip as JSON. cjot-beta and the six AP-side ROM passes
        both run on the *player's* machine when they invoke
        Patch.py -- see CTJoTProcedurePatch.procedure in Rom.py.

        Files written into the .apctjot zip:
          - randomizer_config.json: seed + cjot-beta CLI flag list,
            consumed by apply_cjot_beta_randomization.
          - ap_placements.json:     per-location AP placement
            records, consumed by apply_ctjot_ap_passes.
          - ap_metadata.json:       slot / player_name / game_mode /
            ap_classification_markers toggle, consumed by
            apply_ctjot_ap_passes.
        """
        import json
        from pathlib import Path
        from .Rom import CTJoTProcedurePatch
        from .flag_translation import options_to_cli_args

        player_name = self.multiworld.player_name[self.player]
        seed_str = str(self.multiworld.seed) if self.multiworld.seed is not None else None

        randomizer_config = {
            "seed": seed_str,
            "flags": options_to_cli_args(self.options),
        }
        ap_placements = self._collect_placement_records()
        ap_metadata = {
            "player_name": player_name,
            "player_slot": self.player,
            "game_mode": str(getattr(self.options.game_mode, "value", "") or ""),
            "ap_classification_markers_enabled": bool(
                getattr(getattr(self.options, "ap_classification_markers", None),
                        "value", 0)
            ),
            "item_arrival_textbox_enabled": bool(
                getattr(getattr(self.options, "item_arrival_textbox", None),
                        "value", 0)
            ),
        }

        out_name_base = self.multiworld.get_out_file_name_base(self.player)
        patch_path = (
            Path(output_directory)
            / f"{out_name_base}{CTJoTProcedurePatch.patch_file_ending}"
        )

        patch = CTJoTProcedurePatch(
            path=str(patch_path),
            player=self.player,
            player_name=player_name,
        )
        patch.write_file("randomizer_config.json",
                         json.dumps(randomizer_config).encode("utf-8"))
        patch.write_file("ap_placements.json",
                         json.dumps(ap_placements).encode("utf-8"))
        patch.write_file("ap_metadata.json",
                         json.dumps(ap_metadata).encode("utf-8"))
        patch.write()

    def _collect_placement_records(self) -> list[dict]:
        """Build apply-time placement records for this player's locations.

        Walks `self.multiworld.get_locations(self.player)` once and
        emits the data that apply_selective_placement_from_records
        + apply_ap_classification_markers_from_records will need on
        the player's side. The apply-time pass cannot read the multiworld
        directly -- by then the generator is long gone -- so every
        decision input must be captured here.

        Per-record fields:
          - loc_address:        AP location code (with the
                                +5,100,000 location-id offset)
          - item_for_own_slot:  True iff AP placed an item belonging
                                to this player. Apply-time writes
                                the real CT item byte; otherwise it
                                writes one of four per-classification
                                placeholder bytes (0xEA trap / 0xEB
                                progression / 0xEC useful / 0xED
                                filler) so the chest pickup labels
                                what kind of item was sent.
          - ap_item_code:       AP item ID (with the +5,100,000
                                offset). null for event items
                                (character/victory) which the
                                apply-time pass will treat as
                                placeholders.
          - classification:     int form of the AP ItemClassification
                                bitfield. Used by the marker pass to
                                pick the NPC sprite color (red trap
                                / purple progression / blue useful
                                / brown filler).

        Locations with no `address` (event/recruit/victory event
        nodes) are skipped -- the apply-time selective-placement
        pass ignores them already.
        """
        records: list[dict] = []
        for loc in self.multiworld.get_locations(self.player):
            if loc.address is None:
                continue
            if loc.item is None:
                continue
            records.append({
                "loc_address": int(loc.address),
                "item_for_own_slot": (loc.item.player == self.player),
                "ap_item_code": (int(loc.item.code) if loc.item.code is not None else None),
                "classification": int(loc.item.classification),
            })
        return records

    def modify_multidata(self, multidata: dict):
        import base64
        player_name = self.multiworld.player_name[self.player]
        if player_name and player_name != "":
            new_name = base64.b64encode(bytes(player_name.encode("ascii"))).decode()
            multidata["connect_names"][new_name] = multidata["connect_names"][self.multiworld.player_name[self.player]]

    def _get_access_rule(self, access_rules: list[list[str]]) -> Callable[[CollectionState], bool]:
        """
        Create an access rule function from yaml access_rule data.

        :param access_rules: A list contains lists of item/character requirements for this access rule
        :return: Callable access rule based on the list of requirements
        """
        def can_access(state: CollectionState) -> bool:
            # No access rules means this is sphere 1
            if len(access_rules) == 0:
                return True

            # loop through each access rule for this location
            for rule in access_rules:
                has_access = True
                for item in rule:
                    if not state.has(item, self.player):
                        has_access = False
                        break
                # Check if we have all the items from the rule
                if has_access:
                    return True

            # We didn't satisfy any of the access rules
            return False

        return can_access
