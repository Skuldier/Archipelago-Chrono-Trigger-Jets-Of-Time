'''Contains classes for handling various objective types.'''
from __future__ import annotations

import dataclasses
import enum
import typing
from typing import Optional

import bossrandotypes as rotypes
from bossrandotypes import BossSpotID as BSID

import ctenums
import ctevent
import ctrom

from characters import pcrecruit

from eventcommand import EventCommand as EC, Operation as OP, FuncSync as FS
from eventfunction import EventFunction as EF

import itemdata
from treasures import treasuretypes

import randosettings as rset


class Objective(typing.Protocol):
    '''
    Protocol class for an objective.  Has methods for adding to config and to
    the rom itself.
    '''
    item_id: typing.Optional[ctenums.ItemID]
    name: str
    desc: str

    def update_item_db(self, item_db: itemdata.ItemDB):
        '''Add this objective to the provided config.'''
        item = item_db[self.item_id]
        item.set_name_from_str(self.name)
        item.set_desc_from_str(self.desc)

        item.secondary_stats.is_key_item = True
        item.secondary_stats.is_unsellable = True

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):
        '''Add this objective's check to the given CTRom.'''
        raise NotImplementedError


def add_obj_complete(script: ctevent.Event, pos: int,
                     objective: Objective,
                     num_objs_needed: int,
                     win_game: bool,
                     obj_count_addr: int,) -> int:
    '''
    Adds an objective complete message at the given position in the script.
    Returns the length of the code added.
    '''
    obj_complete_id = script.add_py_string(
        f'Objective Complete!{{linebreak+0}}'
        f'{objective.desc}{{null}}'
    )

    if objective.item_id is None:
        raise ValueError("Objective ItemID is not set.")

    if win_game:
        reward_id = script.add_py_string(
            'You Win!{null}'
        )
        # There are so many different, seemingly identical warp commands.
        # I'm copying the one from Tesseract exactly to avoid weirdness
        warp_ending_cmd = EC.change_location(
            ctenums.LocID.ENDING_SELECTOR, 0, 0, 1, 0, True
        )
        warp_ending_cmd.command = 0xDF
        reward_fn = (
            EF()
            .add(EC.set_storyline_counter(0x75))
            .add(EC.darken(0xC))
            .add(EC.fade_screen())
            .add(warp_ending_cmd)
        )
    else:
        reward_id = script.add_py_string(
            'Bucket unlocked!{linebreak+0}'
            'XP/TP gain doubled!{null}')
        # Set double tp memory location
        reward_fn = EF().add(EC.assign_val_to_mem(1, 0x7E287E, 1))
    func = (
        EF()
        .add(EC.assign_mem_to_mem(obj_count_addr, 0x7F0202, 1))
        .add(EC.increment_mem(0x7F0202, 1))
        .add(EC.assign_mem_to_mem(0x7F0202, obj_count_addr, 1))
        .add(EC.remove_item(int(objective.item_id)))
        .add(EC.remove_item(ctenums.ItemID.OBJ_COUNT))
        .add(EC.auto_text_box(obj_complete_id))
        .add_if(
            EC.if_mem_op_value(0x7F0202, OP.EQUALS, num_objs_needed, 1, 0),
            EF()
            .add(EC.auto_text_box(reward_id))
            .append(reward_fn)
        )
    )

    script.insert_commands(func.get_bytearray(), pos)

    return len(func)


@dataclasses.dataclass(frozen=True)
class BattleLoc:
    '''Class to provide data on how to find a battle command in a script.'''
    loc_id: ctenums.LocID
    obj_id: int
    fn_id: int
    battle_num: int = 0


_spot_battle_dict: dict[BSID, BattleLoc] = {
    BSID.ARRIS_DOME: BattleLoc(ctenums.LocID.ARRIS_DOME_GUARDIAN_CHAMBER,
                               9, 1, 0),
    BSID.BLACK_OMEN_ELDER_SPAWN: BattleLoc(
        ctenums.LocID.BLACK_OMEN_ELDER_SPAWN, 0, 0, 0),
    BSID.BLACK_OMEN_GIGA_MUTANT: BattleLoc(
        ctenums.LocID.BLACK_OMEN_GIGA_MUTANT, 0xA, 1, 0),
    BSID.BLACK_OMEN_TERRA_MUTANT: BattleLoc(
        ctenums.LocID.BLACK_OMEN_TERRA_MUTANT, 8, 2, 0),
    BSID.DEATH_PEAK: BattleLoc(
        ctenums.LocID.DEATH_PEAK_GUARDIAN_SPAWN, 8, 1, 0),
    BSID.DENADORO_MTS: BattleLoc(ctenums.LocID.CAVE_OF_MASAMUNE, 8, 4, 0),
    # Epoch reborn doesn't have a flag, but it sets 0x7F00D2 = 7 before the
    # cutscene starts.  So we can test any of the 0x07 bits for this one.
    # Note: This is only valid in EF b/c we add objects for Crono/Magus
    BSID.EPOCH_REBORN: BattleLoc(ctenums.LocID.REBORN_EPOCH, 9, 0, 0),
    # Actually the flag for activating the power core.
    BSID.FACTORY_RUINS: BattleLoc(
        ctenums.LocID.FACTORY_RUINS_SECURITY_CENTER, 2, 3, 0),
    BSID.GENO_DOME: BattleLoc(
        ctenums.LocID.GENO_DOME_MAINFRAME, 0x1E, 0, 0),
    BSID.GIANTS_CLAW: BattleLoc(
        ctenums.LocID.GIANTS_CLAW_TYRANO, 0, 0, 0),
    BSID.HECKRAN_CAVE: BattleLoc(
        ctenums.LocID.HECKRAN_CAVE_NEW, 0, 0, 0),
    BSID.KINGS_TRIAL: BattleLoc(ctenums.LocID.KINGS_TRIAL_NEW, 0xA, 6, 0),
    BSID.MAGUS_CASTLE_FLEA: BattleLoc(
        ctenums.LocID.MAGUS_CASTLE_FLEA, 0xC, 0, 1),
    BSID.MAGUS_CASTLE_SLASH: BattleLoc(
        ctenums.LocID.MAGUS_CASTLE_SLASH, 0xB, 1, 0),
    BSID.MANORIA_CATHERDAL: BattleLoc(ctenums.LocID.MANORIA_COMMAND, 8, 0, 0),
    BSID.MT_WOE: BattleLoc(ctenums.LocID.MT_WOE_SUMMIT, 0, 3, 0),
    BSID.OCEAN_PALACE_TWIN_GOLEM: BattleLoc(
        ctenums.LocID.OCEAN_PALACE_TWIN_GOLEM, 9, 3, 0),
    BSID.OZZIES_FORT_FLEA_PLUS: BattleLoc(
        ctenums.LocID.OZZIES_FORT_FLEA_PLUS, 9, 1, 0),
    BSID.OZZIES_FORT_SUPER_SLASH: BattleLoc(
        ctenums.LocID.OZZIES_FORT_SUPER_SLASH, 9, 1, 0),
    BSID.PRISON_CATWALKS: BattleLoc(ctenums.LocID.PRISON_CATWALKS, 0, 3, 0),
    BSID.REPTITE_LAIR: BattleLoc(
        ctenums.LocID.REPTITE_LAIR_AZALA_ROOM, 0, 0, 0),
    BSID.SUN_PALACE: BattleLoc(ctenums.LocID.SUN_PALACE, 8, 2, 0),
    BSID.SUNKEN_DESERT: BattleLoc(
        ctenums.LocID.SUNKEN_DESERT_DEVOURER, 2, 0, 0),
    BSID.TYRANO_LAIR_NIZBEL: BattleLoc(
        ctenums.LocID.TYRANO_LAIR_NIZBEL, 0xA, 1, 0),
    BSID.ZEAL_PALACE: BattleLoc(
        ctenums.LocID.ZEAL_PALACE_THRONE_NIGHT, 9, 3, 0),
    BSID.ZENAN_BRIDGE: BattleLoc(ctenums.LocID.ZENAN_BRIDGE_BOSS, 1, 0, 1)
}


