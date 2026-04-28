'''
Give the Robo's Ribbon key item +3 speed and various effects.
'''


# Robo's Rbn is item 0xB8
# Accessories start at 0x94, so it is accessory 0x24
# Accessories start at 0x0C052C
# Each accessory has 4 bytes of stat data.
# Robo's Rbn should start at 0C052C+24×4 = 0C05BC
#  - Default:     00 80 09 42
#  - At +3 Spd:   00 40 07 42
# The plan is to set 0x80 and 0x40 bits (0xC0) for Rbn so that the data is
# 00 C0 09 42.  Then stat boost 7 (+3 spd) will be swapped with stat boost
# 9 (+6 pow).
from typing import Optional, Union

import randoconfig as cfg


def set_robo_ribbon_in_config(config: cfg.RandoConfig):
    ItemID = cfg.ctenums.ItemID
    StatBit = cfg.itemdata.StatBit

    item_db = config.item_db
    robo_ribbon = item_db[ItemID.ROBORIBBON]
    robo_ribbon.secondary_stats.ngplus_carryover = False
    robo_ribbon.stats.has_stat_boost = True

    # Find +3 speed boost in item_db
    stat_boosts = item_db.stat_boosts
    dash_boost_ind = None
    for ind, boost in enumerate(stat_boosts):
        mag = boost.magnitude
        stats = boost.stats_boosted

        if mag == 3 and stats == [StatBit.SPEED]:
            dash_boost_ind = ind
            break

    if dash_boost_ind is None:
        raise ValueError('Missing +3 speed effect.')

    x = item_db.stat_boosts
    ind1 = robo_ribbon.stats.stat_boost_index
    ind2 = dash_boost_ind

    x[ind1], x[ind2] = x[ind2], x[ind1]

    # Replace stat boosts on all equipment
    # Ignore Robo's Ribbon. Giving Robo's Ribbon the +6 str index could
    # result in an invalid accessory configuration.
    equippable_items = (x for x in list(ItemID)
                        if x < 0xBC and x != ItemID.ROBORIBBON)
    for item_id in equippable_items:

        item = item_db[item_id]
        stat_obj: Optional[Union[cfg.itemdata.GearSecondaryStats,
                                 cfg.itemdata.AccessoryStats]] = None
        if isinstance(item.secondary_stats, cfg.itemdata.GearSecondaryStats):
            stat_obj = item.secondary_stats
        elif (isinstance(item.stats, cfg.itemdata.AccessoryStats) and
              item.stats.has_stat_boost):
            stat_obj = item.stats

        if stat_obj is not None:
            stat_boost_index = stat_obj.stat_boost_index

            if stat_boost_index == ind1:
                stat_obj.stat_boost_index = ind2
            elif stat_boost_index == ind2:
                stat_obj.stat_boost_index = ind1


def robo_ribbon_speed_file(filename):
    with open(filename, 'rb') as infile:
        rom = bytearray(infile.read())

    robo_ribbon_speed(rom)

    with open(filename, 'wb') as outfile:
        outfile.write(rom)


def robo_ribbon_speed(rom):
    # Set Robo's Rbn to be both stat and status boost.
    rom[0x0C05BD] = 0xC0

    # Stat boosts are stored starting at 0x0C29D7.  Two byte data.
    #   -1st byte: Magnitude of stat boost
    #   -2nd byte: Bitmask of which stats to apply the boost to

    # We want to swap boost 7 and boost 9
    boost_start = 0x0C29D7
    temp = bytearray(rom[boost_start+2*7:boost_start+2*8])
    rom[boost_start+2*7:boost_start+2*8] = \
        rom[boost_start+2*9:boost_start+2*10]
    rom[boost_start+2*9:boost_start+2*10] = temp[:]

    # Now swap all of the items that use boosts 7 and 9
    # Non accessories have six bytes of data beginning at 0x0C06A4
    # The stat boost is in byte 5 (1-indexed)

    for i in range(0, 0x94):
        boost_byte = 0x0C06A4 + 4 + i*6
        if rom[boost_byte] == 7:
            # print('7 %X' % i)
            rom[boost_byte] = 9
        elif rom[boost_byte] == 9:
            rom[boost_byte] = 7
            # print('9 %X' % i)

    # Accessories have 4 byte data beginning at 0x0C052C
    # We need byte 2 to be 0x40  and byte 3 to be 7 or 9 to do the swap
    for i in range(0x94, 0xBC):
        type_byte = 0x0C052C + 1 + (i-0x94)*4
        if rom[type_byte] == 0x40:
            boost_byte = type_byte+1
            if rom[boost_byte] == 7:
                # print('7 %X' % i)
                rom[boost_byte] = 9
            elif rom[boost_byte] == 9:
                rom[boost_byte] = 7
                # print('9 %X' % i)


def main():
    pass


if __name__ == '__main__':
    main()
