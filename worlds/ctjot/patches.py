"""
AP-side ROM modifications, applied on top of a cjot-beta-randomized ROM.

These passes run at apply-time on the *player's* machine, called by
CTJoTPatchExtension.apply_ctjot_ap_passes (see Rom.py). The generator
side never imports or runs anything in this module; it only writes
the JSON inputs (placement records + metadata) into the .apctjot
zip, which the player's procedure handler later reads back here.

Passes
------
1. `apply_selective_placement_from_records(ct_rom, placement_records)`
   For every CT location that has a corresponding TreasureID, look up
   the AP placement record.
     * Item is for our slot -> write the real CT item byte into the
       chest/script. The player walks into the chest, sees the real
       item name, and SNI's LocationCheck routes the same item back
       through the server to the same slot. We disable the server's
       own-item echo (Client.items_handling = 0b001) so we don't get
       a duplicate.
     * Item is for some OTHER slot -> write one of four placeholder
       bytes (0xEA trap / 0xEB progression / 0xEC useful / 0xED
       filler) picked by the recipient's AP item classification.
       The rename pass labels each placeholder slot accordingly so
       the chest pickup reads "Got 1 AP Trap" / "Got 1 AP Key" /
       "Got 1 AP Useful" / "Got 1 AP Filler". SNI sends the
       LocationCheck; the server routes the real item to the
       recipient's receive hook.

2. `apply_validation_marker(ct_rom, player_name)`
   Stamps `"AP" + version + player_name` at file offset 0x3F8C03.
   Without this, SNIClient.validate_rom returns False and nothing
   happens at runtime.

3. `install_receive_hook(ct_rom)`
   Injects an event-script polling block at the start of every map's
   object-0 startup function. Vanilla command 0xC7 reads the next
   pending item ID out of 0x7F021A and adds it to inventory; we bridge
   from 0x7F01FE (persistent flag memory, where SNI writes) into the
   volatile script slot just before invoking 0xC7.

4. `rename_placeholder_items(ct_rom)`
   Overwrites the in-ROM item-name table rows for slots 0xEA-0xED
   so each placeholder pickup renders with its classification
   label ("AP Trap" / "AP Key" / "AP Useful" / "AP Filler")
   instead of the vanilla "UNUSED_EA" etc.

4b. `install_conditional_chest_verb(ct_rom)`
   Installs an ASM substitution-symbol handler so the chest pickup
   textbox reads "You Sent 1 X!" when the chest holds one of our
   placeholder bytes (0xEA-0xED -> a cross-slot item) and "Got 1 X!"
   otherwise. Handler lives in bank 0x02 freespace; the chest
   string at 0x1EFF0A is rewritten to invoke it before the
   item-name substitution. Mirrors cjot-beta's chesttext.py pattern.

5. `apply_victory_marker(ct_rom)`
   Stamps `set_bit(0x7F0020, 0x01)` at the start of the ENDING_SELECTOR
   map's startup script. Every cjot-beta victory path (Lavos defeat,
   bucket-list auto-win, "open the bucket") warps through this map,
   so the AP server's victory polling at `Client.VICTORY_ADDRESS`
   trips on whichever route the player took.

6. `apply_ap_classification_markers_from_records(ct_rom,
   placement_records, game_mode_str)` (conditional, opt-in via
   `ap_classification_markers` option, default on)
   Injects an NPC marker above every chest, colored by the AP item
   classification (red trap / purple progression / blue useful /
   brown filler). Items routed to other slots are colored from THAT
   slot's perspective -- the classification on each record is the
   recipient's classification, which the generator captured before
   the multiworld went away.

Top-level orchestrator: `apply_all_from_records(ct_rom, placements,
metadata)`. Each pass operates on the same `CTRom` instance; the
caller calls `ct_rom.write_all_scripts_to_rom()` and
`ct_rom.fix_snes_checksum()` once at the end.

Placement record schema (see CTJoTWorld._collect_placement_records
in __init__.py for the producer side):
  - loc_address:        int, AP location code with +5,100,000 offset
  - item_for_own_slot:  bool
  - ap_item_code:       int (with +5,100,000 offset) or None for
                        event items
  - classification:     int, AP ItemClassification bitfield

Metadata schema:
  - player_name:                        str
  - player_slot:                        int (currently unused here)
  - game_mode:                          str (e.g. "Standard", "Lost worlds")
  - ap_classification_markers_enabled:  bool
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterable, Optional, TYPE_CHECKING

from .Rom import get_base_rom_path  # noqa: F401  (sanity import)


log = logging.getLogger("ctjot.patches")


# Apworld-side ID conventions (must match Items.py / Locations.py)
ITEM_ID_START = 5100000
LOCATION_ID_START = 5100000

# --- AP receive queue (WRAM) ---
#
# Phase A receive architecture: a 4-slot FIFO in WRAM at 0x7E2900+,
# a region documented in the Chrono Compendium memory map (line 198
# of Memory Locations.txt) as "Appears to be unused space (included
# in SRAM)". The receive hook below drains up to 4 items per map
# transition using shift-down semantics -- slot 0 is always the next
# item to deliver, after-drain we shift slots[1..3] down by one and
# decrement the count.
#
# Why NOT flag memory: an earlier Phase A attempt put the queue at
# 0x7F01F0+. The memory map documents that range as "Location
# storyline flags" (ferry departures, Black Omen, etc.) -- writing
# arbitrary item bytes into it triggered the ferry-departs cutscene
# on every map exit.
#
# v1.4.4 update: the original 0x7E2880+ placement collided with
# cjot-beta's `patch_timegauge` (basepatch.py:262), which repurposes
# 0x7E2881-0x7E288D as the Epoch time-period table. Our queue/counter/
# rock-flag writes were corrupting that table -- the dial ran its
# CMP loop against garbage map IDs and spun forever after the first
# item was delivered. Moved everything to 0x7E2900+, well past
# cjot-beta's last reference at 0x7E288D and still inside the
# vanilla "appears unused" 0x7E2880-0x7E297F SRAM-persistent block.
#
# All addresses must mirror Client.AP_QUEUE_* / Client.RECEIVED_ITEM_COUNT_ADDR.
AP_QUEUE_SLOT0_ADDR = 0x7E2900  # head of the queue (next byte to deliver)
AP_QUEUE_SLOT1_ADDR = 0x7E2901
AP_QUEUE_SLOT2_ADDR = 0x7E2902
AP_QUEUE_SLOT3_ADDR = 0x7E2903
AP_QUEUE_COUNT_ADDR = 0x7E2904  # number of items pending (0..4)
AP_QUEUE_CAPACITY = 4

# Total-items-received counter. WRAM, save-persistent.
AP_COUNTER_ADDR = 0x7E2905

# Volatile staging slot in script memory; vanilla command 0xC7 reads
# its add-item argument from 0x7F0200 + 2*offset. The receive hook
# copies from AP_QUEUE_SLOT0_ADDR into this address before invoking
# 0xC7.
#
# Originally 0x7F021A (offset 0x0D), but that sits inside cjot-beta's
# scratch zone (0x7F0210-0x7F022E -- epochfail/charassign/iceage). The
# staging slot retains the last delivered item ID across maps because
# we don't zero it after 0xC7. That stale value broke the Epoch
# time-period dial *after first item delivery*. Moved to 0x7F03FC
# (offset 0xFE) alongside the bounce slots in high script memory.
SCRIPT_STAGING_ADDR = 0x7F03FC
RECEIVE_ITEM_OFFSET_BYTE = 0xFE

# AP validation block layout in the ROM.
VALIDATION_OFFSET = 0x3F8C03
VALIDATION_SIZE = 32
AP_VERSION_BYTES = bytes([0x00, 0x01, 0x00])
PLAYER_NAME_MAX = 16

# Item-name table.
ITEM_NAMES_OFFSET = 0x0C0B5E
ITEM_NAME_SIZE = 0x0B

# Per-classification placeholder slots written into chests holding
# cross-slot items. CT renders each chest pickup as "Got 1 <name>",
# where <name> comes from the slot's row of the in-ROM item-name
# table -- so giving each classification its own slot + label
# tells the player at a glance what they sent ("Got 1 AP Trap" vs
# "Got 1 AP Useful" etc.).
#
# 0xEA-0xED are the first four high-range UNUSED entries in
# cjot-beta's `ItemID` enum (see cjot-beta/sourcefiles/ctenums.py).
# They appear in cjot-beta's bucket-list objective pool, but
# cjot-beta consumes pool entries in order starting from 0x1C, and
# the apworld caps BucketNumObjectives at 8 (Options.py). Pool[7]
# is 0x56; pool[11] is 0xEA. So bucket-list can never reach our
# slots -- zero collision in this configuration.
#
# We deliberately don't use 0xFC-0xFF: those bytes exist in `EnemyID`
# but NOT in `ItemID`, so `ItemID.UNUSED_FC` raises AttributeError and
# we'd silently fall through to ItemID.MOP (player sees "Got 1 Mop").
PLACEHOLDER_TRAP_ID        = 0xEA
PLACEHOLDER_PROGRESSION_ID = 0xEB
PLACEHOLDER_USEFUL_ID      = 0xEC
PLACEHOLDER_FILLER_ID      = 0xED

# byte -> visible name. ITEM_NAME_SIZE is 11 (1 icon prefix + 10
# usable chars); every label below fits.
PLACEHOLDER_NAMES = {
    PLACEHOLDER_TRAP_ID:        "AP Trap",
    PLACEHOLDER_PROGRESSION_ID: "AP Key",
    PLACEHOLDER_USEFUL_ID:      "AP Useful",
    PLACEHOLDER_FILLER_ID:      "AP Filler",
}

# Defensive: never treat any of these bytes as a real CT item, even
# if an own-slot AP item code somehow maps here.
PLACEHOLDER_BYTES = frozenset(PLACEHOLDER_NAMES.keys())


def _placeholder_id_for_classification(classification: int) -> int:
    """Pick the placeholder byte for an AP item classification.

    ItemClassification is a bit field:
        0b0001 = progression (or progression_skip_balancing)
        0b0010 = useful
        0b0100 = trap
        0b1000 = skip_balancing
    Priority: trap > progression > useful > filler. Mirrors the
    NPC-marker color logic in _classification_to_npc_sprite.
    """
    cls = int(classification)
    if cls & 0b0100:
        return PLACEHOLDER_TRAP_ID
    if cls & 0b0001:
        return PLACEHOLDER_PROGRESSION_ID
    if cls & 0b0010:
        return PLACEHOLDER_USEFUL_ID
    return PLACEHOLDER_FILLER_ID


# --- beta source path management ---

def _ensure_beta_on_path(cjot_beta_path: Path) -> None:
    """Add cjot-beta/sourcefiles/ to sys.path so its top-level imports work.

    cjot-beta uses bare imports like `import ctenums`, so its sourcefiles
    directory must be on sys.path before we can `from ctrom import CTRom`.
    """
    src = Path(cjot_beta_path).resolve()
    if (src / "sourcefiles").exists():
        src = src / "sourcefiles"
    s = str(src)
    if s not in sys.path:
        sys.path.insert(0, s)


# --- apworld data file readers (consumed by selective placement) ---

def _load_location_id_to_name() -> dict[int, str]:
    """AP location code (with +5,100,000 offset) -> apworld location name.

    Read via pkgutil so this works whether the apworld is unpacked
    on disk or loaded from a zipped .apworld -- the latter is the
    common case for end users (custom_worlds/ctjot.apworld) and
    Path(__file__) cannot be opened with builtin open() inside a
    zip. Mirrors the Client.py / Items.py / Locations.py pattern.
    """
    import pkgutil
    data = pkgutil.get_data(__name__, "data/location_data.json")
    if data is None:
        raise RuntimeError(
            "location_data.json missing from ctjot apworld -- "
            "the apworld zip was built incorrectly."
        )
    raw = json.loads(data.decode())
    return {LOCATION_ID_START + v: k for k, v in raw.items()}


# --- name -> beta TreasureID transform ---

def _tid_name_from_location_name(loc_name: str) -> str:
    """Apworld location string -> ctenums.TreasureID enum-member name.

    Just an uppercase + collapse-non-alnum-to-underscore. The apworld
    location names were derived from beta TreasureID names so this is
    nearly always a clean round-trip. Names that don't map (event /
    recruit locations) are skipped by the caller via `hasattr(...)`.
    """
    out: list[str] = []
    prev_underscore = True
    for ch in loc_name:
        if ch.isalnum():
            out.append(ch.upper())
            prev_underscore = False
        else:
            if not prev_underscore:
                out.append("_")
                prev_underscore = True
    while out and out[-1] == "_":
        out.pop()
    return "".join(out)


# --- pass 1: selective placement ---

def apply_selective_placement_from_records(
    ct_rom, placement_records: list[dict],
) -> dict[str, int]:
    """Walk pre-computed AP placement records and write each chest's reward.

    Records come from CTJoTWorld._collect_placement_records() in the
    generator-side __init__.py and were serialized into the
    .apctjot zip as ap_placements.json. The generator already
    filtered out locations with `loc.address is None` and
    `loc.item is None`, so every record here describes a real
    AP placement.

    Returns a stat dict for diagnostics:
      - own:    real-item writes (own-slot locations)
      - other:  placeholder writes (other-slot locations)
      - skipped_unmapped: AP locations with no matching TreasureID
      - skipped_unsupported: TreasureID exists but has no entry in the
        beta's get_base_treasure_dict() (event/recruit/victory) or
        write_to_ctrom raised
    """
    from ctrom import CTRom  # noqa: F401  (importable proof)
    import ctenums
    from treasures.treasuretypes import (  # type: ignore
        get_base_treasure_dict,
        ChestTreasure,
        ScriptTreasure,
    )

    TreasureID = ctenums.TreasureID
    ItemID = ctenums.ItemID

    # byte -> ItemID enum member, for the four classification slots.
    # Lookup name is "UNUSED_FC".."UNUSED_FF"; if cjot-beta ever
    # changes its enum, fall back to ItemID.MOP so we still produce
    # *some* valid byte rather than blowing up.
    placeholder_items = {
        byte: getattr(ItemID, f"UNUSED_{byte:02X}", ItemID.MOP)
        for byte in PLACEHOLDER_NAMES
    }

    treasure_dict = get_base_treasure_dict()
    id_to_loc_name = _load_location_id_to_name()

    stats = {"own": 0, "other": 0, "skipped_unmapped": 0,
             "skipped_unsupported": 0}

    for record in placement_records:
        loc_address = record.get("loc_address")
        if loc_address is None:
            continue

        loc_name = id_to_loc_name.get(int(loc_address))
        if loc_name is None:
            stats["skipped_unmapped"] += 1
            continue

        tid_name = _tid_name_from_location_name(loc_name)
        tid = getattr(TreasureID, tid_name, None)
        if tid is None or tid not in treasure_dict:
            stats["skipped_unsupported"] += 1
            continue

        treasure = treasure_dict[tid]

        ph_byte = _placeholder_id_for_classification(record.get("classification", 0))
        placeholder = placeholder_items[ph_byte]

        if record.get("item_for_own_slot") and record.get("ap_item_code") is not None:
            ct_item_byte = int(record["ap_item_code"]) - ITEM_ID_START
            if 0 < ct_item_byte <= 0xFF and ct_item_byte not in PLACEHOLDER_BYTES:
                try:
                    treasure.reward = ItemID(ct_item_byte)
                    stats["own"] += 1
                except ValueError:
                    treasure.reward = placeholder
                    stats["other"] += 1
            else:
                # Either out of CT's item range or coincides with
                # one of our placeholder slots -- both indicate this
                # is not a real CT item byte for own-slot use.
                treasure.reward = placeholder
                stats["other"] += 1
        else:
            treasure.reward = placeholder
            stats["other"] += 1

        try:
            treasure.write_to_ctrom(ct_rom)
        except Exception as exc:
            # KNOWN LIMITATION (see docs/KNOWN_LIMITATIONS.md):
            # In Vanilla Rando mode, SUN_PALACE_KEY is the one and only
            # script-based treasure that fails this write. VR's
            # `split_sunstone_quest()` relocates the Sun Palace KI
            # mechanic to the Sun Keep 2300 spot and leaves
            # SUN_PALACE obj 0x11 fn 1 as a 7-byte stub with no
            # 0x4F / 0xCA / 0xCD opcodes for cjot-beta to find. We
            # silently skip the rewrite; the Sun Palace pickup keeps
            # the randomizer's local item, and AP's placement for that
            # location is effectively lost (items_handling=0b001 means
            # the server doesn't echo own items back). All other game
            # modes patch every script-based KI cleanly.
            log.debug("write_to_ctrom failed for %s: %s", tid.name, exc)
            stats["skipped_unsupported"] += 1

    return stats


# --- pass 2: AP validation marker ---

def apply_validation_marker(ct_rom, player_name: str) -> None:
    """Stamp the 32-byte "AP" + version + name block at 0x3F8C03."""
    safe = "".join(c for c in (player_name or "") if 32 <= ord(c) < 127)[:PLAYER_NAME_MAX]
    name_bytes = safe.encode("ascii")
    name_region = name_bytes + b"\x00" * (17 - len(name_bytes))
    block = b"AP" + AP_VERSION_BYTES + name_region + b"\x00" * 10
    assert len(block) == VALIDATION_SIZE
    rom = ct_rom.rom_data
    rom.seek(VALIDATION_OFFSET)
    rom.write(block)


# --- pass 3: receive-item polling hook ---

def _grant_freespace(ct_rom) -> int:
    """Mark long runs of 0xFF/0x00 in banks 0x40-0x5F as free.

    Without this, write_all_scripts_to_rom() raises FreeSpaceError when
    a modified script doesn't fit in its original allocation. Same scan
    strategy as webapp/ap_receive_hook.py and webapp/placeholder_fill.py.
    """
    from freespace import FSWriteType  # type: ignore

    rom = ct_rom.rom_data
    buf = rom.getbuffer()
    rom_size = len(buf)
    scan_start = min(0x400000, rom_size - 1)
    scan_end = min(0x600000, rom_size)
    if scan_end <= scan_start:
        return 0
    region = bytes(buf[scan_start:scan_end])

    granted = 0
    min_run_len = 0x100
    i = 0
    while i < len(region):
        b = region[i]
        if b in (0x00, 0xFF):
            j = i
            while j < len(region) and region[j] == b:
                j += 1
            run_len = j - i
            if run_len >= min_run_len:
                rom.seek(scan_start + i)
                rom.mark(run_len, FSWriteType.MARK_FREE)
                granted += run_len
            i = j
        else:
            i += 1
    return granted


# Working scratch addresses in script memory (volatile per-map).
# These are reset on each map load -- we don't store any persistent
# state here. Used as bounce-through addresses since
# assign_mem_to_mem doesn't support flag->flag and Decrement (0x73)
# requires a script-memory operand.
# Moved from 0x7F0220/0x7F0222 in v1.4.4: those slots were adjacent to
# cjot-beta's epochfail/charassign/iceage scratch range (0x7F0210-0x7F022E)
# and broke the Epoch time-period dial. 0x7F03F8/0x7F03FA are at the
# very top of script-local memory (offsets 0xFC/0xFD) -- well outside
# any documented use by vanilla CT or cjot-beta.
_SCRIPT_COUNT_TMP = 0x7F03F8   # script-memory copy of queue count for decrement
_SCRIPT_SHIFT_TMP = 0x7F03FA   # script-memory bounce slot for shifts
_SCRIPT_COUNT_OFFSET = (_SCRIPT_COUNT_TMP - 0x7F0200) // 2  # for opcode 0x73


def _build_receive_block(textbox_string_id: int | None = None):
    """Construct the queue-drain block injected at every map's obj 0 fn 0.

    `textbox_string_id` is an optional script-local string index. When
    provided, a personal-textbox command (opcode 0xBB) is appended after
    each 0xC7 add-item so the player gets an in-game notification that
    something arrived from the multiworld. The string at that index is
    expected to be the AP-arrival message (e.g. "* AP Item Received *");
    install_receive_hook adds it to each script's string table when the
    item-arrival-textbox option is enabled.

    Up to AP_QUEUE_CAPACITY items drain per map transition. The flow:
      0. Bounce the WRAM queue count into _SCRIPT_COUNT_TMP once.
         (if_mem_op_value can't check WRAM directly -- it only
         dispatches for the 0x7F0000-0x7F03FF range -- so we read
         the count into script memory and check there.)
      For each of AP_QUEUE_CAPACITY drain passes:
        1. Bail via if-guard if _SCRIPT_COUNT_TMP is zero.
        2. Stage the byte from AP_QUEUE_SLOT0_ADDR (WRAM) into
           SCRIPT_STAGING_ADDR via WRAM->script copy (opcode 0x48).
        3. Run vanilla command 0xC7 to add the item to inventory.
        4. Shift the queue: slot1->slot0, slot2->slot1, slot3->slot2.
           Each shift is a WRAM->script->WRAM bounce because
           assign_mem_to_mem only supports WRAM on the source side
           when the dest is script memory (opcode 0x48), and only
           supports WRAM on the dest side when the source is script
           memory (opcode 0x4C).
        5. Zero slot3 (the now-empty tail) via opcode 0x4A
           (assign_val_to_mem to all-RAM range).
        6. Decrement _SCRIPT_COUNT_TMP in-place (opcode 0x73).
      End:
        7. Persist _SCRIPT_COUNT_TMP back to AP_QUEUE_COUNT_ADDR
           via script->WRAM copy (opcode 0x4C).

    Unrolled (one if-guarded drain pass per slot, AP_QUEUE_CAPACITY
    times) so we don't need event-script loop machinery and the
    block remains an easy target for cjot-beta's recompressor to
    place in freespace.
    """
    from eventcommand import EventCommand as EC, Operation as OP  # type: ignore
    from eventfunction import EventFunction as EF  # type: ignore

    queue_slots = [
        AP_QUEUE_SLOT0_ADDR,
        AP_QUEUE_SLOT1_ADDR,
        AP_QUEUE_SLOT2_ADDR,
        AP_QUEUE_SLOT3_ADDR,
    ]

    full = EF()

    # 0. Load WRAM count into a script-memory working copy that we
    #    decrement in-place across all passes, then persist back at
    #    the end. Saves AP_QUEUE_CAPACITY-1 redundant WRAM reads.
    full.add(EC.assign_mem_to_mem(AP_QUEUE_COUNT_ADDR, _SCRIPT_COUNT_TMP, 1))

    def _one_drain_pass() -> "EF":
        """One iteration: deliver slot0, shift the queue, decrement count."""
        body = EF()
        # 1. Stage the head byte (WRAM -> script staging).
        body.add(EC.assign_mem_to_mem(queue_slots[0], SCRIPT_STAGING_ADDR, 1))
        # 2. Add it to inventory via vanilla command 0xC7.
        body.add(EC.generic_one_arg(0xC7, RECEIVE_ITEM_OFFSET_BYTE))
        # 2a. Optional in-game notification (item-arrival-textbox flag).
        # Personal textbox (0xBB) closes when the player walks away --
        # non-blocking enough to be acceptable mid-gameplay. With up to
        # AP_QUEUE_CAPACITY items per drain, the player can get up to 4
        # textboxes in a row on a busy map transition.
        if textbox_string_id is not None:
            body.add(EC.generic_one_arg(0xBB, textbox_string_id))
        # 3. Shift slots down: slot[i] -> slot[i-1] for i in [1..N-1].
        #    Each shift bounces WRAM -> script -> WRAM.
        for i in range(1, len(queue_slots)):
            body.add(EC.assign_mem_to_mem(queue_slots[i], _SCRIPT_SHIFT_TMP, 1))
            body.add(EC.assign_mem_to_mem(_SCRIPT_SHIFT_TMP, queue_slots[i - 1], 1))
        # 4. Zero the now-empty tail slot.
        body.add(EC.assign_val_to_mem(0, queue_slots[-1], 1))
        # 5. Decrement the script-mem count copy in place.
        body.add(EC.generic_one_arg(0x73, _SCRIPT_COUNT_OFFSET))
        return EF().add_if(
            EC.if_mem_op_value(_SCRIPT_COUNT_TMP, OP.NOT_EQUALS, 0, 1, 0),
            body,
        )

    for _ in range(AP_QUEUE_CAPACITY):
        full.append(_one_drain_pass())

    # 7. Persist the (now possibly decremented) count back to WRAM.
    full.add(EC.assign_mem_to_mem(_SCRIPT_COUNT_TMP, AP_QUEUE_COUNT_ADDR, 1))

    return full


def install_receive_hook(
    ct_rom,
    show_textbox: bool = False,
) -> dict[str, list[str]]:
    """Inject the polling block into every LocID's obj 0 fn 0.

    `show_textbox` toggles the v1.4.11 item-arrival-textbox feature.
    When True, each script gets the AP-arrival message string added to
    its string table at install time, and the receive block is built
    per-script with that string ID baked into a 0xBB textbox command
    after each 0xC7 add-item. When False (default), the receive block
    is built once and reused -- no per-script string allocation, no
    textbox commands, identical to the silent-delivery behavior of
    1.4.10 and earlier.
    """
    import ctenums

    _grant_freespace(ct_rom)

    # Pre-build the silent block once if the textbox feature is off,
    # so we keep the cheap shared-bytes path for the common case.
    silent_block_bytes = (
        _build_receive_block().get_bytearray()
        if not show_textbox
        else b""
    )
    if not show_textbox and not silent_block_bytes:
        return {"successes": [], "failures": ["empty hook block"]}

    # Static AP-arrival message. {null} terminates the CT string.
    # Short to keep the textbox unobtrusive; one line, no item name yet
    # (item-name substitution is queued for a v2 of this feature).
    AP_ARRIVAL_MSG = "* AP Item Received *{null}"

    successes: list[str] = []
    failures: list[str] = []
    seen: set[int] = set()
    for member in ctenums.LocID:
        try:
            loc_id = int(member)
        except (TypeError, ValueError):
            continue
        if loc_id in seen:
            continue
        seen.add(loc_id)

        try:
            script = ct_rom.script_manager.get_script(loc_id)
        except Exception as exc:
            failures.append(f"{member.name}: {type(exc).__name__}: {exc}")
            continue
        if script is None:
            failures.append(f"{member.name}: script is None")
            continue
        try:
            if show_textbox:
                # Add the AP-arrival string to THIS script's string table
                # so we can reference it via its script-local index.
                msg_id = script.add_py_string(AP_ARRIVAL_MSG)
                block_bytes = _build_receive_block(
                    textbox_string_id=msg_id
                ).get_bytearray()
            else:
                block_bytes = silent_block_bytes
            fn_start = script.get_function_start(0, 0)
            script.insert_commands(block_bytes, fn_start)
            successes.append(member.name)
        except Exception as exc:
            failures.append(f"{member.name}: {type(exc).__name__}: {exc}")
    return {"successes": successes, "failures": failures}


# --- pass 5: AP classification markers (runs last when enabled) ---

# LocIDs cjot-beta's tier-marker pass refuses to touch (script objects
# in these maps make NPC-marker injection unsafe / crashy). Mirror the
# list so our pass behaves identically.
_MARKER_SKIP_LOCIDS = (0x1C0, 0x1C4, 0x1C5, 0x1C6, 0x1C7)


def _classification_to_npc_sprite(classification, NpcID):
    """Pick a marker sprite for an AP item classification.

    Archipelago's ItemClassification is a bit field:
        0b0001 = progression
        0b0010 = useful
        0b0100 = trap
        0b1000 = skip_balancing
    progression_skip_balancing has both bits 0 and 3 set. We pick by
    priority trap > progression > useful > filler, then map to one of
    the cjot-beta NPC sprites (BROWN/BLUE/PURPLE_GLOWING_LIGHT and
    RED_STAR are the only marker-friendly stationary sparkles in the
    NpcID enum).
    """
    cls = int(classification)
    if cls & 0b0100:  # trap
        return NpcID.RED_STAR
    if cls & 0b0001:  # progression / progression_skip_balancing
        return NpcID.PURPLE_GLOWING_LIGHT
    if cls & 0b0010:  # useful
        return NpcID.BLUE_GLOWING_LIGHT
    return NpcID.BROWN_GLOWING_LIGHT  # filler / nothing


def apply_ap_classification_markers_from_records(
    ct_rom,
    placement_records: list[dict],
    game_mode_str: str,
) -> dict[str, int]:
    """Inject AP-classification-colored markers above every chest.

    Mirrors cjot-beta's `treasurewriter.write_treasure_tier_markers`
    but reads the marker color from each placement record's
    `classification` field rather than from a static treasure-tier
    table. The generator captured each location's classification
    (which is the *recipient's* classification for cross-slot items)
    when it built ap_placements.json, so progression for slot 2
    still shows up as purple in slot 1's ROM.

    Returns a stat dict for diagnostics:
      - markers:        chests that got an NPC marker
      - skipped_chests: chests with no AP classification (no marker)
      - skipped_locs:   LocIDs skipped (bad list / no script)
    """
    import ctenums
    from treasures import treasuretypes as tt  # type: ignore
    from eventcommand import EventCommand as EC, Operation as OP  # type: ignore
    from eventfunction import EventFunction as EF  # type: ignore

    NpcID = ctenums.NpcID
    TreasureID = ctenums.TreasureID

    treasure_ptr_start = 0x35F000
    treasure_data = tt.get_base_treasure_dict()
    id_to_loc_name = _load_location_id_to_name()

    # chest_index -> NpcID sprite for that chest's item classification.
    chest_sprite: dict[int, Any] = {}
    for record in placement_records:
        loc_address = record.get("loc_address")
        if loc_address is None:
            continue
        loc_name = id_to_loc_name.get(int(loc_address))
        if loc_name is None:
            continue
        tid_name = _tid_name_from_location_name(loc_name)
        tid = getattr(TreasureID, tid_name, None)
        if tid is None or tid not in treasure_data:
            continue
        treasure = treasure_data[tid]
        if not isinstance(treasure, tt.ChestTreasure):
            continue
        chest_sprite[treasure.chest_index] = _classification_to_npc_sprite(
            int(record.get("classification", 0)), NpcID
        )

    bad_loc_ids: set[int] = set(_MARKER_SKIP_LOCIDS)
    if str(game_mode_str or "").strip().lower() in ("lost worlds", "lw"):
        try:
            bad_loc_ids.add(int(ctenums.LocID.OZZIES_FORT_GUILLOTINE))
        except Exception:
            pass

    stats = {"markers": 0, "skipped_chests": 0, "skipped_locs": 0}

    for loc_id in range(0, 0x200):
        if loc_id in bad_loc_ids:
            stats["skipped_locs"] += 1
            continue

        ptr_st = treasure_ptr_start + 2 * loc_id
        ct_rom.rom_data.seek(ptr_st)
        ptr = int.from_bytes(ct_rom.rom_data.read(2), "little")
        next_ptr = int.from_bytes(ct_rom.rom_data.read(2), "little")
        num_boxes = (next_ptr - ptr) // 4
        if num_boxes <= 0:
            continue

        try:
            script = ct_rom.script_manager.get_script(loc_id)
        except Exception:
            stats["skipped_locs"] += 1
            continue
        if script is None:
            stats["skipped_locs"] += 1
            continue

        ct_rom.rom_data.seek(0x350000 + ptr)
        first_box = tt.ChestTreasureData(ct_rom.rom_data.read(4))
        first_box_id = tt.get_loc_id_first_chest_id(loc_id)

        if first_box.is_copying_location():
            real_loc_id = first_box.copy_location
            ct_rom.rom_data.seek(treasure_ptr_start + 2 * real_loc_id)
            ptr = int.from_bytes(ct_rom.rom_data.read(2), "little")
            next_ptr = int.from_bytes(ct_rom.rom_data.read(2), "little")
            num_boxes = (next_ptr - ptr) // 4
            first_box_id = tt.get_loc_id_first_chest_id(real_loc_id)

        ct_rom.rom_data.seek(0x350000 + ptr)
        for ind in range(num_boxes):
            chest_id = first_box_id + ind
            sprite = chest_sprite.get(chest_id)
            if sprite is None:
                ct_rom.rom_data.seek(4, 1)
                stats["skipped_chests"] += 1
                continue

            chest_flag_addr = 0x7F0001 + chest_id // 8
            chest_flag_bit = 1 << (chest_id % 8)

            box = tt.ChestTreasureData(ct_rom.rom_data.read(4))
            obj_id = script.append_empty_object()
            script.set_function(
                obj_id, 0,
                EF()
                .add(EC.load_npc(sprite))
                .add_if(
                    EC.if_mem_op_value(
                        chest_flag_addr, OP.BITWISE_AND_NONZERO,
                        chest_flag_bit, 1, 0),
                    EF().add(EC.remove_object(obj_id))
                )
                .add(EC.set_object_coordinates_tile(box.x_coord, box.y_coord))
                .add(EC.generic_command(0x8E, 0x3B))   # sprite priority
                .add(EC.generic_command(0x84, 0))      # ethereal / immovable
                .add(EC.return_cmd())
                .set_label("loop_st")
                .add_if(
                    EC.if_mem_op_value(
                        chest_flag_addr, OP.BITWISE_AND_NONZERO,
                        chest_flag_bit, 1, 0),
                    EF()
                    .add(EC.set_own_drawing_status(False))
                    .jump_to_label(EC.jump_forward(0), "end")
                )
                .jump_to_label(EC.jump_back(0), "loop_st")
                .set_label("end")
                .add(EC.end_cmd())
            )
            script.set_function(obj_id, 1, EF().add(EC.return_cmd()))
            script.set_function(obj_id, 2, EF().add(EC.return_cmd()))
            stats["markers"] += 1

    return stats


# --- pass 6: AP victory marker ---

# Bit 0x01 of 0x7F0020 is the AP victory flag (Client.VICTORY_ADDRESS).
# Client polls this byte every game-watcher tick; once set, it sends
# StatusUpdate with CLIENT_GOAL and unlocks the player's items in the
# multiworld. cjot-beta does not write this address anywhere — every
# victory path funnels through LocID.ENDING_SELECTOR (Lavos defeat,
# bucket-list auto-win when --bucket-objectives-win is set, the
# "open the bucket" path) so we just stamp the bit on entry to that
# map and any victory route flips it.
VICTORY_FLAG_ADDR = 0x7F0020
VICTORY_FLAG_BIT = 0x01


def apply_victory_marker(ct_rom) -> bool:
    """Patch ENDING_SELECTOR's startup to set the AP victory bit.

    Returns True if the patch was applied, False if the script could
    not be loaded (in which case victory detection won't work and the
    player will need to use AP's `/release` to unlock items manually).
    """
    import ctenums  # type: ignore
    from eventcommand import EventCommand as EC  # type: ignore
    from eventfunction import EventFunction as EF  # type: ignore

    try:
        script = ct_rom.script_manager.get_script(int(ctenums.LocID.ENDING_SELECTOR))
    except Exception as exc:
        log.warning("victory marker: failed to load ENDING_SELECTOR: %s", exc)
        return False
    if script is None:
        log.warning("victory marker: ENDING_SELECTOR script is None")
        return False

    block_bytes = (
        EF().add(EC.set_bit(VICTORY_FLAG_ADDR, VICTORY_FLAG_BIT))
        .get_bytearray()
    )
    fn_start = script.get_function_start(0, 0)
    script.insert_commands(block_bytes, fn_start)
    return True


# --- pass 4: item-name rename ---

# --- pass 7: conditional chest verb (Got vs You Sent) ---

# CT's chest pickup textbox is rendered from a single hardcoded string
# at file offset 0x1EFF0A. Vanilla form is roughly:
#   06 <padding> "Got" <pad> "1" <pad> 1F 02 00
# where 0x1F is the item-name substitution code that pulls the name of
# the chest's item byte (which the chest engine has just stored at
# script-staging address 0x7F0200) from CT's item-name table.
#
# To say "You Sent 1 X!" only when X is one of our cross-slot
# placeholder bytes (0xEA-0xED), we install a custom CT
# substitution-symbol handler that:
#   1. Reads the item byte at 0x7F0200.
#   2. If it's in [0xEA, 0xEE) -> emits "You Sent 1 ".
#      Otherwise -> emits "Got 1 ".
# We then rewrite the chest pickup string to start with this dynamic
# substitution rather than the literal "Got 1 " bytes.
#
# This mirrors cjot-beta's existing pattern in
# `_beta/sourcefiles/base/chesttext.py` (which uses sym 0x01 for an
# item-description substitution). We use a different sym so the two
# features can coexist.
CHEST_STRING_OFFSET            = 0x1EFF0A
SUBSTITUTION_JUMP_TABLE_BASE   = 0x025903   # entry stride is 2 bytes
TEXT_ENGINE_CONTINUATION_ADDR  = 0xC25BF5   # bus address; same value chesttext.py jumps to
VERB_SUB_SYMBOL                = 0x04       # vanilla jump-table entry points at default handler 0x594F

# CT-encoded byte sequences. Encoding rules per
# `_beta/sourcefiles/ctstrings.py`:
#   uppercase: ord(c) - 0x41 + 0xA0
#   lowercase: ord(c) - 0x61 + 0xBA
#   numbers:   ord(c) - 0x30 + 0xD4
#   space:     0xFF
_GOT_PREFIX_ENCODED = bytes([
    0xA6,  # G
    0xC8,  # o
    0xCD,  # t
    0xFF,  # space
    0xD5,  # 1
    0xFF,  # space
])

_SENT_PREFIX_ENCODED = bytes([
    0xB8,  # Y
    0xC8,  # o
    0xCE,  # u
    0xFF,  # space
    0xB2,  # S
    0xBE,  # e
    0xC7,  # n
    0xCD,  # t
    0xFF,  # space
    0xD5,  # 1
    0xFF,  # space
])


# Empirically (see analysis below), bank 0x02 in a cjot-beta-output
# ROM has only ~50-60 bytes of total free space spread across two
# small runs -- nowhere near enough for our ~70-byte handler.
# cjot-beta consumes the bank-0x02 free blocks documented in
# basepatch.py:mark_initial_free_space for its own ASM hooks and
# string tables.
#
# Workaround: put the real handler in any freespace (banks 0x40-0x5F
# work, that's where _grant_freespace marks ~MB of room) and write a
# tiny 4-byte JML trampoline into a small bank-0x02 run. CT's
# substitution jump table points at the trampoline (16-bit offset,
# bank-0x02 implicit); the trampoline does a long jump out to the
# real handler. Trampoline byte size: 0x5C lo mi hi = 4 bytes, fits
# in the smallest known runs.
_TRAMPOLINE_SIZE = 4


def _find_bank02_run(ct_rom, length: int) -> int:
    """Scan bank 0x02 for a contiguous FF or 00 run of `length` bytes.

    Returns the file offset of the run's start. Raises if no run of
    sufficient size exists (extremely unlikely for our 4-byte
    trampoline; the smallest CT bank-0x02 free runs are typically
    20+ bytes).
    """
    rom = ct_rom.rom_data
    buf = rom.getbuffer()
    bank_start = 0x020000
    bank_end = min(0x030000, len(buf))

    i = bank_start
    while i < bank_end:
        b = buf[i]
        if b in (0x00, 0xFF):
            j = i
            while j < bank_end and buf[j] == b:
                j += 1
            if j - i >= length:
                return i
            i = j
        else:
            i += 1

    raise RuntimeError(
        f"Bank 0x02 has no FF/00 run of {length} bytes; cannot place "
        "verb-substitution trampoline."
    )


def install_conditional_chest_verb(ct_rom) -> None:
    """Make chest pickups display "You Sent 1 X!" for cross-slot
    placeholder bytes (0xEA-0xED) and "Got 1 X!" for everything else.

    Mechanism:
      1. Pre-write both verb strings ("Got 1 ", "You Sent 1 ") to
         freespace (any bank).
      2. Assemble the conditional-prefix ASM handler. Reads the item
         byte at 0x7F0200, branches on whether it's in the
         placeholder range, sets up the right string pointer/length
         at the engine's expected fields (0x0237/0x0239/0x023A),
         and tail-jumps to the engine's continuation point.
      3. Place the handler in any freespace -- typically bank
         0x40-0x5F where _grant_freespace already marked ~MB of
         room. Bank 0x02 is too crowded for the full handler.
      4. Write a tiny 4-byte JML trampoline at a bank-0x02 FF/00
         run. CT's substitution jump table only stores 16-bit
         offsets (bank 0x02 implicit), so the trampoline must live
         there even if the real handler doesn't.
      5. Patch the substitution-symbol jump table at
         0x025903 + 2*VERB_SUB_SYMBOL with the trampoline's offset.
      6. Overwrite the chest pickup string at 0x1EFF0A to start
         with our substitution code instead of the literal "Got 1 "
         bytes.
    """
    from asm import assemble
    from asm import instructions as inst
    from asm.instructions import AddressingMode as AM
    import byteops
    from freespace import FSWriteType  # type: ignore

    rom = ct_rom.rom_data

    # Step 1: write the two verb strings to freespace.
    got_addr = rom.space_manager.get_free_addr(len(_GOT_PREFIX_ENCODED))
    rom.seek(got_addr)
    rom.write(_GOT_PREFIX_ENCODED, FSWriteType.MARK_USED)

    sent_addr = rom.space_manager.get_free_addr(len(_SENT_PREFIX_ENCODED))
    rom.seek(sent_addr)
    rom.write(_SENT_PREFIX_ENCODED, FSWriteType.MARK_USED)

    got_bus  = byteops.to_rom_ptr(got_addr)
    sent_bus = byteops.to_rom_ptr(sent_addr)

    # Step 2: assemble the conditional handler.
    # Tail boilerplate (LDA #$01 / STA $30 / LDA #$00 / XBA / JMP $C25BF5)
    # mirrors chesttext.py:add_get_desc_char's exit. The engine expects
    # 0x0237/0x0239 = bus addr of the substring, 0x023A = length, and
    # then the continuation at $C25BF5 inlines that substring into the
    # textbox render.
    handler: list = [
        # 8-bit accumulator; load chest's item byte from 0x7F0200.
        inst.SEP(0x20),
        inst.LDA(0x7F0200, AM.LNG),

        # Branch to "use_got" unless byte is in [0xEA, 0xEE).
        inst.CMP(0xEA, AM.IMM8),
        inst.BCC('use_got'),
        inst.CMP(0xEE, AM.IMM8),
        inst.BCS('use_got'),

        # Item byte is one of our placeholders -> emit "You Sent 1 ".
        inst.REP(0x20),
        inst.LDA(sent_bus & 0xFFFF, AM.IMM16),
        inst.STA(0x0237, AM.ABS),
        inst.SEP(0x20),
        inst.LDA(sent_bus >> 16, AM.IMM8),
        inst.STA(0x0239, AM.ABS),
        inst.LDA(len(_SENT_PREFIX_ENCODED), AM.IMM8),
        inst.STA(0x023A, AM.ABS),
        inst.BRA('finish'),

        'use_got',
        # Real CT item byte -> emit "Got 1 ".
        inst.REP(0x20),
        inst.LDA(got_bus & 0xFFFF, AM.IMM16),
        inst.STA(0x0237, AM.ABS),
        inst.SEP(0x20),
        inst.LDA(got_bus >> 16, AM.IMM8),
        inst.STA(0x0239, AM.ABS),
        inst.LDA(len(_GOT_PREFIX_ENCODED), AM.IMM8),
        inst.STA(0x023A, AM.ABS),

        'finish',
        # Tail: hand off to the engine's substring-render continuation.
        inst.LDA(0x01, AM.IMM8),
        inst.STA(0x30, AM.DIR),
        inst.LDA(0x00, AM.IMM8),
        inst.XBA(),
        inst.JMP(TEXT_ENGINE_CONTINUATION_ADDR, AM.LNG),
    ]
    handler_b = assemble.assemble(handler)

    # Step 3: place the real handler anywhere there's freespace
    # (typically bank 0x40-0x5F via _grant_freespace).
    handler_addr = rom.space_manager.get_free_addr(len(handler_b))
    rom.seek(handler_addr)
    rom.write(handler_b, FSWriteType.MARK_USED)

    # Step 4: write a 4-byte JML trampoline into a small bank-0x02
    # free run. Trampoline encodes `JML <handler bus addr>` so when
    # CT's text engine indirects through the jump table into bank
    # 0x02, we forward the call out to the real handler.
    handler_bus = byteops.to_rom_ptr(handler_addr)
    trampoline = bytes([
        0x5C,                            # JML LNG
        handler_bus & 0xFF,
        (handler_bus >> 8) & 0xFF,
        (handler_bus >> 16) & 0xFF,
    ])
    trampoline_addr = _find_bank02_run(ct_rom, _TRAMPOLINE_SIZE)
    rom.seek(trampoline_addr)
    rom.write(trampoline)
    # Bypassing space_manager for the trampoline because we located
    # it via direct scan; no other pass at apply time needs bank 0x02
    # so this won't be double-allocated.

    # Step 5: patch the jump-table entry for our substitution symbol
    # to point at the trampoline (low 16 bits; bank 0x02 implicit).
    rom.seek(SUBSTITUTION_JUMP_TABLE_BASE + 2 * VERB_SUB_SYMBOL)
    rom.write(int.to_bytes(trampoline_addr & 0xFFFF, 2, "little"))

    # Step 6: overwrite the chest pickup string.
    # Layout per byte:
    #   0x06       open textbox / window control (preserved from vanilla)
    #   VERB_SUB   our dynamic prefix substitution ("Got 1 " or "You Sent 1 ")
    #   0x1F       item-name substitution (existing CT engine code)
    #   0xDE       '!'
    # Optional tail (only when cjot-beta's chesttext-hack is active):
    #   0x06 0x01  control + sym 0x01, which the chesttext-hack overrides
    #              to render the item's description below the pickup text.
    #              Cross-slot placeholder items (UNUSED_EA-ED) have empty
    #              descriptions so they render as blank space, same as
    #              vanilla items without descriptions.
    #   0x00       end terminator
    # When chesttext-hack ISN'T active (i.e. cjot-beta didn't apply
    # `apply_chest_text_hack` for this seed), the trailing `06 01`
    # would invoke vanilla CT's sym 0x01 handler from chest-text
    # context and produce undefined output -- so we skip it and
    # terminate cleanly after `!`.
    # Pad to 12 bytes total (matching cjot-beta's chesttext-hack
    # write width) with NULs so any engine over-read terminates
    # immediately.
    rom.seek(CHEST_STRING_OFFSET)
    original_tail = rom.read(12)[9:12]
    chesttext_active = bytes(original_tail) == bytes([0x06, 0x01, 0x00])

    if chesttext_active:
        new_chest_string = bytes([
            0x06, VERB_SUB_SYMBOL, 0x1F, 0xDE, 0x06, 0x01, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00,
        ])
    else:
        new_chest_string = bytes([
            0x06, VERB_SUB_SYMBOL, 0x1F, 0xDE, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        ])
    rom.seek(CHEST_STRING_OFFSET)
    rom.write(new_chest_string)


def rename_placeholder_items(ct_rom) -> None:
    """Rename each AP placeholder slot in CT's item-name table.

    Walks PLACEHOLDER_NAMES and writes the per-classification label
    ("AP Trap" / "AP Key" / "AP Useful" / "AP Filler") into each
    slot's row of the in-ROM name table. Each row is
    ITEM_NAME_SIZE (11) bytes: one icon prefix byte (preserved
    from whatever cjot-beta wrote) followed by 10 bytes of
    CT-encoded name.
    """
    from ctstrings import CTNameString  # type: ignore

    rom = ct_rom.rom_data
    for byte, label in PLACEHOLDER_NAMES.items():
        name_offset = ITEM_NAMES_OFFSET + byte * ITEM_NAME_SIZE
        rom.seek(name_offset)
        existing = rom.read(ITEM_NAME_SIZE)
        prefix_byte = existing[0] if existing else 0xEF
        display_bytes = CTNameString.from_string(label, ITEM_NAME_SIZE - 1)
        full = bytes([prefix_byte & 0xFF]) + bytes(display_bytes)
        if len(full) != ITEM_NAME_SIZE:
            raise RuntimeError(
                f"Built item-name for slot 0x{byte:02X} has length "
                f"{len(full)}, expected {ITEM_NAME_SIZE}."
            )
        rom.seek(name_offset)
        rom.write(full)


# --- pass 8: rock-pickup flag injection ---
#
# The script-treasure rocks (Denadoro, Laruba, Kajar) live at LocIDs
# whose vanilla CT scripts use the storyline counter, not bit flags,
# to track event completion. cjot-beta's Rocksanity adds the rocks
# but doesn't add per-rock event flags either. Without a unique flag
# per rock pickup, the SNI client can't tell when a player picked up
# a rock at one of these spots, so AP can't route the placed item to
# its destination slot -- the user opens the chest, AP server never
# hears about it, and the item silently never delivers.
#
# Fix: inject a "write 1 to a unique WRAM byte" command into each
# rock pickup script, right after the existing add-item command. The
# SNI client reads these bytes each tick and reports the location
# check when it sees a non-zero value.
#
# Bytes are placed in our safe WRAM region at 0x7E2900+
# (already partly used by the receive queue at 0x7E2900-0x7E2905).
# Black Omen Terra Rock is a ChestTreasure(0xCE) -- vanilla
# data-driven chest tracking already covers it via the chest-flag
# mechanism (chest 0xCE -> byte offset 0x19, bit mask 0x40), so no
# injection is needed for it.

ROCK_PICKUP_BASE_ADDR = 0x7E2906  # starts after queue + counter at 0x7E2900-0x7E2905

# (LocID name, object_id, function_id, target WRAM byte address).
# LocIDs are looked up by name on cjot-beta's ctenums.LocID at apply
# time -- we don't import the enum here so this module can stay
# importable on the generator side (which doesn't have cjot-beta on
# sys.path).
_ROCK_PICKUP_FLAG_TARGETS = (
    ("DENADORO_MTS_MASAMUNE_EXTERIOR", 0x01, 0x07, ROCK_PICKUP_BASE_ADDR + 0),
    ("LARUBA_RUINS",                   0x0D, 0x01, ROCK_PICKUP_BASE_ADDR + 1),
    ("KAJAR_ROCK_ROOM",                0x08, 0x01, ROCK_PICKUP_BASE_ADDR + 2),
)


def install_rock_pickup_flags(ct_rom) -> dict[str, list[str]]:
    """Inject pickup-completion flags into rocksanity rock event scripts.

    For each script-treasure rock target, find the existing add-item
    command (0xC7 from our hook or 0xCA from vanilla) inside the
    pickup function, then insert an `assign_val_to_mem(1, addr, 1)`
    immediately after it. The flag fires only when the player has
    actually picked up the rock (which is what the add-item command
    represents), not on every script entry.

    Returns a stat dict: {"successes": [...], "failures": [...]}.
    Failures are typically "function not found" (the rock spot isn't
    available in this seed's mode/flag combination, e.g., a
    non-Rocksanity seed) and are non-fatal.
    """
    import ctenums  # type: ignore  # cjot-beta module
    from eventcommand import EventCommand as EC  # type: ignore

    successes: list[str] = []
    failures: list[str] = []
    LocID = ctenums.LocID

    for loc_name, obj_id, fn_id, addr in _ROCK_PICKUP_FLAG_TARGETS:
        loc_id = getattr(LocID, loc_name, None)
        if loc_id is None:
            failures.append(f"{loc_name}: LocID not found")
            continue
        try:
            script = ct_rom.script_manager.get_script(int(loc_id))
            if script is None:
                failures.append(f"{loc_name}: script is None")
                continue
            fn_start = script.get_function_start(obj_id, fn_id)
            fn_end = script.get_function_end(obj_id, fn_id)
            # Look for the add-item command in the function.
            # 0xC7 is "Add Item from local memory" (the receive-hook
            # form) and 0xCA is "Add Item by literal byte" (vanilla
            # chest form). Either confirms a rock was just delivered.
            pos, cmd = script.find_command([0xC7, 0xCA], fn_start, fn_end)
            insert_pos = pos + len(cmd)
            flag_cmd = EC.assign_val_to_mem(1, addr, 1)
            script.insert_commands(flag_cmd.to_bytearray(), insert_pos)
            successes.append(loc_name)
        except Exception as exc:
            failures.append(
                f"{loc_name}: {type(exc).__name__}: {exc}")

    return {"successes": successes, "failures": failures}


# --- top-level orchestration ---

def apply_all_from_records(
    ct_rom,
    placements: list[dict],
    metadata: dict,
) -> dict[str, Any]:
    """Run the AP-side passes in order against pre-computed records.

    Inputs come from the .apctjot zip:
      - `placements`: parsed ap_placements.json
      - `metadata`:   parsed ap_metadata.json

    Caller (CTJoTPatchExtension.apply_ctjot_ap_passes) must already
    have the cjot-beta sourcefiles/ on sys.path, and is responsible
    for finalizing the CTRom with `ct_rom.write_all_scripts_to_rom()`
    and `ct_rom.fix_snes_checksum()` before serializing it.
    """
    placement_stats = apply_selective_placement_from_records(ct_rom, placements)
    apply_validation_marker(ct_rom, str(metadata.get("player_name", "") or ""))
    hook_stats = install_receive_hook(
        ct_rom,
        show_textbox=bool(metadata.get("item_arrival_textbox_enabled")),
    )
    rename_placeholder_items(ct_rom)
    install_conditional_chest_verb(ct_rom)
    rock_flags_stats = install_rock_pickup_flags(ct_rom)
    victory_ok = apply_victory_marker(ct_rom)

    # AP classification markers are gated by the option captured into
    # ap_metadata.json at generate time. When on, the generator also
    # suppresses cjot-beta's `--treasure-tier-markers` switch in
    # flag_translation.py so the two passes don't collide.
    marker_stats = None
    if metadata.get("ap_classification_markers_enabled"):
        marker_stats = apply_ap_classification_markers_from_records(
            ct_rom, placements, str(metadata.get("game_mode", "") or "")
        )

    return {
        "placement": placement_stats,
        "hook": hook_stats,
        "rock_flags": rock_flags_stats,
        "markers": marker_stats,
        "victory_marker": victory_ok,
    }