def get_battle_loc_from_spot(spot: BSID) -> Optional[BattleLoc]:
    '''Gets a BattleLoc corresponding to a BossSpotID.'''
    return _spot_battle_dict.get(spot, None)


class BattleObjective(Objective):
    '''
    Class for objectives earned by winning a battle.

    This class only works property for battles which game over when lost.
    Otherwise, the objective complete dialog will come up even when the fight
    is lost.
    '''
    def __init__(self, battle_loc: BattleLoc,
                 name: str, desc: str,
                 item_id: typing.Optional[ctenums.ItemID]):
        self.name = name
        self.desc = desc
        self.battle_loc = battle_loc
        self.item_id = item_id

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):

        num_objectives_needed = bucket_settings.num_objectives_needed
        script = ct_rom.script_manager.get_script(self.battle_loc.loc_id)
        pos: Optional[int]
        pos = script.get_function_start(self.battle_loc.obj_id,
                                        self.battle_loc.fn_id)
        end = script.get_function_end(self.battle_loc.obj_id,
                                      self.battle_loc.fn_id)

        battle_cmd_id = 0xD8
        battle_cmd_len = len(EC.get_blank_command(battle_cmd_id))

        for _ in range(self.battle_loc.battle_num+1):
            pos, _ = script.find_command([battle_cmd_id], pos, end)
            pos += battle_cmd_len

        add_obj_complete(script, pos, self, num_objectives_needed,
                         bucket_settings.objectives_win,
                         objective_count_addr)


@dataclasses.dataclass(frozen=True)
class QuestData:
    '''Simple dataclass for holding quest name and description.'''
    name: str
    desc: str


