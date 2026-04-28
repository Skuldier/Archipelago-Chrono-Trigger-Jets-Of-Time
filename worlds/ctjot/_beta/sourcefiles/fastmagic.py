
from byteops import get_value_from_bytes, to_file_ptr
from ctenums import CharID, LocID
from ctrom import CTRom
import ctevent

import randosettings as rset
import randoconfig as cfg


def write_config(settings: rset.Settings, config: cfg.RandoConfig):

    if rset.GameFlags.UNLOCKED_MAGIC not in settings.gameflags:
        return

    techdb = config.tech_db

    control_headers = techdb.controls
    control_size = techdb.control_size

    # The 0x80 bit of the first byte of each control header controls whether
    # a tech requires magic to learn (single techs only). We will unset this
    # byte on all single techs so that a trip to spekkio is not required.

    # Single techs are 1 to 1+7*8
    for tech in range(1, 1+7*8+1):
        magic_byte = tech*control_size
        control_headers[magic_byte] &= 0x7F


def write_ctrom(ctrom: CTRom,
                settings: rset.Settings):
    # Not sure whether flag tests should be in randomize() or in the various
    # module process_ctrom routines
    if rset.GameFlags.UNLOCKED_MAGIC in settings.gameflags:
        magic_learners = [CharID.CRONO, CharID.MARLE,
                          CharID.LUCCA, CharID.FROG]

        # If UNLOCKED_MAGIC is enabled, then the techdb has set all single
        # techs to be non-magical for learning purposes.  Now we just need
        # to let the game know that everyone can learn their techs without
        # a visit to Spekkio.

        # The array in rom beginning at (default) 0x3FF951 gives says how many
        # techs a character can learn without visiting Spekkio.

        # Default Values: 03 03 03 FF 03 FF 00
        # Note: Magus is 00 but also comes with magic learned initially.

        rom_data = ctrom.rom_data

        rom_data.seek(0x3FF894)  # location of ptr to thresholds on rom
        thresh_ptr_bytes = rom_data.read(3)
        thresh_ptr = get_value_from_bytes(thresh_ptr_bytes)
        thresh_ptr = to_file_ptr(thresh_ptr)

        for x in magic_learners:
            rom_data.seek(thresh_ptr + x)
            # Set the threshold to 8.
            # 0xFF works here but confuses the dc flag into thinking that the
            # chars are not magic users.
            rom_data.write(b'\x08')

def add_tracker_hook(ct_rom: CTRom):
    # For the tracker:  Set the flag 0x7F00E1 & 0x02 to indicate
    # magic is learned
    script = ct_rom.script_manager.get_script(LocID.TELEPOD_EXHIBIT)
    EC = ctevent.EC

    hook_pos = script.get_function_start(0x0E, 4)
    set_flag_cmd = EC.set_bit(0x7F00E1, 0x02)
    script.insert_commands(set_flag_cmd.to_bytearray(), hook_pos)


# This is more in line with how the other randomizer functions work
def set_fast_magic_file(filename):
    with open(filename, 'r+b') as file:

        # This should give the start address for tech control headers no matter
        # how the rom has been messed with.
        # Default: 0x0C1BEB
        file.seek(0x01CBA1)
        control_ptr_bytes = file.read(3)
        control_ptr = get_value_from_bytes(control_ptr_bytes)
        control_ptr = to_file_ptr(control_ptr)

        magic_learners = [CharID.CRONO, CharID.MARLE,
                          CharID.LUCCA, CharID.FROG]

        for x in magic_learners:
            # Each control header is 11 bytes and each PC has 8 single techs
            # Then there's a blank 0th control header
            file.seek(control_ptr + (1+x*8)*11)

            for i in range(0, 8):
                # Resetting the 0x80 bit marks a tech as non-magical.
                # TP will accumulate regardless of magic learning provided the
                # next tech has the 0x80 bit unset.

                y = bytearray(file.read(1))
                y[0] &= 0x7F
                file.seek(-1, 1)
                file.write(y)
                file.seek(10, 1)  # 1 written byte + 10 after == 11 bytes

        # The remaining issue is the menu not displaying techs past a certain
        # tech level until magic is learned from Spekkio.

        # The array in rom beginning at (default) 0x3FF951 gives this threshold
        # Default Values: 03 03 03 FF 03 FF 00
        # Note: Magus is 00 but also comes with magic learned initially.

        file.seek(0x3FF894)  # location of ptr to thresh on rom
        thresh_ptr_bytes = file.read(3)
        thresh_ptr = get_value_from_bytes(thresh_ptr_bytes)
        thresh_ptr = to_file_ptr(thresh_ptr)

        for x in magic_learners:
            file.seek(thresh_ptr + x)
            # Set the threshold to 8.
            # 0xFF works here but confuses the dc flag into thinking that the
            # chars are not magic users.
            file.write(b'\x08')


def set_fast_magic(rom):

    # This should give the start address for tech control headers no matter
    # how the rom has been messed with.
    # Default: 0x0C1BEB
    control_ptr = get_value_from_bytes(rom[0x01CBA1:0x01CBA1+3])
    control_ptr = to_file_ptr(control_ptr)

    magic_learners = [CharID.CRONO, CharID.MARLE, CharID.LUCCA, CharID.FROG]

    for x in magic_learners:
        # Each control header is 11 bytes and each PC has 8 single techs
        # Then there's a blank 0th control header
        tech_ptr = control_ptr + (1+x*8)*11

        for i in range(0, 8):
            # Resetting the 0x80 bit marks a tech as non-magical for learning.
            # TP will accumulate regardless of magic learning as long as the
            # next tech has the 0x80 bit unset.
            rom[tech_ptr] &= 0x7F
            tech_ptr += 11

    # The remaining issue is the menu not displaying techs past a certain point
    # until magic is learned from Spekkio.

    # The array in rom beginning at (default) 0x3FF951 gives this threshold
    # Default Values: 03 03 03 FF 03 FF 00
    # Note: Magus is 00 but also comes with magic learned initially.

    thresh_ptr = get_value_from_bytes(rom[0x3FF894:0x3FF894+3])
    thresh_ptr = to_file_ptr(thresh_ptr)
    for x in magic_learners:
        # Set the threshold to 8
        rom[thresh_ptr + x] = 0x08
