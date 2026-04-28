from __future__ import annotations
from dataclasses import dataclass
import typing

import byteops

import ctenums
import ctrom

import enemystats


class _FixedLengthRecord:
    SIZE = 1

    def __init__(self, data: bytes, pos: int = 0):
        self._data = bytearray(data[pos:pos+self.SIZE])

    def get_as_bytearray(self):
        return bytearray(self._data)

    def __len__(self):
        if len(self._data) != self.SIZE:
            raise ValueError('Size mismatch')

        return self.SIZE

    def __str__(self):
        byte_str = ' '.join(f'{x:02X}' for x in self._data)
        return f'{self.__class__.__name__}: {byte_str}'


class EffectMod(ctenums.StrIntEnum):
    NONE = 0x00
    CRITICAL_X2 = 0x01
    RANDOM_DAMAGE = 0x02
    PHYS_DAMAGE_125 = 0x03
    PHYS_DAMAGE_150 = 0x04
    PHYS_DAMAGE_175 = 0x05
    PHYS_DAMAGE_200 = 0x06
    MAGIC = 0x07
    MAGIC_DAMAGE_125 = 0x08
    MAGIC_DAMAGE_150 = 0x09
    MAGIC_DAMAGE_175 = 0x0A
    MAGIC_DAMAGE_200 = 0x0B
    HP_TO_1 = 0x0E
    HALF_HP = 0x1E
    SELF_DESTRUCT = 0x23
    END_BATTLE = 0x25
    RANDOM_STATUS = 0x36


class DamageFormula(ctenums.StrIntEnum):
    MAGIC = 0x39
    PHYSICAL = 0x3A


class EnemyControlHeader(_FixedLengthRecord):
    SIZE = 0xB

    @classmethod
    def verify_effect_num(cls, eff_num: int):
        if not 0 <= eff_num < 3:
            raise ValueError('Effect index must be in range(0, 3).')

    def get_effect_index(self, eff_num: int):
        self.verify_effect_num(eff_num)
        return self._data[5+eff_num]

    def set_effect_index(self, eff_num: int, new_index: int):
        self.verify_effect_num(eff_num)
        self._data[5+eff_num] = new_index

    def get_effect_mod(self, eff_num: int) -> EffectMod:
        self.verify_effect_num(eff_num)
        return EffectMod(self._data[9+eff_num])

    def set_effect_mod(self, eff_num: int, eff_mod: EffectMod):
        self.verify_effect_num(eff_num)
        self._data[9+eff_num] = eff_mod

    @property
    def element(self):
        elem_byte = self._data[3]
        elem_byte &= 0xF0

        if bin(elem_byte).count('1') > 1:
            raise ValueError('A tech can only have one element set.')
        elif bin(elem_byte).count('1') == 0:
            return ctenums.Element.NONELEMENTAL
        elif elem_byte & 0x80:
            return ctenums.Element.LIGHTNING
        elif elem_byte & 0x40:
            return ctenums.Element.SHADOW
        elif elem_byte & 0x20:
            return ctenums.Element.ICE
        elif elem_byte & 0x10:
            return ctenums.Element.FIRE

    @element.setter
    def element(self, value: ctenums.Element):
        self._data[3] &= 0x0F

        if value == ctenums.Element.LIGHTNING:
            self._data[3] |= 0x80
        elif value == ctenums.Element.SHADOW:
            self._data[3] |= 0x40
        elif value == ctenums.Element.ICE:
            self._data[3] |= 0x20
        elif value == ctenums.Element.FIRE:
            self._data[3] |= 0x10


class EnemyAtkControlHeader(_FixedLengthRecord):
    SIZE = 0xB

    @property
    def effect_index(self):
        return self._data[4]

    @effect_index.setter
    def effect_index(self, val):
        self._data[4] = val


