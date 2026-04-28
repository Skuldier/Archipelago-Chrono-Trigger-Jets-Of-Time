'''Functions for Epoch Fail flag.'''
from typing import Optional

import eventcommand

import ctenums
import ctevent
import ctrom

import randoconfig as cfg
import randosettings as rset


# I think vanilla coords are 0x0270, 0x258
def ground_epoch(ct_rom: ctrom.CTRom):
    '''Disable Epoch flight on game start.  Places it in 1000AD'''
    script = ct_rom.script_manager.get_script(
        ctenums.LocID.TELEPOD_EXHIBIT
    )

    EC = ctevent.EC
    EF = ctevent.EF

    epoch_status_byte = 0x7E0294
    epoch_loc_byte = 0x7E029F

    # Bytes that indicate what kind of movement to do on the ow.  Should be
    # set to 0 for normal walking.  Originally were 2 for flying.
    ow_move_type_byte1 = 0x7E027E
    ow_move_type_byte2 = 0x7E028F  # Pretty sure this is a typo.  0x7E027F

    ow_move_type_cmd1 = EC.assign_val_to_mem(0x02, ow_move_type_byte1, 1)
    new_move_type_cmd1 = EC.assign_val_to_mem(0x00, ow_move_type_byte1, 1)

    ow_move_type_cmd2 = EC.assign_val_to_mem(0x02, ow_move_type_byte2, 1)
    new_move_type_cmd2 = EC.assign_val_to_mem(0x00, ow_move_type_byte2, 1)

    pos: Optional[int]
    pos = script.find_exact_command(ow_move_type_cmd1)
    script.data[pos: pos+len(ow_move_type_cmd1)] = \
        new_move_type_cmd1.to_bytearray()

    pos = script.find_exact_command(ow_move_type_cmd2)
    script.data[pos: pos+len(ow_move_type_cmd2)] = \
        new_move_type_cmd2.to_bytearray()

    pos = script.find_exact_command(
        EC.set_reset_bit(0x7F00BA, 0x80, True)
    )
    script.delete_commands(pos, 1)

    func = EF()
    (
        func
        .add(EC.set_reset_bit(0x7F00EC, 0x04, True))  # Epoch out of hangar
        .add(EC.set_reset_bit(0x7F00EE, 0x80, True))  # Nu in Hangar on
        .add(EC.set_reset_bit(0x7F00EF, 0x10, True))  # Seen Epoch scene
        .add(EC.set_reset_bit(0x7F01F0, 0x01, True))  # Vortex Pt
        .add(EC.set_reset_bit(0x7F01A3, 0x02, True))  # H. Cave 1st Fight Done
    )

    script.insert_commands(func.get_bytearray(), pos)

    epoch_status_cmd = EC.assign_val_to_mem(0xF2, epoch_status_byte, 1)
    new_status_cmd = EC.assign_val_to_mem(0x80, epoch_status_byte, 1)
    status_cmd_len = len(epoch_status_cmd)

    pos = script.find_exact_command(epoch_status_cmd)
    script.data[pos:pos+status_cmd_len] = new_status_cmd.to_bytearray()

    epoch_map_cmd = EC.assign_val_to_mem(0x01F1, epoch_loc_byte, 2)
    new_map_cmd = EC.assign_val_to_mem(0x01F0, epoch_loc_byte, 2)
    map_cmd_len = len(epoch_map_cmd)

    pos = script.find_exact_command(epoch_map_cmd)
    script.data[pos:pos+map_cmd_len] = new_map_cmd.to_bytearray()

    new_loc_cmd = EC.change_location(
        int(ctenums.LocID.LEENE_SQUARE),
        0x18, 0x1
    )

    func = (
        EF()
        .add(new_loc_cmd)
    )

    pos = script.find_exact_command(EC.fade_screen(),
                                    script.get_function_start(0xE, 4))
    script.insert_commands(EC.darken(1).to_bytearray(), pos)

    pos, _ = script.find_command([0xE0], pos)

    script.delete_commands(pos, 1)
    script.insert_commands(new_loc_cmd.to_bytearray(), pos)

    song_slow = bytearray.fromhex(
        'AD20'  # Pause
        'EC854080'  # Slow to half speed
        'BCBC'  # Pause Pause
        'ECF00000'  # Fade out song
        'EC850000'  # Reset speed
    )

    # Remove Epoch sfx
    start = script.get_function_start(0x0E, 4)

    pos, _ = script.find_command([0xEA], start)
    pos, _ = script.find_command([0xEC], pos)
    script.delete_commands(pos, 5)
    script.insert_commands(song_slow, pos)