class QuestID(enum.Enum):
    '''Enum for quests that can be objectives.'''
    FORGE_MASAMUNE = QuestData('*Forge Masa', 'Forge the Masamune')
    CHARGE_MOONSTONE = QuestData('*ChargeMoon', 'Charge the Moonstone')
    GIVE_JERKY_TO_MAYOR = QuestData('*Give Jerky', 'Trade away the Jerky')
    CLEAR_ARRIS_DOME = QuestData('*ArrisBoss', 'Defeat Arris Dome Boss')
    GET_ARRIS_FOOD_ITEM = QuestData('*Arris Food',
                                    'Get Arris Food Storage Item')
    GIVE_SEED_TO_DOAN = QuestData('*Doan Seed', 'Give the seed to Doan')
    VISIT_CYRUS_GRAVE = QuestData('*Cyrus', 'Visit Cyrus\'s grave with Frog')
    CLEAR_DEATH_PEAK = QuestData('*Death Peak', 'Clear Death Peak')
    CLEAR_DENADORO = QuestData('*Denadoro', 'Clear Denadoro Mountains')
    GAIN_EPOCH_FLIGHT = QuestData('*Epoch Fly', 'Gain Epoch Flight')
    CLEAR_FACTORY_RUINS = QuestData('*Factory', 'Clear Factory Ruins')
    CLEAR_GENO_DOME = QuestData('*Geno Dome', 'Clear Geno Dome')
    CLEAR_GIANTS_CLAW = QuestData('*GiantsClaw', 'Clear Giant\'s Claw')
    CLEAR_HECKRANS_CAVE = QuestData('*HeckranCve', 'Clear Hecrkan\'s Cave')
    CLEAR_KINGS_TRIAL = QuestData('*ShardTrial', 'Clear King\'s Trial')
    CLEAR_CATHEDRAL = QuestData('*Cathedral', 'Clear Cathedral')
    CLEAR_MT_WOE = QuestData('*Mt. Woe', 'Clear Mt. Woe')
    CLEAR_OCEAN_PALACE = QuestData('*OceanPalac', 'Clear Ocean Palace')
    CLEAR_OZZIES_FORT = QuestData('*Ozzie Fort', 'Clear Ozzie\'s Fort')
    CLEAR_PENDANT_TRIAL = QuestData('*PendntJail', 'Clear Pendant Trial')
    CLEAR_REPTITE_LAIR = QuestData('*Reptite Lr', 'Clear Reptite Lair')
    CLEAR_SUN_PALACE = QuestData('*Sun Palace', 'Clear the Sun Palace')
    CLEAR_SUNKEN_DESERT = QuestData('*Desert', 'Clear the Sunken Desert')
    CLEAR_ZEAL_PALACE = QuestData('*ZealThrone',
                                  'Defeat the Boss in Zeal Throne')
    CLEAR_ZENAN_BRIDGE = QuestData('*ZenanBrdge', 'Clear Zenan Bridge')
    CLEAR_TYRANO_MIDBOSS = QuestData('*TyranoMid', 'Clear Nizbel II Spot.')
    CLEAR_BLACK_TYRANO = QuestData('*TyranoLair', 'Clear the Tyrano Lair')
    CLEAR_MAGUS_FLEA_SPOT = QuestData('*MagusFlea',
                                      'Defeat the boss at Flea\'s Spot')
    CLEAR_MAGUS_SLASH_SPOT = QuestData('*MagusSlash',
                                       'Defeat the boss at Slash\'s Spot')
    CLEAR_MAGUS_CASTLE = QuestData('*MagusCstle', 'Clear Magus\'s Castle')
    CLEAR_OMEN_GIGASPOT = QuestData('*OmenGiga', 'Clear Omen GigaMutant Spot')
    CLEAR_OMEN_TERRASPOT = QuestData('*OmenTerra',
                                     'Clear Omen TerraMutant Spot')
    CLEAR_OMEN_ELDERSPOT = QuestData('*OmenElder',
                                     'Clear Omen ElderSpawn Spot')
    CLEAR_TWINBOSS_SPOT = QuestData('*TwinSpot',
                                    'Clear Ocean Palace Twin Spot')
    # Meme Objectives
    DEFEAT_JOHNNY = QuestData('*BeatJohnny', 'Beat Johnny in a Race')
    WIN_RACE_BET = QuestData('*Fair Race', 'Bet on a fair race and win.')
    DRINK_SODA = QuestData('*SodaGame', 'Play the fair Drinking Game.')


_quest_to_spot_dict: dict[QuestID, BSID] = {
    QuestID.CLEAR_ARRIS_DOME: BSID.ARRIS_DOME,
    QuestID.CLEAR_DEATH_PEAK: BSID.DEATH_PEAK,
    QuestID.GAIN_EPOCH_FLIGHT: BSID.EPOCH_REBORN,
    QuestID.CLEAR_DENADORO: BSID.DENADORO_MTS,
    QuestID.CLEAR_FACTORY_RUINS: BSID.FACTORY_RUINS,
    QuestID.CLEAR_GENO_DOME: BSID.GENO_DOME,
    QuestID.CLEAR_GIANTS_CLAW: BSID.GIANTS_CLAW,
    QuestID.CLEAR_HECKRANS_CAVE: BSID.HECKRAN_CAVE,
    QuestID.CLEAR_KINGS_TRIAL: BSID.KINGS_TRIAL,
    QuestID.CLEAR_CATHEDRAL: BSID.MANORIA_CATHERDAL,
    QuestID.CLEAR_MT_WOE: BSID.MT_WOE,
    QuestID.CLEAR_OCEAN_PALACE: BSID.OCEAN_PALACE_TWIN_GOLEM,
    QuestID.CLEAR_PENDANT_TRIAL: BSID.PRISON_CATWALKS,
    QuestID.CLEAR_REPTITE_LAIR: BSID.REPTITE_LAIR,
    QuestID.CLEAR_SUN_PALACE: BSID.SUN_PALACE,
    QuestID.CLEAR_SUNKEN_DESERT: BSID.SUNKEN_DESERT,
    QuestID.CLEAR_TWINBOSS_SPOT: BSID.OCEAN_PALACE_TWIN_GOLEM,
    QuestID.CLEAR_ZEAL_PALACE: BSID.ZEAL_PALACE,
    QuestID.CLEAR_ZENAN_BRIDGE: BSID.ZENAN_BRIDGE,
    QuestID.CLEAR_TYRANO_MIDBOSS: BSID.TYRANO_LAIR_NIZBEL,
    QuestID.CLEAR_OMEN_GIGASPOT: BSID.BLACK_OMEN_GIGA_MUTANT,
    QuestID.CLEAR_OMEN_TERRASPOT: BSID.BLACK_OMEN_TERRA_MUTANT,
    QuestID.CLEAR_OMEN_ELDERSPOT: BSID.BLACK_OMEN_ELDER_SPAWN,
    QuestID.CLEAR_MAGUS_FLEA_SPOT: BSID.MAGUS_CASTLE_FLEA,
    QuestID.CLEAR_MAGUS_SLASH_SPOT: BSID.MAGUS_CASTLE_SLASH
}


class QuestObjective(Objective):
    '''
    Base class for QuestObjectives.  Implementation will differ depending
    on the particular quest.
    '''
    def __init__(self, quest_id: QuestID, item_id: ctenums.ItemID):
        self.name = quest_id.value.name
        self.desc = quest_id.value.desc
        self.item_id = item_id


class ChargeMoonStoneObjective(QuestObjective):
    '''Class for the charge moon stone objective.'''
    def __init__(self, item_id: ctenums.ItemID):
        QuestObjective.__init__(self, QuestID.CHARGE_MOONSTONE, item_id)

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):
        num_objectives_needed = bucket_settings.num_objectives_needed
        script = ct_rom.script_manager.get_script(
            ctenums.LocID.SUN_KEEP_2300)

        # This one is scary because we don't want the player to run off
        # while the objective is being calculated.
        obj_id, fn_id = 8, 1
        start = script.get_function_start(obj_id, fn_id)

        script.insert_commands(
            EC.set_explore_mode(False).to_bytearray(), start)

        end = script.get_function_end(obj_id, fn_id)
        pos = script.find_exact_command(EC.generic_command(0xEE), start, end)

        script.insert_commands(
            EC.set_explore_mode(True).to_bytearray(), pos
        )

        add_obj_complete(script, pos, self, num_objectives_needed,
                         bucket_settings.objectives_win,
                         objective_count_addr)


