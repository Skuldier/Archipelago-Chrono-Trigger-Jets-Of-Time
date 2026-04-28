from __future__ import annotations
import copy
from typing import Union, Literal

from bossrandotypes import BossID, BossSpotID
import bossrandoscaling
from ctenums import EnemyID, TreasureID as TID, ItemID, RecruitID, CharID

from enemystats import EnemyStats
# import logicfactory

import randoconfig as cfg
import randosettings as rset

# Order of stats:
# HP, Level, Magic, Magic Def, Off, Def, XP, GP, TP
# Sometimes xp, gp, tp are omitted at the end.
_scaling_data: dict[EnemyID, list[list[Union[int, Literal[""]]]]] = {
    EnemyID.RUST_TYRANO: [[6000, 16, 16, 50, 160, 127, 3000, 4000, 50],
                          [7000, 20, 20, 50, 170, 127, 3500, 6000, 60],
                          [8000, 30, 30, 50, 180, 127, 4000, 8000, 70]],
    EnemyID.DRAGON_TANK: [[1100, 15, 15, 60, 50, 160, 1600, 2500, 26],
                          [1300, 30, 30, 60, 100, 160, 2200, 4000, 36],
                          [1300, 30, 30, 60, 100, 160, 2200, 4000, 36]],
    EnemyID.TANK_HEAD: [[1400, 20, 20, 60, 50, 160],
                        [1600, 30, 30, 60, 50, 160],
                        [1600, 30, 30, 60, 50, 160]],
    EnemyID.GRINDER: [[1400, 20, 20, 60, 50, 160],
                      [1600, 30, 30, 60, 50, 160],
                      [1600, 30, 30, 60, 50, 160]],
    EnemyID.SON_OF_SUN_EYE: [["", 20, 20, "", "", "", 1600, 3000, 30],
                             ["", 30, 20, "", "", "", 2200, 5000, 40],
                             ["", 30, 30, "", "", "", 2800, 7000, 50]],
    EnemyID.SON_OF_SUN_FLAME: [["", 20, 20, "", "", ""],
                               ["", 30, 20, "", "", ""],
                               ["", 30, 30, "", "", ""]],
    EnemyID.NIZBEL: [[6000, 20, 20, 60, 155, 253, 4000, 4400, 45],
                     [7000, 30, 30, 60, 175, 253, 5000, 5500, 55],
                     [8000, 40, 40, 65, 190, 253, 6000, 6800, 65]],
    EnemyID.RETINITE_TOP: [[2000, 15, 15, 60, 130, 153, 1200, 0, 12],
                           [2200, 20, 20, 65, 160, 165, 1400, 0, 14],
                           [2400, 25, 25, 70, 190, 178, 1600, 0, 16]],
    EnemyID.RETINITE_BOTTOM: [[2000, 15, 15, 60, 130, 153, 1200, 0, 12],
                              [2200, 20, 20, 65, 160, 165, 1400, 0, 14],
                              [2400, 25, 25, 70, 190, 178, 1600, 0, 16]],
    # Should the eye get less hp with higher scaling?
    EnemyID.RETINITE_EYE: [[700, 15, 19, 60, 50, 153, 2400, 2100, 30],
                           [800, 15, 19, 65, 50, 165, 2800, 2700, 40],
                           [900, 15, 19, 70, 50, 178, 3200, 3300, 50]],
    EnemyID.YAKRA_XIII: [[5200, 17, 18, 50, 95, 127, 2800, 3000, 50],
                         [5800, 17, 18, 50, 120, 127, 3400, 4000, 60],
                         [6300, 17, 18, 50, 150, 127, 4000, 5000, 70]],
    EnemyID.GUARDIAN: [[3500, 15, 15, 50, 16, 127, 2500, 3000, 30],
                       [4000, 20, 20, 50, 16, 127, 3000, 4000, 40],
                       [4300, 30, 30, 50, 16, 127, 3500, 5000, 50]],
    EnemyID.GUARDIAN_BIT: [[500, 12, 12, 50, 32, 127],
                           [500, 15, 15, 50, 50, 127],
                           [500, 17, 17, 50, 74, 127]],
    EnemyID.MOTHERBRAIN: [[3500, 20, 20, 50, 100, 127, 3100, 4000, 50],
                          [4000, 30, 30, 50, 100, 127, 3700, 5000, 60],
                          [4500, 40, 40, 50, 100, 127, 4300, 6000, 70]],
    EnemyID.DISPLAY: [[1, 15, 15, 50, 144, 127],
                      [1, 15, 20, 50, 144, 127],
                      [1, 15, 25, 50, 144, 127]],
    EnemyID.R_SERIES: [[1200, 15, 15, 50, 52, 127, 500, 400, 10],
                       [1400, 20, 20, 50, 75, 127, 600, 600, 15],
                       [1200, 15, 15, 50, 52, 127, 500, 400, 10]],
    EnemyID.GIGA_GAIA_HEAD: [[8000, 32, 15, 50, 50, 127, 5000, 7000, 90],
                             [9000, 32, 15, 50, 50, 127, 6000, 8100, 100],
                             [10000, 32, 15, 50, 50, 127, 7000, 9200, 110]],
    EnemyID.GIGA_GAIA_LEFT: [[2500, 20, 30, 61, 40, 127],
                             [3000, 30, 30, 61, 40, 127],
                             [3500, 40, 30, 61, 40, 127]],
    EnemyID.GIGA_GAIA_RIGHT: [[2500, 20, 30, 50, 60, 158],
                              [3000, 30, 30, 50, 60, 158],
                              [3500, 40, 30, 50, 60, 158]]
}


