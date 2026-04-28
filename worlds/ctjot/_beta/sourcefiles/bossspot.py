from __future__ import annotations

from dataclasses import dataclass
from enum import auto

import bossrandotypes as rotypes
import bossscaler
import enemystats
import ctenums

import randosettings as rset
import randoconfig as cfg


class BossSpotID(ctenums.StrIntEnum):
    MANORIA_CATHERDAL = auto()
    HECKRAN_CAVE = auto()
    DENADORO_MTS = auto()
    ZENAN_BRIDGE = auto()
    REPTITE_LAIR = auto()
    MAGUS_CASTLE_FLEA = auto()
    MAGUS_CASTLE_SLASH = auto()
    GIANTS_CLAW = auto()
    TYRANO_LAIR_NIZBEL = auto()
    ZEAL_PALACE = auto()
    DEATH_PEAK = auto()
    BLACK_OMEN_GIGA_MUTANT = auto()
    BLACK_OMEN_TERRA_MUTANT = auto()
    BLACK_OMEN_ELDER_SPAWN = auto()
    KINGS_TRIAL = auto()
    OZZIES_FORT_FLEA_PLUS = auto()
    OZZIES_FORT_SUPER_SLASH = auto()
    SUN_PALACE = auto()
    SUNKEN_DESERT = auto()
    OCEAN_PALACE_TWIN_GOLEM = auto()
    GENO_DOME = auto()
    MT_WOE = auto()
    ARRIS_DOME = auto()
    FACTORY_RUINS = auto()
    PRISON_CATWALKS = auto()
    EPOCH_REBORN = auto()


@dataclass
class SpotReward:
    xp: int = 0
    tp: int = 0
    gp: int = 0


def get_spot_reward_dict(
        settings: rset.Settings,
        config: cfg.RandoConfig
        ) -> dict[rotypes.BossSpotID, SpotReward]:
    '''
    Get the xp/tp/gp reward for each boss spot
    '''
    reward_dict = {}
    stat_dict = config.enemy_dict

    for boss_spot, boss_id in rotypes.get_default_boss_assignment().items():
        scheme = config.boss_data_dict[boss_id]
        xp = sum(stat_dict[part.enemy_id].xp for part in scheme.parts)
        tp = sum(stat_dict[part.enemy_id].tp for part in scheme.parts)
        gp = sum(stat_dict[part.enemy_id].gp for part in scheme.parts)

        reward_dict[boss_spot] = SpotReward(xp, tp, gp)

    return reward_dict


def distribute_rewards(
        spot_reward: SpotReward,
        scheme: rotypes.BossScheme,
        stat_dict: dict[ctenums.EnemyID, enemystats.EnemyStats]
        ):
    '''
    Distribute spot_reward over the parts of scheme with the same distribution.
    '''
    # print(f'Distributing {spot_reward} to {scheme}')
    total_xp = sum(stat_dict[part.enemy_id].xp for part in scheme.parts)
    total_tp = sum(stat_dict[part.enemy_id].tp for part in scheme.parts)
    total_gp = sum(stat_dict[part.enemy_id].gp for part in scheme.parts)

    part_ids = [part.enemy_id for part in scheme.parts]
    for part_id in set(part_ids):
        if total_xp == 0:
            xp_share = 1 / len(part_ids)
        else:
            xp_share = stat_dict[part_id].xp/total_xp

        if total_tp == 0:
            tp_share = 1 / len(part_ids)
        else:
            tp_share = stat_dict[part_id].tp/total_tp

        if total_gp == 0:
            gp_share = 1 / len(part_ids)
        else:
            gp_share = stat_dict[part_id].gp/total_gp

        new_xp = round(xp_share*spot_reward.xp)
        new_tp = round(tp_share*spot_reward.tp)
        new_gp = round(gp_share*spot_reward.gp)
        # print(f'\t{part_id}: xp={new_xp}, tp={new_tp}, gp={new_gp}')
        stat_dict[part_id].xp = new_xp
        stat_dict[part_id].tp = new_tp
        stat_dict[part_id].gp = new_gp

    # TODO:  Total may be off by 1.  Fix if so desired.


def get_spot_hp_dict(settings: rset.Settings, config: cfg.RandoConfig):

    hp_dict = get_initial_hp_dict(settings, config)
    spot_hp_dict = {}
    
    default_assignment = rotypes.get_default_boss_assignment()
    for spot in config.boss_assign_dict:
        default_boss = default_assignment[spot]
        scheme = config.boss_data_dict[default_boss]
        spot_hp_dict[spot] = get_boss_total_hp(scheme, hp_dict)

    return spot_hp_dict

def get_initial_hp_dict(settings: rset.Settings, config: cfg.RandoConfig):
    hp_dict = {
        part.enemy_id: config.enemy_dict[part.enemy_id].hp
        for boss_id in list(rotypes.BossID)
        for part in config.boss_data_dict[boss_id].parts
    }

    if rset.GameFlags.BOSS_SCALE in settings.gameflags:
        # Gather boss HP as though it were the default boss assignment
        # to correctly record spot HPs.

        # That is, if Reptite Lair's boss is rank 3, we want the boss
        # to have the HP of a rank 3 Nizbel.
        default_assignment = rotypes.get_default_boss_assignment()
        current_assignment = dict(config.boss_assign_dict)

        for spot in current_assignment:
            current_boss_id = current_assignment[spot]

            if current_boss_id in config.boss_rank_dict:
                rank = config.boss_rank_dict[current_boss_id]
            else:
                rank = 0

            orig_boss_id = default_assignment[spot]
            ranked_stats = bossscaler.get_ranked_boss_stats(
                orig_boss_id, rank, config
            )

            for part in ranked_stats:
                hp_dict[part] = ranked_stats[part].hp

    return hp_dict


