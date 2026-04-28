'''
Module for PCTech class and functions related to manipulating PCTechs.
'''
from __future__ import annotations
import copy
import functools
import typing

import byteops
import ctenums
import ctrom
import ctstrings
import cttypes as cty
import cttechtypes as ctt


class TechNotFoundException(Exception):
    '''Raise when trying to get a nonexistent tech'''


def get_menu_usable_list(ct_rom: ctrom.CTRom) -> list[int]:
    '''
    Get a list of techs marked as usuable in the menu.
    '''
    hook_pos = 0x3FF82E

    rom_buf = ct_rom.rom_data.getbuffer()
    hook_byte = rom_buf[hook_pos]

    if hook_byte == 0xA9:
        # Not expanded
        tech_list_start = 0x3FF830
    elif hook_byte == 0x22:
        # Expanded, starts with JSL
        rt_addr = byteops.file_ptr_from_rom(rom_buf, hook_pos+1)
        tech_list_start = rt_addr + 2
    else:
        raise ValueError("Could not read menu usable list from ct_rom.")

    # tech_list_start points to code that's just a list of instructions
    # TSB XX 77 which sets some bits in 0x7E77XX to mark tech XX as usable
    # in the menu.  TSB has opcode 0x0C.
    ret_list: list[int] = []
    cur_pos = tech_list_start
    while rom_buf[cur_pos] == 0x0C:
        ret_list.append(rom_buf[cur_pos+1])
        cur_pos += 3

    return ret_list


def get_menu_usable(ct_rom: ctrom.CTRom, tech_id: int) -> bool:
    '''Determine if tech tech_id is usable in the menu.'''
    return tech_id in get_menu_usable_list(ct_rom)


RockType = typing.Literal[
    ctenums.ItemID.BLUE_ROCK, ctenums.ItemID.BLACK_ROCK,
    ctenums.ItemID.SILVERROCK, ctenums.ItemID.WHITE_ROCK,
    ctenums.ItemID.GOLD_ROCK
]


def determine_rock_used(
        ct_rom: ctrom.CTRom, tech_id: int) -> typing.Optional[RockType]:
    '''
    Determine which rock a tech needs.  Returns None if no rock is needed.
    '''
    rom = ct_rom.rom_data

    hook_pos = 0x0282F3
    hook_value = rom.getbuffer()[hook_pos]

    rock_list: list[RockType] = [
        ctenums.ItemID.BLACK_ROCK, ctenums.ItemID.BLUE_ROCK,
        ctenums.ItemID.SILVERROCK, ctenums.ItemID.WHITE_ROCK,
        ctenums.ItemID.GOLD_ROCK
    ]

    if hook_value == 0x5C:
        # Is modified
        routine_addr = byteops.file_ptr_from_rom(rom.getbuffer(), hook_pos+1)

        num_rock_techs = ctt.get_rock_tech_count(ct_rom)
        num_techs = ctt.get_total_tech_count(ct_rom)

        rock_tech_number = tech_id - (num_techs - num_rock_techs)
        if rock_tech_number < 0:
            return None

        # Otherwise, find rock_tech_number in the rock assignment table.

        # We use raw offsets into the routine to find the location of their
        # rock pointer table and the actual rock data.
        rock_table_ptr = routine_addr + 0x30
        rock_table_addr = byteops.file_ptr_from_rom(rom.getbuffer(),
                                                    rock_table_ptr)

        # The rock table data is lexicographic order on (pc_id, rock_id)
        # Each entry is a 0xFF-terminated list of rock_tech_numbers.  So
        # We loop until we find the desired rock_tech_number and can % 5
        # to find which rock is used for that tech.
        ff_count = 0
        rom.seek(rock_table_addr)
        while ff_count < 35:

            # This could be more efficient by reading chunks, but it's unlikely
            # to matter with how infrequently we call this.
            cur_byte = rom.read(1)[0]

            if cur_byte == 0xFF:
                ff_count += 1
            elif cur_byte == rock_tech_number:
                rock_num = ff_count % 5
                return rock_list[rock_num]

        raise ValueError("No rock found for tech.")

    if hook_value == 0xA2:
        # Is vanilla
        num_techs = ctt.get_total_tech_count(ct_rom)
        first_rock_tech = num_techs - 5
        rock_num = tech_id - first_rock_tech

        if rock_num < 0:
            return None
        return rock_list[rock_num]

    raise ValueError("Unable to read rock data from rom.")


