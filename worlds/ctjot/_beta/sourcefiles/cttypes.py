'''
Experimental module exploring better ways to represent binary data on ROM.
'''
import abc
import inspect
import typing
from typing import Optional

import byteops
import ctenums
import ctrom

ValFilter = typing.Callable[[typing.Any, int], int]
# IntBase = typing.TypeVar('IntBase', bound=typing.Union[bool, int])
IntBase = typing.Union[typing.Type[int], typing.Type[bool]]
ByteOrder = typing.Literal['big', 'little']


class BytesProp(property):
    '''
    Implement masked byte getter/setters as an extension of property.  This
    allows for inspection of these types of properties.
    '''
    def __init__(self, start_idx: int, num_bytes: int = 1,
                 mask: Optional[int] = None,
                 byteorder: ByteOrder = 'little',
                 ret_type: IntBase = int,
                 input_filter: ValFilter = lambda self, val: val,
                 output_filter: ValFilter = lambda self, val: val):
        '''
        Constructs a property for getting/setting a masked range in BinaryData.

        Parameters:
        - start_idx (no default), num_bytes (defaults to 1): Get the bytes in
          range(start_idx, start_idx+num_bytes).
        - mask: integer with contiguous set bits.  Only the portion of the data
          corresponding to the set bits of mask are gotten/set. Defaults to
          0xFF.
        - byteorder: Indicates how range(start_idx, start_idx+num_bytes) should
          be interpreted before applying mask.  Defaults to 'little'.
        - ret_type: Type to return (derives from int).  Defaults to int.
        - input_filter: Method for massaging input when setting.  Assumed to
          be a method of BinaryData, so it is self, val -> val.  Defaults to
          do nothing.
        - output_filter: Method for massaging output when getting.  Similar to
          input_filter.  Defaults to do nothing.
        '''

        if mask is None:
            mask = (1 << 8*num_bytes) - 1

        # Store some state for fun (and the __str__ method)
        # Private because changing them won't change the underlying get/setter.
        self._start_idx = start_idx
        self._num_bytes = num_bytes
        self._mask = mask

        getter = self._make_getter(start_idx, num_bytes, mask, byteorder,
                                   ret_type, output_filter)
        setter = self._make_setter(start_idx, num_bytes, mask, byteorder,
                                   ret_type, input_filter)

        property.__init__(self, getter, setter)

    @staticmethod
    def _make_getter(start_idx: int, num_bytes: int, mask: int,
                     byteorder: ByteOrder, ret_type: typing.Type,
                     output_filter: ValFilter):
        '''
        Construct the getter function for a BytesProp.
        '''

        def getter(obj):
            val = byteops.get_masked_range(obj, start_idx,
                                           num_bytes, mask, byteorder)
            val = output_filter(obj, val)
            return ret_type(val)

        return getter

    @staticmethod
    def _make_setter(start_idx: int, num_bytes: int, mask: int,
                     byteorder: ByteOrder, ret_type: typing.Type,
                     input_filter: ValFilter):
        '''
        Construct the setter function for a BytesProp.
        '''
        def setter(obj, val):
            val = int(val)
            val = input_filter(obj, val)
            byteops.set_masked_range(obj, start_idx, num_bytes,
                                     mask, val, byteorder)

        return setter

    def __str__(self):
        '''
        Simple string method that gives the basic information about the
        property.
        '''
        ret_str = f'{self.__class__.__name__}: '
        st = self._start_idx
        end = self._start_idx + self._num_bytes
        ret_str += f'On range({st}, {end}) with mask {bin(self._mask)}'
        return ret_str


# These two functions exist so the properties can be used indepdendently of the
# implementation of the byte properties.
def bytes_prop(start_idx: int, num_bytes: int = 1,
               mask: Optional[int] = None,
               byteorder: ByteOrder = 'little',
               ret_type: IntBase = int,
               input_filter: ValFilter = lambda self, val: val,
               output_filter: ValFilter = lambda self, val: val):
    return BytesProp(start_idx, num_bytes, mask, byteorder, ret_type,
                     input_filter, output_filter)


def byte_prop(index: int,
              mask: Optional[int] = None,
              byteorder: ByteOrder = 'little',
              ret_type: IntBase = int,
              input_filter: ValFilter = lambda self, val: val,
              output_filter: ValFilter = lambda self, val: val):
    '''
    Special case of a bytes_prop that uses only one byte.
    '''
    return BytesProp(index, 1, mask, byteorder, ret_type,
                     input_filter, output_filter)