def get_scaled_hp_dict(
        from_boss: rotypes.BossScheme,
        to_boss: rotypes.BossScheme,
        hp_dict: dict[ctenums.EnemyID, int]
) -> dict[ctenums.EnemyID, int]:
    boss_total_hp = get_boss_total_hp(from_boss, hp_dict)
    scaled_hp_dict = get_part_new_hps(to_boss, hp_dict, boss_total_hp)

    return scaled_hp_dict


def distribute_hp(
        from_scheme: rotypes.BossScheme,
        to_scheme: rotypes.BossScheme,
        hp_dict: dict[ctenums.EnemyID, int],
        scaled_stats: dict[ctenums.EnemyID, enemystats.EnemyStats]
        ):
    total_hp = get_boss_total_hp(from_scheme, hp_dict)
    scaled_hp_dict = get_part_new_hps(to_scheme, hp_dict, total_hp)

    for part in scaled_hp_dict:
        scaled_stats[part].hp = scaled_hp_dict[part]


def get_boss_total_hp(
        boss_scheme: rotypes.BossScheme,
        hp_dict: dict[ctenums.EnemyID, int]
) -> int:

    EnID = ctenums.EnemyID
    boss_ids = [part.enemy_id for part in boss_scheme.parts]
    main_ids = set([EnID.LAVOS_SPAWN_HEAD,
                    EnID.ELDER_SPAWN_HEAD,
                    EnID.GUARDIAN,
                    EnID.GIGA_GAIA_HEAD])
    if len(boss_ids) == 1:
        ret_hp = hp_dict[boss_ids[0]]
        if boss_ids[0] == EnID.RUST_TYRANO:
            ret_hp = round(ret_hp / 1.75)
    elif boss_ids[0] == EnID.TWIN_BOSS:
        ret_hp = round((hp_dict[EnID.TWIN_BOSS]*3)/2)
    elif EnID.TERRA_MUTANT_HEAD in boss_ids:
        head_hp = max(1, hp_dict[EnID.TERRA_MUTANT_HEAD])
        ret_hp = round(3*head_hp/2)
    elif not main_ids.isdisjoint(set(boss_ids)):
        main_id = next(x for x in main_ids if x in boss_ids)
        ret_hp = hp_dict[main_id]
    elif EnID.MOTHERBRAIN in boss_ids:
        ret_hp = hp_dict[EnID.MOTHERBRAIN]
    elif EnID.SON_OF_SUN_EYE in boss_ids:
        ret_hp = 6500  # Completely Fabricated!
    else:
        # The general case.  Just sum up the part HPs.

        ret_hp = sum(hp_dict[part] for part in boss_ids)

    return ret_hp


def get_part_new_hps(
        boss_scheme: rotypes.BossScheme,
        hp_dict: dict[ctenums.EnemyID, int],
        new_hp: int
) -> dict[ctenums.EnemyID, int]:

    EnID = ctenums.EnemyID

    main_ids = set([EnID.LAVOS_SPAWN_HEAD,
                    EnID.ELDER_SPAWN_HEAD,
                    EnID.GUARDIAN,
                    EnID.GIGA_GAIA_HEAD])

    boss_ids = [part.enemy_id for part in boss_scheme.parts]
    if len(boss_ids) == 1:
        if boss_ids[0] == EnID.RUST_TYRANO:
            new_hp = round(new_hp * 1.75)
        ret_dict = {boss_ids[0]: new_hp}
    elif boss_ids[0] == EnID.TWIN_BOSS:
        ret_dict = {EnID.TWIN_BOSS: round((new_hp*2)/3)}
    elif EnID.TERRA_MUTANT_HEAD in boss_ids:
        head_hp = max(1, hp_dict[EnID.TERRA_MUTANT_HEAD])
        bottom_hp = hp_dict[EnID.TERRA_MUTANT_BOTTOM]
        bot_proportion = bottom_hp/head_hp

        # Terra gets 2/3 of the spot hp and maintains head/bot proportion
        new_head_hp = round(new_hp*2/3)
        new_bottom_hp = round(bot_proportion*new_head_hp)
        ret_dict = {
            EnID.TERRA_MUTANT_HEAD: new_head_hp,
            EnID.TERRA_MUTANT_BOTTOM: new_bottom_hp
        }
    elif not main_ids.isdisjoint(set(boss_ids)):
        # Covers Lavos Spawns, Guardian, Giga Gaia
        # Give the main part the spot hp.  Assign the others proportionally.
        main_id = next(x for x in main_ids if x in boss_ids)
        main_hp = hp_dict[main_id]
        ret_dict = {
            part: round(new_hp*(hp_dict[part]/main_hp))
            for part in boss_ids
        }
    elif EnID.MOTHERBRAIN in boss_ids:
        ret_dict = {
            EnID.MOTHERBRAIN: new_hp,
            EnID.DISPLAY: 1
        }
    elif EnID.SON_OF_SUN_EYE in boss_ids:
        ret_dict = {}
    else:
        # The general case.  Carve up new_hp by the original hp distribution.
        # Being lazy because no leftover bosses have duplicate parts.
        total_hp = sum(hp_dict[part] for part in boss_ids)
        part_props = {
            part: hp_dict[part]/total_hp for part in boss_ids
        }
        ret_dict = {
            part: round(part_props[part]*new_hp) for part in part_props
        }

    return ret_dict
