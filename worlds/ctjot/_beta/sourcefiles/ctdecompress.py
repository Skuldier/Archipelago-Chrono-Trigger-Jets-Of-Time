# Copied from Gieger's (Michael Springer, evilpeer@hotmail.com) C version
from byteops import get_value_from_bytes, to_little_endian
from typing import ByteString

# ctcompress is the fast C library.  If it's not present, use the python
# implementation.
try:
    from ctcompress import compress
    # print('Using C compression implementation.')
except ImportError:
    # print('C compression module not found.  Falling back to python.')
    def compress(source: bytearray) -> bytearray:
        return compress_py_2(source)


def decompress(rom, start):
    out_buffer = bytearray([0 for i in range(0, 0x10000)])

    # First two bytes are little endian size of compressed packet
    main_len = get_value_from_bytes(rom[start:start+2])

    # print(f"Start position: {start:06X}")
    # print(f"Main body length: {main_len:04X}")
    # print(f"Max compr length: {len(rom[start:]):04X}")

    out_pos = 0
    src_pos = start+2

    add_byte = src_pos + main_len

    if rom[add_byte] & 0xC0 != 0:
        smallwidth = True
    else:
        smallwidth = False

    end_pos = add_byte

    while True:
        # First check if we've passed the main body
        if src_pos == end_pos:
            # print(f"End pos: {end_pos:06X}")
            # print(f"Addendum byte: {rom[src_pos]:02X}")
            if rom[src_pos] & 0x3F == 0:
                # No addendum
                # print(f"Compressed Size: {end_pos-start:04X}")
                return out_buffer[0:out_pos]
            else:
                # Addendum, new end in next two bytes
                end_pos = \
                    start + get_value_from_bytes(rom[src_pos+1:src_pos+3])
                # print(' '.join(f"{x:02X}"
                #                for x in rom[src_pos+1:src_pos+3]))
                # print(f"Addendum found, new end pos = {end_pos:04X}")
                src_pos += 3  # Get to the byte after the new end byte

        # print(f"[{out_pos:04X}] Getting new packet.")
        header = rom[src_pos]
        src_pos += 1
        # input()

        for i in range(8):
            if src_pos == end_pos:
                # ran out of data mid packet (in addendum)
                break
            elif header & (1 << i) == 0:
                # Uncompressed, copy next byte
                out_buffer[out_pos] = rom[src_pos]
                out_pos += 1
                src_pos += 1
            else:
                # Compressed, determine copy size and offset

                copy_size = rom[src_pos+1]
                copy_off = get_value_from_bytes(rom[src_pos:src_pos+2])

                if smallwidth:
                    copy_size >>= 3
                    copy_off &= 0x07FF
                else:
                    copy_size >>= 4
                    copy_off &= 0x0FFF

                copy_size += 3
                for j in range(0, copy_size):
                    try:
                        out_buffer[out_pos + j] = \
                            out_buffer[out_pos - copy_off + j]
                    except IndexError:

                        # print(out_pos + j)
                        exit()

                out_pos += copy_size
                src_pos += 2


# Find the length of a compressed packet
def get_compressed_length(rom: ByteString, addr: int):

    # First two bytes determine length of main body
    main_length = get_value_from_bytes(rom[addr:addr+2])

    # print(f"Start position: {addr:06X}")
    # print(f"Main body length = 0x{main_length:04X}")

    # len main body + main body + addendum byte
    compr_len = 2 + main_length + 1
    add_byte_addr = addr + compr_len - 1

    while rom[add_byte_addr] & 0x3F != 0:
        # print(f"Addendum byte: {rom[add_byte_addr]: 02X}")
        compr_len = get_value_from_bytes(rom[add_byte_addr+1:add_byte_addr+3])
        # print(' '.join(f"{x:02X}"
        #                 for x in rom[add_byte_addr:add_byte_addr+3]))
        add_byte_addr = addr + compr_len
        # Perhaps add logic here to make sure the addendum size is within
        # reason.  There are some bad packets out there.

        # print(f"Compressed len = {compr_len:04X}")
    return compr_len + 1


# Just isolate a compressed packet starting at a certain address
def get_compressed_packet(rom: ByteString, addr):
    return rom[addr:addr+get_compressed_length(rom, addr)]


