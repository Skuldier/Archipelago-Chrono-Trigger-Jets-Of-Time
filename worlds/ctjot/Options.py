from dataclasses import dataclass

from Options import (
    Choice,
    DefaultOnToggle,
    FreeText,
    OptionDict,
    OptionList,
    OptionSet,
    PerGameCommonOptions,
    Range,
    TextChoice,
    Toggle,
)


# Pool of valid CT character identities used by the char-rando "can be"
# matrix below. Matches the set in beta.ctjot.com's UI.
_CT_CHAR_POOL = frozenset({
    "crono", "marle", "lucca", "robo", "frog", "ayla", "magus",
})


class Locations(OptionList):
    """List of locations chosen by the randomizer to hold key items"""
    display_name = "locations"


class RegionList(OptionDict):
    """List of regions and their locations"""
    display_name = "regions"


class CharLocations(OptionList):
    """Character recruitment locations"""
    display_name = "char locations"


class Items(OptionList):
    """List of key items to be randomized"""
    display_name = "items"


class Rules(OptionDict):
    """Access rules for the chosen locations"""
    display_name = "rules"


class Victory(OptionList):
    """Victory conditions for the chosen game mode"""
    display_name = "victory"


class GameMode(FreeText):
    """Game mode chosen by the user."""
    display_name = "Game Mode"


class ItemDifficulty(FreeText):
    """Game mode chosen by the user."""
    display_name = "Item Difficulty"


class TabTreasures(Toggle):
    """All treasures are replaced with tabs."""
    display_name = "All treasures are tabs"


class BucketFragments(Toggle):
    """Enable the placement of Bucket Fragments."""
    display_name = "Enable Bucket Fragments"


class FragmentCount(Range):
    """Total number of bucket fragments to place"""
    range_start = 0
    range_end = 100
    default = 15
    display_name = "Fragment Count"


# Beta branch: bucket-list (objective-based go mode) replaces fragments when enabled.
# These are passthrough options populated by the web generator; apworld honors
# bucket_list by suppressing fragment injection, but all objective selection /
# victory-rule encoding lives in the web generator's emitted `victory` list.
class BucketList(Toggle):
    """Enable Bucket List objective mode."""
    display_name = "Enable Bucket List"


class BucketObjectivesWin(Toggle):
    """If set, completing the required number of objectives wins directly
    (instead of unlocking the End of Time bucket to Lavos)."""
    display_name = "Objectives Auto-Win"


class BucketDisableOtherGoModes(Toggle):
    """Disable all other go modes; only the Bucket counts as victory."""
    display_name = "Disable Other Go Modes"


class BucketNumObjectives(Range):
    """Number of objectives in the pool."""
    range_start = 1
    range_end = 8
    default = 5
    display_name = "Number of Objectives"


class BucketNumObjectivesNeeded(Range):
    """Number of objectives that must be completed."""
    range_start = 1
    range_end = 8
    default = 4
    display_name = "Objectives Needed"


class BucketObjectiveHints(OptionList):
    """Per-objective specification strings (beta bucket-list `hints` list)."""
    display_name = "Objective Hints"


# ------------------------------------------------------------------
# Step 4: cjot-beta CLI flag passthroughs.
#
# These options expose the most-used parts of beta.ctjot.com's flag
# surface as YAML-configurable knobs. CTJoTWorld.generate_output() runs
# them through worlds.ctjot.flag_translation.options_to_cli_args() which
# converts each into the matching `--<flag>` argument the cjot-beta
# randomizer understands. Flag names below are the apworld YAML keys;
# the corresponding randomizer flags live in flag_translation.py.
# ------------------------------------------------------------------


# --- General difficulty / structure ---

class EnemyDifficulty(TextChoice):
    """Enemy difficulty: normal or hard."""
    display_name = "Enemy Difficulty"
    option_normal = 0
    option_hard = 1
    default = 0