class ForgeMasaMuneObjective(QuestObjective):
    '''Class for the forge Masamune objective.'''
    def __init__(self, item_id: ctenums.ItemID):
        QuestObjective.__init__(self, QuestID.FORGE_MASAMUNE, item_id)

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):
        num_objectives_needed = bucket_settings.num_objectives_needed
        script = ct_rom.script_manager.get_script(
            ctenums.LocID.MELCHIORS_KITCHEN)
        pos = script.find_exact_command(
            EC.party_follow(),
            script.get_function_start(8, 1))

        add_obj_complete(script, pos, self, num_objectives_needed,
                         bucket_settings.objectives_win,
                         objective_count_addr)


class JerkyRewardObjective(QuestObjective):
    '''Class for the turn jerky in objective.'''
    def __init__(self, item_id: ctenums.ItemID):
        QuestObjective.__init__(self, QuestID.GIVE_JERKY_TO_MAYOR, item_id)

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):
        num_objectives_needed = bucket_settings.num_objectives_needed
        script = ct_rom.script_manager.get_script(
            ctenums.LocID.PORRE_MAYOR_1F)
        # Stop exploration upon receiving the item.
        pos, _ = script.find_command(
            [0xCA],
            script.get_function_start(8, 1))

        script.insert_commands(
            EC.set_explore_mode(False).to_bytearray(), pos
        )

        # Turn exploration back on before jumping on.
        pos = script.find_exact_command(EC.generic_command(0x10, 0), pos)

        script.insert_commands(
            EC.set_explore_mode(True).to_bytearray(), pos)
        # Add the objective hook
        add_obj_complete(script, pos, self, num_objectives_needed,
                         bucket_settings.objectives_win,
                         objective_count_addr)


class CyrusGraveObjecitve(QuestObjective):
    '''Class for the Northern Ruins Tools check.'''
    def __init__(self, item_id: ctenums.ItemID):
        QuestObjective.__init__(self, QuestID.VISIT_CYRUS_GRAVE, item_id)

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):
        num_objectives_needed = bucket_settings.num_objectives_needed
        script = ct_rom.script_manager.get_script(
            ctenums.LocID.NORTHERN_RUINS_HEROS_GRAVE)

        hook_cmd = EC.call_obj_function(5, 6, 6, FS.CONT)
        pos = script.find_exact_command(hook_cmd,
                                        script.get_function_start(8, 1))

        # Put an extra empty pause after as a place to insert the objective
        repl_fn = EF().add(hook_cmd).add(EC.pause(0))

        script.insert_commands(repl_fn.get_bytearray(), pos)
        script.delete_commands(pos+len(repl_fn), 1)
        pos += len(hook_cmd)

        add_obj_complete(script, pos, self, num_objectives_needed,
                         bucket_settings.objectives_win,
                         objective_count_addr)

        # delete the empty pause
        pos = script.find_exact_command(EC.pause(0), pos)
        script.delete_commands(pos, 1)


class DefeatJohnnyObjective(QuestObjective):
    '''Class for beating Johnny in a bike race.'''
    def __init__(self, item_id: ctenums.ItemID):
        QuestObjective.__init__(self, QuestID.DEFEAT_JOHNNY, item_id)

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):
        num_objectives_needed = bucket_settings.num_objectives_needed
        # We need to put a check on both ends of lab32.
        script = ct_rom.script_manager.get_script(
            ctenums.LocID.LAB_32_WEST)

        hook_cmd = EC.call_obj_function(8, 5, 1, FS.HALT)
        pos = script.find_exact_command(hook_cmd) + len(hook_cmd)

        func = (
            EF()
            .add_if(
                EC.if_has_item(self.item_id, 0),
                EF().set_label('hook').add(EC.pause(0))
            )
        )
        script.insert_commands(func.get_bytearray(), pos)
        offset = func.labels['hook']
        add_obj_complete(script, pos+offset, self,
                         num_objectives_needed,
                         bucket_settings.objectives_win,
                         objective_count_addr)

        pos = script.find_exact_command(EC.pause(0), pos)
        script.delete_commands(pos, 1)

        # East End
        script = ct_rom.script_manager.get_script(
            ctenums.LocID.LAB_32_EAST)
        hook_cmd = EC.call_obj_function(8, 4, 1, FS.CONT)

        # same func, offset as before.
        pos = script.find_exact_command(hook_cmd)
        script.insert_commands(func.get_bytearray(), pos)
        add_obj_complete(script, pos+offset, self, num_objectives_needed,
                         bucket_settings.objectives_win,
                         objective_count_addr)
        pos = script.find_exact_command(EC.pause(0), pos)
        script.delete_commands(pos, 1)


class ClearOzziesFortObjective(QuestObjective):
    '''Class for beating Ozzie's Fort (cat drop).'''
    def __init__(self, item_id: ctenums.ItemID):
        QuestObjective.__init__(self, QuestID.CLEAR_OZZIES_FORT, item_id)

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):
        num_objectives_needed = bucket_settings.num_objectives_needed
        script = ct_rom.script_manager.get_script(
            ctenums.LocID.OZZIES_FORT_THRONE_INCOMPETENCE)

        hook_cmd = EC.call_pc_function(2, 5, 6, FS.HALT)
        pos = script.find_exact_command(
            hook_cmd, script.get_function_start(8, 2))
        pos += len(hook_cmd)

        add_obj_complete(script, pos, self, num_objectives_needed,
                         bucket_settings.objectives_win,
                         objective_count_addr)