class EnemyEffectHeader(_FixedLengthRecord):
    SIZE = 0xC

    @property
    def damage_formula_id(self):
        return self._data[5]

    @damage_formula_id.setter
    def damage_formula_id(self, val):
        val = DamageFormula(val)
        self._data[5] = val

    @property
    def power(self):
        return self._data[9]

    @power.setter
    def power(self, val: int):
        self._data[9] = val

    @property
    def status_effect(self) -> list[ctenums.StatusEffect]:
        status_byte = self._data[2]
        statuses = []
        for x in list(ctenums.StatusEffect):
            if int(x) & status_byte:
                statuses.append(x)
        return statuses

    @status_effect.setter
    def status_effect(
            self,
            statuses: typing.Union[typing.Iterable[ctenums.StatusEffect],
                                   ctenums.StatusEffect]
    ):
        if isinstance(statuses, ctenums.StatusEffect):
            status_byte = int(statuses)
        else:
            status_byte = 0
            for x in statuses:
                status_byte |= int(x)

        self._data[2] = status_byte

    @property
    def defense_byte(self) -> int:
        return self._data[6]

    @defense_byte.setter
    def defense_byte(self, value):
        self._data[6] = value


class EnemyTechGfxHeader(_FixedLengthRecord):
    SIZE = 0x7

    @property
    def script_id(self):
        return self._data[0]

    @script_id.setter
    def script_id(self, val):
        self._data[0] = val


class EnemyTargetData(_FixedLengthRecord):
    SIZE = 0x2


class EnemyAtkGfxHeader(_FixedLengthRecord):
    SIZE = 0x6


class EnemyTech:

    def __init__(self, control: EnemyControlHeader,
                 effect: EnemyEffectHeader,
                 gfx: EnemyTechGfxHeader,
                 target: EnemyTargetData):
        self.control = control
        self.effect = effect
        self.gfx = gfx
        self.target = target

    def is_physical(self) -> bool:
        return self.effect.damage_formula_id == int(DamageFormula.PHYSICAL)

    def __str__(self):
        ret_str = self.__class__.__name__ + ':\n'
        ret_str += '\n'.join(str(x)
                             for x in (self.control, self.effect,
                                       self.gfx, self.target))
        return ret_str


class EnemyAttack:
    def __init__(self,
                 control: EnemyAtkControlHeader,
                 effect: EnemyEffectHeader):
        self.control = control
        self.effect = effect

    def __str__(self):
        ret_str = self.__class__.__name__ + ':\n\t'
        ret_str += str(self.control) + '\n\t'
        ret_str += str(self.effect) + '\n'

        return ret_str


@dataclass
class RomRef:
    file_loc: int = 0
    offset: int = 0