def get_pc_target_data(
        ct_rom: ctrom.CTRom, tech_id: int,
        tech_target_data: typing.Optional[ctt.PCTechTargetData] = None
) -> typing.Optional[ctenums.CharID]:
    '''
    Determine whether a tech needs to target based on a particular PC index.
    When charrando is used, this needs to be updated.

    Notable Examples:
    - Doublevbomb targets around PC with index 3.
    - Black hole targets around PC with index 6.
    '''

    hook_pos = 0x0122A9
    rom_buf = ct_rom.rom_data.getbuffer()

    hook_byte = rom_buf[hook_pos]

    if hook_byte == 0xBD:
        # Unmodified
        # Determine pc target data from normal tech target data.
        if tech_target_data is None:
            tech_target_data = ctt.PCTechTargetData.read_from_ctrom(
                ct_rom, tech_id)

        target_type = tech_target_data.select_target
        if target_type == ctt.TargetType.AREA_MAGUS:
            return ctenums.CharID.MAGUS
        if target_type in (ctt.TargetType.LINE_ROBO,
                           ctt.TargetType.AREA_ROBO_13,
                           ctt.TargetType.AREA_ROBO_14):
            return ctenums.CharID.ROBO
        return None
    if hook_byte == 0x5C:
        # Modified
        # Determine pc targt data from special range on rom
        rt_start = byteops.file_ptr_from_rom(rom_buf, hook_pos+1)
        rt_offset = 5
        target_table_start = byteops.file_ptr_from_rom(rom_buf,
                                                       rt_start + rt_offset)
        target_byte = rom_buf[target_table_start + tech_id]

        if target_byte == 0xFF:
            return None
        return ctenums.CharID(target_byte)

    raise ValueError("Could not parse rom target routine.")