class RomRW(abc.ABC):
    '''
    Class which describes how to read data from a ROM (ctrom.CTRom) and write
    it back out.
    '''
    @abc.abstractmethod
    def read_data_from_ctrom(self,
                             ct_rom: ctrom.CTRom,
                             num_bytes: int,
                             record_num: int = 0) -> bytes:
        '''
        Read num_bytes bytes from a ctrom.CTRom.  If the data is arranged in
        records, read record number record_num.
        '''

    @abc.abstractmethod
    def write_data_to_ct_rom(self,
                             ct_rom: ctrom.CTRom,
                             data: bytes,
                             record_num: int = 0):
        '''
        Write data to a ctrom.CTRom.  If the target data is arranged in
        records of length len(data), write to record number record_num.
        '''
        pass

    @abc.abstractmethod
    def free_data_on_ct_rom(self, ct_rom: ctrom.CTRom,
                            num_bytes: int, record_num: int = 0):
        '''
        Mark the data on the ROM that would be read/written as free
        '''
        pass


class AbsPointerRW(RomRW):
    '''
    Class to read BinaryData from a ROM when the data's location is given by
    an absolute (3 byte) pointer on the ROM.
    '''
    def __init__(self, abs_file_ptr):
        self.abs_file_ptr = abs_file_ptr

    def get_data_start_from_ctrom(self, ct_rom: ctrom.CTRom) -> int:
        rom = ct_rom.rom_data
        rom.seek(self.abs_file_ptr)
        rom_ptr = int.from_bytes(rom.read(3), 'little')
        file_ptr = byteops.to_file_ptr(rom_ptr)
        return file_ptr

    def read_data_from_ctrom(self, ct_rom: ctrom.CTRom,
                             num_bytes: int,
                             record_num: int = 0) -> bytes:
        '''
        Use the absolute pointer on the ROM to read data.
        '''
        start = self.get_data_start_from_ctrom(ct_rom)
        ct_rom.rom_data.seek(start + num_bytes*record_num)
        return ct_rom.rom_data.read(num_bytes)

    def write_data_to_ct_rom(self, ct_rom: ctrom.CTRom,
                             data: bytes,
                             record_num: int = 0):
        '''
        Use the absolute pointer on the rom to write data.
        '''
        mark_used = ctrom.freespace.FSWriteType.MARK_USED
        start = self.get_data_start_from_ctrom(ct_rom)
        ct_rom.rom_data.seek(start + len(data)*record_num)
        ct_rom.rom_data.write(data, mark_used)

    def free_data_on_ct_rom(self, ct_rom: ctrom.CTRom, num_bytes,
                            record_num: int = 0):
        '''
        Use the absolute pointer on the rom to free data.
        '''
        mark_free = ctrom.freespace.FSWriteType.MARK_FREE
        start = self.get_data_start_from_ctrom(ct_rom) + num_bytes*record_num
        ct_rom.rom_data.space_manager.mark_block(
            (start, start+num_bytes), mark_free
        )


class LocalPointerRW(RomRW):
    '''
    Class that extends RomRW by reading a bank and offset from a rom to
    read and write data.

    Sometimes there is no pointer directly to the data we want because it's
    part of a larger write.  In this case, parameter shift can be used.
    Example:
    $C2/9583 A2 00 00    LDX #$0000
    ...
    $C2/958C 54 7E CC    MVN CC 7E
    This indirectly holds the pointer for tech levels.  The tech level bytes
    only begin after 0x230 bytes.  So to grab the tech levels, we would call
    LocalPointerRW(0x029584, 0x02958E, 0x230)
    '''
    def __init__(self, bank_ptr: int, offset_ptr: int, shift: int = 0):
        self.bank_ptr = bank_ptr
        self.offset_ptr = offset_ptr
        self.shift = shift

    def get_data_start_from_ctrom(self, ct_rom: ctrom.CTRom) -> int:
        rom = ct_rom.rom_data
        rom.seek(self.offset_ptr)
        offset = int.from_bytes(rom.read(2), 'little')

        rom.seek(self.bank_ptr)
        bank = int(rom.read(1)[0]) * 0x10000

        rom_ptr = bank + offset + self.shift
        return byteops.to_file_ptr(rom_ptr)

    def read_data_from_ctrom(self, ct_rom: ctrom.CTRom,
                             num_bytes: int,
                             record_num: int = 0) -> bytes:
        '''
        Use the bank and offset pointers on the rom to read the data.
        '''
        start = self.get_data_start_from_ctrom(ct_rom)
        ct_rom.rom_data.seek(start + num_bytes*record_num)
        return ct_rom.rom_data.read(num_bytes)

    def write_data_to_ct_rom(self, ct_rom: ctrom.CTRom,
                             data: bytes,
                             record_num: int = 0):
        '''
        Use the bank and offset pointers on the rom to write data.
        '''
        mark_used = ctrom.freespace.FSWriteType.MARK_USED
        start = self.get_data_start_from_ctrom(ct_rom)
        ct_rom.rom_data.seek(start + len(data)*record_num)
        ct_rom.rom_data.write(data, mark_used)

    def free_data_on_ct_rom(self, ct_rom: ctrom.CTRom, num_bytes,
                            record_num: int = 0):
        mark_free = ctrom.freespace.FSWriteType.MARK_FREE
        start = self.get_data_start_from_ctrom(ct_rom)
        start += num_bytes*record_num
        ct_rom.rom_data.space_manager.mark_block(
            (start, start+num_bytes), mark_free
        )