class DefeatMagusObjective(QuestObjective):
    '''Class for defeating Magus at the end of Magus's Castle.'''
    def __init__(self, item_id: ctenums.ItemID):
        QuestObjective.__init__(self, QuestID.CLEAR_MAGUS_CASTLE, item_id)

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):
        num_objectives_needed = bucket_settings.num_objectives_needed
        loc_id = ctenums.LocID.MAGUS_CASTLE_INNER_SANCTUM
        script = ct_rom.script_manager.get_script(loc_id)

        obj_id, func_id = 9, 1  # Magus activation to start battle
        start = script.get_function_start(obj_id, func_id)
        end = script.get_function_end(obj_id, func_id)

        battle_result_cmd = \
            EC.if_mem_op_value(0x7F0232, OP.EQUALS, 0, 1, 0)

        pos = script.find_exact_command(battle_result_cmd, start, end)
        pos += len(battle_result_cmd)

        add_obj_complete(script, pos, self, num_objectives_needed,
                         bucket_settings.objectives_win,
                         objective_count_addr)


class DrinkSodaObjective(QuestObjective):
    '''Class for drinking a soda at the fair.'''
    def __init__(self, item_id: ctenums.ItemID):
        QuestObjective.__init__(self, QuestID.DRINK_SODA, item_id)

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):
        script = ct_rom.script_manager.get_script(
            ctenums.LocID.LEENE_SQUARE)

        hook_cmd = EC.assign_mem_to_mem(0x7F0236, 0x7E0200, 1)

        pos = script.find_exact_command(
            hook_cmd, script.get_function_start(0x1B, 1))
        pos += len(hook_cmd)

        func = (
            EF()
            .add_if(
                EC.if_has_item(self.item_id, 0),
                EF()
                .add_if(
                    EC.if_mem_op_value(0x7F0236, OP.NOT_EQUALS, 0, 1, 0),
                    EF()
                    .set_label('hook')
                    .add(EC.pause(0))
                )
            )
        )
        offset = func.labels['hook']
        script.insert_commands(func.get_bytearray(), pos)

        add_obj_complete(script, pos+offset, self,
                         bucket_settings.num_objectives_needed,
                         bucket_settings.objectives_win,
                         objective_count_addr)


class RecruitStarterObjective(Objective):
    '''
    Class for obtaining a starter char objective.

    This is dumb but someone may put a fixed 'Recruit Char' hint on, and then
    we need to allow this.
    '''
    def __init__(self, name: str, desc: str,
                 recruit: pcrecruit.StarterChar,
                 item_id: ctenums.ItemID):
        self.name = name
        self.desc = desc
        self.item_id = item_id
        self.loc_id = recruit.loc_id
        self.starter_num = recruit.starter_num

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):
        num_objectives_needed = bucket_settings.num_objectives_needed
        script = ct_rom.script_manager.get_script(self.loc_id)

        pos: typing.Optional[int]
        pos = script.get_object_start(0)

        name_pc_cmd = EC.name_pc(0)
        num_name_cmds_found = 0
        while True:
            pos, cmd = script.find_command_opt([name_pc_cmd.command], pos)

            if pos is None:
                break

            pos += len(name_pc_cmd)
            if cmd.args[0] in range(0xC0, 0xC7):
                if num_name_cmds_found == self.starter_num:
                    add_obj_complete(script, pos, self, num_objectives_needed,
                                     bucket_settings.objectives_win,
                                     objective_count_addr)
                    break

                num_name_cmds_found += 1

        if num_name_cmds_found != self.starter_num:
            raise ValueError('Unable to find starter')


class RecruitSpotObjective(Objective):
    '''Class for an objective fulfilled by recruiting from a given spot.'''
    def __init__(self, name: str, desc: str,
                 recruit: pcrecruit.CharRecruit,
                 item_id: ctenums.ItemID):
        self.name = name
        self.desc = desc
        self.item_id = item_id
        self.loc_id = recruit.loc_id

        # The changes to recruits means that the recruit_obj_id may not be
        # valid anymore.  We shove code into the actual player instead of the
        # dummy object.  So we just have to search the whole object for the
        # name command.

        # self.recruit_obj_id = recruit.recruit_obj_id

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):
        num_objectives_needed = bucket_settings.num_objectives_needed
        script = ct_rom.script_manager.get_script(self.loc_id)

        pos: typing.Optional[int]
        pos = script.get_object_start(0)

        name_pc_cmd = EC.name_pc(0)
        while True:
            pos, cmd = script.find_command_opt([name_pc_cmd.command], pos)

            if pos is None:
                break
            pos += len(name_pc_cmd)
            if cmd.args[0] in range(0xC0, 0xC7):
                add_obj_complete(script, pos, self, num_objectives_needed,
                                 bucket_settings.objectives_win,
                                 objective_count_addr)


def add_counting_object(script: ctevent.Event,
                        objective: Objective,
                        accum_addr: int,
                        accum_target: int,
                        bucket_settings: rset.BucketSettings,
                        objective_count_addr: int) -> int:
    '''
    Add an object with a function to call for counting. Returns the index of
    the newly-created object. We do this because
    some recruit objects have large jumps that can not be expanded much at all.
    This allows the insertion to just be a call_obj_function command.
    '''
    obj_id = script.append_empty_object()
    script.set_function(obj_id, 0,
                        EF().add(EC.return_cmd()).add(EC.end_cmd()))

    func = (
        EF()
        .add(EC.assign_mem_to_mem(accum_addr, 0x7F0202, 1))
        .add(EC.increment_mem(0x7F0202, 1))
        .add(EC.assign_mem_to_mem(0x7F0202, accum_addr, 1))
        .add_if(
            EC.if_mem_op_value(0x7F0202, OP.EQUALS, accum_target, 1, 0),
            (
                EF()
                .set_label('objcheck')
                # Dummy command so that there's a non-empty conditional block
                .add(EC.pause(0))
            )
        )
        .add(EC.return_cmd())
    )

    script.set_function(obj_id, 1, func)
    pos = script.get_function_start(obj_id, 1)
    offset = func.labels['objcheck'] + pos

    add_obj_complete(script, offset, objective,
                     bucket_settings.num_objectives_needed,
                     bucket_settings.objectives_win,
                     objective_count_addr)

    return obj_id