class TechRandomization(TextChoice):
    """Tech learning order: normal, balanced, fully random.

    NOTE: AP reserves the value name `random` for built-in randomization,
    so we use `fully_random` here. The translator maps this back to
    cjot-beta's `random` flag value.
    """
    display_name = "Tech Randomization"
    option_normal = 0
    option_balanced = 1
    option_fully_random = 2
    default = 0


class ShopPrices(TextChoice):
    """Shop pricing: normal, fully random, mostly random, free.

    NOTE: AP reserves `random`, so we use `fully_random` for that value.
    """
    display_name = "Shop Prices"
    option_normal = 0
    option_fully_random = 1
    option_mostly_random = 2
    option_free = 3
    default = 0


# --- Major game-shape toggles ---

class DisableGlitches(DefaultOnToggle):
    """Disable known game-breaking glitches (vanilla beta default ON)."""
    display_name = "Disable Glitches"


class BossScaling(Toggle):
    """Bosses scale to expected progression."""
    display_name = "Boss Scaling"


class EarlyPendant(Toggle):
    """Pendant charges early so sealed chests/doors are reachable sooner."""
    display_name = "Early Pendant Charge"


class UnlockedMagic(Toggle):
    """All characters can learn magic from the start (no Spekkio gate)."""
    display_name = "Unlocked Magic"


class Chronosanity(Toggle):
    """Every chest in the game becomes a possible KI location."""
    display_name = "Chronosanity"


class RandomizeHealing(Toggle):
    """Randomize healing-item effects."""
    display_name = "Randomize Healing Items"


class MysterySeed(Toggle):
    """Mystery seed: flags chosen randomly from configured probabilities."""
    display_name = "Mystery Seed"


class RandomizeBosses(Toggle):
    """Boss locations are shuffled."""
    display_name = "Randomize Bosses"


class Zeal2LastBoss(Toggle):
    """Zeal 2 counts as defeating the last boss."""
    display_name = "Zeal 2 Counts As Last Boss"


class LockedCharacters(Toggle):
    """Characters lock until specific story events."""
    display_name = "Locked Characters"


class RandomizeCharacters(Toggle):
    """Characters at recruit spots are shuffled."""
    display_name = "Randomize Characters"


class RandomizeGear(Toggle):
    """Randomize weapon/armor/accessory effects."""
    display_name = "Randomize Gear"


class EpochFail(Toggle):
    """Epoch flight requires the JetsOfTime KI from Dalton."""
    display_name = "Epoch Fail"


# --- Character rando sub-options ---

class DuplicateCharacters(Toggle):
    """Allow duplicate characters in the recruit pool."""
    display_name = "Duplicate Characters"


class DuplicateDualTechs(Toggle):
    """Each duplicate character learns its own dual techs."""
    display_name = "Duplicate Dual Techs"


# --- Boss rando sub-options ---

class LegacyBossPlacement(Toggle):
    """Use the legacy random-boss placement algorithm."""
    display_name = "Legacy Boss Placement"


class BossSpotHPs(Toggle):
    """Bosses keep the HP of their original spot, not their type."""
    display_name = "Boss Spot HPs"


# --- Quality of Life ---

class SightscopeAlwaysOn(Toggle):
    """All enemies show their HP without needing the Sightscope."""
    display_name = "Sightscope Always On"


class BossSightscope(Toggle):
    """Sightscope works on bosses."""
    display_name = "Boss Sightscope"


class FastTabs(Toggle):
    """Tabs apply instantly with no animation."""
    display_name = "Fast Tabs"


class FreeMenuGlitch(Toggle):
    """Menu can be opened anytime (skips some triggers)."""
    display_name = "Free Menu Glitch"


class VisibleTechlist(Toggle):
    """All techs visible in the menu, even unlearned ones."""
    display_name = "Visible Techlist"


