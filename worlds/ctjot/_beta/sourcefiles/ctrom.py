import hashlib

import ctevent
import freespace


class InvalidRomException(Exception):
    pass


class RomFormatException(Exception):
    pass


# CTRom is just a combination FSRom and ScriptManager
# It needs to have all of the information that other modules need to make
# freespace-aware changes to the rom.
# The driving need here is that a randoconfig.ChestTreasure only needs the
# rom data to make a change but a randoconfig.ScriptTreasure needs the rom
# and mechanisms for manipulating scripts.
class CTRom():

    def __init__(self, rom: bytes, ignore_checksum=False):
        # ignore_checksum is so that I can load already-randomized roms
        # if need be.
        if not ignore_checksum and not CTRom.validate_ct_rom_bytes(rom):
            raise InvalidRomException('Bad checksum.')

        self.rom_data = freespace.FSRom(rom, False)
        self.script_manager = ctevent.ScriptManager(self.rom_data, [])

    @classmethod
    def from_file(cls, filename: str, ignore_checksum=False):
        with open(filename, 'rb') as infile:
            rom_bytes = infile.read()

        return cls(rom_bytes, ignore_checksum)

    def write_all_scripts_to_rom(self, clear_scripts: bool = True):
        script_dict = self.script_manager.script_dict
        for loc_id in script_dict:
            self.script_manager.write_script_to_rom(loc_id)

        if clear_scripts:
            self.script_manager.script_dict = {}
            self.script_manager.orig_len_dict = {}

    @staticmethod
    def validate_ct_rom_file(filename: str) -> bool:
        with open(filename, 'rb') as infile:
            hasher = hashlib.md5()

            infile.seek(0, 2)
            file_size = infile.tell()

            if file_size == 4194816:
                print('Header detected.')
                infile.seek(0x200)

            chunk_size = 8192

            infile.seek(0)
            chunk = infile.read(chunk_size)
            while chunk:
                hasher.update(chunk)
                chunk = infile.read(chunk_size)

            # print(f"\'{filename}\' hash: {hasher.hexdigest()}")
            # print('Known good hash: a2bc447961e52fd2227baed164f729dc')
            return hasher.hexdigest() == 'a2bc447961e52fd2227baed164f729dc'

    @staticmethod
    def validate_ct_rom_bytes(rom: bytes) -> bool:
        hasher = hashlib.md5()
        # Check if this is the size of a headered ROM.
        # If it is, strip off the header before hashing.
        if len(rom) == 4194816:
            rom = rom[0x200:]

        chunk_size = 8192
        start = 0

        while start < len(rom):
            hasher.update(rom[start:start+chunk_size])
            start += chunk_size

        return hasher.hexdigest() == 'a2bc447961e52fd2227baed164f729dc'

    def fix_snes_checksum(self):
        rom = self.rom_data

        if len(rom.getbuffer()) == 0x400000:
            exhirom = False
        elif len(rom.getbuffer()) == 0x600000:
            exhirom = True
        else:
            raise InvalidRomException('Invalid ROM size.')

        # Write dummy checksums that add up to 0xFFFF like they ought.
        rom.seek(0xFFDC)
        rom.write(int(0xFFFF0000).to_bytes(4, 'little'))

        if exhirom:
            rom.seek(0x40FFDC)
            rom.write(int(0xFFFF0000).to_bytes(4, 'little'))

        def get_checksum(byte_seq: bytes) -> int:
            # return functools.reduce(
            #     lambda x, y: (x+y) % 0x10000,
            #     byte_seq,
            #     0
            # )
            return sum(byte_seq) % 0x10000

        # Compute the checksum of the first 0x400000
        checksum = get_checksum(self.rom_data.getbuffer()[0:0x400000])

        # Compute twice the expanded 2MB if exhirom
        if exhirom:
            checksum += 2*get_checksum(rom.getbuffer()[0x400000:0x600000])
            checksum = checksum % 0x10000

        inverse_checksum = checksum ^ 0xFFFF
        checksum_b = inverse_checksum.to_bytes(2, 'little') + \
            checksum.to_bytes(2, 'little')

        # Write correct checksum out
        rom.seek(0xFFDC)
        rom.write(checksum_b)

        # Mirror in bank 0x40 if exhirom
        if exhirom:
            rom.seek(0x40FFDC)
            rom.write(checksum_b)

    def make_exhirom(self):
        '''
        Turns a HiROM CTRom into an ExHiROM CTRom.

        Throws an exception if the rom is not HiROM
        '''

        rom = self.rom_data

        def header_is_hirom(buffer) -> bool:
            if buffer[0xFFD5] != 0x31 or buffer[0xFFD7] != 0x0C:
                print('asdf')
                return False
            return True

        if len(rom.getbuffer()) != 0x400000 or \
           not header_is_hirom(rom.getbuffer()):
            raise RomFormatException('Existing ROM not HiRom')

        # ROM type:  Old value was 0x31 - HiROM + fastrom
        #            New value is  0x35 for ExHiROM
        rom.seek(0xFFD5)
        rom.write(b'\x35')

        # ROM size:  Old value was 0x0C - 4Mbit (why?)
        #            New value is  0x0D
        # I don't know how the value is determined, but ok.
        rom.seek(0xFFD7)
        rom.write(b'\x0D')

        FSW = freespace.FSWriteType
        # Mirror [0x008000, 0x010000) to [0x408000, 0x410000)
        rom.seek(0x008000)
        mirror_bytes = rom.read(0x8000)

        # 00s to [0x400000, 0x408000)
        rom.seek(0x400000)
        rom.write(b'\x00' * 0x8000, FSW.MARK_FREE)
        # Mirror
        rom.write(mirror_bytes, FSW.MARK_USED)
        rom.write(b'\x00' * 0x1F0000, FSW.MARK_FREE)

        self.fix_snes_checksum()


def main():
    pass


if __name__ == '__main__':
    main()
