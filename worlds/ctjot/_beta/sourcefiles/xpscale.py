
from byteops import to_little_endian as tle, to_rom_ptr
from ctrom import CTRom
from freespace import FSWriteType
import ctenums
import ctevent

# This is what happens to XP when an enemy is defeated
# $FD/ABD6 BF 00 5E CC LDA $CC5E00,x[$CC:5E85] <-- XP
# $FD/ABDA 18          CLC
# $FD/ABDB 6D 8C B2    ADC $B28C  [$7E:B28C]
# $FD/ABDE 8D 8C B2    STA $B28C  <-- Battle total XP

# Then at the end of battle
# $C1/F93E AE 8C B2    LDX $B28C  [$7E:B28C]
# $C1/F941 DA          PHX
# $C1/F942 9C 11 B3    STZ $B311  [$7E:B311] 
# stuff... I think all that matters is doing something to $B28C at this point
# in the code.

# $FD/ABE1 BF 02 5E CC LDA $CC5E02,x[$CC:5E87] <-- GP
# $FD/ABEF BF 06 5E CC LDA $CC5E06,x[$CC:5E8B] <-- TP


def double_xp(ctrom: CTRom, mem_addr: int = 0x7E287E):
    # rt asm
    '''
    C2 20             REP #$20
    AD 8C B2          LDA $B28C
    0A                ASL
    10 03             BPL 03
    A9 FF 7F          LDA #$7FFF
    8D 8C B2          STA $B28C
    AA                TAX
    E2 20             SEP #$20
    9C 11 B3          STZ $B311
    6B                RTL
    '''

    rt = bytearray.fromhex(
        'C2 20'              # REP #$20
        'AD 8C B2'           # LDA $B28C
        '0A'                 # ASL
        '10 03'              # BPL 03
        'A9 FF 7F'           # LDA #$7FFF
        '8D 8C B2'           # STA $B28C
        'AA'                 # TAX
        'AD DB B2'           # LDA $B2DB (Battle TP)
        '0A'                 # ASL
        '10 06'              # BPL 06
        'A9 FF 7F'           # LDA #$7FFF
        'EE DD B2'           # INC $B2DD <-- Orig does this, why?
        '8D DB B2'           # STA $B28C
        'E2 20'              # SEP #$20
        '9C 11 B3'           # STZ $B311
        '6B'                 # RTL
    )

    len_rt = len(rt)
    len_to_rtl = len_rt-1

    mem_bank = (mem_addr >> 16) << 16
    if mem_bank != 0x7E0000:
        raise ValueError('Address of flag must be in bank 7E')

    mem_offset = mem_addr % 0x10000
    mem_offset_b = tle(mem_offset, 2)
    # LDA ${mem_addr}
    check = (
        b'\xAD' + mem_offset_b +            # LDA ${mem_offset}
        b'\xD0\x05' +                       # BNE $05 (get to the doubling)
        b'\xAE\x8C\xB2' +                   # LDX #$B28C
        b'\x80' + bytearray([len_to_rtl])   # BRA #${len_to_rtl} (to RTL)
    )

    rt = check + rt

    fsrom = ctrom.rom_data
    space_man = fsrom.space_manager
    rt_addr = space_man.get_free_addr(len(rt))

    jsl_bytes = b'\x22' + tle(to_rom_ptr(rt_addr), 3)
    # the NOPs cover the last two bytes of the original STZ $B311
    hook = jsl_bytes + bytearray.fromhex('DA EA EA')

    fsrom.seek(0x01F93E)
    fsrom.write(hook)

    fsrom.seek(rt_addr)
    fsrom.write(rt, FSWriteType.MARK_USED)

    script = ctrom.script_manager.get_script(ctenums.LocID.LOAD_SCREEN)
    EF = ctevent.EF
    EC = ctevent.EC

    st_cmd = EC.assign_val_to_mem(0x100, 0x7F01CD, 2)
    pos = script.find_exact_command(st_cmd)

    new_cmd = EC.assign_val_to_mem(0, mem_addr, 1)
    script.insert_commands(new_cmd.to_bytearray(), pos)


def scale_xp(ctrom: CTRom, mem_addr: int, scale_factor: int):
    
    # ASM for integer scaling things
    '''
    AE 8C B2          LDX $B28C
    86 28             STX $28
    AE XX XX          LDX ${mem_addr}
    86 2A             STX $2A
    22 0B 90 C1       JSL $C1C90B
    AC 2C             LDX $2C
    8E 8C B2          STX $B28C
    9C 11 B3          STZ $B311
    6B                RTL
    '''
    rt = bytearray.fromhex(
        'AE 8C B2'
        '86 28'
        'AE 7F 28'  # Using 0x7E287F which is by luck in SRAM!
        '86 2A'
        '20 0B C9'
        'A6 2C'
        '8E 8C B2'
        '9C 11 B3'
        '6B'
    )
    fsrom = ctrom.rom_data
    space_man = fsrom.space_manager
    rt_addr = 0x01FFDF # space_man.get_free_addr(len(rt))

    # Replace the LDX, PHX (4 bytes) with the JSL (also 4 bytes)
    # The following STZ $B311 is part of the routine above, but the PHA is
    # not, so at the hook ($C1/F93E) we need
    '''
    22 XX XX XX       JSL ${rt addr}
    DA                PHX
    EA                NOP
    EA                NOP
    '''

    jsl_bytes = b'\x22' + tle(to_rom_ptr(rt_addr), 3)
    # the NOPs cover the last two bytes of the original STZ $B311
    hook = jsl_bytes + bytearray.fromhex('DA EA EA')
    
    fsrom.seek(0x01F93E)
    fsrom.write(hook)

    fsrom.seek(rt_addr)
    fsrom.write(rt, FSWriteType.MARK_USED)
