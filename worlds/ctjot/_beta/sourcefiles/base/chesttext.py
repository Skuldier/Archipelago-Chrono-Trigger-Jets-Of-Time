'''
Module to alter treasure chest text boxes to include the item description.

Mainly useful for gear rando.
'''
from typing import Optional

from asm import instructions as inst, assemble
from base import basepatch

import byteops
import ctenums
import ctrom
import itemdata

from ctstrings import CTNameString


def write_desc_strings(ct_rom: ctrom.CTRom,
                       item_db: Optional[itemdata.ItemDB] = None,
                       max_desc_len: int = 0x28) -> int:
    '''
    Write the description strings to rom
    '''

    if item_db is None:
        item_db = itemdata.ItemDB.from_rom(ct_rom.rom_data.getbuffer())
        item_db.update_all_descriptions()

    desc_size = max_desc_len
    total_size = 0x100 * desc_size

    start = ct_rom.rom_data.space_manager.get_free_addr(total_size)

    rom = ct_rom.rom_data
    rom.seek(start)

    valid_item_ids = set(x.value for x in ctenums.ItemID)
    for index in range(0x100):
        if index in valid_item_ids:
            item_id = ctenums.ItemID(index)
            desc_str = item_db[item_id].get_desc_as_str()

            if not desc_str:
                desc = CTNameString(b''.join(b'\xEF' for _ in range(desc_size)))
                desc[0] = 0xFF
            else:
                desc = CTNameString.from_string(desc_str,
                                                length=desc_size)
        else:
            # print(f'Error: {index:02X}')
            desc = CTNameString.from_string(f'Item 0x{index:02X}',
                                            length=desc_size)

        rom.write(desc,
                  ctrom.freespace.FSWriteType.MARK_USED)

    return start


def add_strlen_func(ct_rom: ctrom.CTRom, max_length: int = 0x28) -> int:
    '''Add a string length function to the ctrom to help with descs.'''
    AM = inst.AddressingMode

    routine: assemble.ASMList = [
        inst.LDY(0x0000, AM.IMM16),
        'START',
        inst.LDA(0x37, AM.DIR_24_Y),
        inst.CMP(0xEF, AM.IMM8),
        inst.BEQ('END'),
        inst.INY(),
        inst.CPY(max_length, AM.IMM16),
        inst.BCC('START'),
        'END',
        inst.TYA(),
        inst.RTL()
    ]

    routine_b = assemble.assemble(routine)

    space_man = ct_rom.rom_data.space_manager
    start = space_man.get_free_addr(len(routine_b), 0x410000)

    ct_rom.rom_data.seek(start)
    ct_rom.rom_data.write(
        routine_b, ctrom.freespace.FSWriteType.MARK_USED
    )

    return start


def add_get_desc_char(ct_rom: ctrom.CTRom,
                      desc_start: int,
                      desc_size: int = 0x28):
    '''
    Add a character to string handling to fetch a description.
    '''

    AM = inst.AddressingMode
    SR = inst.SpecialRegister

    strlen_start = add_strlen_func(ct_rom, desc_size)

    rom_start = byteops.to_rom_ptr(desc_start)
    routine: assemble.ASMList = [
        inst.REP(0x20),
        inst.LDA(0x7F0200, AM.LNG),
        inst.AND(0x00FF, AM.IMM16),
        inst.SEP(0x20),
        inst.STA(SR.WRMPYA, AM.ABS),
        inst.LDA(desc_size, AM.IMM8),
        inst.STA(SR.WRMPYB, AM.ABS),
        inst.NOP(),
        inst.CLC(),
        inst.REP(0x20),
        inst.LDA(SR.RDMPYL, AM.ABS),
        inst.ADC(rom_start & 0x00FFFF, AM.IMM16),
        inst.STA(0x0237, AM.ABS),  # Memory for start of substring addr
        inst.SEP(0x20),
        inst.LDA(rom_start >> 16, AM.IMM8),
        inst.STA(0x0239, AM.ABS),
        inst.JSL(byteops.to_rom_ptr(strlen_start)),
        inst.STA(0x023A, AM.ABS),
        inst.LDA(0x01, AM.IMM8),
        inst.STA(0x30, AM.DIR),  # 0x000230
        # Copying without truly understanding.
        inst.LDA(0x00, AM.IMM8),
        inst.XBA(),
        inst.JMP(0xC25BF5, AM.LNG)
    ]

    # snippet = assemble.ASMSnippet(routine)
    # print(snippet)

    routine_b = assemble.assemble(routine)

    rom = ct_rom.rom_data
    new_start = rom.space_manager.get_free_addr(
        len(routine_b), hint=0x020000
    )

    # print(f'{new_start:06X}')

    if new_start >> 16 != 0x02:
        raise ValueError

    rom.seek(new_start)
    rom.write(routine_b, ctrom.freespace.FSWriteType.MARK_USED)

    # We are going to alter unused symbol 0x01
    ctstr_jump_table_st = 0x025903
    rom.seek(ctstr_jump_table_st + 2)
    rom.write(int.to_bytes(new_start & 0xFFFF, 2, 'little'))


def ugly_hack_chest_str(ct_rom: ctrom.CTRom):
    '''
    Just overwrite the old chest string.
    '''
    rom = ct_rom.rom_data
    # orig_string = bytes.fromhex(
    #     '06 EF EF EF EF EF EF EF EF EF EF '
    #     'EF EF EF A6 C8 CD EF D5 EF 1F 02 00'
    # )

    new_string = bytes.fromhex(
        '06 A6 C8 CD EF D5 EF 1F DE 06 01 00'
    )
    rom.seek(0x1EFF0A)
    rom.write(new_string)


def apply_chest_text_hack(ct_rom: ctrom.CTRom,
                          item_db: Optional[itemdata.ItemDB]):
    '''
    Make treasure chests display an item's description.
    '''

    max_desc_len = 0x28
    
    start = write_desc_strings(ct_rom, item_db, max_desc_len)
    add_get_desc_char(ct_rom, start, max_desc_len)
    ugly_hack_chest_str(ct_rom)



def main():
    ct_rom = ctrom.CTRom.from_file('./ct.sfc')
    basepatch.mark_initial_free_space(ct_rom)
    ct_rom.make_exhirom()

    start = write_desc_strings(ct_rom)
    add_get_desc_char(ct_rom, start, 0x30)
    ugly_hack_chest_str(ct_rom)

    with open('./ct_mod.sfc', 'wb') as outfile:
        outfile.write(ct_rom.rom_data.getbuffer())


if __name__ == '__main__':
    main()