def update_keepers_dome(ct_rom: ctrom.CTRom):
    '''
    Set the Keeper's dome corridor and hangar script to allow for access with
    both flying and grounded epochs.
    '''

    # Keeper's Dome Corridor
    # 1) Always leave the door open.  Otherwise it would potentially softlock
    #    if you warp to the future and leave the hangar without the pendant.
    # 2) Use Vanilla logic to block the door when the Epoch isn't in the
    #    hangar.

    script = ctevent.Event.from_flux('./flux/EF_0F2_Keepers_Dome.Flux')
    ct_rom.script_manager.set_script(
        script, ctenums.LocID.KEEPERS_DOME_CORRIDOR
    )

    # Remember to set the in hangar flag correctly when flight is obtained.

    # Another issue is that leaving in the epoch from Keeper's Dome will
    # set three characters in the epoch.  This will lock if only two are
    # present.

    script = ctevent.Event.from_flux('./flux/EF_0F3_Keepers_Dome_Hangar.Flux')
    ct_rom.script_manager.set_script(
        script, ctenums.LocID.KEEPERS_DOME_HANGAR
    )


def restore_dactyls(ct_rom: ctrom.CTRom):
    '''
    Put the party on Dactyls after Dactyl Recruit
    '''

    script = ct_rom.script_manager.get_script(
        ctenums.LocID.DACTYL_NEST_SUMMIT
    )

    pos, _ = script.find_command([0xE0])
    script.delete_commands(pos, 1)

    EF = ctevent.EF
    EC = ctevent.EC

    func = EF()
    (
        func
        .add(EC.assign_val_to_mem(3, 0x7E027E, 1))
        .add(EC.assign_val_to_mem(3, 0x7E028F, 1))
        .add(EC.assign_val_to_mem(0x01F8, 0x7E029A, 2))
        .add(EC.assign_val_to_mem(0x0048, 0x7E029C, 2))
        .add(EC.assign_val_to_mem(0xC3, 0x7E029E, 1))
        .add(EC.change_location(0x01F3, 0x3F, 0x09, 0, 1, False))
    )

    # Weird note.  The changelocation coordinates are essential.  If they are
    # not changed back to vanilla, the overworld never draws the dactyls and
    # softlocks as a result.

    script.insert_commands(func.get_bytearray(), pos)


def undo_epoch_relocation(ct_rom: ctrom.CTRom):
    '''
    Keep the Epoch from moving around before flight.
    '''

    # Possible Relocations
    #   After trial (Guardia Forest Dead End)
    #   After Heckran's Cave (Duplicated to 0xC0, Heckran Passageways New)
    #   After Desert turn-in (Fiona's Villa)
    #   After Zenan Bridge (Guardia Throneroom)
    #   After Magic Cave cutscene (Magic Cave Exterior)
    #   After defeating Magus (Magus Castle Inner Sanctum)
    #   After defeating Yakra (Manoria Command)
    #   Taking off from Keeper's Dome Hangar (don't change)
    #   After Lavos crashes (0x105 Prehistoric Canyon)
    #   Leaving Mystic Mts (0x112)
    #   Going through Lair Ruins portal (0x133)
    #   Maybe after losing to lavos?  Might have to just give flight.

    EC = eventcommand.EventCommand
    OP = eventcommand.Operation

    jump_len = 13  # 2 assignments + 1
    jmp = EC.if_mem_op_value(0x7F00BA, OP.BITWISE_AND_NONZERO,
                             0x80, 1, jump_len)

    LocID = ctenums.LocID
    locations = (
        LocID.GUARDIA_FOREST_DEAD_END, LocID.HECKRAN_CAVE_NEW,
        LocID.FIONAS_VILLA, LocID.GUARDIA_THRONEROOM_600,
        LocID.MAGIC_CAVE_EXTERIOR, LocID.MAGUS_CASTLE_INNER_SANCTUM,
        LocID.MANORIA_COMMAND, LocID.PREHISTORIC_CANYON,
        LocID.MYSTIC_MTN_GULCH, LocID.LAIR_RUINS_PORTAL
    )

    for loc in locations:
        script = ct_rom.script_manager.get_script(loc)

        pos: Optional[int]
        pos = script.get_function_start(0, 0)
        found = False

        # You can get in an awkward spot when you do Cathedral.  The
        # Epoch is moved to 600.  The Epoch becomes unavailable until you
        # do bridge.
        jump_len = 13  # 1 + 2 assigns
        if loc in (LocID.MANORIA_COMMAND, LocID.GUARDIA_FOREST_DEAD_END):
            jump_len += 6  # Also jump over the map switch assign.

        jmp = EC.if_mem_op_value(0x7F00BA, OP.BITWISE_AND_NONZERO,
                                 0x80, 1, jump_len)

        while True:
            pos, cmd = script.find_command_opt([0x4B], pos)
            if pos is None:
                break
            if cmd.args[0] == 0x7E0290:
                found = True
                script.insert_commands(jmp.to_bytearray(), pos)

            pos += len(cmd)

        if not found:
            raise ctevent.CommandNotFoundException(
                f"Couldn't find Epoch location commands in {loc}"
            )


