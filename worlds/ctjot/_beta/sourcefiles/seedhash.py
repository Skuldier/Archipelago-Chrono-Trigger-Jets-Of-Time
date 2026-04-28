'''Module for putting a seed hash on the Active/Wait screen.'''
import hashlib

import ctrom
import ctstrings

def calculate_hash_string(ct_rom: ctrom.CTRom) -> bytes:
    rom = ct_rom.rom_data

    rom.seek(0)
    seed = rom.read()

    hasher = hashlib.md5()
    hasher.update(seed)
    hex_str = hasher.hexdigest()

    symbols = [0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x29,
               0x2E, 0x2F]

    num_symbols = 8  # Num symbols to put in hash string, not len(symbols)
    hash_string = []
    num = int(hex_str, base=16)
    for _ in range(num_symbols):
        num, rem = divmod(num, len(symbols))
        hash_string.append(symbols[rem])

    return bytes(hash_string)

def write_hash_string(ct_rom: ctrom.CTRom) -> bytes:
    ''' Puts a hash string on the active/wait screen of this ctrom.'''
    hash_string = calculate_hash_string(ct_rom)

    seed_ctstr = ctstrings.CTString.from_str('Seed:')

    # There's a script for laying out layer1 tiles.
    new_menu_script = bytes.fromhex(
        '0A 11'  # Change page of VRAM to 0x11
        '80 81 82 83 84 85 86 87 88 89 8A 8B'  # BattleMode top
        '01'  # next line
        '8C 8D 8E 8F 90 91 92 93 94 95 96 97'  # BattleMode mid
        '01'  # next line
        '98 99 9A 9B 9C 9D 9E 9F A0 A1 A2 A3'  # BattleMode bot
        '01'  # next line
        '0A 01'  # Change to page 0x01
        '02 9A 01'  # Change to location 0x019A
        'A4 A5 A6 A7 A8 A9'  # Active Time
        '01'  # next line
        'AA AB AC AD AE AF'  # Battle ver.2
        '0A 00'  # Change to page 0x00 (characters)
        '02 DA 02'  # Change to location 0x02DA
        'A0 A2 B3 A8 B5 A4'  # Active
        '01'
        '01'  # next line x 2
        'FF B6 A0 A8 B3'  # (space)Wait
        '02 42 00'  # 2nd line 2nd tile
        + seed_ctstr.hex() + hash_string.hex() +  # Seed string
        '0A 03'  # Change to page 0x03 (menu stuff)
        '02 00 00'  # Top left
        'AC'  # grey square
        '02 3E 00'  # Top right
        'AC'  # grey square
        '02 3E 07'  # Bot right
        'AC'  # grey square
        '02 00 07'  # Bot left
        'AC'  # grey square
        '00'  # end
    )

    # The menu data needs to be in bank 0x3F.  It would be a pain to relocate.
    # The data in [0x3FFC67, 0x400000) is suspected junk.  I can't get the
    # game to rwx anything in this range, but to be safe we'll put it as far
    # to the end as possible.

    new_loc = 0x400000 - len(new_menu_script)

    rom = ct_rom.rom_data

    rom.seek(0x3FC49F)
    rom.write(int.to_bytes(new_loc & 0xFFFF, 2, 'little'))

    rom.seek(new_loc)
    rom.write(new_menu_script)

    new_hdma = bytes.fromhex('50 FF FF 30 03 00 30 07 00 00')
    new_hdma = bytes([len(new_hdma)]) + new_hdma
    new_hdma_loc = new_loc - len(new_hdma)

    rom.seek(0x3FC442)
    rom.write(int.to_bytes(new_hdma_loc % 0x10000, 2, 'little'))

    rom.seek(new_hdma_loc)
    rom.write(new_hdma)

    return hash_string