# Mostly copied directly from Geiger's code.
# Not using this implementation anymore.
def decompress_geiger(rom, nStartAddr):

    WorkingBuffer = bytearray([0 for i in range(0, 0x10000)])

    bCarryFlag = False

    # First two bytes are little endian size of compressed packet
    nCompressedSize = get_value_from_bytes(rom[nStartAddr:nStartAddr+2])

    print('Compressed Size: %X' % nCompressedSize)

    nBytePos = nStartAddr + 2
    nByteAfter = nBytePos + nCompressedSize

    nWorkPos = 0
    bSmallerBitWidth = False

    if rom[nByteAfter] & 0xC0 != 0:
        bSmallerBitWidth = True

    nBitCtr = 8
    while True:
        # print('%X' % nBytePos)
        if nBytePos == nByteAfter:
            nCurByte = rom[nBytePos]
            nCurByte &= 0x3F
            print(f"End pos: {nByteAfter:06X}")
            print(f"Addendum byte: {rom[nBytePos]:02X}")

            if nCurByte == 0:
                print('No addendum')
                print(f"Compressed len = {nBytePos-nStartAddr:X}")
                return WorkingBuffer[0:nWorkPos]

            nBitCtr = nCurByte
            bCarryFlag = False

            nByteAfter = (nStartAddr
                          + get_value_from_bytes(rom[nBytePos+1:nBytePos+3]))

            print(f"Addendum found, new end pos = {nByteAfter:04X}")
            nBytePos += 3
        else:
            nCurByte = rom[nBytePos]
            # print('Header: %X' % nCurByte)
            if nCurByte == 0:
                nCurByte = rom[nBytePos + 1]
                WorkingBuffer[nWorkPos] = nCurByte
                nWorkPos += 1
                nCurByte = rom[nBytePos + 2]
                WorkingBuffer[nWorkPos] = nCurByte
                nWorkPos += 1
                nCurByte = rom[nBytePos + 3]
                WorkingBuffer[nWorkPos] = nCurByte
                nWorkPos += 1
                nCurByte = rom[nBytePos + 4]
                WorkingBuffer[nWorkPos] = nCurByte
                nWorkPos += 1
                nCurByte = rom[nBytePos + 5]
                WorkingBuffer[nWorkPos] = nCurByte
                nWorkPos += 1
                nCurByte = rom[nBytePos + 6]
                WorkingBuffer[nWorkPos] = nCurByte
                nWorkPos += 1
                nCurByte = rom[nBytePos + 7]
                WorkingBuffer[nWorkPos] = nCurByte
                nWorkPos += 1
                nCurByte = rom[nBytePos + 8]
                WorkingBuffer[nWorkPos] = nCurByte
                nWorkPos += 1
                bCarryFlag = False
                nBytePos += 9
            else:
                nBytePos += 1
                if nCurByte & 0x01 == 1:
                    bCarryFlag = True
                else:
                    bCarryFlag = False

                nCurByte >>= 1
                nMem0D = nCurByte
                if bCarryFlag:
                    nBytePos, nWorkPos = \
                        CTCopyBytes(rom,
                                    WorkingBuffer,
                                    nBytePos, nWorkPos, bSmallerBitWidth)
                else:
                    nCurByte = rom[nBytePos]
                    WorkingBuffer[nWorkPos] = nCurByte
                    nWorkPos += 1

                    nBytePos += 1

                while True:
                    nBitCtr -= 1

                    if nBitCtr == 0:
                        nBitCtr = 8
                        break
                    else:
                        if (nMem0D & 0x01) == 1:
                            bCarryFlag = True
                        else:
                            bCarryFlag = False

                        nMem0D >>= 1

                        if bCarryFlag:
                            nBytePos, nWorkPos = \
                                CTCopyBytes(rom,
                                            WorkingBuffer,
                                            nBytePos,
                                            nWorkPos,
                                            bSmallerBitWidth)
                        else:
                            nCurByte = rom[nBytePos]
                            WorkingBuffer[nWorkPos] = nCurByte
                            nWorkPos += 1

                            nBytePos += 1

    return WorkingBuffer


