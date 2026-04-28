'''Collection of routines for operating on bytearrays'''

import typing

def get_record(data, index, record_size):
    return data[index*record_size:(index+1)*record_size]


def set_record(data, new_record, index, record_size):
    start = index*record_size
    data[start:start+record_size] = new_record


def print_bytes(data, row_size):
    for index, val in enumerate(data):
        if index % row_size == 0:
            print("%2.2X:  " % (index//row_size), end='')
        print("%2.2X" % (val), end=' ')
        if index % row_size == row_size-1:
            print('', end='\n')
        elif index+1 == len(data):
            print('')


def to_little_endian(value, num_bytes):
    # I'd delete this, but to avoid breaking code, just call the python
    # function that I didn't know about way back then.
    return int.to_bytes(value, num_bytes, 'little')


def get_value_from_bytes(byte_arr):
    # I'd delete this, but to avoid breaking code, just call the python
    # function that I didn't know about way back then.
    return int.from_bytes(byte_arr, 'little')


def get_value_from_bytes_be(byte_arr):
    # I'd delete this, but to avoid breaking code, just call the python
    # function that I didn't know about way back then.
    return int.from_bytes(byte_arr, 'big')


# Pointers/addresses in the game code to the rom are not the same as file
# locations.  This helper function turns pointers in game code into file
# pointers.
def to_file_ptr(ptr):
    if 0xC00000 <= ptr <= 0xFFFFFF:
        # The [0xC00000, 0xFFFFFF] range maps to [0x000000,0x3FFFFF]
        return ptr - 0xC00000
    elif 0x400000 <= ptr <= 0x5FFFFF:
        # Extended rom area [0x400000,0x5FFFFF] maps normally
        return ptr
    else:
        print("Warning: ptr %6.6X out of rom range. Not changing." % ptr)
        return ptr


# inverse of to_file_ptr.  Turn file pointers into snes/rom pointers.
def to_rom_ptr(ptr):
    if 0x000000 <= ptr <= 0x3FFFFF:
        # The [0xC00000, 0xFFFFFF] range maps to [0x000000,0x3FFFFF]
        return ptr + 0xC00000
    elif 0x400000 <= ptr <= 0x5FFFFF:
        # Extended rom area [0x400000,0x5FFFFF] maps normally
        return ptr
    else:
        print("Warning: ptr %6.6X out of rom range. Not changing." % ptr)
        return ptr


# Function used when repointing rom data.  Update a list of pointers to point
# relative to a new start.
# ptr_list is a list of addresses (write locations) in the rom file/bytearray
def update_ptrs(rom, ptr_list, old_start, new_start):
    for ptr in ptr_list:
        addr = get_value_from_bytes(rom[ptr:ptr+3])

        # print('%X, %X' % (ptr, addr))

        # remap snes pointer to file pointer
        addr = to_file_ptr(addr)

        offset = addr-old_start
        new_ptr = to_rom_ptr(new_start+offset)

        # print('%x' % new_ptr)
        new_ptr_bytes = to_little_endian(new_ptr, 3)

        rom[ptr:ptr+3] = new_ptr_bytes[0:3]


# When you just need starts and offsets to determine the new pointer.
# Each ptr in ptr_list is known to be an offset (list offsets param)
# from a given start location (start param)
def change_ptrs(rom, ptr_list, start, offsets, num_bytes=3):

    # Maybe verify ptr_list and offsets are the same length?
    for i in range(len(ptr_list)):
        rom_loc = ptr_list[i]

        new_val = to_little_endian(to_rom_ptr(start + offsets[i]), num_bytes)
        rom[rom_loc:rom_loc+num_bytes] = new_val[:]
        # print('%x' % to_rom_ptr(start + offsets[i]))


# Reads an n-byte ptr from the rom at a given addr (file relative).  The read
# pointer is then converted to a file pointer and returned.
# Yes it feels weird having a one line function, but it gets used frequently.
def file_ptr_from_rom(rom, addr, num_bytes=3):
    return to_file_ptr(get_value_from_bytes(rom[addr:addr+num_bytes]))


def get_minimal_shift(mask: int):
    '''
    Find the minimal N such that (mask/2^N % 1) != 0.
    '''
    
    # Put the binary string in reverse, and chop off the '0b' from the
    # start.
    try:
        return bin(mask)[:1:-1].index('1')
    except ValueError as orig:  # Give a more reasonable ValueError
        raise ValueError('Mask must be nonzero.') from orig


def get_masked_range(data: bytes, start_idx: int, num_bytes: int,
                     mask: int,
                     byteorder: typing.Literal['big', 'little'] = 'little'
                     ) -> int:
    '''
    Return the bytes in range(start_idx, start_idx+num_bytes) with
    mask applied.

    More precisely, this
    1) Reads the bytes in range(start_idx, start_idx+num_bytes) as in
      integer with the given byteorder.
    2) Applies the mask to the integer.  In some sense this means the 
       mask is big-endian.  The mask must have only consecutive bytes set.
    3) Returns the masked bits as an integer.

    Example (from the DB):
    Location Exit	03	01FF	2	Destination Location
        To get this range, you read bytes 3, 4 as a little-endian and then
        apply the mask 0x1FF.  The actual bytes read are Bytes 3.FF and 4.01.
        get_masked_range(self, 3, 2, 0x1FF, 'little')
    '''
    val = int.from_bytes(data[start_idx:start_idx+num_bytes], byteorder)
    val &= mask
    val >>= get_minimal_shift(mask)
    return val


def set_masked_range(data: bytearray, start_idx: int, num_bytes: int,
                     mask: int, val: int,
                     byteorder: typing.Literal['big', 'little'] = 'little'
                     ):
    '''
    Set the bytes in range(start_idx, start_idx+num_bytes) corresponding
    to bits set in mask to val.  Dual to get_masked_range such that
        set_masked_range(start, n, mask, val, byteorder)
        new_val = get_masked_range(start, n, mask, byteorder)
    will have new_val == val.

    More precisely, this
    1) Reads the bytes in range(start_idx, start_idx+num_bytes) as in
       integer with the given byteorder.  Python treats this as big-endian.
    2) Write val (as big-endian) into the bits ste by mask.
    3) Write the bytes back into self.

    Example (from the DB):
    Location Exit	03	01FF	2	Destination Location
        To set this range, you read bytes 3, 4 as a little-endian int, write
        a big-endian value into the 0x1FF bits, and write the result as
        little-endian bytes into bytes 3 and 4.
        set_masked_range(self, 3, 2, 0x1FF, set_val, 'little')
    '''
    shift = get_minimal_shift(mask)
    max_val = mask >> shift  # assuming contiguous mask

    if not 0 <= val <= max_val:
        raise ValueError(
            f'Value must be in range({max_val+1:0{2*num_bytes}X})'
        )

    inv_mask = (1 << (num_bytes*8)) - mask - 1
    cur_val = int.from_bytes(data[start_idx: start_idx+num_bytes],
                             byteorder)
    cur_val &= inv_mask
    cur_val |= (val << shift)

    data[start_idx:start_idx+num_bytes] = \
        cur_val.to_bytes(num_bytes, byteorder)