class APClassificationMarkers(Toggle):
    """Color-code chests by Archipelago item classification.

    When ON, the apworld injects a colored NPC marker above every
    chest in your ROM, keyed off the AP item placed there:
        Red    = trap
        Purple = progression
        Blue   = useful (light-blue glow)
        Brown  = filler
    Items belonging to OTHER players are colored by THAT player's
    classification — so progression for someone else still shows up
    as purple in your world."""
    display_name = "AP Classification Markers"
    default = 1


class ItemArrivalTextbox(Toggle):
    """Show an in-game textbox when an AP item arrives in your inventory.

    When ON, the receive hook displays a "* AP Item Received *" textbox
    after each item delivered from the multiworld queue. Up to 4
    textboxes may pop up in a row on a busy map transition (one per
    item drained). Default is OFF (silent delivery, matches pre-1.4.11
    behavior)."""
    display_name = "Item Arrival Textbox"


# --- Extra flags ---

class StartersSufficient(Toggle):
    """The starting two characters are guaranteed to be enough for go-mode."""
    display_name = "Starters Sufficient"


class TechDamageRando(Toggle):
    """Randomize tech damage values."""
    display_name = "Tech Damage Rando"


class ElementRando(Toggle):
    """Randomize tech elements."""
    display_name = "Element Rando"


class TackleOnHit(Toggle):
    """Robo's Tackle uses on-hit weapon effects."""
    display_name = "Tackle On-Hit Effects"


class UseAntiLife(Toggle):
    """Replace Magus's Black Hole with Anti-Life for tech rando."""
    display_name = "Use Anti-Life"


# --- Logic Tweaks: Add Key Item ---

class RestoreJohnnyRace(Toggle):
    """Re-enable Johnny's Race; Bike Key gates Lab 32."""
    display_name = "Restore Johnny Race"


class RestoreTools(Toggle):
    """Tools fix the Northern Ruins."""
    display_name = "Restore Tools"


# --- Logic Tweaks: Add/Remove Key Item Spot ---

class AddBekklerSpot(Toggle):
    """Bekkler's Lab gives a KI when paid with C. Trigger."""
    display_name = "Add Bekkler Spot"


class AddCyrusGraveSpot(Toggle):
    """Frog at Cyrus's Grave yields a KI."""
    display_name = "Add Cyrus Grave Spot"


class AddOzzieFortSpot(Toggle):
    """Ozzie's Fort yields a KI on completion."""
    display_name = "Add Ozzie's Fort Spot"


class AddRaceLogSpot(Toggle):
    """Race Log chest yields a KI."""
    display_name = "Add Race Log Spot"


class VanillaRoboRibbon(Toggle):
    """Restore Robo's Ribbon stat boost from AtroposXR / Geno Dome."""
    display_name = "Vanilla Robo Ribbon"


class RemoveBlackOmenSpot(Toggle):
    """Remove the Black Omen Terra rock as a KI location."""
    display_name = "Remove Black Omen Spot"


# --- Logic Tweaks: Spot-Neutral ---

class AddSunKeepSpot(Toggle):
    """Sun Keep 2300 yields a KI when given the Moon Stone."""
    display_name = "Add Sun Keep Spot"


class SplitArrisDome(Toggle):
    """Arris Dome corpse + Doan turn-in are two separate KI spots."""
    display_name = "Split Arris Dome"


class VanillaDesert(Toggle):
    """Sunken Desert only opens after talking to the plant lady."""
    display_name = "Vanilla Desert"


class UnlockedSkyways(Toggle):
    """Zeal skyways are unlocked from the start."""
    display_name = "Unlocked Skyways"


class Rocksanity(Toggle):
    """Rocks become KIs and may be found in standard KI locations."""
    display_name = "Rocksanity"


# --- Cosmetics ---

class AutoRun(Toggle):
    """Run automatically; press the run button to walk."""
    display_name = "Auto-run"


class QuietMode(Toggle):
    """Disable music (sound effects unaffected)."""
    display_name = "Quiet Mode"


class ReduceFlash(Toggle):
    """Disable most flashing effects."""
    display_name = "Reduce Flashing"