class PCTech:
    '''
    Class to store all data needed by a tech.

    Most of this is straightforward, but there are three dc-flag specific
    fields that are included.
    - rock_used: With dc the rock -> tech association can not be determined
        from the tech_id.  This needs to be given explicitly.
    - menu_usable:  With dc, there can be many (or no) techs which are usable
        in the menu.
    - pc_target: Some techs target a particular CharID (e.g. Doublevbomb).
        The target needs to be tracked explicitly for dc flag when there may
        be multiple of the same character in a fight.
    '''
    def __init__(
            self,
            battle_group: ctt.PCTechBattleGroup,
            control_header: ctt.PCTechControlHeader,
            effect_headers: list[ctt.PCTechEffectHeader],
            effect_mps: list[int],
            menu_mp_reqs: typing.Optional[ctt.PCTechMenuMPReq],
            graphics_header: ctt.PCTechGfxHeader,
            target_data: ctt.PCTechTargetData,
            learn_reqs: typing.Optional[ctt.PCTechLearnRequirements],
            name: ctstrings.CTNameString,
            desc: ctstrings.CTString,
            atb_penalty: ctt.PCTechATBPenalty,
            rock_used: typing.Optional[RockType],
            menu_usable: bool,
            pc_target: typing.Optional[ctenums.CharID]
    ):
        self.battle_group = battle_group.get_copy()
        self.control_header = control_header.get_copy()
        self.graphics_header = graphics_header.get_copy()
        self.target_data = target_data.get_copy()
        self.learn_reqs: typing.Optional[ctt.PCTechLearnRequirements]
        self.atb_penalty = atb_penalty.get_copy()
        self.rock_used = rock_used
        self.menu_usable = menu_usable
        self.pc_target = pc_target

        if learn_reqs is not None:
            self.learn_reqs = learn_reqs.get_copy()
        else:
            self.learn_reqs = None

        # TODO: Are menu_mp_reqs needed?  Why not load the effect index in?
        self.menu_mp_reqs: typing.Optional[ctt.PCTechMenuMPReq]
        if menu_mp_reqs is not None:
            self.menu_mp_reqs = menu_mp_reqs.get_copy()
        else:
            self.menu_mp_reqs = None

        self._name = ctstrings.CTNameString(name)
        self._desc = ctstrings.CTString(desc)

        self.effect_headers = []
        self.effect_mps = []

        # Make sure that everything is sized correctly.
        num_pcs = battle_group.number_of_pcs
        if len(effect_headers) != num_pcs:
            raise ValueError('Number of PCs and effect headers differs')

        if len(effect_mps) != num_pcs:
            raise ValueError('Number of PCs and mps differs')

        if len(atb_penalty) == 1 and num_pcs not in (1, 2):
            raise ValueError("Number of PCs and atb penalties differs.")
        if len(atb_penalty) == 2 and num_pcs != 3:
            raise ValueError("Number of PCs and atb penalties differs.")

        if menu_mp_reqs is None and num_pcs != 1:
            raise ValueError('Number of PCs and menu mp requirements differs')
        if menu_mp_reqs is not None and len(menu_mp_reqs) != num_pcs:
            raise ValueError('Number of PCs and menu mp requirements differs')

        for effect_header, mp in zip(effect_headers, effect_mps):
            self.effect_headers.append(effect_header)
            self.effect_mps.append(mp)

    @property
    def name(self) -> str:
        '''This tech's name as a string.'''
        return str(self._name)

    @name.setter
    def name(self, val: str):
        new_name = ctstrings.CTNameString.from_string(val, length=0xB)
        self._name = new_name

    @property
    def desc(self) -> str:
        '''This tech's description as a string.'''
        return str(self._desc)

    @desc.setter
    def desc(self, val: str):
        new_desc = ctstrings.CTString.from_str(val, compress=True)
        self._desc = new_desc

    @property
    def num_pcs(self) -> int:
        '''The number of PCs who perform this tech.'''
        return self.battle_group.number_of_pcs

    @property
    def needs_magic_to_learn(self):
        '''Does this tech need magic to learn (single only)'''
        if self.num_pcs != 1:
            raise TypeError("Combo techs don't need magic to learn")

        return self.control_header[0] & 0x80

    @needs_magic_to_learn.setter
    def needs_magic_to_learn(self, val: bool):
        if self.num_pcs != 1:
            raise TypeError("Combo techs don't need magic to learn")

        self.control_header[0] &= 0x7F
        self.control_header[0] |= 0x80*(val is True)

    @property
    def is_unlearnable(self):
        '''Can this tech be learned (combo tech only).'''
        if self.num_pcs == 1:
            raise TypeError("Single techs cannot be marked unlearnable.")

        return self.control_header[0] & 0x80

    @is_unlearnable.setter
    def is_unlearnable(self, val: bool):
        if not self.num_pcs == 1:
            raise TypeError("Single techs cannot be marked unlearnable.")

        self.control_header[0] &= 0x7F
        self.control_header[0] |= 0x80*(val is True)

    @classmethod
    def read_from_ctrom(
            cls, ct_rom: ctrom.CTRom, tech_id: int,
            lrn_req_rw: typing.Optional[cty.RomRW] = None,
            atb_pen_rw: typing.Optional[cty.RomRW] = None
            ) -> PCTech:
        '''
        Read the PCTech with a given tech id from a ctrom.CTRom.

        If reading many techs, it may be more efficient to compute the
        cttypes.RomRW objects for learning requirements and atb penalties
        since these involve some computations.  These can be provided with
        optional arguments lrn_req_rw and atb_pen_rw.
        '''
        control_header = ctt.PCTechControlHeader.read_from_ctrom(
            ct_rom, tech_id)

        battle_group_index = control_header.battle_group_id
        battle_group = ctt.PCTechBattleGroup.read_from_ctrom(
            ct_rom, battle_group_index)

        eff_inds = [control_header.get_effect_index(eff_num)
                    for eff_num in range(battle_group.number_of_pcs)]
        effect_headers = [
            ctt.PCTechEffectHeader.read_from_ctrom(ct_rom, eff_ind)
            for eff_ind in eff_inds
        ]

        effect_mps = [
            int(ctt.PCEffectMP.read_from_ctrom(ct_rom, eff_ind)[0])
            for eff_ind in eff_inds
        ]

        graphics_header = ctt.PCTechGfxHeader.read_from_ctrom(
            ct_rom, tech_id)

        target_data = ctt.PCTechTargetData.read_from_ctrom(
            ct_rom, tech_id)

        if battle_group.number_of_pcs > 1:
            if lrn_req_rw is None:
                lrn_req_rw = ctt.PCTechLearnRequirements.ROM_RW

                # There are always 0x39 single tech entries: 1 fake +
                # 7*8 singles.
                lrn_req_index = tech_id - 0x39
                learn_reqs = ctt.PCTechLearnRequirements.read_from_ctrom(
                    ct_rom, lrn_req_index, None, lrn_req_rw
                )
        else:
            learn_reqs = None

        if battle_group.number_of_pcs > 1:
            menu_mps = ctt.PCTechMenuMPReq.read_from_ctrom(
                ct_rom, tech_id, battle_group.number_of_pcs
            )
        else:
            menu_mps = None

        name = ctt.read_tech_name_from_ctrom(ct_rom, tech_id)
        desc = ctt.read_tech_desc_from_ctrom(ct_rom, tech_id)

        if atb_pen_rw is None:
            num_dual_techs = ctt.get_dual_tech_count(ct_rom)
            num_triple_techs = ctt.get_triple_tech_count(ct_rom)
            atb_pen_rw = ctt.PCTechATBPenaltyRW(0x01BDF6, num_dual_techs,
                                                num_triple_techs)

        if battle_group.number_of_pcs == 3:
            num_atb_bytes = 2
        else:
            num_atb_bytes = 1

        atb_penalty = ctt.PCTechATBPenalty.read_from_ctrom(
            ct_rom, tech_id, num_atb_bytes, atb_pen_rw)

        rock_used = determine_rock_used(ct_rom, tech_id)
        menu_usable = get_menu_usable(ct_rom, tech_id)
        pc_target = get_pc_target_data(ct_rom, tech_id, target_data)

        return PCTech(battle_group, control_header, effect_headers,
                      effect_mps, menu_mps, graphics_header, target_data,
                      learn_reqs, name, desc, atb_penalty, rock_used,
                      menu_usable, pc_target)