class RecruitNCharactersObjective(Objective):
    '''Objective for recruiting some number of characters.'''
    def __init__(self,
                 num_recruits: int,
                 num_recruits_addr: int,
                 item_id: ctenums.ItemID):
        if num_recruits not in range(1, 6):
            raise ValueError('Recruit count must be in range(1, 6)')

        self.num_recruits = num_recruits
        self.num_recruits_addr = num_recruits_addr
        self.name = f'*Recruit {num_recruits}'
        self.desc = f'Recruit {num_recruits} chars (total {num_recruits+2})'
        self.item_id = item_id

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):
        '''Add counting hooks to each recruit spot.  Give the objective when
        enough have been accumulated.'''

        # Put a count on each name char command in the following locations
        recruit_locs = [
            ctenums.LocID.MANORIA_SANCTUARY,
            ctenums.LocID.GUARDIA_QUEENS_CHAMBER_600,
            ctenums.LocID.DACTYL_NEST_SUMMIT, ctenums.LocID.PROTO_DOME,
            ctenums.LocID.FROGS_BURROW
        ]

        for loc in recruit_locs:
            script = ct_rom.script_manager.get_script(loc)

            obj_id = add_counting_object(
                script, self, self.num_recruits_addr,
                self.num_recruits, bucket_settings,
                objective_count_addr)

            pos: typing.Optional[int]
            pos = script.get_object_start(0)
            name_cmd = EC.name_pc(0)
            while True:
                pos, cmd = script.find_command_opt([name_cmd.command], pos)

                if pos is None:
                    break

                # The command is the "special dialog" command that includes
                # shops, etc.  We need to filter out all but names.
                if cmd.args[0] not in range(0xC0, 0xC7):
                    break

                pos += len(name_cmd)
                script.insert_commands(
                    EC.call_obj_function(obj_id, 1, 5, FS.HALT).to_bytearray(),
                    pos)


def add_box_check(
        script: ctevent.Event,
        chest_id: int,
        objective: Objective,
        accum_addr: int,
        accum_target: int,
        bucket_settings: rset.BucketSettings,
        objective_count_addr: int
        ):
    '''
    Add an object to listen for when a box is first opened.  Use carefully
    because I don't know how many active loops a script can handle.
    '''

    chest_flag_addr = 0x7F0001 + chest_id // 8
    chest_flag_bit = 1 << (chest_id % 8)

    func = (
        EF()
        .add(EC.return_cmd())
        .add_if(
            # If the chest is already opened, we can quit.
            EC.if_mem_op_value(chest_flag_addr, OP.BITWISE_AND_NONZERO,
                               chest_flag_bit, 1, 0),
            EF().add(EC.end_cmd())
        )
        .set_label('loop')
        .add_if(
            EC.if_mem_op_value(chest_flag_addr, OP.BITWISE_AND_NONZERO,
                               chest_flag_bit, 1, 0),
            EF()
            .add(EC.assign_mem_to_mem(accum_addr, 0x7F0202, 1))
            .add(EC.increment_mem(0x7F0202))
            .add(EC.assign_mem_to_mem(0x7F0202, accum_addr, 1))
            .add_if(
                EC.if_mem_op_value(0x7F0202, OP.EQUALS, accum_target, 1, 0),
                EF()
                .add(EC.set_explore_mode(False))
                .set_label('obj')
                .add(EC.set_explore_mode(True))
            )
            .add(EC.end_cmd())
        )
        .jump_to_label(EC.jump_back(0), 'loop')
    )

    offset = func.labels['obj']
    obj_id = script.append_empty_object()
    script.set_function(obj_id, 0, func)

    offset += script.get_function_start(obj_id, 0)

    add_obj_complete(script, offset, objective,
                     bucket_settings.num_objectives_needed,
                     bucket_settings.objectives_win,
                     objective_count_addr)


def add_script_treasure_count(
        ct_rom: ctrom.CTRom,
        treasure: treasuretypes.ScriptTreasure,
        objective: Objective,
        accum_addr: int,
        accum_target: int,
        bucket_settings: rset.BucketSettings,
        objective_count_addr: int):
    '''
    Adds an object to a script that increments a certain address when the
    specified ScriptTreasure is obtained.
    '''
    script = ct_rom.script_manager.get_script(treasure.location)

    obj_id = add_counting_object(script, objective, accum_addr,
                                 accum_target, bucket_settings,
                                 objective_count_addr)

    # Find the correct gain item command
    pos: typing.Optional[int]
    pos = script.get_function_start(treasure.object_id, treasure.function_id)
    end = script.get_function_end(treasure.object_id, treasure.function_id)

    for _ in range(treasure.item_num+1):
        pos, _ = script.find_command([0xCA], pos, end)
        pos += 2

    # Find the next textbox command
    pos, _ = script.find_command([0xBB, 0xC1, 0xC2], pos, end)
    pos += 2

    script.insert_commands(
        EC.call_obj_function(obj_id, 1, 5, FS.HALT).to_bytearray(), pos
    )