# Helper funtion for Geiger's implementation
def CTCopyBytes(rom, WorkingBuffer, nBytePos, nWorkPos,  bSmallerBitWidth):

    nBytesCopyNum = rom[nBytePos + 1]

    # print('bSmallerBitWidth ==', bSmallerBitWidth)

    if bSmallerBitWidth:
        nBytesCopyNum >>= 3
    else:
        nBytesCopyNum >>= 4

    nBytesCopyNum += 2
    nBytesCopyOff = get_value_from_bytes(rom[nBytePos:nBytePos+2])

    if bSmallerBitWidth:
        nBytesCopyOff &= 0x07FF
    else:
        nBytesCopyOff &= 0x0FFF

    # print('nBytesCopyNum: %X' % (nBytesCopyNum+1))
    # print('nBytesCopyOff: %X' % (nBytesCopyOff))

    for i in range(0, nBytesCopyNum+1):
        WorkingBuffer[nWorkPos + i] = \
            WorkingBuffer[nWorkPos - nBytesCopyOff + i]

    nWorkPos += nBytesCopyNum + 1
    nBytePos += 2

    # input()

    return nBytePos, nWorkPos


def find_match_len(data: bytes, pos_1: int, pos_2: int,
                   max_match: int):

    match_len = 0
    while data[pos_1+match_len] == data[pos_2+match_len]:
        match_len += 1

        if match_len == max_match:
            break

        if (pos_1 + match_len == len(data)) or \
           (pos_2 + match_len == len(data)):
            break

    return match_len


