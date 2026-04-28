'''
Module to implement some functions for scaling bosses.
'''

from __future__ import annotations

import math

import bossrandotypes as rotypes

import ctenums
from characters import ctpcstats

import enemyai
import enemystats as es
import enemytechdb

import piecewiselinear
import randosettings as rset


def get_hp(level: int):
    '''
    Get Frog's hp at the given level.
    '''
    base_hp = 80
    # hp_growth = bytearray.fromhex('0A 0D 15 0F 30 15 63 0A')
    hp_growth_b = bytearray.fromhex('0A 0C 15 0E 1D 13 63 14')
    hp_growth = ctpcstats.HPGrowth(hp_growth_b)
    return hp_growth.cumulative_growth_at_level(level) + base_hp


def get_mdef(level: int):
    '''
    Return's Frog's magic defense at the given level.
    '''
    # These are Frog's stats (also Crono's)
    BASE_MDEF = 15
    MDEF_GROWTH = 0.46

    return min(BASE_MDEF + (level-1)*MDEF_GROWTH, 100)


def get_phys_def(level: int, max_level):
    '''
    Get a character's expected physical defense at the given level.
    max_level says what the expected maximum level is.
    '''
    BASE_STM = 8
    STM_GROWTH = 1.65

    # In practice, jets has weird armor curve.  You can get about 80% of
    # endgame armor in the early game.
    LV1_ARMOR_DEF = 3 + 5  # hide cap + hide armor
    MID_ARMOR = 45 + 20  # ruby vest + rock helm
    LATE_ARMOR = 75 + 35  # aeon suit + mermaid cap

    # This is calibrated for lv12, lv30 for normal jets cap of 35
    mid_level = round(4*max_level/10)
    late_level = max_level

    pwl = piecewiselinear.PiecewiseLinear(
        (1, LV1_ARMOR_DEF),
        (mid_level, MID_ARMOR),
        (late_level, LATE_ARMOR)
    )

    armor = pwl(level)
    stamina = BASE_STM + STM_GROWTH*(level-1)

    return min(stamina + armor, 256)


def get_eff_phys_hp(level: int, max_level: int = 35):
    '''
    Effective magic hp is hp/(1-phys_reduction).
    '''
    hp = get_hp(level)
    defense = get_phys_def(level, max_level)
    def_reduction = defense/256

    return hp/(1-def_reduction)


def get_eff_mag_hp(level: int):
    '''
    Effective magic hp is hp/(1-mag_reduction).
    '''
    hp = get_hp(level)
    mdef = get_mdef(level)

    mag_reduction = 10*mdef/1024

    return hp/(1-mag_reduction)


def update_son_of_sun_scheme(
        game_mode: rset.GameMode,
        sos_scheme: rotypes.BossScheme,
        new_power: int):
    '''
    Currently only VanillaMode.  Change SoS flame count depending on spot.
    '''
    if game_mode != rset.GameMode.VANILLA_RANDO:
        return

    if new_power < 15:
        flames_removed = 2
    elif new_power < 30:
        flames_removed = 1
    else:
        flames_removed = 0

    # There's a bug where removing more than 2 flames will make any hit
    # on a flame count.  No idea why.
    last_ind = len(sos_scheme.parts)-flames_removed
    del sos_scheme.parts[last_ind:]