def determine_boss_rank(settings: rset.Settings, config: cfg.RandoConfig):
    '''
    Use the key item placement and boss assignment to determine the rank of
    each boss.
    '''
    # First, boss scaling only works for normal logic, standard_mode
    chronosanity = rset.GameFlags.CHRONOSANITY in settings.gameflags
    # epoch_fail = rset.GameFlags.EPOCH_FAIL in settings.gameflags
    standard_mode = settings.game_mode == rset.GameMode.STANDARD
    boss_scaling = rset.GameFlags.BOSS_SCALE in settings.gameflags

    if not boss_scaling or not standard_mode or chronosanity:
        return

    # I can't do this because of a circular import.
    # game_config = logicfactory.getGameConfig(settings, config)
    # key_item_list = game_config.keyItemList

    # It's ok to get more KIs than needed
    key_item_list = ItemID.get_key_items()

    # To match the original implementation, make a dict with
    # ItemID --> TreasureID  for key items
    key_item_dict = {config.treasure_assign_dict[loc].reward: loc
                     for loc in config.treasure_assign_dict.keys()
                     if config.treasure_assign_dict[loc].reward
                     in key_item_list}

    boss_rank: dict[BossID, int] = {}
    boss_assign = config.boss_assign_dict

    # Treasure --> Location of Boss
    # This gives the location of the boss to scale when the treasure location
    # holds a key item.
    # Note:  Locations open at the start of the game (Denadoro, Bridge,
    #        Heckran) are never scaled, even if they have top rank items.
    loc_dict: dict[TID, BossSpotID] = {
        TID.REPTITE_LAIR_KEY: BossSpotID.REPTITE_LAIR,
        TID.KINGS_TRIAL_KEY: BossSpotID.KINGS_TRIAL,
        TID.GIANTS_CLAW_KEY: BossSpotID.GIANTS_CLAW,
        TID.FIONA_KEY: BossSpotID.SUNKEN_DESERT,
        TID.MT_WOE_KEY: BossSpotID.MT_WOE
    }

    # Treasure --> Item prerequisite
    # This gives the item to add to the important_keys pool when the treasure
    # location holds a key item.
    # TODO:  Automate this somehow in the logic object.
    item_req_dict: dict[TID, ItemID] = {
        TID.REPTITE_LAIR_KEY: ItemID.GATE_KEY,
        TID.KINGS_TRIAL_KEY: ItemID.PRISMSHARD,
        TID.GIANTS_CLAW_KEY: ItemID.TOMAS_POP,
        TID.FROGS_BURROW_LEFT: ItemID.HERO_MEDAL
    }

    no_req_tids = [TID.DENADORO_MTS_KEY, TID.ZENAN_BRIDGE_KEY,
                   TID.SNAIL_STOP_KEY, TID.LAZY_CARPENTER,
                   TID.TABAN_KEY]

    rank = 3
    important_keys = [ItemID.C_TRIGGER, ItemID.CLONE, ItemID.RUBY_KNIFE]

    while rank > 0:
        # print(f"rank = {rank}")
        # print(important_keys)
        important_tids = [key_item_dict[item] for item in important_keys]

        for item in important_keys:
            # print(f"{item} is in {key_item_dict[item]}")
            pass

        important_keys = list()

        for tid in important_tids:
            if tid in [TID.SUN_PALACE_KEY, TID.ARRIS_DOME_FOOD_LOCKER_KEY,
                       TID.GENO_DOME_KEY, TID.ARRIS_DOME_DOAN_KEY]:
                # If you found an important item in the future:
                #   1) Set prison boss (dtank) to rank-1 if not already ranked
                #   2) Set all future bosses to rank
                # This only happens once, for the highest ranked item in the
                # future.  Lower rank items found in the future will not
                # decrease the rank of the future bosses.
                if ItemID.PENDANT not in important_keys:
                    important_keys.append(ItemID.PENDANT)
                # print(f"Adding {ItemID.PENDANT} to important keys")
                prisonboss = boss_assign[BossSpotID.PRISON_CATWALKS]

                # Skip rank assignment if dtank already has a higher rank.
                # This will happen if keys of multiple levels are in future.
                if prisonboss not in boss_rank.keys() or (
                        prisonboss in boss_rank.keys() and
                        boss_rank[prisonboss] < rank
                ):
                    boss_rank[prisonboss] = rank - 1

                # There is a bug in previous implementations where the future
                # bosses were also only ranked if dtank was not already ranked.
                # In the case that Melchior's item changes dtank's rank, the
                # future bosses would never be ranked.

                # The original intention was to rank the future bosses based on
                # the highest ranked item there.  We'll preserve this.

                # All future bosses have the same rank, so just pick Arris.
                arrisboss = boss_assign[BossSpotID.ARRIS_DOME]
                if arrisboss not in boss_rank or boss_rank[arrisboss] < rank:
                    future_spots = [
                        BossSpotID.SUN_PALACE, BossSpotID.GENO_DOME,
                        BossSpotID.ARRIS_DOME
                    ]
                    for spot in future_spots:
                        futureboss = boss_assign[spot]
                        # print(f"Setting {futureboss} to rank {rank}")
                        boss_rank[futureboss] = rank
            elif tid == TID.MELCHIOR_KEY:
                # When Melchior gets a key item:
                #  1) gate key and pendant get added for next rank
                #  2) king's trial boss gets set to rank
                #  3) prison boss (dtank) gets set to rank-1
                # This is subtle:  Dtank's rank can not be decreased by future
                # locations holding items of lower rank, but it will be reduced
                # by Melchior having a lower rank item.
                for item in (ItemID.GATE_KEY, ItemID.PENDANT):
                    if item not in important_keys:
                        important_keys.append(item)

                trialboss = boss_assign[BossSpotID.KINGS_TRIAL]
                boss_rank[trialboss] = rank

                prisonboss = boss_assign[BossSpotID.PRISON_CATWALKS]
                boss_rank[prisonboss] = rank-1

            else:
                # Other TIDs are straightforward.  Add their prerequisite item
                # to the important_keys pool if they have one.  Rank their
                # boss if they have one.
                if tid in loc_dict:
                    location = loc_dict[tid]
                    boss = boss_assign[location]
                    boss_rank[boss] = rank
                    # print(f"Setting {boss} to rank {rank}")

                if tid in item_req_dict:
                    item = item_req_dict[tid]
                    important_keys.append(item)
                    # print(f"Adding {item} to important keys")

                # if (
                #         tid not in loc_dict.keys() and
                #         tid not in item_req_dict.keys() and
                #         tid not in no_req_tids
                # ):
                #     print(f"Warning: {tid} not in either dictionary")

        # Really, this just happens on the first iteration of the loop.
        if rank > 2:
            important_keys.extend([ItemID.BENT_HILT,
                                   ItemID.BENT_SWORD,
                                   ItemID.DREAMSTONE])

        important_keys = list(set(important_keys))
        rank -= 1

    char_dict = config.char_assign_dict
    proto_char = char_dict[RecruitID.PROTO_DOME].held_char
    factoryboss = boss_assign[BossSpotID.FACTORY_RUINS]

    if rset.GameFlags.LOCKED_CHARS in settings.gameflags:
        if proto_char in [CharID.ROBO, CharID.AYLA]:
            boss_rank[factoryboss] = 1
        elif proto_char in [CharID.CRONO, CharID.MAGUS]:
            boss_rank[factoryboss] = 2

    config.boss_rank_dict = boss_rank