# Modification of compress_py which precomputes starting indices of every byte.
# This was suggested by Atmatek on
# https://www.ff6hacking.com/forums/thread-4085.html.
def compress_py_2(source: bytes) -> bytearray:
    # We have to try compressing in two configurations and then return the
    # better of the two.
    compressed_data = [bytearray([0 for i in range(0x10000)])
                       for j in range(2)]

    best_size = 0x10000

    byte_starts: list[list[int]] = [[] for ind in range(0x100)]
    for ind, byte in enumerate(source):
        byte_starts[byte].append(ind)

    byte_ptrs = [0 for ind in range(0x100)]

    # We're only going to use the i=0 version because it's almost always a
    # smaller file.
    for i in range(1):
        # i=0: use 0x07FF for the range, 0xF800 for the max copy length
        # i=1: use 0x0FFF for the range, 0xF000 for the max copy length
        lookback_range = 0x07FF | (i << 11)

        # max_copy_length = 0xFFFF ^ lookback_range (bits used)
        max_copy_length = (0xFFFF ^ lookback_range) >> (16-(5-i))
        max_copy_length += 3
        src_pos = 0

        # First two bytes are main body length
        # Next byte will be the first packet's header
        out_pos = 2

        done = False
        while not done:
            # Fill up a compressed packet
            header_pos = out_pos
            out_pos += 1

            for bit in range(8):
                # While filling a packet we ran out of source.
                if src_pos == len(source):
                    if bit == 0:
                        # If bit == 0, then we ran out after filling a packet.
                        # This means no addendum.
                        compressed_data[i][header_pos] = 0xC0*(1-i)

                        # Truncate to used size
                        compressed_data[i] = compressed_data[i][0:header_pos+1]
                    else:
                        # Otherwise, we're mid-packet.  The packet becomes
                        # the addendum.
                        # print("Addendum.")

                        # set unused bits of header for addendum header
                        mask = (0xFF << bit) & 0xFF
                        compressed_data[i][header_pos] |= mask

                        # shift the addendum packet down three bytes
                        compressed_data[i][header_pos+3:out_pos+3] = \
                            compressed_data[i][header_pos:out_pos]

                        # copy range + addendum length
                        compressed_data[i][header_pos] = \
                            0xC0*(1-i) | bit

                        # total compressed length (remember shift by 3)
                        compressed_data[i][header_pos+1:header_pos+3] = \
                            int.to_bytes(out_pos+3, 2, 'little')

                        # Truncate to used size
                        compressed_data[i][out_pos+3] = 0xC0*(1-i)
                        compressed_data[i] = compressed_data[i][0:out_pos+4]

                    # print(f"Main body len: {header_pos-2:04X}")
                    compressed_data[i][0:2] =\
                        int.to_bytes(header_pos-2, 2, 'little')

                    done = True
                    break

                lookback_st = max(0, src_pos - lookback_range)
                lookback_end = src_pos

                best_len = 0
                best_len_st = 0

                src_val = source[src_pos]
                while byte_starts[src_val][byte_ptrs[src_val]] < lookback_st:
                    byte_ptrs[src_val] += 1

                ptr = byte_ptrs[src_val]
                while byte_starts[src_val][ptr] < src_pos:
                    match_len = find_match_len(
                        source,
                        byte_starts[src_val][ptr],
                        src_pos,
                        max_copy_length
                    )

                    if match_len > best_len:
                        best_len = match_len
                        best_len_st = byte_starts[src_val][ptr]

                    ptr += 1

                if best_len > 2:
                    # print(f'Best len: {best_len:02X}')
                    # We matched at least 3 bytes, so we'll use compression

                    # Mark the header to use compression for this bit
                    compressed_data[i][header_pos] |= (1 << bit)

                    lookback = src_pos - best_len_st
                    # print(f"\tlookback: {lookback:04X}")

                    # length is encoded with a -3 because there are always at
                    # least 3 bytes to copy.  The length is shifted to the most
                    # significant bits.  The shift depends on i.
                    length = ((best_len-3) << (16-(5-i)))

                    compr_stream = lookback | length

                    compressed_data[i][out_pos:out_pos+2] = \
                        int.to_bytes(compr_stream, 2, 'little')

                    out_pos += 2
                    src_pos += best_len
                else:
                    # We failed to match 3 or more bytes, so just copy a byte
                    compressed_data[i][out_pos] = source[src_pos]
                    out_pos += 1
                    src_pos += 1
            # End of for loop to fill packet
            # print(f'Header: {compressed_data[i][header_pos]:02X}')
        # End of while not done loop

        if len(compressed_data[i]) < best_size:
            best_size = len(compressed_data[i])
            best_ind = i
        else:
            best_ind = 0

    # Test code for comparing performance of the two window schemes
    # if len(compressed_data[0]) < len(compressed_data[1]):
    #     min_len = len(compressed_data[0])
    #     max_len = len(compressed_data[1])
    #     best = "0"
    # elif len(compressed_data[1]) < len(compressed_data[0]):
    #     min_len = len(compressed_data[1])
    #     max_len = len(compressed_data[0])
    #     best = "1"
    # else:
    #     min_len = 1
    #     max_len = 1
    #     best = "Tie"

    # print(max_len/min_len, 'Best:', best)

    # if len(compressed_data[0]) <= len(compressed_data[1]):
    #     return compressed_data[0]
    # else:
    #     return compressed_data[1]

    return compressed_data[0]
    