# Scale boss depending on stat progression of players
def progressive_scale_stats(
        enemy_id: ctenums.EnemyID,
        stats: es.EnemyStats,
        atk_db: enemytechdb.EnemyAttackDB,
        ai_db: enemyai.EnemyAIDB,
        from_power: int, to_power: int,
        max_power: int = 30,
        scale_hp: bool = True,
        scale_level: bool = True,
        scale_speed: bool = True,
        scale_magic: bool = True,
        scale_mdef: bool = False,
        scale_offense: bool = True,
        scale_defense: bool = False,
        scale_xp: bool = False,
        scale_gp: bool = False,
        scale_tp: bool = False,
        scale_techs: bool = True,
        scale_atk: bool = True) -> es.EnemyStats:

    new_stats = stats.get_copy()

    off_scale_factor = \
        get_eff_phys_hp(to_power, max_power) / \
        get_eff_phys_hp(from_power, max_power)
    mag_scale_factor = get_eff_mag_hp(to_power)/get_eff_mag_hp(from_power)

    if scale_offense:
        new_offense = stats.offense * off_scale_factor
        set_stats_offense(new_stats, new_offense, atk_db,  scale_atk)

    if scale_techs:
        scale_enemy_techs(enemy_id, stats,
                          off_scale_factor, mag_scale_factor,
                          atk_db, ai_db)

    if scale_magic:
        new_stats.magic = \
            int(max(1, min(stats.magic*mag_scale_factor, 0xFF)))

    if scale_level:
        new_stats.level = \
            int(max(1, min(stats.level*mag_scale_factor, 0xFF)))

    # Player attack scales superlinearly.  Atk scales roughly linearly with
    # level, but tech power scales too, we need to do something extra.
    # TODO:  Be a little more accurate and model tech power growth.
    def get_hp_scale_factor(
            from_power: float, to_power: float, max_power: float
    ) -> float:

        # This is super contrived.  It just scales from 1 to about 15 with
        # steeper scaling at the higher end.
        def hp_marker(level: float, max_level: float):
            return 1+15*(level/max_level)**1.5

        # print(f'from, marker: {from_power}, {hp_marker(from_power)}')
        # print(f'  to, marker: {to_power}, {hp_marker(to_power)}')
        if from_power*to_power == 0:
            return 0
        return (
            hp_marker(to_power, max_power) /
            hp_marker(from_power, max_power)
        )

    hp_scale_factor = get_hp_scale_factor(from_power, to_power, max_power)
    if scale_hp:
        new_stats.hp = int(min(stats.hp*hp_scale_factor, 0x7FFF))
        new_stats.hp = max(new_stats.hp, 1)

    # Going to add 1 speed for every  power doubling.
    # At present, the biggest swing is 5 to 40 which is 3 doublings for
    # +3 speed.
    if scale_speed:
        if from_power*to_power == 0:
            add_speed = 0
        else:
            add_speed = round(math.log(to_power/from_power, 2))
            # print(f'{enemy_id}: adding {add_speed} speed')

        new_stats.speed = min(new_stats.speed + add_speed, 16)

    # xp to next level is approximately quadratic.  Scale all rewards
    # quadratically.
    # def xp_mark(level: float):
    #     return 5.62*(level**2) + 11.31*level

    orig_stats = (stats.xp, stats.tp, stats.gp)

    # Observed that gp, tp scale roughly with hp.  So for now we're lazy
    # and reusing that scale factor.
    scales = (hp_scale_factor, hp_scale_factor, hp_scale_factor)
    is_scaled = (scale_xp, scale_tp, scale_gp)
    reward_max = (0x7FFF, 0xFF, 0x7FFF)

    new_stats.xp, new_stats.tp, new_stats.gp = \
        (int(min(orig_stats[i]*scales[i], reward_max[i]))
         if is_scaled[i] else orig_stats[i]
         for i in range(len(orig_stats)))

    return new_stats


def scale_enemy_techs(enemy_id: ctenums.EnemyID,
                      orig_stats: es.EnemyStats,
                      off_scale_factor: float,
                      mag_scale_factor: float,
                      atk_db: enemytechdb.EnemyAttackDB,
                      ai_db: enemyai.EnemyAIDB):
    '''
    If the scale factor is too high, just setting magic/offense is not enough.
    Scale the tech power individually to reach the correct damage numbers.
    '''
    # Need to copy the list.  Otherwise duplicated techs get readded to
    # the list and scaled twice.
    enemy_techs = list(ai_db.scripts[enemy_id].tech_usage)
    # print(f'Scaling techs for {enemy_id}')
    # print(f'  mag scale: {mag_scale_factor}')
    # print(f'  off scale: {off_scale_factor}')
    # print(f'  used: {enemy_techs}')
    # unused_tech_count = len(ai_db.unused_techs)
    # print(f'num unused_techs: {unused_tech_count}')

    new_offense = orig_stats.offense*off_scale_factor
    effective_new_offense = min(new_offense, 0xFF)

    if orig_stats.offense == 0:
        effective_scale_factor = 1
    else:
        effective_scale_factor = effective_new_offense/orig_stats.offense
    overflow_scale = new_offense/0xFF

    for tech_id in enemy_techs:
        tech = atk_db.get_tech(tech_id)
        effect = tech.effect

        new_power = effect.power
        if effect.damage_formula_id == 4:  # physical damage formulas
            if effect.defense_byte == 0x3E:  # Defended by phys def (normal)
                # print(f'Tech {tech_id:02X} is normal')
                if overflow_scale > 1.05:
                    new_power = round(effect.power*overflow_scale)
            elif effect.defense_byte == 0x3C:  # Defended by mdef (weird)
                # print(f'Tech {tech_id:02X} is weird')
                rescale = mag_scale_factor/effective_scale_factor
                new_power = round(effect.power*rescale)
        elif effect.damage_formula_id == 3 and effect.defense_byte == 0x3E:
            # Magic calculated attack defended by physical defense
            rescale = effective_scale_factor/mag_scale_factor
            new_power = round(effect.power*rescale)

        new_power = min(0xFF, new_power)
        if new_power != effect.power:  # Need to scale
            # print(f'Scaling tech {tech_id:02X} from {effect.power} to '
            #       f'{new_power}')

            tech.effect.power = new_power
            usage = ai_db.tech_to_enemy_usage[tech_id]
            new_id = None
            if len(usage) > 1:
                # print(f'\t{usage}')
                # print('\tNeed to duplicate.')
                if ai_db.unused_techs:
                    new_id = ai_db.unused_techs[-1]
                    # print(f'\tNew ID: {new_id:02X}')
                    ai_db.change_tech_in_ai(enemy_id, tech_id, new_id)
                else:
                    print('Warning: No unused techs remaining.')
            else:
                new_id = tech_id

            if new_id is not None:
                atk_db.set_tech(tech, new_id)
            else:
                print(f'Skipped scaling {tech_id} because no unused techs.')


