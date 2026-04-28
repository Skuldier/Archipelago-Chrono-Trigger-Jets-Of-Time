'''Module to remove pendant charge by altering scripts of objects.'''

from dataclasses import dataclass
from typing import Optional

import ctenums
import ctevent
from ctrom import CTRom
from treasures import treasuretypes


@dataclass
class ObjectRef:
    '''Dataclass to store references to a particular object/function.'''
    loc_id: ctenums.LocID = ctenums.LocID(0)
    obj_id: int = 0
    func_id: int = 0


def apply_fast_pendant_script(ctrom: CTRom):
    '''
    Update every script with an object that activates with the charged pendant
    to only require the pendant.
    '''
    # The strategy is just to change every 'if pendant charged' to
    # 'if has pendant' since there's no well-defined event to add a scene
    # to charge the pendant.  Especially in chronosanity.
    TID = ctenums.TreasureID
    LocID = ctenums.LocID

    sealed_tids = [
        TID.PORRE_ELDER_SEALED_1, TID.PORRE_ELDER_SEALED_2,
        TID.PORRE_MAYOR_SEALED_1, TID.PORRE_MAYOR_SEALED_2,
        TID.HECKRAN_SEALED_1,  # No need for sealed_2 because same trigger
        TID.MAGIC_CAVE_SEALED,
        TID.GUARDIA_CASTLE_SEALED_600,
        TID.GUARDIA_CASTLE_SEALED_1000,
        TID.GUARDIA_FOREST_SEALED_600, TID.GUARDIA_FOREST_SEALED_1000,
        TID.TRUCE_INN_SEALED_600, TID.TRUCE_INN_SEALED_1000
    ]

    # Just to get the TID -> script reference dict
    treasure_dict = treasuretypes.get_base_treasure_dict()
    obj_refs = []
    for tid in sealed_tids:
        treasure_obj = treasure_dict[tid]

        if not isinstance(treasure_obj, treasuretypes.ScriptTreasure):
            raise TypeError("TreasureID {tid} is not a script treasure.")

        obj_refs.append(
            ObjectRef(treasure_obj.location,
                      treasure_obj.object_id,
                      treasure_obj.function_id)
        )

    # Non-treasure references are:
    #   1) Bangor sealed door
    #   2) Trann sealed door
    #   3) Arris sealed door
    #   4) Pyramid

    bangor_door = ObjectRef(LocID.BANGOR_DOME, 8, 1)
    trann_door = ObjectRef(LocID.TRANN_DOME, 0x11, 1)
    arris_door = ObjectRef(LocID.ARRIS_DOME_LOWER_COMMONS, 9, 1)
    pyramid = ObjectRef(LocID.FOREST_RUINS, 0, 0)

    obj_refs.extend([bangor_door, trann_door, arris_door, pyramid])

    script_man = ctrom.script_manager

    for obj_ref in obj_refs:
        script = script_man.get_script(obj_ref.loc_id)
        obj_id = obj_ref.obj_id
        func_id = obj_ref.func_id

        # print(f"{obj_ref.loc_id}, {obj_ref.obj_id}, {obj_ref.func_id}")

        start = script.get_function_start(obj_id, func_id)
        end = script.get_function_end(obj_id, func_id)

        pos: Optional[int] = start

        while True:
            pos, cmd = script.find_command([0x16], pos, end)

            # Make sure it's the right command.
            # 1st arg: 0xF4 indicating checking memory 0x7F00F4
            # 2nd arg: 0x40 indicating we're operating with value 0x40
            # 3rd arg: 0x06 indicating we're testing set bits
            # 4th arg: jump length will vary from command to command
            if cmd.args[0:3] == [0xF4, 0x40, 0x06]:
                break

            pos += len(cmd)

        jump_length = cmd.args[3]
        new_if = ctevent.EC.generic_two_arg(0xC9, 0xD6, jump_length)

        script.delete_commands(pos, 1)
        script.insert_commands(new_if.to_bytearray(), pos)