class DeathPeakAltMusic(Toggle):
    """Use the Singing Mountain track on Death Peak."""
    display_name = "Death Peak Alt Music"


class ZenanAltMusic(Toggle):
    """Use the alternate battle theme for Zenan Bridge."""
    display_name = "Zenan Alt Music"


# ------------------------------------------------------------------
# Tab min/max ranges
# ------------------------------------------------------------------

class PowerTabMin(Range):
    """Lower bound for Power Tab values."""
    display_name = "Power Tab Min"
    range_start = 1
    range_end = 9
    default = 1


class PowerTabMax(Range):
    """Upper bound for Power Tab values."""
    display_name = "Power Tab Max"
    range_start = 1
    range_end = 9
    default = 1


class MagicTabMin(Range):
    """Lower bound for Magic Tab values."""
    display_name = "Magic Tab Min"
    range_start = 1
    range_end = 9
    default = 1


class MagicTabMax(Range):
    """Upper bound for Magic Tab values."""
    display_name = "Magic Tab Max"
    range_start = 1
    range_end = 9
    default = 1


class SpeedTabMin(Range):
    """Lower bound for Speed Tab values."""
    display_name = "Speed Tab Min"
    range_start = 1
    range_end = 9
    default = 1


class SpeedTabMax(Range):
    """Upper bound for Speed Tab values."""
    display_name = "Speed Tab Max"
    range_start = 1
    range_end = 9
    default = 1


# ------------------------------------------------------------------
# Character names (5 chars max each, beta enforces in-game)
# ------------------------------------------------------------------

class CronoName(FreeText):
    """Crono's display name (max 5 chars)."""
    display_name = "Crono name"
    default = "Crono"


class MarleName(FreeText):
    """Marle's display name (max 5 chars)."""
    display_name = "Marle name"
    default = "Marle"


class LuccaName(FreeText):
    """Lucca's display name (max 5 chars)."""
    display_name = "Lucca name"
    default = "Lucca"


class RoboName(FreeText):
    """Robo's display name (max 5 chars)."""
    display_name = "Robo name"
    default = "Robo"


class FrogName(FreeText):
    """Frog's display name (max 5 chars)."""
    display_name = "Frog name"
    default = "Frog"


class AylaName(FreeText):
    """Ayla's display name (max 5 chars)."""
    display_name = "Ayla name"
    default = "Ayla"


class MagusName(FreeText):
    """Magus's display name (max 5 chars)."""
    display_name = "Magus name"
    default = "Magus"


class EpochName(FreeText):
    """Epoch's display name (max 5 chars)."""
    display_name = "Epoch name"
    default = "Epoch"


# ------------------------------------------------------------------
# Char-rando "can be" matrix.
# Each row says which character models that role can be assigned in
# Character Rando. Default: all seven, i.e. fully unrestricted.
# ------------------------------------------------------------------

class _CharCanBe(OptionSet):
    """Subset of character names this slot may be assigned to."""
    valid_keys = _CT_CHAR_POOL
    default = frozenset(_CT_CHAR_POOL)


class CronoCanBe(_CharCanBe):
    display_name = "Crono can be"


class MarleCanBe(_CharCanBe):
    display_name = "Marle can be"


class LuccaCanBe(_CharCanBe):
    display_name = "Lucca can be"


class RoboCanBe(_CharCanBe):
    display_name = "Robo can be"


class FrogCanBe(_CharCanBe):
    display_name = "Frog can be"


class AylaCanBe(_CharCanBe):
    display_name = "Ayla can be"


class MagusCanBe(_CharCanBe):
    display_name = "Magus can be"


# ------------------------------------------------------------------
# Mystery Seed sub-options.
#
# Only meaningful when MysterySeed is on. All weights are non-negative
# integers; per-flag probabilities are stored as 0-100 and converted to
# 0.0-1.0 floats by the translator (cjot-beta's CLI takes floats).
# ------------------------------------------------------------------

# --- Game-mode weights ---

