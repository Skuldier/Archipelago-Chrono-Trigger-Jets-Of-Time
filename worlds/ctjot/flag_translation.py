"""
Translate CTJoTOptions -> cjot-beta CLI argv.

Each entry below maps an apworld YAML option attribute to the matching
cjot-beta `--<flag>` argument. The translator reads the player's
`self.options` dataclass and returns a flat list[str] suitable to pass
into `randomizer.invoke(extra_args=...)`.

Source of truth for the CLI arg names: cjot-beta/sourcefiles/cli/.
For values: see Options.py for the typed Option subclasses; the
mapping below mirrors what beta.ctjot.com surfaces in its UI.

Notes
-----
- Toggles emit the bare switch when on (e.g. `--chronosanity`) and
  nothing when off.
- Choice / TextChoice options translate via per-option value tables.
- Range / Number options emit `--flag <int>`.
- BucketObjectiveHints (an OptionList of strings) becomes
  `--bucket-objective1 X --bucket-objective2 Y ...` up to 8 entries.
- Options that have no cli_arg (yaml-only structural data, seed share
  link) are explicitly skipped.
"""
from __future__ import annotations

from typing import Any


# Static maps for choice-style options.
_GAME_MODE_TO_FLAG = {
    "Standard":         "std",
    "Lost worlds":      "lw",
    "Ice Age":          "ia",
    "Legacy of cyrus":  "loc",
    "Vanilla rando":    "van",
}
_ITEM_DIFF_TO_FLAG = {
    "Easy":   "easy",
    "Normal": "normal",
    "Hard":   "hard",
}
_ENEMY_DIFF_TO_FLAG = {0: "normal", 1: "hard"}
_TECH_TO_FLAG = {0: "normal", 1: "balanced", 2: "random"}
_SHOP_TO_FLAG = {
    0: "normal",
    1: "random",
    2: "mostly_random",
    3: "free",
}


# Toggle -> cjot-beta CLI switch. Each entry is (option_attr, cli_arg).
# When the option's value is truthy, the cli_arg is appended to argv.
_TOGGLE_FLAGS: list[tuple[str, str]] = [
    ("disable_glitches",      "--fix-glitch"),
    ("boss_scaling",          "--boss-scale"),
    ("early_pendant",         "--fast-pendant"),
    ("unlocked_magic",        "--unlocked-magic"),
    ("chronosanity",          "--chronosanity"),
    ("randomize_healing",     "--healing-item-rando"),
    ("mystery_seed",          "--mystery"),
    ("tab_treasures",         "--tab-treasures"),
    ("randomize_bosses",      "--boss-randomization"),
    ("zeal_2_last_boss",      "--zeal-end"),
    ("locked_characters",     "--locked-chars"),
    ("randomize_characters",  "--char-rando"),
    ("randomize_gear",        "--gear-rando"),
    ("epoch_fail",            "--epoch-fail"),
    # Character rando
    ("duplicate_characters",  "--duplicate-characters"),
    ("duplicate_dual_techs",  "--duplicate-techs"),
    # Boss rando
    ("legacy_boss_placement", "--legacy-boss-placement"),
    ("boss_spot_hps",         "--boss-spot-hp"),
    # Quality of life
    # cjot-beta exposes "sightscope always on" as --visible-health
    # (the corresponding GameFlag is VISIBLE_HEALTH).
    ("sightscope_always_on",  "--visible-health"),
    ("boss_sightscope",       "--boss-sightscope"),
    ("fast_tabs",             "--fast-tabs"),
    ("free_menu_glitch",      "--free-menu-glitch"),
    ("visible_techlist",      "--visible-techlist"),
    # Extra
    ("starters_sufficient",   "--starters-sufficient"),
    ("tech_damage_rando",     "--tech-damage-rando"),
    ("element_rando",         "--element-randomization"),
    ("tackle_on_hit",         "--tackle-on-hit-effects"),
    ("use_anti_life",         "--use-antilife"),
    # Logic tweaks: add KI
    ("restore_johnny_race",   "--restore-johnny-race"),
    ("restore_tools",         "--restore-tools"),
    # Logic tweaks: add/remove KI spot
    ("add_bekkler_spot",      "--add-bekkler-spot"),
    ("add_cyrus_grave_spot",  "--add-cyrus-spot"),
    ("add_ozzie_fort_spot",   "--add-ozzie-spot"),
    ("add_race_log_spot",     "--add-racelog-spot"),
    ("vanilla_robo_ribbon",   "--vanilla-robo-ribbon"),
    ("remove_black_omen_spot","--remove-black-omen-spot"),
    # Logic tweaks: spot-neutral
    ("add_sun_keep_spot",     "--add-sunkeep-spot"),
    ("split_arris_dome",      "--split-arris-dome"),
    ("vanilla_desert",        "--vanilla-desert"),
    ("unlocked_skyways",      "--unlocked-skyways"),
    ("rocksanity",            "--rocksanity"),
    # Cosmetics
    ("auto_run",              "--autorun"),
    ("quiet_mode",            "--quiet"),
    ("reduce_flash",          "--reduce-flashes"),
    ("death_peak_alt_music",  "--death-peak-alt-music"),
    ("zenan_alt_music",       "--zenan-alt-music"),
    # Bucket
    ("bucket_list",                  "--bucket-list"),
    ("bucket_objectives_win",        "--bucket-objectives-win"),
    ("bucket_disable_other_go_modes","--bucket-disable-other-go"),
]