TechList = typing.List[typing.Optional[PCTech]]


class PCTechManagerGroup:
    '''
    Class used internally by PCTechManager to store groups of techs.

    PCTechManagerGroup has no public-facing members.  The only changes to
    instances of the class should be made to self._techs through the
    add_tech and set_tech methods.
    '''
    _pc_bitmask: typing.ClassVar[dict[ctenums.CharID, int]] = {
        ctenums.CharID.CRONO: 0x80,
        ctenums.CharID.MARLE: 0x40,
        ctenums.CharID.LUCCA: 0x20,
        ctenums.CharID.ROBO: 0x10,
        ctenums.CharID.FROG: 0x08,
        ctenums.CharID.AYLA: 0x04,
        ctenums.CharID.MAGUS: 0x02,
    }

    def __init__(self, bitmask: int,
                 rock_used: typing.Optional[RockType] = None,
                 techs: typing.Optional[TechList] = None):

        self._rock_used = rock_used

        if bitmask not in range(1, 0x100):
            raise ValueError("Bitmask must be i range(1x100)")

        if bool(bitmask & 0x01):
            raise ValueError("Bit 0x01 does not correspond to a PC.")

        self._bitmask = bitmask
        self._num_pcs = bin(self.bitmask).count('1')

        if self.num_pcs not in range(1, 4):
            raise ValueError(
                f"Bitmask 0x{self.bitmask:02X} must only have 1, 2 or 3 "
                "bytes set."
            )

        self._num_techs = (
            8 if self.num_pcs == 1 else (
                3 if self.num_pcs == 2 else 1
            )
        )

        self._techs: TechList
        if techs is None:
            self._techs = [None for _ in range(self.num_techs)]
        else:
            if len(techs) != self.num_techs:
                raise ValueError(
                    "Size of parameter techs inconsistent with number of PCs."
                )
            for tech in techs:
                self._validate_tech(tech)

            self._techs = techs

    def get_all_techs(self) -> TechList:
        '''Get the internal list of techs (not a copy).'''
        return self._techs

    def has_tech(self, index: int) -> bool:
        '''Is there a tech at the given index.'''
        return self._techs[index] is not None

    def get_tech(self, index: int) -> PCTech:
        '''
        Get the tech at the given index.

        Raises TechNotFoundException if there is none.'''
        tech = self._techs[index]
        if tech is None:
            raise TechNotFoundException

        return tech

    def has_free_space(self) -> bool:
        '''Does this group have any free space.'''
        return None in self._techs

    def add_tech(self, tech: PCTech) -> int:
        '''Add a tech to this group.  Returns the insertion index.'''
        if None not in self._techs:
            raise IndexError(f"No room in group {self._bitmask:02X}.")

        insertion_index = self._techs.index(None)
        self.set_tech(insertion_index, tech)
        return insertion_index

    def set_tech(self, index: int, tech: typing.Optional[PCTech]):
        '''Add a tech to this group at a particular index.'''
        self._validate_tech(tech)
        self._techs[index] = tech

    def _validate_tech(self, tech: typing.Optional[PCTech]) -> None:
        '''
        Verify that a tech belongs in this group.  Raises ValueError on
        failure.
        '''
        if tech is not None:
            if tech.battle_group.to_bitmask() != self._bitmask:
                raise ValueError(
                    "Tech bitmask does not match group bitmask"
                )
            if tech.rock_used != self._rock_used:
                raise ValueError(
                    "Tech rock usage does not match group rock usage."
                )

    @classmethod
    def bitmask_from_pcs(
            cls, *pcs: ctenums.CharID
    ) -> int:
        '''Create a bitmask from ctenums.CharIDs.'''
        if isinstance(pcs, ctenums.CharID):
            pcs = [pcs]

        bitmask = functools.reduce(
            lambda x, y: x | y, (cls._pc_bitmask[char] for char in pcs), 0
        )
        return bitmask

    @classmethod
    def from_pcs(cls, *pcs: ctenums.CharID,
                 rock_used: typing.Optional[RockType] = None,
                 techs: typing.Optional[list[typing.Optional[PCTech]]] = None
                 ) -> PCTechManagerGroup:
        '''Create a PCTechManagerGroup from ctenums.CharIDs.'''
        return cls(cls.bitmask_from_pcs(*pcs), rock_used=rock_used,
                   techs=techs)

    @property
    def bitmask(self) -> int:
        '''Get the bitmask associated with this group.'''
        return self._bitmask

    @property
    def pcs(self) -> list[ctenums.CharID]:
        '''Get a list of CharIDs in this group.'''
        return [
            char_id for char_id in ctenums.CharID
            if bool(self._pc_bitmask[char_id] & self.bitmask)
        ]

    @property
    def rock_used(self) -> typing.Optional[RockType]:
        '''Get the rock used by this group.'''
        return self._rock_used

    @property
    def num_pcs(self) -> int:
        '''Get how many pcs are in this group's bitmask.'''
        return self._num_pcs

    @property
    def num_techs(self) -> int:
        '''Get how many techs this group can hold.'''
        return self._num_techs