def update_reborn_epoch_script(ct_rom: ctrom.CTRom):
    '''
    Add Magus and Crono to Epoch Reborn (0x179)
    '''

    def change_pc_checks(script: ctrom.ctevent.Event, obj_id, pc_id):
        start = script.get_object_start(obj_id)
        end = script.get_object_end(obj_id)

        EC = ctrom.ctevent.EC

        OP = eventcommand.Operation

        load_pc_cmd = EC.load_pc_in_party(pc_id)
        script.data[start] = load_pc_cmd.command

        check_pc_cmds = [
            EC.if_mem_op_value(addr, OP.EQUALS, 1, 1, 0)
            for addr in (0x7F020C, 0x7F020E, 0x7F0210)
        ]

        for cmd in check_pc_cmds:
            pos: Optional[int] = start

            while True:
                pos = script.find_exact_command_opt(cmd, start, end)

                if pos is None:
                    break

                script.data[pos+2] = pc_id
                pos += len(cmd)

    EC = ctrom.ctevent.EC
    EF = ctrom.ctevent.EF
    OP = eventcommand.Operation

    er_script = ct_rom.script_manager.get_script(ctenums.LocID.REBORN_EPOCH)
    er_script.insert_copy_object(1, 1)
    er_script.insert_copy_object(1, 7)

    change_pc_checks(er_script, 1, 0)
    change_pc_checks(er_script, 7, 6)

    get_command = ctevent.get_command
    del_st_cmd = get_command(b'\xEA\x16', 0)

    start = er_script.get_function_start(9, 0)
    del_st = er_script.find_exact_command(del_st_cmd, start)
    er_script.delete_commands(del_st, 1)
    del_st += 6  # jump over some function calls to the pc2 function call

    func = (
        EF()
        .add_if_else(
            EC.if_mem_op_value(0x7F0210, OP.LESS_OR_EQUAL, 6, 1, 0),
            EF().add(get_command(bytes.fromhex('070448'))),  # PC func
            EF().add(EC.pause(1))
        )
    )
    er_script.delete_commands(del_st, 1)
    er_script.insert_commands(func.get_bytearray(), del_st)
    del_st += len(func) + 3

    del_end = er_script.get_function_end(9, 0)

    er_script.delete_commands_range(del_st, del_end)

    func = EF()
    (
        func
        .add(EC.assign_mem_to_mem(0x7E2094, 0x7F021E, 1))
        .add_if_else(
            EC.if_mem_op_value(0x7F0210, OP.EQUALS, 0x80, 1, 0),
            (
                EF()
                .add(EC.set_reset_bits(0x7F021E, 0x62, True))
            ),
            (
                EF()
                .add(EC.set_reset_bits(0x7F021E, 0x63, True))
            )
        )
        .add(EC.set_bit(0x7F00BA, 0x80))
        .add(EC.assign_mem_to_mem(0x7F021E, 0x7E0294, 1))
        .add(EC.assign_val_to_mem(0x1F4, 0x7E029F, 2))
        .add(EC.assign_val_to_mem(0x03F8, 0x7E0290, 2))
        .add(EC.assign_val_to_mem(0x01C0, 0x7E0292, 2))
        .add(EC.assign_val_to_mem(0x02, 0x7E027E, 1))
        .add(EC.assign_val_to_mem(0x02, 0x7E028F, 1))
        .add(EC.assign_val_to_mem(0x00, 0x7F00D2, 1))  # Ending bug prevention
        .add(get_command(b'\xEA\x13'))
        .add(EC.darken(1))
        .add(EC.fade_screen())
        .add(EC.change_location(0x1F4, 0x7F, 0x38, 0, 0, True))
    )

    er_script.insert_commands(func.get_bytearray(), del_st)