# Perhaps replace config with the parts actually used: enemy, ai, atk data
# Otherwise it's silly because config has the boss rank dict already.
def get_ranked_boss_stats(
        boss_id: BossID,
        rank: int,
        config: cfg.RandoConfig
) -> dict[EnemyID, EnemyStats]:

    boss = config.boss_data_dict[boss_id]
    has_scaling_data = boss.parts[0].enemy_id in _scaling_data
    scaled_stats = {}

    if has_scaling_data and rank > 0:
        for part in boss.parts:
            stats = copy.deepcopy(config.enemy_dict[part.enemy_id])
            stat_list = _scaling_data[part.enemy_id][rank-1]
            stats.replace_from_stat_list(stat_list)

            scaled_stats[part.enemy_id] = stats
    elif rank == 0:
        scaled_stats = {
            part.enemy_id: copy.deepcopy(config.enemy_dict[part.enemy_id])
            for part in boss.parts
        }
    else:
        cur_level = bossrandoscaling.get_standard_boss_power(boss_id)
        new_level = cur_level + 4*rank
        scaled_stats = bossrandoscaling.scale_boss_scheme_progessive(
            boss, cur_level, new_level, config.enemy_dict,
            config.enemy_atk_db, config.enemy_ai_db
        )

    return scaled_stats