T = typing.TypeVar('T', bound='BinaryData')


class BinaryData(bytearray):
    '''
    Class for representing binary data on a ROM.

    Includes methods for getting/setting bytes with a mask applied which are
    used by BytesProp for generating properties.
    '''
    SIZE: typing.Optional[int] = None
    ROM_RW: typing.Optional[RomRW] = None

    @classmethod
    def get_bytesprops(cls):
        '''
        Dummy classmethod for inspecting BytesProp objects just to show how it
        can be done.
        '''
        def is_bytesprop(x):
            return isinstance(x, BytesProp)

        bytes_props = [
            name for (name, value)
            in inspect.getmembers(cls, is_bytesprop)
        ]

        for name in bytes_props:
            prop_str = str(getattr(cls, name))
            print(f'{name}: {prop_str}')

        return bytes_props

    @classmethod
    def read_from_ctrom(cls: typing.Type[T],
                        ct_rom: ctrom.CTRom,
                        record_num: int = 0,
                        num_bytes: typing.Optional[int] = None,
                        rom_rw: typing.Optional[RomRW] = None) -> T:
        if num_bytes is None:
            if cls.SIZE is None:
                raise ValueError("Cannot read with unknown (None) size")
            num_bytes = cls.SIZE

        if rom_rw is None:
            if cls.ROM_RW is None:
                raise ValueError("No RomRW specified.")
            rom_rw = cls.ROM_RW

        return cls(
            rom_rw.read_data_from_ctrom(ct_rom, num_bytes, record_num)
        )

    def write_to_ctrom(
            self, ct_rom: ctrom.CTRom,
            record_num: int = 0,
            rom_rw: typing.Optional[RomRW] = None):

        if rom_rw is None:
            if self.ROM_RW is None:
                raise ValueError("No ROM_RW set")
            rom_rw = self.ROM_RW

        rom_rw.write_data_to_ct_rom(ct_rom, self, record_num)

    def free_data_on_ct_rom(
            self, ct_rom: ctrom.CTRom,
            record_num: int = 0,
            rom_rw: typing.Optional[RomRW] = None):
        if rom_rw is None:
            if self.ROM_RW is None:
                raise ValueError("No ROM_RW set")
            rom_rw = self.ROM_RW

        rom_rw.free_data_on_ct_rom(ct_rom, len(self), record_num)

    @classmethod
    def _get_default_value(cls) -> bytearray:
        if cls.SIZE is None:
            return bytearray()

        return bytearray(cls.SIZE)

    def __init__(self, *args, **kwargs):
        if not args and not kwargs:
            init_data = self._get_default_value()
            bytearray.__init__(self, init_data)
        else:
            bytearray.__init__(self, *args, **kwargs)
        self.validate_data(self)

    @classmethod
    def validate_data(cls: typing.Type[T], data: T):
        if data.SIZE is not None and len(data) != cls.SIZE:
            raise ValueError(
                f'Given data has length {len(data)} (Needs {cls.SIZE}).'
            )

    def get_copy(self: T) -> T:
        return type(self)(self)

    def __str__(self):
        ret_str = f'{self.__class__.__name__}: '
        ret_str += ' '.join(f'{x:02X}' for x in self)
        return ret_str


# This is just so that I don't have to check None on everything.
class SizedBinaryData(BinaryData):
    SIZE: int = 1


class TestBin(BinaryData):

    # filter for constraining values to range(0, 8)
    def test_filter(self, val):
        new_val = sorted([0, val, 0x7])[1]
        if new_val != val:
            print(f'Clamped to {new_val}')
        return new_val

    # A bogus example where the middle eight bits of the first two bytes are
    # encoding an item_id.
    # When setting the property, the input is increased by 1 by test_filter
    test_prop = bytes_prop(0, 2, 0x0FF0,
                           byteorder='big',
                           ret_type=ctenums.ItemID)

    # mimicking Rythrix's battle speed property
    # could be lambda obj, val: sorted([0, val, 7])[1]
    test2 = byte_prop(0, 0xE0, input_filter=test_filter)

    # mimicking Rythyrix's stereo audio property
    # filters negate the values so set means False and unset means True
    stereo_audio = byte_prop(0, 0x10,
                             ret_type=bool,
                             input_filter=lambda self, val: not val,
                             output_filter=lambda self, val: not val)

    test3 = byte_prop(2, 0x0F)

    @property
    def not_byteprop(self):
        return self[0]

    @not_byteprop.setter
    def not_byteprop(self, val):
        self[0] = val


def main():

    # Note that not_byteprop gets left out of the output because it was not
    # created with the BytesProp class.
    TestBin.get_bytesprops()

    test = TestBin(b'\x00\x00')
    print(test.test3)
    test.test3 = 5
    test.not_byteprop = 7
    print(test.test3)
    print(test)


if __name__ == '__main__':
    main()