def _opt_value(options: Any, attr: str) -> Any:
    """Read an option's `.value` if present, else just the attribute."""
    obj = getattr(options, attr, None)
    if obj is None:
        return None
    return getattr(obj, "value", obj)


def options_to_cli_args(options: Any) -> list[str]:
    """Translate a CTJoTOptions dataclass into cjot-beta argv."""
    args: list[str] = []

    # Game mode + difficulty are required (defaults handled here).
    gm = _opt_value(options, "game_mode") or "Standard"
    args += ["--mode", _GAME_MODE_TO_FLAG.get(gm, "std")]

    idiff = _opt_value(options, "item_difficulty") or "Normal"
    args += ["--item-difficulty", _ITEM_DIFF_TO_FLAG.get(idiff, "normal")]

    ediff = _opt_value(options, "enemy_difficulty")
    args += ["--enemy-difficulty", _ENEMY_DIFF_TO_FLAG.get(int(ediff or 0), "normal")]

    tech = _opt_value(options, "tech_randomization")
    args += ["--tech-order", _TECH_TO_FLAG.get(int(tech or 0), "normal")]

    shop = _opt_value(options, "shop_prices")
    args += ["--shop-prices", _SHOP_TO_FLAG.get(int(shop or 0), "normal")]

    # All boolean toggles.
    for attr, cli_arg in _TOGGLE_FLAGS:
        if _opt_value(options, attr):
            args.append(cli_arg)

    # Bucket numeric ranges (only meaningful with --bucket-list, but
    # always passing them through is harmless).
    n_obj = _opt_value(options, "bucket_num_objectives")
    if n_obj is not None:
        args += ["--bucket-objective-count", str(int(n_obj))]

    n_need = _opt_value(options, "bucket_num_objectives_needed")
    if n_need is not None:
        args += ["--bucket-objective-needed-count", str(int(n_need))]

    # Bucket objective hint strings (up to 8). The CTJoTOptions field is
    # an OptionList of plain strings.
    hints = _opt_value(options, "bucket_objective_hints")
    if hints:
        try:
            hint_list = list(hints)
        except TypeError:
            hint_list = []
        for i, hint in enumerate(hint_list[:8], start=1):
            if hint:
                args += [f"--bucket-objective{i}", str(hint)]

    # Bucket fragments: only fragment_count is a numeric arg; the
    # bucket_fragments toggle is implicit (non-zero count enables it).
    if _opt_value(options, "bucket_fragments"):
        frag_count = _opt_value(options, "fragment_count")
        if frag_count is not None and int(frag_count) > 0:
            # cjot-beta does not have an explicit `--bucket-fragments`
            # switch in its CLI parser; fragment count is the gate.
            # Skipping for now -- if production exposes this we can
            # surface it in a follow-up.
            pass

    # --- Tab ranges ---
    for attr, cli_arg in _TAB_RANGE_FLAGS:
        v = _opt_value(options, attr)
        if v is not None:
            args += [cli_arg, str(int(v))]

    # --- Character names ---
    # Beta enforces a 5-char ASCII limit; we silently truncate / strip
    # so a malformed YAML doesn't blow up generation.
    for attr, cli_arg in _CHAR_NAME_FLAGS:
        raw = _opt_value(options, attr)
        if not raw:
            continue
        safe = "".join(c for c in str(raw) if 32 <= ord(c) < 127)[:5]
        if safe:
            args += [cli_arg, safe]

    # --- Char-rando "can be" matrix ---
    # cjot-beta's --crono-choices etc. take a whitespace-separated list
    # of character names. We emit nothing when the set covers all seven
    # (that's the default) so we don't pollute argv with no-ops.
    full_pool = {"crono", "marle", "lucca", "robo", "frog", "ayla", "magus"}
    for attr, cli_arg in _CHAR_CAN_BE_FLAGS:
        sel = _opt_value(options, attr)
        if sel is None:
            continue
        try:
            sel_set = {str(s).lower() for s in sel}
        except TypeError:
            continue
        sel_set &= full_pool
        if not sel_set or sel_set == full_pool:
            continue
        # Preserve a stable order (canonical CT order) for reproducibility.
        order = ["crono", "marle", "lucca", "robo", "frog", "ayla", "magus"]
        ordered = [c for c in order if c in sel_set]
        args += [cli_arg, " ".join(ordered)]

    # --- Mystery weights / probabilities ---
    # Always emitted. They have no effect unless --mystery is set, and
    # passing the defaults explicitly is harmless.
    for attr, cli_arg in _MYSTERY_WEIGHT_FLAGS:
        v = _opt_value(options, attr)
        if v is not None:
            args += [cli_arg, str(int(v))]

    for attr, cli_arg in _MYSTERY_PROBABILITY_FLAGS:
        v = _opt_value(options, attr)
        if v is None:
            continue
        # Stored as 0-100 percent; cjot-beta CLI takes a float in [0, 1].
        prob = max(0.0, min(1.0, int(v) / 100.0))
        args += [cli_arg, f"{prob:.2f}"]

    return args