def set_stats_offense(stats: es.EnemyStats,
                      new_offense: float,
                      atk_db: enemytechdb.EnemyAttackDB,
                      scale_atk: bool = True):
    '''
    Sets the given EnemyStats to have the desired new offense.
    If new_offense exceeds the maximum, also scale basic attack 1.
    '''
    if new_offense/0xFF > 1.05:
        remaining_scale = new_offense/0xFF

        # Scale atk 01
        if scale_atk:
            atk_1_id = stats.secondary_attack_id
            atk_1 = atk_db.get_atk(atk_1_id)
            new_power = int(min(atk_1.effect.power * remaining_scale, 0xFF))
            atk_1.effect.power = new_power
            new_atk_id = atk_db.append_attack(atk_1)
            stats.secondary_attack_id = new_atk_id

        stats.offense = 0xFF
    else:
        stats.offense = int(new_offense)


_standard_powers: dict[rotypes.BossID, int] = {
    rotypes.BossID.ATROPOS_XR: 14,
    rotypes.BossID.DALTON_PLUS: 20,
    rotypes.BossID.DRAGON_TANK: 12,
    rotypes.BossID.ELDER_SPAWN: 30,
    rotypes.BossID.FLEA: 14,
    rotypes.BossID.FLEA_PLUS: 14,
    rotypes.BossID.GIGA_GAIA: 20,
    rotypes.BossID.GIGA_MUTANT: 30,
    rotypes.BossID.GUARDIAN: 12,
    rotypes.BossID.GOLEM: 18,
    rotypes.BossID.GOLEM_BOSS: 15,  # Power is only for hp setting
    rotypes.BossID.HECKRAN: 8,
    rotypes.BossID.LAVOS_SPAWN: 18,
    rotypes.BossID.MAGUS_NORTH_CAPE: 30,  # Unsure
    rotypes.BossID.MASA_MUNE: 12,
    rotypes.BossID.MEGA_MUTANT: 30,
    rotypes.BossID.MOTHER_BRAIN: 14,
    rotypes.BossID.MUD_IMP: 25,  # Unsure
    rotypes.BossID.NIZBEL: 14,
    rotypes.BossID.NIZBEL_2: 16,
    rotypes.BossID.RETINITE: 12,
    rotypes.BossID.R_SERIES: 15,
    rotypes.BossID.RUST_TYRANO: 15,
    rotypes.BossID.SLASH_SWORD: 14,
    rotypes.BossID.SUPER_SLASH: 14,
    rotypes.BossID.SON_OF_SUN: 18,
    rotypes.BossID.TERRA_MUTANT: 30,
    rotypes.BossID.TWIN_BOSS: 25,
    rotypes.BossID.YAKRA: 1,
    rotypes.BossID.YAKRA_XIII: 12,
    rotypes.BossID.ZOMBOR: 5,
    # Midbosses
    # rotypes.BossID.MAGUS: None,
    # rotypes.BossID.BLACK_TYRANO: None,
    # End Bosses
    # rotypes.BossID.MAMMON_M: None,
    # rotypes.BossID.LAVOS_SHELL: None,
    # rotypes.BossID.INNER_LAVOS: None,
    # rotypes.BossID.LAVOS_CORE: None,
    # rotypes.BossID.ZEAL: None,
    # rotypes.BossID.ZEAL_2: None,
}