class PCTechManager:
    '''Handle all PC tech data.'''

    def __init__(self, techs: typing.Optional[typing.Iterable[PCTech]] = None):
        '''
        Construct a PCTechManager from a collection of PCTechs.

        Note that the iteration order of the techs parameter matters.
        The first Crono tech encountered while iterating will be Crono's first
        tech
        '''

        # self._bitmasks stores raw int bitmasks in an order that CT likes.
        self._bitmasks: list[int] = []

        # Associate bitmask with PCTechManagerGroup (num_techs, rock_used)
        # This is especially important for triple vs rock to prevent
        # re-definition of a bitmask.
        self._bitmask_group_dict: dict[int, PCTechManagerGroup] = {}

        # Needed for identifying by tech_id.
        self.__num_dual_groups = 0
        self.__num_triple_groups = 0
        self.__num_rock_groups = 0

        # Add the single tech groups in a particular order.
        # just char_id in ctenums.CharID should work, but be explicit.
        for char_id in (ctenums.CharID.CRONO, ctenums.CharID.MARLE,
                        ctenums.CharID.LUCCA, ctenums.CharID.ROBO,
                        ctenums.CharID.FROG, ctenums.CharID.AYLA,
                        ctenums.CharID.MAGUS):
            group = PCTechManagerGroup.from_pcs(char_id, rock_used=None)
            self._bitmasks.append(group.bitmask)
            self._bitmask_group_dict[group.bitmask] = group

        if techs is not None:
            for tech in techs:
                self.add_tech(tech)

    @property
    def num_single_techs(self) -> int:
        '''The number of single techs in this class.'''
        return 56

    @property
    def num_dual_techs(self) -> int:
        '''The number of dual techs in this class.'''
        return self.__num_dual_groups*3

    @property
    def num_triple_techs(self) -> int:
        '''The number of triple techs in this class.'''
        return self.__num_triple_groups

    @property
    def num_rock_techs(self) -> int:
        '''The number of rock techs in this class.'''
        return self.__num_rock_groups

    @property
    def num_techs(self) -> int:
        return self.num_single_techs + self.num_dual_techs + \
            self.num_triple_techs + self.num_rock_techs

    def add_tech(self, tech: PCTech) -> int:
        '''
        Adds a tech and returns the tech_id where it is inserted.

        Note: the tech_id may change with future tech insertions.
        '''
        bitmask = tech.battle_group.to_bitmask()
        rock_used = tech.rock_used

        bitmask_index = self._add_bitmask(bitmask, rock_used)
        group = self._bitmask_group_dict[bitmask]
        tech_index = group.add_tech(tech)

        return self._get_tech_id(bitmask_index, tech_index)

    def get_tech(self, tech_id) -> PCTech:
        '''
        Get (a copy of) the PCTech with the given tech_id.

        Notes:
        - Will raise IndexError if the given tech_id is out of range.
        - Will raise TechNotFoundException if the given tech_id is valid but
          has no PCTech associated with it.
        - Follows Chrono Trigger's tech_id system where Crono's first tech has
          an id of 1 (not 0).  Requesting tech_id=0 will raise an IndexError
        '''

        if tech_id == 0:
            raise IndexError("Player Techs begin at tech_id 1")

        tech_id -= 1
        tech_counts = [self.num_single_techs, self.num_dual_techs,
                       self.num_triple_techs, self.num_rock_techs]

        if tech_id > sum(tech_counts):
            raise IndexError("tech_id out of range.")

        group_counts = [7, self.__num_dual_groups,
                        self.__num_triple_groups, self.__num_rock_groups]
        group_sizes = [8, 3, 1, 1]

        group_start = 0
        tech_start = 0

        group_index, tech_index = None, None
        for tech_count, group_count, group_size in (
                zip(tech_counts, group_counts, group_sizes)
        ):
            if tech_id < tech_start + tech_count:
                tech_id -= tech_start
                group_index = group_start + tech_id // group_size
                tech_index = tech_id % group_size
                break

            tech_start += tech_count
            group_start += group_count

        if group_index is None or tech_index is None:
            raise TechNotFoundException(
                "Failed to find tech group.")  # Should never happen.

        bitmask = self._bitmasks[group_index]
        group = self._bitmask_group_dict[bitmask]
        tech = group.get_tech(tech_index)  # May raise TechNotFoundException

        return copy.deepcopy(tech)

    def _get_tech_id(self, bitmask_index, tech_list_index):
        '''
        Internal method to determine a tech's tech_id from the index of its
        bitmask and it's index within its group.

        Note: This uses CT's 1-indexing of techs rather than the usual 0.
        '''
        if bitmask_index < 7:
            return 8*bitmask_index + tech_list_index

        start_tech_index = 7*8
        start_group_index = 7
        if bitmask_index < start_group_index + self.__num_dual_groups:
            dual_index = bitmask_index - start_group_index
            return start_tech_index + dual_index*3 + tech_list_index + 1

        start_tech_index += self.__num_dual_groups*3
        start_group_index += self.__num_dual_groups

        if tech_list_index != 0:
            print(self.__num_dual_groups, self.__num_triple_groups)
            raise ValueError("Triple groups have only one tech")

        if bitmask_index < start_group_index + self.__num_triple_groups:
            triple_index = bitmask_index - start_group_index
            return start_tech_index + triple_index + 1

        start_tech_index += self.__num_triple_groups
        start_group_index += self.__num_triple_groups

        rock_index = bitmask_index - start_group_index
        return start_tech_index + rock_index + 1

    def _add_bitmask(self, bitmask: int,
                     rock_used: typing.Optional[RockType]) -> int:
        if bitmask in self._bitmasks:
            return self._bitmasks.index(bitmask)

        group = PCTechManagerGroup(bitmask, rock_used)

        # Insert bitmask in order
        if group.num_pcs == 2:
            insertion_index = 7 + self.__num_dual_groups
        elif group.num_pcs == 3:
            insertion_index = 7 + self.__num_dual_groups + \
                self.__num_triple_groups
            if group.rock_used is not None:
                insertion_index += self.__num_rock_groups
        else:
            raise ValueError(
                f"Adding a single tech group {group.bitmask:02X}."
            )

        self._bitmasks.insert(insertion_index, bitmask)
        self._bitmask_group_dict[bitmask] = group

        # Maybe this could go up during computation of insertion_index,
        # but it feels wrong to increment until the group is actually in.
        if group.num_pcs == 2:
            self.__num_dual_groups += 1
        elif group.rock_used is None:
            self.__num_triple_groups += 1
        else:
            self.__num_rock_groups += 1

        self._bitmask_group_dict[group.bitmask] = group

        return insertion_index

    @classmethod
    def read_from_ctrom(cls, ct_rom: ctrom.CTRom):
        '''Read techs into a PCTechManager from a ctrom.CTRom.'''
        num_techs = ctt.get_total_tech_count(ct_rom)  # Includes dummy tech0

        tech_man = PCTechManager()
        for tech_id in range(1, num_techs):
            tech = PCTech.read_from_ctrom(ct_rom, tech_id)
            tech_man.add_tech(tech)

    def _verify_battle_groups(
            self,
            battle_groups: list[ctt.PCTechBattleGroup]) -> None:
        for bitmask in self._bitmasks:
            for tech in self._bitmask_group_dict[bitmask].get_all_techs():
                if tech is None:
                    raise ValueError(f"Unset tech in group {bitmask:02X}")

                if tech.battle_group != \
                   battle_groups[tech.control_header.battle_group_id]:
                    raise ValueError("Battle Group Mismatch")

    def _collect_update_battle_groups(self) -> bytes:
        '''
        Returns a bytes object consisting of all battle groups in order.

        Warning: This has side effects.  All control headers will be updated
                 to use the correct battle_group_id.
        '''

        # One battle group per bitmask is forced by CT.
        # Get each group's 0th tech's battle group.  So group i's forced
        # group is in position i in the list.
        first_techs: typing.Iterator[PCTech] = (
            self._bitmask_group_dict[bitmask].get_tech(0)
            for bitmask in self._bitmasks
        )

        battle_groups: list[ctt.PCTechBattleGroup] = [
            tech.battle_group for tech in first_techs
        ]

        for bitmask_ind, bitmask in enumerate(self._bitmasks):
            # Get all techs but the first, and add their battle groups
            group_techs =\
                self._bitmask_group_dict[bitmask].get_all_techs()
            for tech in group_techs:
                if tech is None:
                    raise ValueError(f"Undefined Tech in group {bitmask:02X}")

                if tech.battle_group == battle_groups[bitmask_ind]:
                    new_battle_index = bitmask_ind
                else:
                    new_battle_index = len(battle_groups)
                    battle_groups.append(tech.battle_group)

                tech.control_header.battle_group_id = new_battle_index

        self._verify_battle_groups(battle_groups)
        battle_group_bytes = \
            b''.join(bytes(group) for group in battle_groups)

        return battle_group_bytes

    def _collect_update_effect_headers(self) -> bytes:
        '''
        Returns bytes for the techs effect headers.

        Warning: This has side effects.  All control headers will be updated
                 to use the correct effect indices.
        '''

        # begin with an empty header for effect 0
        effect_headers: list[ctt.PCTechEffectHeader] = [
            ctt.PCTechEffectHeader()
        ]

        # Single techs go in order.  self._bitmasks are in the right order
        # So the single techs are the first 7 bitmasks.
        for bitmask in self._bitmasks[0:7]:
            group = self._bitmask_group_dict[bitmask]
            if group.num_pcs != 1:
                raise ValueError("Expected single tech group")
            for ind in range(group.num_techs):
                tech = group.get_tech(ind)
                effect_headers.append(tech.effect_headers[0])
                tech.control_header.set_effect_index(0, len(effect_headers)-1)

        for bitmask in self._bitmasks[7:]:
            group = self._bitmask_group_dict[bitmask]
            if group.num_pcs == 1:
                raise ValueError("Expected combo tech group")
            for ind in range(group.num_techs):
                tech = group.get_tech(ind)
                for ind, effect_header in enumerate(tech.effect_headers):
                    if effect_header in effect_headers:
                        new_eff_ind = effect_headers.index(effect_header)
                    else:
                        new_eff_ind = len(effect_headers)
                        effect_headers.append(effect_header)

                    tech.control_header.set_effect_index(ind, new_eff_ind)

                for var in range(ind+1, 3):
                    if tech.control_header.get_effect_index(var) != 0:
                        print(tech.control_header)
                        print(tech.control_header.get_effect_index(var))
                        raise ValueError("Incorrectly set effect headers")

        for tech_id in range(1, self.num_techs+1):
            tech = self.get_tech(tech_id)
            ctl = tech.control_header
            for ind in range(3):
                eff_ind = ctl.get_effect_index(ind)
                if eff_ind == 0:
                    continue

                effect = tech.effect_headers[ind]
                if effect_headers[eff_ind] != effect:
                    raise ValueError

        return b''.join(effect for effect in effect_headers)

    def _verify_effect_headers(self,
                               effect_headers: list[ctt.PCTechEffectHeader]):
        '''
        Verify that the control headers of techs point to the correct index
        in parameter effect_headers.
        '''
        for bitmask in self._bitmasks:
            for tech in self._bitmask_group_dict[bitmask].get_all_techs():
                if tech is None:
                    raise ValueError("Unset Tech")

                ctl = tech.control_header
                for ind in range(3):
                    eff_ind = ctl.get_effect_index(ind)
                    if eff_ind == 0:
                        continue

                    effect = tech.effect_headers[ind]
                    if effect_headers[eff_ind] != effect:
                        raise ValueError

    def write_to_ctrom(self, ct_rom: ctrom.CTRom,
                       free_existing_tech_data: bool = True):
        '''
        Write this PCTechManager to a ctrom.CTRom.

        In particular this method:
        1) Frees all existing tech data (to be re-written) if the parameter
           free_existing_tech_data is True.
        2) Writes all new tech data back to the ct_rom and marks it used
        3) Changes pointers to point to new tech data
        4) Patches the ct_rom for dc-specific changes
           - Patch menu-usable list to be arbitrarily long
           - Patch rock tech routines to allow multiple techs per rock
           - Patch target routines to allow pc-specific targeting other than
             Robo and Magus.
           - Expand to allow tech_ids exceeding 0x7F (max is 0xFE I think?)
        '''
        menu_groups = list(self._bitmasks)
        battle_group_bytes = self._collect_update_battle_groups()

    def print_protected(self):
        '''Debug method for tracking the group counts.'''
        print(self.__num_dual_groups, self.__num_triple_groups,
              self.__num_rock_groups)

    def print_all_techs(self):
        '''Debug method for displaying all techs.'''
        for bitmask in self._bitmasks:
            group = self._bitmask_group_dict[bitmask]
            pcs = ' '.join(str(pc) for pc in group.pcs)
            print(f"Group: {group.bitmask:02X} ({pcs})")
            for tech in group.get_all_techs():
                if tech is None:
                    print("None")
                else:
                    print(f"    {tech.name}")