# --- Step-4-extended tables: tab ranges, names, char-rando, mystery ---

_TAB_RANGE_FLAGS: list[tuple[str, str]] = [
    ("power_tab_min", "--min-power-tab"),
    ("power_tab_max", "--max-power-tab"),
    ("magic_tab_min", "--min-magic-tab"),
    ("magic_tab_max", "--max-magic-tab"),
    ("speed_tab_min", "--min-speed-tab"),
    ("speed_tab_max", "--max-speed-tab"),
]

_CHAR_NAME_FLAGS: list[tuple[str, str]] = [
    ("crono_name", "--crono-name"),
    ("marle_name", "--marle-name"),
    ("lucca_name", "--lucca-name"),
    ("robo_name",  "--robo-name"),
    ("frog_name",  "--frog-name"),
    ("ayla_name",  "--ayla-name"),
    ("magus_name", "--magus-name"),
    ("epoch_name", "--epoch-name"),
]

_CHAR_CAN_BE_FLAGS: list[tuple[str, str]] = [
    ("crono_can_be", "--crono-choices"),
    ("marle_can_be", "--marle-choices"),
    ("lucca_can_be", "--lucca-choices"),
    ("robo_can_be",  "--robo-choices"),
    ("frog_can_be",  "--frog-choices"),
    ("ayla_can_be",  "--ayla-choices"),
    ("magus_can_be", "--magus-choices"),
]

_MYSTERY_WEIGHT_FLAGS: list[tuple[str, str]] = [
    # Game-mode weights
    ("mystery_mode_std",        "--mystery-mode-std"),
    ("mystery_mode_lw",         "--mystery-mode-lw"),
    ("mystery_mode_loc",        "--mystery-mode-loc"),
    ("mystery_mode_ia",         "--mystery-mode-ia"),
    ("mystery_mode_van",        "--mystery-mode-van"),
    # Difficulty weights
    ("mystery_item_easy",       "--mystery-item-easy"),
    ("mystery_item_norm",       "--mystery-item-norm"),
    ("mystery_item_hard",       "--mystery-item-hard"),
    ("mystery_enemy_norm",      "--mystery-enemy-norm"),
    ("mystery_enemy_hard",      "--mystery-enemy-hard"),
    # Tech / shop weights
    ("mystery_tech_norm",       "--mystery-tech-norm"),
    ("mystery_tech_balanced",   "--mystery-tech-balanced"),
    ("mystery_tech_rand",       "--mystery-tech-rand"),
    ("mystery_prices_norm",     "--mystery-prices-norm"),
    ("mystery_prices_mostly_rand", "--mystery-prices-mostly-rand"),
    ("mystery_prices_rand",     "--mystery-prices-rand"),
    ("mystery_prices_free",     "--mystery-prices-free"),
]

_MYSTERY_PROBABILITY_FLAGS: list[tuple[str, str]] = [
    ("mystery_flag_tab_treasures",   "--mystery-flag-tab-treasures"),
    ("mystery_flag_unlocked_magic",  "--mystery-flag-unlocked-magic"),
    ("mystery_flag_bucket_list",     "--mystery-flag-bucket-list"),
    ("mystery_flag_chronosanity",    "--mystery-flag-chronosanity"),
    ("mystery_flag_boss_rando",      "--mystery-flag-boss-rando"),
    ("mystery_flag_boss_scaling",    "--mystery-flag-boss-scaling"),
    ("mystery_flag_locked_chars",    "--mystery-flag-locked-chars"),
    ("mystery_flag_char_rando",      "--mystery-flag-char-rando"),
    ("mystery_flag_duplicate_chars", "--mystery-flag-duplicate-chars"),
    ("mystery_flag_epoch_fail",      "--mystery-flag-epoch-fail"),
    ("mystery_flag_gear_rando",      "--mystery-flag-gear-rando"),
    ("mystery_flag_heal_rando",      "--mystery-flag-heal-rando"),
]
