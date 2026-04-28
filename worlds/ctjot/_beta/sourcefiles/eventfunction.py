'''
Module with classes for manipulating snippets of event scripts.
'''
from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Optional

from eventcommand import get_command, EventCommand


class CommandNotFoundException(Exception):
    '''Raise when a find_exact_command call fails.'''


class EventFunction:

    @dataclass
    class JumpRecord:
        from_label: str = ''
        to_label: str = ''

        def copy(self) -> EventFunction.JumpRecord:
            return EventFunction.JumpRecord(self.from_label, self.to_label)

    def __init__(self):
        self.data: bytearray = bytearray()
        self.commands: list[EventCommand] = []
        self.offsets: list[int] = []

        self.labels: dict[str: int] = {}
        self.jumps: list[EventFunction.JumpRecord] = []

        self.pos = 0

    def copy(self) -> EventFunction:
        ret_ef = EventFunction()
        ret_ef.data = self.data[:]
        ret_ef.commands = self.commands[:]
        ret_ef.offsets = self.offsets[:]
        ret_ef.labels = dict(self.labels.items())
        ret_ef.jumps = [replace(x) for x in self.jumps]

        return ret_ef

    # This feels really silly because we're almost having to repeat the
    # logic from ctevent.  But that's just where we are now.
    def __shift_jumps(self,
                      before_pos: int,
                      after_pos: int,
                      shift_magnitude: int):

        # for label in self.labels:
        #     print(label, ':', self.labels[label])

        # print(f'__shift_jumps({before_pos:04X}, {after_pos:04X}, '
        #       f'{shift_magnitude:04X})')
        del_inds = []

        for ind, jump in enumerate(self.jumps):

            # from_label should always be valid
            orig_from_pos = self.labels[jump.from_label]
            from_jump_cmd = self.data[orig_from_pos]

            if from_jump_cmd in EventCommand.conditional_commands and \
               shift_magnitude > 0:
                # It's easier if the default behavior is to not extend an
                # if block when inserting at the very end of one.

                # When deleting (shift is negative) we should shift the
                # conditional's end label back
                to_after_pos = after_pos + 1
            else:
                to_after_pos = after_pos

            # When a label involved in a jump is not set yet, that's ok.
            # just set the from and/or to pos to -1 so that it avoids shifting
            if jump.from_label in self.labels:
                orig_from_pos = self.labels[jump.from_label]
            else:
                orig_from_pos = -1

            if jump.to_label in self.labels:
                orig_to_pos = self.labels[jump.to_label]
            else:
                orig_to_pos = -1

            # Putting a comment here because it was wrong for a while.
            # If the from_pos is in [before, after), delete the jump.
            # But if the to_pos==before, don't delete it.  That jump is fine.
            # If we're inserting commands, it will point to the inserted block.
            # If we're deleting commands, it will point to the first command
            # after the deleted block.
            if before_pos <= orig_from_pos < after_pos or \
               before_pos < orig_to_pos < after_pos:

                del_inds.append(ind)
            else:
                if orig_from_pos >= after_pos and jump.from_label[0] == '[':
                    new_from_pos = orig_from_pos + shift_magnitude
                    jump.from_label = f'[{new_from_pos:04X}]'

                if orig_to_pos >= to_after_pos and jump.to_label[0] == '[':
                    new_to_pos = orig_to_pos + shift_magnitude
                    jump.to_label = f'[{new_to_pos:04X}]'

            # print(jump)

        for ind in sorted(del_inds, reverse=True):
            del self.jumps[ind]

    def __shift_labels(self,
                       before_pos: int,
                       after_pos: int,
                       shift_magnitude: int):

        labels_to_delete = []
        shifted_label_dict = {}

        for label in self.labels:
            if before_pos <= self.labels[label] < after_pos:
                labels_to_delete.append(label)
            elif self.labels[label] >= after_pos:
                new_pos = self.labels[label] + shift_magnitude
                if label[0] == '[':
                    labels_to_delete.append(label)

                    new_label = f'[{new_pos:04X}]'
                    shifted_label_dict[new_label] = new_pos
                else:
                    self.labels[label] = new_pos

        for label in labels_to_delete:
            del self.labels[label]

        self.labels.update(shifted_label_dict)

    def __get_cmd_index_from_pos(self, pos: int):
        return self.offsets.index(pos)

    @staticmethod
    def from_bytearray(func_bytes: bytearray) -> EventFunction:
        ret = EventFunction()

        pos = 0
        while pos < len(func_bytes):
            cmd = get_command(func_bytes, pos)
            ret.add(cmd)
            pos += len(cmd)

        return ret

    def add(self, event_command: EventCommand,
            register_jump: bool = True) -> EventFunction:

        self.commands.append(event_command)
        self.offsets.append(self.pos)
        self.data.extend(event_command.to_bytearray())

        if register_jump and \
           event_command.command in EventCommand.jump_commands:

            is_back_jump = \
                event_command.command in EventCommand.back_jump_commands
            jump_mult = 1 - 2*(is_back_jump)

            target = (
                self.pos + len(event_command) +
                jump_mult*event_command.args[-1] - 1
            )

            # self.__set_pos_label(target)
            self.jumps.append(
                EventFunction.JumpRecord(
                    self.__get_label(self.pos),
                    self.__get_label(target)
                )
            )

        self.pos += len(event_command)

        return self

    def delete_at_index(self, ind: int):

        del_pos = self.offsets[ind]
        cmd_len = len(self.commands[ind])
        self.__shift_jumps(del_pos, del_pos+cmd_len,
                           -cmd_len)
        self.__shift_labels(del_pos, del_pos+cmd_len,
                            -cmd_len)

        for i in range(ind+1, len(self.offsets)):
            self.offsets[i] -= cmd_len

        del self.offsets[ind]
        del self.commands[ind]
        del self.data[del_pos:del_pos+cmd_len]

        self.pos -= cmd_len

    def insert_at_index(self, event_function: EventFunction, ind: int):
        pos = self.offsets[ind]
        self.insert(event_function, pos)

    def insert(self, event_function: EventFunction, pos: int):

        # print('inserting:')
        # print(event_function)
        # print('into')
        # print(self)
        # print(self.jumps)
        # print(f'at {pos:04X}')
        # Shift all of the function's jumps and labels
        # After shifting, we should be able to just append the function's
        # labels and jumps into self
        ins_function = event_function.copy()
        ins_function.__shift_jumps(0, 0, pos)
        ins_function.__shift_labels(0, 0, pos)

        for ind, _ in enumerate(ins_function.offsets):
            ins_function.offsets[ind] += pos

        if pos == self.pos:
            ins_index = len(self.commands)
        else:
            ins_index = self.offsets.index(pos)

        self.__shift_jumps(pos, pos, len(ins_function))
        self.__shift_labels(pos, pos, len(ins_function))

        # self.data[pos:pos] = ins_function.get_bytearray()
        self.data[pos:pos] = ins_function.data[:]

        for i in range(ins_index, len(self.offsets)):
            self.offsets[i] += len(ins_function)
        self.offsets[ins_index:ins_index] = ins_function.offsets[:]

        self.commands[ins_index:ins_index] = ins_function.commands[:]

        self.jumps.extend(ins_function.jumps)
        self.labels.update(ins_function.labels)

        self.pos += len(ins_function)

        return self

    def append(self, event_function: EventFunction):

        return self.insert(event_function, self.pos)

    def find_command(self, command_ids: list[int]) -> list[int]:

        ret_ind = [self.commands.index(x) for x in self.commands
                   if x.command in command_ids]
        return ret_ind

    def find_exact_command(self, event_command: EventCommand,
                           loose_match_jumps: bool = True) -> int:

        for ind, cmd in enumerate(self.commands):

            if event_command.command in EventCommand.jump_commands and \
               loose_match_jumps:
                if event_command.command == cmd.command and \
                   event_command.args[0:-1] == cmd.args[0:-1]:
                    return ind
            elif cmd == event_command:
                return ind

        raise CommandNotFoundException

    @classmethod
    def if_do(cls, if_command: EventCommand,
              if_block: EventFunction):
        return EventFunction().add_if(if_command, if_block)

    @classmethod
    def if_else(cls, if_command: EventCommand,
                if_block: EventFunction,
                else_block: EventFunction):
        return EventFunction().add_if_else(if_command, if_block, else_block)

    @classmethod
    def while_do(cls, if_command: EventCommand,
                 while_block: EventFunction):
        return EventFunction().add_while(if_command, while_block)

    def __set_label(self, label: str, pos: Optional[int] = None):
        if label in self.labels and label[0] != '[':
            print(f'Warning: Resetting label {label}.')

        if pos is None:
            pos = self.pos

        self.labels[label] = pos

        return self

    def __set_pos_label(self, pos: Optional[int] = None):
        if pos is None:
            pos = self.pos

        label = f'[{pos:04X}]'
        self.__set_label(label, pos)

    def __get_label(self, pos: Optional[int] = None) -> str:
        if pos is None:
            pos = self.pos

        if pos in self.labels.values():
            label = next(label for label in self.labels
                         if self.labels[label] == pos)
            return label

        label = f'[{pos:04X}]'
        self.__set_label(label, pos)
        return label

    def set_label(self, label: str,
                  pos: Optional[int] = None) -> EventFunction:
        if not label[0].isalpha():
            raise ValueError(
                'Error: User generated labels must begin with a letter.'
            )

        return self.__set_label(label, pos)

    def jump_to_label(self, event_command: EventCommand, label: str):
        jump_cmds = (
            EventCommand.fwd_jump_commands +
            EventCommand.back_jump_commands
        )

        if event_command.command not in jump_cmds:
            raise ValueError(
                f'Error: {event_command.command:02X} is not a jump command'
            )

        from_label = self.__get_label()

        self.add(event_command, register_jump=False)
        self.__add_jump(from_label, label)

        return self

    def __add_jump(self, from_label, to_label):

        from_pos = self.labels[from_label]
        from_cmd = self.data[from_pos]

        jump_cmds = (
            EventCommand.fwd_jump_commands +
            EventCommand.back_jump_commands
        )

        if from_cmd not in jump_cmds:
            raise ValueError(
                f'Error: {from_cmd:02X} is not a jump command'
            )

        self.jumps.append(self.JumpRecord(from_label, to_label))

        return self

    def __add_jump_from_pos(self, from_pos, to_pos):
        from_label = self.__get_label(from_pos)
        to_label = self.__get_label(to_pos)

        self.__add_jump(from_label, to_label)

    # if (if command):
    #     if_block
    # rest of eventfunction
    def add_if(self, if_command, if_block: EventFunction):
        from_label = self.__get_label()
        self.add(if_command, register_jump=False)

        self.append(if_block)
        to_label = self.__get_label()

        self.__add_jump(from_label, to_label)

        return self

    #         if (if command):
    #             if_block
    #             goto label2
    #         else_block
    # label2:
    def add_if_else(self, if_command,
                    if_block: EventFunction,
                    else_block: EventFunction):

        if_start_pos = self.pos
        if_block.add(EventCommand.jump_forward(0),
                     register_jump=False)
        self.add(if_command, register_jump=False)
        self.append(if_block)

        jump_over_else_pos = self.pos - len(EventCommand.jump_forward(0))
        else_start_pos = self.pos

        self.append(else_block)
        after_else_pos = self.pos

        self.__add_jump(
            self.__get_label(if_start_pos),
            self.__get_label(else_start_pos)
        )
        self.__add_jump(
            self.__get_label(jump_over_else_pos),
            self.__get_label(after_else_pos)
        )

        return self

    #  label1:  if(if_cmd):  (to label2)
    #               while_block
    #               jump label1
    #  label2:
    def add_while(self, if_command, while_block: EventFunction):

        start_loop_label = self.__get_label()
        while_block.add(EventCommand.jump_back(0),
                        register_jump=False)
        self.add_if(if_command, while_block)

        from_pos = self.pos - len(EventCommand.jump_back(0))
        from_label = self.__get_label(from_pos)

        self.jumps.append(
            self.JumpRecord(from_label, start_loop_label)
        )

        return self

    def __len__(self):
        return len(self.data)

    def __str__(self):
        ret = ''
        pos = 0

        self.resolve_jumps()
        reverse_labels = {pos: label for label, pos in self.labels.items()}
        # jump_pos = [x.from_pos for x in self.jumps]
        # jump_labels = (x.from_label for x in self.jumps)
        jump_pos = [self.labels[x]
                    for x in (y.from_label for y in self.jumps)]

        indent_level = 0
        decr_indent_positions = []

        conditionals = EventCommand.fwd_jump_commands[:]
        conditionals.remove(0x10)

        for i in range(len(self.commands)):

            if pos in reverse_labels:
                # print(f'{pos} in label positions')
                label = reverse_labels[pos]
            else:
                # print(f'{pos} nope')
                label = ''

            label = label.ljust(8)

            if pos in jump_pos:
                index = jump_pos.index(pos)
                jump_label = self.jumps[index].to_label
                jump_label = f' (to: {jump_label})'
            else:
                jump_label = ''

            ret += label
            ret += ('    '*indent_level)
            ret += (f"[{self.offsets[i]:04X}]" + str(self.commands[i]))
            ret += jump_label
            ret += '\n'

            if self.commands[i].command in conditionals:
                indent_level += 1
                target = (
                    pos + len(self.commands[i]) +
                    self.commands[i].args[-1] - 1
                )
                decr_indent_positions.append(target)

            pos += len(self.commands[i])
            while pos in decr_indent_positions:
                indent_level -= 1
                decr_indent_positions.remove(pos)

        return ret

    def resolve_jumps(self):
        for jump_record in self.jumps:

            if jump_record.from_label not in self.labels or \
               jump_record.to_label not in self.labels:
                # print('Ignoring')
                # input()
                # Ignore labels that don't exist.  Assume they are in the
                # outer scope.
                continue

            # print('From:', self.labels[jump_record.from_label])
            # print('  To:', self.labels[jump_record.to_label])
            from_pos = self.labels[jump_record.from_label]
            from_index = self.__get_cmd_index_from_pos(from_pos)
            command = self.commands[from_index]

            cmd_id = command.command  # gross

            to_pos = self.labels[jump_record.to_label]

            jump_length = (to_pos - (from_pos+len(command)))

            jump_cmds = \
                EventCommand.fwd_jump_commands + \
                EventCommand.back_jump_commands

            if cmd_id not in jump_cmds:
                print(jump_record)
                for i, x in enumerate(self.offsets):
                    print(f'[{x:04X}]\t{self.commands[i]}')
                raise ValueError('JumpRecord does not point to a jump cmd')

            if cmd_id in EventCommand.back_jump_commands and jump_length > 0:
                raise ValueError('Back jump jumps to forward label')

            if cmd_id in EventCommand.fwd_jump_commands and jump_length < 0:
                raise ValueError('Forward jump jumps to backward label')

            jump_length = abs(jump_length + 1)
            command.args[-1] = jump_length
            try:
                # print(f'Writing {jump_length:02X} to '
                #       f'[{from_pos+len(command)-1:04X}]')
                # print(
                #     'Current Value:'
                #     f'{self.data[from_pos+len(command)-1]:02X}'
                # )
                self.data[from_pos+len(command)-1] = jump_length
            except IndexError:
                pass

    def get_bytearray(self):
        '''Get this function in a bytearray as it would appear in a script.'''
        self.resolve_jumps()
        return self.data