_vr_boss_power_dict = {
    rotypes.BossID.ATROPOS_XR: 20,
    rotypes.BossID.DALTON_PLUS: 30,
    rotypes.BossID.DRAGON_TANK: 12,
    rotypes.BossID.ELDER_SPAWN: 45,
    rotypes.BossID.FLEA: 20,
    rotypes.BossID.FLEA_PLUS: 20,
    rotypes.BossID.GIGA_GAIA: 30,
    rotypes.BossID.GIGA_MUTANT: 45,
    rotypes.BossID.GUARDIAN: 8,
    rotypes.BossID.GOLEM: 25,
    rotypes.BossID.GOLEM_BOSS: 25,  # Power is only for hp setting
    rotypes.BossID.HECKRAN: 10,
    rotypes.BossID.LAVOS_SPAWN: 25,
    rotypes.BossID.MAGUS_NORTH_CAPE: 30,  # Unsure
    rotypes.BossID.MASA_MUNE: 13,
    rotypes.BossID.MEGA_MUTANT: 40,
    rotypes.BossID.MOTHER_BRAIN: 30,
    rotypes.BossID.MUD_IMP: 25,  # Unsure
    rotypes.BossID.NIZBEL: 15,
    rotypes.BossID.NIZBEL_2: 25,
    rotypes.BossID.RETINITE: 40,
    rotypes.BossID.R_SERIES: 15,
    rotypes.BossID.RUST_TYRANO: 40,
    rotypes.BossID.SLASH_SWORD: 20,
    rotypes.BossID.SUPER_SLASH: 20,
    rotypes.BossID.SON_OF_SUN: 50,
    rotypes.BossID.TERRA_MUTANT: 50,
    rotypes.BossID.TWIN_BOSS: 25,
    rotypes.BossID.YAKRA: 1,
    rotypes.BossID.YAKRA_XIII: 40,
    rotypes.BossID.ZOMBOR: 10,
    # Midbosses
    # rotypes.BossID.MAGUS: None,
    # rotypes.BossID.BLACK_TYRANO: None,
    # End Bosses
    # rotypes.BossID.MAMMON_M: None,
    # rotypes.BossID.LAVOS_SHELL: None,
    # rotypes.BossID.INNER_LAVOS: None,
    # rotypes.BossID.LAVOS_CORE: None,
    # rotypes.BossID.ZEAL: None,
    # rotypes.BossID.ZEAL_2: None,
}


def get_spot_power(spot_id: rotypes.BossSpotID,
                   settings: rset.Settings):
    '''
    Get the power of a spot.  This only exists because the Epoch Reborn spot
    should not have Dalton's power.  It needs to be a mid-game spot.
    '''
    if settings.game_mode == rset.GameMode.VANILLA_RANDO:
        epoch_spot_power = 25  # ?
    else:
        epoch_spot_power = 15  # ?

    default_assignment = rotypes.get_default_boss_assignment()

    if spot_id == rotypes.BossSpotID.EPOCH_REBORN:
        return epoch_spot_power

    return get_base_boss_power(default_assignment[spot_id], settings)


def get_standard_boss_power(boss_id: rotypes.BossID) -> int:
    return _standard_powers[boss_id]


def get_base_boss_power(boss_id: rotypes.BossID,
                        settings: rset.Settings):
    '''
    Determine the power of a boss in its default location.
    '''
    if settings.game_mode == rset.GameMode.VANILLA_RANDO:
        return _vr_boss_power_dict[boss_id]

    return _standard_powers[boss_id]


def scale_boss_scheme_progessive(
        scheme: rotypes.BossScheme,
        from_power: int,
        to_power: int,
        stat_dict: dict[ctenums.EnemyID, es.EnemyStats],
        atk_db: enemytechdb.EnemyAttackDB,
        ai_db: enemyai.EnemyAIDB,
        game_mode: rset.GameMode = rset.GameMode.STANDARD
) -> dict[ctenums.EnemyID, es.EnemyStats]:
    '''
    Returns a dictionary of EnemyID -> EnemyStats with the scaled stats
    for each part in the scheme.
    '''

    if game_mode == rset.GameMode.VANILLA_RANDO:
        max_power = 50
    else:
        max_power = 35

    scaled_stats = {}
    for part in list(set(scheme.parts)):
        scale_hp = scale_offense = True
        if part.enemy_id in (ctenums.EnemyID.SON_OF_SUN_EYE,
                             ctenums.EnemyID.SON_OF_SUN_FLAME):
            scale_hp = False
            scale_offense = False

        scaled_stats[part.enemy_id] = \
            progressive_scale_stats(
                part.enemy_id, stat_dict[part.enemy_id],
                atk_db, ai_db, from_power, to_power, max_power,
                scale_hp=scale_hp, scale_offense=scale_offense,
                scale_xp=False, scale_tp=False, scale_gp=False
            )

    return scaled_stats