class _MysteryWeight(Range):
    range_start = 0
    range_end = 100
    default = 0


class MysteryModeStd(_MysteryWeight):
    """Mystery: relative weight for picking Standard mode."""
    display_name = "Mystery: Standard weight"
    default = 75


class MysteryModeLw(_MysteryWeight):
    """Mystery: relative weight for picking Lost Worlds mode."""
    display_name = "Mystery: Lost Worlds weight"
    default = 25


class MysteryModeLoc(_MysteryWeight):
    """Mystery: relative weight for picking Legacy of Cyrus mode."""
    display_name = "Mystery: Legacy of Cyrus weight"
    default = 0


class MysteryModeIa(_MysteryWeight):
    """Mystery: relative weight for picking Ice Age mode."""
    display_name = "Mystery: Ice Age weight"
    default = 0


class MysteryModeVan(_MysteryWeight):
    """Mystery: relative weight for picking Vanilla Rando mode."""
    display_name = "Mystery: Vanilla Rando weight"
    default = 0


# --- Difficulty weights ---

class MysteryItemEasy(_MysteryWeight):
    """Mystery: relative weight for Easy item difficulty."""
    display_name = "Mystery: Item Easy weight"
    default = 15


class MysteryItemNorm(_MysteryWeight):
    """Mystery: relative weight for Normal item difficulty."""
    display_name = "Mystery: Item Normal weight"
    default = 70


class MysteryItemHard(_MysteryWeight):
    """Mystery: relative weight for Hard item difficulty."""
    display_name = "Mystery: Item Hard weight"
    default = 15


class MysteryEnemyNorm(_MysteryWeight):
    """Mystery: relative weight for Normal enemy difficulty."""
    display_name = "Mystery: Enemy Normal weight"
    default = 75


class MysteryEnemyHard(_MysteryWeight):
    """Mystery: relative weight for Hard enemy difficulty."""
    display_name = "Mystery: Enemy Hard weight"
    default = 25


# --- Tech / shop weights ---

class MysteryTechNorm(_MysteryWeight):
    """Mystery: relative weight for Normal tech order."""
    display_name = "Mystery: Tech Normal weight"
    default = 10


class MysteryTechBalanced(_MysteryWeight):
    """Mystery: relative weight for Balanced Random tech order."""
    display_name = "Mystery: Tech Balanced weight"
    default = 10


class MysteryTechRand(_MysteryWeight):
    """Mystery: relative weight for fully Random tech order."""
    display_name = "Mystery: Tech Random weight"
    default = 80


class MysteryPricesNorm(_MysteryWeight):
    """Mystery: relative weight for Normal shop prices."""
    display_name = "Mystery: Prices Normal weight"
    default = 70


class MysteryPricesMostlyRand(_MysteryWeight):
    """Mystery: relative weight for Mostly Random shop prices."""
    display_name = "Mystery: Prices Mostly-Random weight"
    default = 10


class MysteryPricesRand(_MysteryWeight):
    """Mystery: relative weight for fully Random shop prices."""
    display_name = "Mystery: Prices Random weight"
    default = 10


class MysteryPricesFree(_MysteryWeight):
    """Mystery: relative weight for Free shop prices."""
    display_name = "Mystery: Prices Free weight"
    default = 10


# --- Per-flag probabilities ---
# Stored as 0-100 percentages; translator divides by 100 to feed beta's
# float-style CLI args.

class _MysteryProbability(Range):
    range_start = 0
    range_end = 100


class MysteryFlagTabTreasures(_MysteryProbability):
    """Mystery: chance the Tab Treasures flag is rolled."""
    display_name = "Mystery: P(Tab Treasures)"
    default = 10


class MysteryFlagUnlockedMagic(_MysteryProbability):
    """Mystery: chance the Unlocked Magic flag is rolled."""
    display_name = "Mystery: P(Unlocked Magic)"
    default = 50