class EnemyAttackDB:

    TECH_CONTROL_START = 0x0C6FC9
    TECH_EFFECT_START = 0x0C7AC9
    TECH_GFX_START = 0x0D5526
    TECH_TARGET_START = 0x0C86C9

    ATK_CONTROL_PTR = 0x01D8FD
    ATK_EFFECT_PTR = 0x01D946
    ATK_GFX_1_START = 0x0D4926
    ATK_GFX_2_START = 0x0D4F26

    tech_control_refs = [
        RomRef(0x01D7F0, 0x01), RomRef(0x01D817, 0x05), RomRef(0x01D854, 0x08),
        RomRef(0x01D875, 0x03), RomRef(0x01D8A1, 0x01), RomRef(0x01D8B5, 0x01),
        RomRef(0x3CBAC3, 0x03), RomRef(0x3DAAEA, 0x02), RomRef(0x3DAAF7, 0x03)
    ]

    tech_effect_refs = [
        RomRef(0x01D839, 0x00)
    ]

    atk_control_refs = [
        RomRef(0x01D8FD, 0x00), RomRef(0x01D924, 0x04), RomRef(0x01D961, 0x07),
        RomRef(0x01D9A7, 0x00), RomRef(0x01D9BB, 0x00), RomRef(0x3DAB19, 0x01),
        RomRef(0x3DAB26, 0x02)
    ]

    atk_effect_refs = [RomRef(0x01D946, 0x00)]

    def __init__(self,
                 tech_controls: bytes = b'',
                 tech_effects: bytes = b'',
                 tech_gfx: bytes = b'',
                 tech_targets: bytes = b'',
                 atk_controls: bytes = b'',
                 atk_effects: bytes = b'',
                 atk_gfx_1: bytes = b'',
                 atk_gfx_2: bytes = b'',):
        self._tech_controls = bytearray(tech_controls)
        self._tech_effects = bytearray(tech_effects)
        self._tech_gfx = bytearray(tech_gfx)
        self._tech_targets = bytearray(tech_targets)

        self._atk_controls = bytearray(atk_controls)
        self._atk_effects = bytearray(atk_effects)
        self._atk_gfx_1 = bytearray(atk_gfx_1)
        self._atk_gfx_2 = bytearray(atk_gfx_2)

    def get_tech_control(self, tech_id: int) -> EnemyControlHeader:
        return EnemyControlHeader(self._tech_controls,
                                  tech_id*EnemyControlHeader.SIZE)

    def get_tech_effect(self, tech_id: int) -> EnemyEffectHeader:
        return EnemyEffectHeader(self._tech_effects,
                                 tech_id*EnemyEffectHeader.SIZE)

    def get_tech_gfx(self, tech_id: int) -> EnemyTechGfxHeader:
        return EnemyTechGfxHeader(self._tech_gfx,
                                  tech_id*EnemyTechGfxHeader.SIZE)

    def get_tech_target(self, tech_id: int) -> EnemyTargetData:
        return EnemyTargetData(self._tech_targets,
                               tech_id*EnemyTargetData.SIZE)

    def get_tech(self, tech_id: int) -> EnemyTech:
        control = self.get_tech_control(tech_id)
        effect = self.get_tech_effect(tech_id)
        gfx = self.get_tech_gfx(tech_id)
        target = self.get_tech_target(tech_id)

        return EnemyTech(control, effect, gfx, target)

    def get_atk_control(self, atk_id: int):
        return EnemyAtkControlHeader(self._atk_controls,
                                     atk_id*EnemyControlHeader.SIZE)

    def get_atk_effect(self, atk_id: int):
        return EnemyEffectHeader(self._atk_effects,
                                 atk_id*EnemyEffectHeader.SIZE)

    def get_atk(self, atk_id: int) -> EnemyAttack:
        control = self.get_atk_control(atk_id)
        effect = self.get_atk_effect(atk_id)

        return EnemyAttack(control, effect)

    def get_atk_count(self) -> int:
        return len(self._atk_effects)//EnemyEffectHeader.SIZE

    def copy_atk_gfx(self,
                     changed_enemy_id: ctenums.EnemyID,
                     copied_enemy_id: ctenums.EnemyID):
        new_gfx_1 = EnemyAtkGfxHeader(self._atk_gfx_1,
                                      copied_enemy_id*EnemyAtkGfxHeader.SIZE)
        new_gfx_2 = EnemyAtkGfxHeader(self._atk_gfx_2,
                                      copied_enemy_id*EnemyAtkGfxHeader.SIZE)

        self._set_atk_gfx(new_gfx_1, changed_enemy_id,
                          is_secondary_attack=False)
        self._set_atk_gfx(new_gfx_2, changed_enemy_id,
                          is_secondary_attack=True)

    def _set_data_record(self,
                         data: _FixedLengthRecord,
                         target: bytearray,
                         record_id: int):

        start = record_id*data.SIZE
        end = (record_id+1)*data.SIZE
        target[start:end] = data.get_as_bytearray()

    def _set_tech_control(self, control: EnemyControlHeader, tech_id: int):
        self._set_data_record(control, self._tech_controls, tech_id)

    def _set_tech_effect(self, effect: EnemyEffectHeader, tech_id: int):
        self._set_data_record(effect, self._tech_effects, tech_id)

    def _set_tech_gfx(self, gfx: EnemyTechGfxHeader, tech_id: int):
        self._set_data_record(gfx, self._tech_gfx, tech_id)

    def _set_tech_target(self, target: EnemyTargetData, tech_id: int):
        self._set_data_record(target, self._tech_targets, tech_id)

    def set_tech(self, tech: EnemyTech, tech_id: int):
        if not 0 <= tech_id < 0x100:
            print('Error: Enemy tech_id must be in range(0, 0x100)')
            exit()

        if tech.control.get_effect_index(0) != tech_id:
            # print('Warning: effect index does not match tech_id.  Changing.')
            tech.control.set_effect_index(0, tech_id)

        self._set_tech_control(tech.control, tech_id)
        self._set_tech_effect(tech.effect, tech_id)
        self._set_tech_gfx(tech.gfx, tech_id)
        self._set_tech_target(tech.target, tech_id)

    def _set_atk_control(self, control: EnemyAtkControlHeader, atk_id: int):
        self._set_data_record(control, self._atk_controls, atk_id)

    def _set_atk_effect(self, effect: EnemyEffectHeader, atk_id: int):
        self._set_data_record(effect, self._atk_effects, atk_id)

    def _set_atk_gfx(self, gfx: EnemyAtkGfxHeader, enemy_id: int,
                     is_secondary_attack: bool = False):
        if is_secondary_attack:
            self._set_data_record(gfx, self._atk_gfx_2, enemy_id)
        else:
            self._set_data_record(gfx, self._atk_gfx_1, enemy_id)

    def append_attack(self, attack: EnemyAttack) -> int:
        new_index = len(self._atk_controls) // EnemyControlHeader.SIZE
        attack.control.effect_index = new_index
        self.set_attack(attack, new_index)

        return new_index

    def set_attack(self, attack: EnemyAttack, atk_id: int):
        self._set_atk_control(attack.control, atk_id)
        self._set_atk_effect(attack.effect, atk_id)
        
    @classmethod
    def _repoint_data(cls,
                      base_rom_ptr: int,
                      refs: list[RomRef],
                      rom: typing.Union[bytearray, memoryview]):
        for ref in refs:
            ptr = ref.file_loc
            offset = ref.offset
            new_ptr = base_rom_ptr + offset
            rom[ptr:ptr+3] = int.to_bytes(new_ptr, 3, 'little')

    @classmethod
    def _get_num_atks_from_rom(cls, rom: bytes):
        max_atk_id = 0
        for enemy_id in range(0x100):
            stats = enemystats.EnemyStats.from_rom(
                rom, ctenums.EnemyID(enemy_id))
            max_atk_id = max(stats.secondary_attack_id, max_atk_id)

        return max_atk_id

    @classmethod
    def _get_records_from_rom(cls,
                              rom: bytes,
                              start: int,
                              num_records: int,
                              record_size: int):
        return bytearray(rom[start:start+num_records*record_size])

    # Unlike player techs which have variable length, the enemy attacks/techs
    # always have 0x100 records.
    @classmethod
    def from_rom(cls, rom: bytes):

        # There are 0x100 techs, and there will never be any more.
        # So there is no risk of the enemy tech data moving around...
        # ... unless we need to move it to free up space in that bank.
        num_techs = 0x100

        tech_controls = cls._get_records_from_rom(
            rom, cls.TECH_CONTROL_START, num_techs, EnemyControlHeader.SIZE
        )

        tech_effects = cls._get_records_from_rom(
            rom, cls.TECH_EFFECT_START, num_techs, EnemyEffectHeader.SIZE
        )

        tech_gfx = cls._get_records_from_rom(
            rom, cls.TECH_GFX_START, num_techs, EnemyTechGfxHeader.SIZE
        )

        tech_targets = cls._get_records_from_rom(
            rom, cls.TECH_TARGET_START, num_techs, EnemyTargetData.SIZE
        )

        # Enemy attack data is different!
        # Every enemy shares Attack 0, but then each enemy has a secondary
        # attack which may be shared by other enemies.

        # First, read the rom to see how many attacks there are.
        max_atk_id = 0
        for enemy_id in range(0x100):
            stats = enemystats.EnemyStats.from_rom(
                rom, ctenums.EnemyID(enemy_id))
            max_atk_id = max(stats.secondary_attack_id, max_atk_id)

        # print(f'Found 0x{max_atk_id:02X} attacks')
        num_enemies = 0x100
        num_attacks = max_atk_id + 1

        # Default 0x0C88CA
        atk_control_start = byteops.file_ptr_from_rom(
            rom, cls.ATK_CONTROL_PTR
        )

        # Default: 0x0C89C6
        atk_controls = cls._get_records_from_rom(
            rom, atk_control_start, num_attacks, EnemyControlHeader.SIZE
        )

        atk_effect_start = byteops.file_ptr_from_rom(
            rom, cls.ATK_EFFECT_PTR
        )

        atk_effects = cls._get_records_from_rom(
            rom, atk_effect_start, num_attacks, EnemyEffectHeader.SIZE
        )

        # Each enemy does have unique graphics headers for both attacks
        atk_gfx_1 = cls._get_records_from_rom(
            rom, cls.ATK_GFX_1_START, num_enemies, EnemyAtkGfxHeader.SIZE
        )

        atk_gfx_2 = cls._get_records_from_rom(
            rom, cls.ATK_GFX_2_START, num_enemies, EnemyAtkGfxHeader.SIZE
        )

        return EnemyAttackDB(tech_controls, tech_effects, tech_gfx,
                             tech_targets,
                             atk_controls,
                             atk_effects,
                             atk_gfx_1, atk_gfx_2)

    @classmethod
    def from_ctrom(cls, ct_rom: ctrom.CTRom):
        return cls.from_rom(ct_rom.rom_data.getbuffer())

    def write_to_ctrom(self, ct_rom: ctrom.CTRom):

        rom = ct_rom.rom_data
        # For tech data, just overwrite the original spot
        if len(self._tech_controls) == 0x100*EnemyControlHeader.SIZE:
            rom.seek(self.TECH_CONTROL_START)
            rom.write(self._tech_controls)
        else:
            raise ValueError('Incorrect tech control size.')

        if len(self._tech_effects) == 0x100*EnemyEffectHeader.SIZE:
            tech_effect_start = 0x0C7AC9
            rom.seek(tech_effect_start)
            rom.write(self._tech_effects)
        else:
            raise ValueError('Incorrect tech effect size.')

        if len(self._tech_gfx) == 0x100*EnemyTechGfxHeader.SIZE:
            rom.seek(self.TECH_GFX_START)
            rom.write(self._tech_gfx)
        else:
            raise ValueError('Incorrect tech gfx size.')

        if len(self._tech_targets) == 0x100*EnemyTargetData.SIZE:
            rom.seek(self.TECH_TARGET_START)
            rom.write(self._tech_targets)
        else:
            raise ValueError('Incorrect tech targets size.')

        # For attack gfx_1, gfx_2, also put back in place.
        if len(self._atk_gfx_1) == 0x100*EnemyAtkGfxHeader.SIZE:
            rom.seek(self.ATK_GFX_1_START)
            rom.write(self._atk_gfx_1)
        else:
            raise ValueError('Incorrect atk gfx 1 size')

        if len(self._atk_gfx_2) == 0x100*EnemyAtkGfxHeader.SIZE:
            rom.seek(self.ATK_GFX_2_START)
            rom.write(self._atk_gfx_2)
        else:
            raise ValueError('Incorrect atk gfx 2 size')

        num_attacks = self._get_num_atks_from_rom(rom.getbuffer())
        atk_control_orig_start = byteops.file_ptr_from_rom(
            rom.getbuffer(), self.ATK_CONTROL_PTR
        )

        atk_effect_orig_start = byteops.file_ptr_from_rom(
            rom.getbuffer(), self.ATK_EFFECT_PTR
        )

        MARK_FREE = ctrom.freespace.FSWriteType.MARK_FREE

        # controls and effects have the same size always
        if len(self._atk_controls) <= num_attacks*EnemyControlHeader.SIZE:
            # Safe to overwrite
            rom.seek(atk_control_orig_start)
            rom.write(self._atk_controls)

            rom.seek(atk_effect_orig_start)
            rom.write(self._atk_effects)
        else:
            rom.seek(atk_control_orig_start)
            rom.mark(num_attacks*EnemyControlHeader.SIZE, MARK_FREE)

            rom.seek(atk_effect_orig_start)
            rom.mark(num_attacks*EnemyEffectHeader.SIZE, MARK_FREE)

            atk_control_start = rom.write_data_to_freespace(
                self._atk_controls
            )

            self._repoint_data(
                byteops.to_rom_ptr(atk_control_start),
                self.atk_control_refs,
                rom.getbuffer()
            )

            atk_effect_start = rom.write_data_to_freespace(
                self._atk_effects
            )

            self._repoint_data(
                byteops.to_rom_ptr(atk_effect_start),
                self.atk_effect_refs,
                rom.getbuffer()
            )