class ObtainNRocksObjective(Objective):
    '''Class for rock collection.'''
    def __init__(self,
                 num_rocks_needed: int,
                 num_rocks_addr: int,
                 treasure_dict: dict[ctenums.TreasureID, treasuretypes.Treasure],
                 item_id: ctenums.ItemID):
        if num_rocks_needed not in range(1, 6):
            raise ValueError('num_rocks_needed must be in range(1, 6)')

        rocks = (ctenums.ItemID.BLUE_ROCK, ctenums.ItemID.BLACK_ROCK,
                 ctenums.ItemID.SILVERROCK, ctenums.ItemID.WHITE_ROCK,
                 ctenums.ItemID.GOLD_ROCK)
        rock_dict = {
            tid: treasure for (tid, treasure) in treasure_dict.items()
            if treasure.reward in rocks
        }

        if len(rock_dict) != 5:
            # This should only be acceptable if we have a double-assignment
            # on the pyramid.
            TID = ctenums.TreasureID
            if (
                TID.PYRAMID_LEFT not in rock_dict or
                TID.PYRAMID_RIGHT not in rock_dict or
                len(rock_dict) != 6
            ):
                raise ValueError("Not all rocks are assigned in treaure_dict")

        self.rock_dict = rock_dict
        self.num_rocks_needed = num_rocks_needed
        self.num_rocks_addr = num_rocks_addr
        self.name = f'*{num_rocks_needed} Rocks'
        self.desc = f'Collect {num_rocks_needed} Rocks.'
        self.item_id = item_id

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):
        """Add listeners to the treasures which hold rocks."""

        for tid, treasure in self.rock_dict.items():
            if isinstance(treasure, treasuretypes.ScriptTreasure):
                add_script_treasure_count(
                    ct_rom, treasure, self,
                    self.num_rocks_addr, self.num_rocks_needed,
                    bucket_settings, objective_count_addr
                )
            elif isinstance(treasure, treasuretypes.ChestTreasure):
                # I've checked chest-having locations for enough objects.
                # If more box checks are added for other objectives, we may
                # need to aggregate box check objects.
                chest_id = treasure.chest_index
                loc_id = treasuretypes.get_chest_loc_id(chest_id)
                script = ct_rom.script_manager.get_script(loc_id)
                add_box_check(script, chest_id, self,
                              self.num_rocks_addr, self.num_rocks_needed,
                              bucket_settings, objective_count_addr)
            else:
                raise TypeError(f"Unsupported Treasure Type: {type(treasure).__name__}")


class CollectNFragmentsObjective(Objective):
    '''Objective for collecting some number of fragments.'''
    def __init__(self, fragments_needed: int, extra_fragments: int,
                 item_id: ctenums.ItemID):
        self.fragments_needed = fragments_needed
        self.extra_fragments = extra_fragments
        self.item_id = item_id
        total_fragments = fragments_needed + extra_fragments
        self.name = f'*Frag {fragments_needed}/{total_fragments}'
        self.desc = f'Bring {fragments_needed} fragments '\
            f'(of {total_fragments}) to Gaspar'

    def add_objective_check_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            bucket_settings: rset.BucketSettings,
            objective_count_addr: int
            ):
        script = ct_rom.script_manager.get_script(ctenums.LocID.END_OF_TIME)

        gaspar_id = 0x1C

        succ_id = script.add_py_string(
            'Hey.{full break}'
            'Looks like you got all the fragments. {null}'
        )
        fail_id = script.add_py_string(
            'You still have a few fragments to find.{null}'
        )

        gaspar_func = (
            EF()
            .add_if(
                # If the objective is still in inventory.
                EC.if_has_item(self.item_id, 0),
                EF()
                .add(EC.get_item_count(ctenums.ItemID.BUCKETFRAG, 0x7F0204))
                .add_if_else(
                    EC.if_mem_op_value(0x7F0204, OP.GREATER_OR_EQUAL,
                                       self.fragments_needed, 1, 0),
                    EF()
                    .add(EC.set_explore_mode(False))
                    .add(EC.generic_command(0xAA, 5))  # gaspar awake anim
                    .add(EC.auto_text_box(succ_id))
                    .set_label('obj')
                    .add(EC.set_explore_mode(True))
                    .add(EC.generic_command(0xAA, 0))
                    .add(EC.return_cmd()),
                    EF()
                    .add(EC.generic_command(0xAA, 5))
                    .add(EC.auto_text_box(fail_id))
                    .add(EC.generic_command(0xAA, 0))
                    .add(EC.return_cmd())
                )
            )
        )

        num_objectives_needed = bucket_settings.num_objectives_needed
        pos = script.get_function_start(gaspar_id, 1)
        script.insert_commands(gaspar_func.get_bytearray(), pos)
        offset = pos + gaspar_func.labels['obj']

        add_obj_complete(script, offset, self, num_objectives_needed,
                         bucket_settings.objectives_win,
                         objective_count_addr)


_boss_abbrev: dict[rotypes.BossID, str] = {
    rotypes.BossID.ATROPOS_XR: 'AtroposXR',
    rotypes.BossID.DALTON_PLUS: 'DaltonPlus',
    rotypes.BossID.ELDER_SPAWN: 'ElderSpawn',
    rotypes.BossID.FLEA: 'Flea',
    rotypes.BossID.FLEA_PLUS: 'Flea Plus',
    rotypes.BossID.GIGA_MUTANT: 'GigaMutant',
    rotypes.BossID.GOLEM: 'Golem',
    rotypes.BossID.GOLEM_BOSS: 'Golem Boss',
    rotypes.BossID.HECKRAN: 'Heckran',
    rotypes.BossID.LAVOS_SPAWN: 'LavosSpawn',
    rotypes.BossID.MAMMON_M: 'Mammon M',
    rotypes.BossID.MAGUS_NORTH_CAPE: 'Magus (NC)',
    rotypes.BossID.MASA_MUNE: 'Masa&Mune',
    rotypes.BossID.MEGA_MUTANT: 'MegaMutant',
    rotypes.BossID.MUD_IMP: 'Mud Imp',
    rotypes.BossID.NIZBEL: 'Nizbel',
    rotypes.BossID.NIZBEL_2: 'Nizbel II',
    rotypes.BossID.RETINITE: 'Retinite',
    rotypes.BossID.R_SERIES: 'R Series',
    rotypes.BossID.RUST_TYRANO: 'RustTyrano',
    rotypes.BossID.SLASH_SWORD: 'Slash',
    rotypes.BossID.SUPER_SLASH: 'SuperSlash',
    rotypes.BossID.SON_OF_SUN: 'Son of Sun',
    rotypes.BossID.TERRA_MUTANT: 'TerraMutnt',
    rotypes.BossID.TWIN_BOSS: 'Twin Boss',
    rotypes.BossID.YAKRA: 'Yakra',
    rotypes.BossID.YAKRA_XIII: 'Yakra XIII',
    rotypes.BossID.ZOMBOR: 'Zombor',
    rotypes.BossID.MOTHER_BRAIN: 'MotherBrn',
    rotypes.BossID.DRAGON_TANK: 'DragonTank',
    rotypes.BossID.GIGA_GAIA: 'Giga Gaia',
    rotypes.BossID.GUARDIAN: 'Guardian',

    # Midbosses -- Should be unused
    rotypes.BossID.MAGUS: 'Magus',
    rotypes.BossID.BLACK_TYRANO: 'Black Tyrano'
}