# Modification of Michael Springer's code to fit my applications
# This is a greedy algorithm. On occassion it will be a byte (or two?) larger
# than the original game's compression.  This happens when you almost fill up
# the addendum packet but then have to add another 2 bytes for the compressed
# length prior to the addendum.
def compress_py(source):

    # We have to try compressing in two configurations and then return the
    # better of the two.
    compressed_data = [bytearray([0 for i in range(0x10000)])
                       for j in range(2)]

    best_size = 0x10000

    for i in range(2):
        # i=0: use 0x07FF for the range, 0xF800 for the max copy length
        # i=1: use 0x0FFF for the range, 0xF000 for the max copy length
        lookback_range = 0x07FF | (i << 11)

        # max_copy_length = 0xFFFF ^ lookback_range (bits used)
        max_copy_length = (0xFFFF ^ lookback_range) >> (16-(5-i))
        max_copy_length += 3

        # print(f'Iteration: i={i}')
        # print(f'{lookback_range:04X} {max_copy_length:04X}')
        src_pos = 0

        # First two bytes are main body length
        # Next byte will be the first packet's header
        out_pos = 2

        done = False

        # print('i =', i)

        while out_pos < best_size and not done:
            # Fill up a compressed packet
            header_pos = out_pos
            out_pos += 1

            # print(f'out_pos: {out_pos:04X}')

            for bit in range(8):

                # While filling a packet we ran out of source.
                if src_pos == len(source):
                    if bit == 0:
                        # If bit == 0, then we ran out after filling a packet.
                        # This means no addendum.
                        compressed_data[i][header_pos] = 0xC0*(1-i)

                        # Truncate to used size
                        compressed_data[i] = compressed_data[i][0:header_pos+1]
                    else:
                        # Otherwise, we're mid-packet.  The packet becomes
                        # the addendum.
                        # print("Addendum.")

                        # set unused bits of header for addendum header
                        mask = (0xFF << bit) & 0xFF
                        compressed_data[i][header_pos] |= mask

                        # shift the addendum packet down three bytes
                        compressed_data[i][header_pos+3:out_pos+3] = \
                            compressed_data[i][header_pos:out_pos]

                        # copy range + addendum length
                        compressed_data[i][header_pos] = \
                            0xC0*(1-i) | bit

                        # total compressed length (remember shift by 3)
                        compressed_data[i][header_pos+1:header_pos+3] = \
                            to_little_endian(out_pos+3, 2)

                        # Truncate to used size
                        compressed_data[i][out_pos+3] = 0xC0*(1-i)
                        compressed_data[i] = compressed_data[i][0:out_pos+4]

                    # print(f"Main body len: {header_pos-2:04X}")
                    compressed_data[i][0:2] = \
                        to_little_endian(header_pos-2, 2)

                    done = True
                    break

                lookback_st = max(0, src_pos - lookback_range)
                lookback_end = src_pos

                best_len = 0
                best_len_st = 0

                # Weird python stuff to avoid too many loops
                # I hope we can do better than this.

                # Use list comprehension to find potential starts
                starts = [x for x in range(lookback_st, lookback_end)
                          if source[x] == source[src_pos]]

                # Refine the list of starts by matching the next bytes up
                # to max copy length
                for j in range(1, max_copy_length):
                    next_starts = \
                        [x for x in starts
                         if (src_pos + j < len(source)
                             and source[x+j] == source[src_pos+j])]

                    if not next_starts:  # 'pythonic' way to check empty
                        break
                    else:
                        starts = next_starts
                        best_len_st = starts[0]
                        best_len = j+1

                '''
                # This is how it would go in a C program and in Geiger's orig

                best_len = 0
                for start in range(lookback_st, lookback_end):
                # for start in starts:

                    # Match the source starting at 'start' with the source
                    # starting at 'src_pos'
                    cur_len = 0

                    while (src_pos + cur_len < len(source) and
                           cur_len < max_copy_length and
                           source[start+cur_len] == source[src_pos+cur_len]):
                        cur_len += 1

                    # Update best match if needed
                    if cur_len >= best_len:
                        best_len = cur_len
                        best_len_st = start
                        if cur_len == max_copy_length:
                            break

                '''

                if best_len > 2:
                    # print(f'Best len: {best_len:02X}')
                    # We matched at least 3 bytes, so we'll use compression

                    # Mark the header to use compression for this bit
                    compressed_data[i][header_pos] |= (1 << bit)

                    lookback = src_pos - best_len_st
                    # print(f"\tlookback: {lookback:04X}")

                    # length is encoded with a -3 because there are always at
                    # least 3 bytes to copy.  The length is shifted to the most
                    # significant bits.  The shift depends on i.
                    length = ((best_len-3) << (16-(5-i)))

                    compr_stream = lookback | length

                    compressed_data[i][out_pos:out_pos+2] = \
                        to_little_endian(compr_stream, 2)

                    out_pos += 2
                    src_pos += best_len
                else:
                    # We failed to match 3 or more bytes, so just copy a byte
                    compressed_data[i][out_pos] = source[src_pos]
                    out_pos += 1
                    src_pos += 1
            # End of for loop to fill packet
            # print(f'Header: {compressed_data[i][header_pos]:02X}')
        # End of while not done loop

        if len(compressed_data[i]) < best_size:
            best_size = len(compressed_data[i])

    if len(compressed_data[0]) <= len(compressed_data[1]):
        return compressed_data[0]
    else:
        return compressed_data[1]