class MysteryFlagBucketList(_MysteryProbability):
    """Mystery: chance the Bucket List flag is rolled."""
    display_name = "Mystery: P(Bucket List)"
    default = 15


class MysteryFlagChronosanity(_MysteryProbability):
    """Mystery: chance the Chronosanity flag is rolled."""
    display_name = "Mystery: P(Chronosanity)"
    default = 50


class MysteryFlagBossRando(_MysteryProbability):
    """Mystery: chance the Boss Rando flag is rolled."""
    display_name = "Mystery: P(Boss Rando)"
    default = 50


class MysteryFlagBossScaling(_MysteryProbability):
    """Mystery: chance the Boss Scaling flag is rolled."""
    display_name = "Mystery: P(Boss Scaling)"
    default = 10


class MysteryFlagLockedChars(_MysteryProbability):
    """Mystery: chance the Locked Characters flag is rolled."""
    display_name = "Mystery: P(Locked Characters)"
    default = 25


class MysteryFlagCharRando(_MysteryProbability):
    """Mystery: chance the Character Rando flag is rolled."""
    display_name = "Mystery: P(Character Rando)"
    default = 50


class MysteryFlagDuplicateChars(_MysteryProbability):
    """Mystery: chance the Duplicate Characters flag is rolled."""
    display_name = "Mystery: P(Duplicate Characters)"
    default = 25


class MysteryFlagEpochFail(_MysteryProbability):
    """Mystery: chance the Epoch Fail flag is rolled."""
    display_name = "Mystery: P(Epoch Fail)"
    default = 50


class MysteryFlagGearRando(_MysteryProbability):
    """Mystery: chance the Gear Rando flag is rolled."""
    display_name = "Mystery: P(Gear Rando)"
    default = 25


class MysteryFlagHealRando(_MysteryProbability):
    """Mystery: chance the Heal Rando flag is rolled."""
    display_name = "Mystery: P(Heal Rando)"
    default = 25