def get_defeat_boss_obj(
        boss_id: rotypes.BossID,
        settings: rset.Settings,
        boss_assign_dict: dict[rotypes.BossSpotID, rotypes.BossID],
        item_id: typing.Optional[ctenums.ItemID] = None
        ) -> BattleObjective:
    '''
    Returns a BattleObjective for defeating the given boss.
    '''
    # BossID.TWIN_BOSS will not be found in the assignment dictionary.  The
    # one-spot boss to be duplicated will be there.
    twin_spot = rotypes.BossSpotID.OCEAN_PALACE_TWIN_GOLEM

    if boss_id == rotypes.BossID.TWIN_BOSS:
        spot = twin_spot
    else:
        try:
            spots = (spot_id for spot_id, val
                     in boss_assign_dict.items()
                     if boss_id == val and spot_id != twin_spot)
            spot = next(spots)
        except StopIteration as exc:
            raise ValueError('boss_id not found') from exc

    battle_loc = _spot_battle_dict[spot]
    boss_abbrev = _boss_abbrev[boss_id]
    boss_name = str(boss_id)
    return BattleObjective(battle_loc,
                           f'*{boss_abbrev}', f'Defeat {boss_name}',
                           item_id)


def get_quest_obj(qid: QuestID,
                  settings: rset.Settings,
                  item_id: ctenums.ItemID,
                  ) -> Objective:
    '''Return an objective for completing the given quest.'''
    if qid in _quest_to_spot_dict:
        spot = _quest_to_spot_dict[qid]
        battle_loc = _spot_battle_dict[spot]
        return BattleObjective(
            battle_loc, qid.value.name, qid.value.desc, item_id
        )

    if qid == QuestID.CLEAR_BLACK_TYRANO:
        return BattleObjective(
            BattleLoc(ctenums.LocID.TYRANO_LAIR_KEEP, 0x10, 3),
            qid.value.name, qid.value.desc, item_id
        )

    if qid == QuestID.FORGE_MASAMUNE:
        return ForgeMasaMuneObjective(item_id)

    if qid == QuestID.CHARGE_MOONSTONE:
        return ChargeMoonStoneObjective(item_id)

    if qid == QuestID.GIVE_JERKY_TO_MAYOR:
        return JerkyRewardObjective(item_id)

    if qid == QuestID.VISIT_CYRUS_GRAVE:
        return CyrusGraveObjecitve(item_id)

    if qid == QuestID.CLEAR_OZZIES_FORT:
        return ClearOzziesFortObjective(item_id)

    if qid == QuestID.DEFEAT_JOHNNY:
        return DefeatJohnnyObjective(item_id)

    if qid == QuestID.DRINK_SODA:
        return DrinkSodaObjective(item_id)

    if qid == QuestID.CLEAR_MAGUS_CASTLE:
        return DefeatMagusObjective(item_id)

    raise ValueError(f'Invalid QuestID: {qid}')


def get_recruit_spot_obj(
        spot: ctenums.RecruitID,
        settings: rset.Settings,
        char_assign_dict: dict[ctenums.RecruitID, pcrecruit.RecruitSpot],
        item_id: ctenums.ItemID
):
    '''Create an objective for recruiting from a particular spot.  The char
    assign dict is used to find the correct map to place the hook.
    '''
    if spot == ctenums.RecruitID.CASTLE:
        name = '*CastleChar'
        desc = 'Recruit from Guardia Castle'
    elif spot == ctenums.RecruitID.DACTYL_NEST:
        name = '*DactylChar'
        desc = 'Recruit from Dactyl Nest'
    elif spot == ctenums.RecruitID.PROTO_DOME:
        name = '*ProtoChar'
        desc = 'Recruit from Proto Dome'
    elif spot == ctenums.RecruitID.FROGS_BURROW:
        name = '*BurrowChar'
        desc = 'Recruit from Frog\'s Burrow'
    else:
        raise ValueError('Invalid Spot')

    recruit = char_assign_dict[spot]
    if not isinstance(recruit, pcrecruit.CharRecruit):
        raise ValueError('Invalid Spot (Starter?)')

    return RecruitSpotObjective(name, desc, recruit, item_id)


def get_recruit_char_obj(
        char_id: ctenums.CharID,
        settings: rset.Settings,
        char_assign_dict: dict[ctenums.RecruitID, pcrecruit.RecruitSpot],
        item_id: ctenums.ItemID
) -> Objective:
    '''Create an objective for recruiting the given character given an
    assignment dictionary'''
    items = ((rid, recruit) for rid, recruit
             in char_assign_dict.items()
             if recruit.held_char == char_id)
    rid, recruit = next(items)

    name = f'*{char_id}'
    desc = f'Recruit {char_id}'

    if rid in (ctenums.RecruitID.STARTER_1, ctenums.RecruitID.STARTER_2):
        if not isinstance(recruit, pcrecruit.StarterChar):
            raise TypeError

        return RecruitStarterObjective(name, desc, recruit, item_id)

    if isinstance(recruit, pcrecruit.CharRecruit):
        return RecruitSpotObjective(name, desc, recruit, item_id)

    raise TypeError("Invalid recruit type.")