def add_jets_turnin_to_blackbird_scaffolding(ct_rom: ctrom.CTRom):
    '''
    Have the JetsOfTime be turned in at the blackbird scaffolding (0x16A)
    '''
    update_reborn_epoch_script(ct_rom)

    EC = ctevent.EC
    EF = ctevent.EF
    OP = eventcommand.Operation
    FS = eventcommand.FuncSync

    script = ct_rom.script_manager.get_script(
        ctenums.LocID.BLACKBIRD_SCAFFOLDING
    )

    bb_script = ct_rom.script_manager.get_script(ctenums.LocID(0x16B))

    get_command = ctevent.get_command
    epoch_ind = script.append_empty_object()
    startup = bb_script.get_function(6, 0)
    script.set_function(epoch_ind, 0, startup)
    script.set_function(epoch_ind, 1, EF().add(EC.return_cmd()))

    arb0 = bb_script.get_function(6, 3)
    script.set_function(epoch_ind, 3, arb0)

    for obj in range(3):
        ind = script.append_empty_object()

        startup = bb_script.get_function(7+obj, 0)
        arb0 = bb_script.get_function(7+obj, 3)

        script.set_function(ind, 0, startup)
        script.set_function(ind, 1, EF().add(EC.return_cmd()))
        script.set_function(ind, 3, arb0)

        follow_loc = script.get_function_end(ind, 0) - 1
        script.data[follow_loc] = 2*(ind-1)

    script.replace_command(get_command(bytes.fromhex('A00800'), 0),
                           get_command(bytes.fromhex('A00100'), 0))

    script.replace_command(get_command(bytes.fromhex('8B0820'), 0),
                           get_command(bytes.fromhex('8B0112'), 0))

    del ct_rom.script_manager.script_dict[ctenums.LocID(0x16B)]

    # Just to see what happens, make talking to the Basher throw you to the
    # Reborn Epoch map.

    basher_ids = [7, 8]

    change_loc_cmd = EC.change_location(ctenums.LocID.REBORN_EPOCH, 7, 0x19)

    new_str = 'BASHER: Those jets will be perfect {line break}'\
        'for Lord Dalton\'s improvements!{null}'
    new_ind = script.add_py_string(new_str)

    for obj_id in basher_ids:
        # ins_pos = script.get_function_end(obj_id, 1) - 2
        orig_func = script.get_function(obj_id, 1)

        turnin_block = (
            EF()
            .add(EC.set_explore_mode(False))
            .add(EC.auto_text_box(new_ind))
            .add(EC.assign_val_to_mem(7, 0x7F00D2, 1))
            .add(EC.call_obj_function(epoch_ind, 3, 4, FS.SYNC))
            .add(EC.call_obj_function(epoch_ind+1, 3, 4, FS.CONT))
            .add(EC.call_obj_function(epoch_ind+2, 3, 4, FS.CONT))
            .add(EC.call_obj_function(epoch_ind+3, 3, 4, FS.HALT))
            .add(get_command(b'\xEA\x16'))
            .add(EC.move_party(6, 0x14, 6, 0x14, 6, 0x14))
            .add(EC.darken(1))
            .add(EC.fade_screen())
            .add(change_loc_cmd)
        )

        func = (
            EF()
            .add_if_else(
                EC.if_has_item(ctenums.ItemID.JETSOFTIME, 0),
                turnin_block,
                orig_func
            )
        )

        script.set_function(obj_id, 1, func)

        orig_func = script.get_function(obj_id, 0)
        func = (
            EF()
            .add_if_else(
                EC.if_mem_op_value(0x7F00BA, OP.BITWISE_AND_NONZERO, 0x80,
                                   1, 0),
                EF().add(EC.return_cmd()).add(EC.end_cmd()),
                orig_func
            )
        )
        script.set_function(obj_id, 0, func)


def add_dalton_to_snail_stop(ct_rom: ctrom.CTRom):
    '''
    Add Dalton to fix the Epoch in the Snail Stop.
    '''

    script = ctevent.Event.from_flux('./flux/EF_035_Snail_Stop.Flux')
    ct_rom.script_manager.set_script(script, ctenums.LocID.SNAIL_STOP)


def update_config(config: cfg.RandoConfig):
    '''
    Add JetsOfTime to the item list.
    '''
    jot = config.item_db[ctenums.ItemID.JETSOFTIME]
    jot.set_name_from_str(' JetsOfTime')


def apply_epoch_fail(ct_rom: ctrom.CTRom, settings: rset.Settings):
    '''
    Apply Epoch Fail if the settings allow it.
    '''

    # Sanity check should be in randomizer.py, but keep redundant check here.
    if settings.game_mode != rset.GameMode.LOST_WORLDS and \
       rset.GameFlags.EPOCH_FAIL in settings.gameflags:

        ground_epoch(ct_rom)
        update_keepers_dome(ct_rom)
        undo_epoch_relocation(ct_rom)
        restore_dactyls(ct_rom)

        # Use the Dark Ages turn-in for Jets in Vanilla or with unlocked
        # skygates.
        if rset.GameFlags.UNLOCKED_SKYGATES in settings.gameflags:
            add_jets_turnin_to_blackbird_scaffolding(ct_rom)
        else:
            add_dalton_to_snail_stop(ct_rom)