@dataclass
class CTJoTOptions(PerGameCommonOptions):
    game_mode: GameMode
    item_difficulty: ItemDifficulty
    enemy_difficulty: EnemyDifficulty
    tech_randomization: TechRandomization
    shop_prices: ShopPrices
    tab_treasures: TabTreasures
    # General flags
    disable_glitches: DisableGlitches
    boss_scaling: BossScaling
    early_pendant: EarlyPendant
    unlocked_magic: UnlockedMagic
    chronosanity: Chronosanity
    randomize_healing: RandomizeHealing
    mystery_seed: MysterySeed
    randomize_bosses: RandomizeBosses
    zeal_2_last_boss: Zeal2LastBoss
    locked_characters: LockedCharacters
    randomize_characters: RandomizeCharacters
    randomize_gear: RandomizeGear
    epoch_fail: EpochFail
    # Character rando
    duplicate_characters: DuplicateCharacters
    duplicate_dual_techs: DuplicateDualTechs
    # Boss rando
    legacy_boss_placement: LegacyBossPlacement
    boss_spot_hps: BossSpotHPs
    # Quality of life
    sightscope_always_on: SightscopeAlwaysOn
    boss_sightscope: BossSightscope
    fast_tabs: FastTabs
    free_menu_glitch: FreeMenuGlitch
    visible_techlist: VisibleTechlist
    ap_classification_markers: APClassificationMarkers
    item_arrival_textbox: ItemArrivalTextbox
    # Extra
    starters_sufficient: StartersSufficient
    tech_damage_rando: TechDamageRando
    element_rando: ElementRando
    tackle_on_hit: TackleOnHit
    use_anti_life: UseAntiLife
    # Logic tweaks: add KI
    restore_johnny_race: RestoreJohnnyRace
    restore_tools: RestoreTools
    # Logic tweaks: add/remove KI spot
    add_bekkler_spot: AddBekklerSpot
    add_cyrus_grave_spot: AddCyrusGraveSpot
    add_ozzie_fort_spot: AddOzzieFortSpot
    add_race_log_spot: AddRaceLogSpot
    vanilla_robo_ribbon: VanillaRoboRibbon
    remove_black_omen_spot: RemoveBlackOmenSpot
    # Logic tweaks: spot-neutral
    add_sun_keep_spot: AddSunKeepSpot
    split_arris_dome: SplitArrisDome
    vanilla_desert: VanillaDesert
    unlocked_skyways: UnlockedSkyways
    rocksanity: Rocksanity
    # Cosmetics
    auto_run: AutoRun
    quiet_mode: QuietMode
    reduce_flash: ReduceFlash
    death_peak_alt_music: DeathPeakAltMusic
    zenan_alt_music: ZenanAltMusic
    # Tab ranges
    power_tab_min: PowerTabMin
    power_tab_max: PowerTabMax
    magic_tab_min: MagicTabMin
    magic_tab_max: MagicTabMax
    speed_tab_min: SpeedTabMin
    speed_tab_max: SpeedTabMax
    # Character names
    crono_name: CronoName
    marle_name: MarleName
    lucca_name: LuccaName
    robo_name: RoboName
    frog_name: FrogName
    ayla_name: AylaName
    magus_name: MagusName
    epoch_name: EpochName
    # Char-rando "can be" matrix
    crono_can_be: CronoCanBe
    marle_can_be: MarleCanBe
    lucca_can_be: LuccaCanBe
    robo_can_be: RoboCanBe
    frog_can_be: FrogCanBe
    ayla_can_be: AylaCanBe
    magus_can_be: MagusCanBe
    # Mystery seed sub-options (only effective when mystery_seed is on)
    mystery_mode_std: MysteryModeStd
    mystery_mode_lw: MysteryModeLw
    mystery_mode_loc: MysteryModeLoc
    mystery_mode_ia: MysteryModeIa
    mystery_mode_van: MysteryModeVan
    mystery_item_easy: MysteryItemEasy
    mystery_item_norm: MysteryItemNorm
    mystery_item_hard: MysteryItemHard
    mystery_enemy_norm: MysteryEnemyNorm
    mystery_enemy_hard: MysteryEnemyHard
    mystery_tech_norm: MysteryTechNorm
    mystery_tech_balanced: MysteryTechBalanced
    mystery_tech_rand: MysteryTechRand
    mystery_prices_norm: MysteryPricesNorm
    mystery_prices_mostly_rand: MysteryPricesMostlyRand
    mystery_prices_rand: MysteryPricesRand
    mystery_prices_free: MysteryPricesFree
    mystery_flag_tab_treasures: MysteryFlagTabTreasures
    mystery_flag_unlocked_magic: MysteryFlagUnlockedMagic
    mystery_flag_bucket_list: MysteryFlagBucketList
    mystery_flag_chronosanity: MysteryFlagChronosanity
    mystery_flag_boss_rando: MysteryFlagBossRando
    mystery_flag_boss_scaling: MysteryFlagBossScaling
    mystery_flag_locked_chars: MysteryFlagLockedChars
    mystery_flag_char_rando: MysteryFlagCharRando
    mystery_flag_duplicate_chars: MysteryFlagDuplicateChars
    mystery_flag_epoch_fail: MysteryFlagEpochFail
    mystery_flag_gear_rando: MysteryFlagGearRando
    mystery_flag_heal_rando: MysteryFlagHealRando
    # Bucket
    bucket_fragments: BucketFragments
    fragment_count: FragmentCount
    bucket_list: BucketList
    bucket_objectives_win: BucketObjectivesWin
    bucket_disable_other_go_modes: BucketDisableOtherGoModes
    bucket_num_objectives: BucketNumObjectives
    bucket_num_objectives_needed: BucketNumObjectivesNeeded
    bucket_objective_hints: BucketObjectiveHints
    # YAML-driven structural data (still needed: items/regions/etc.)
    items: Items
    region_list: RegionList
    char_locations: CharLocations
    rules: Rules
    victory: Victory
