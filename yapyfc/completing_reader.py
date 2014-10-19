import os.path
import re

from pyrepl.commands import Command
from pyrepl.input import KeymapTranslator
from pyrepl.reader import SYNTAX_WORD, Reader


# XXX lots of c/p from pyrepl's completion reader
from termcolor import colored


COMPLETION_KEYMAP = [
    (r"\<right>", "complete-next")
]

STRIPCOLOR_REGEX = re.compile(r"\x1B\[([0-9]{1,3}(;[0-9]{1,2})?)?[m|K]")


def stripcolor(s):
    return STRIPCOLOR_REGEX.sub('', s)


def real_len(s):
    return len(stripcolor(s))


def left_align(s, maxlen):
    stripped = stripcolor(s)
    if len(stripped) > maxlen:
        # too bad, we remove the color
        return stripped[:maxlen]
    padding = maxlen - len(stripped)
    return s + ' ' * padding


def build_menu(cons, wordlist, selected_entry, sort_in_column):
    item = "%s  "
    padding = 2
    maxlen = min(max(map(real_len, wordlist)), cons.width - padding)
    cols = cons.width // (maxlen + padding)
    rows = (len(wordlist) - 1) // cols + 1

    if sort_in_column:
        # sort_in_column=False (default)     sort_in_column=True
        #          A B C                       A D G
        #          D E F                       B E
        #          G                           C F
        #
        # "fill" the table with empty words, so we always have the same amout
        # of rows for each column
        missing = cols * rows - len(wordlist)
        wordlist = wordlist + [''] * missing
        indexes = [(i % cols) * rows + i // cols for i in range(len(wordlist))]
        wordlist = [wordlist[i] for i in indexes]
    menu = []
    i = 0
    for r in range(rows):
        row = []
        for col in range(cols):
            entry = item % left_align(wordlist[i], maxlen)
            if (selected_entry >= 0 and (sort_in_column and i == indexes[
                selected_entry] or not sort_in_column and i == selected_entry)):
                entry = colored(entry, attrs=["reverse"])
            row.append(entry)
            i += 1
            if i >= len(wordlist):
                break
        menu.append(''.join(row))
        if i >= len(wordlist):
            i = 0
            break
        if r + 5 > cons.height:
            menu.append("   %d more... " % (len(wordlist) - i))
            break
    return menu, i


class CompletingReader(Reader):
    def __init__(self, **kwargs):
        super(CompletingReader, self).__init__(**kwargs)
        self.completion_menu = []
        self.completion_menu_visible = False
        self.selected_completion_entry = -1
        self.completion_input_translator = KeymapTranslator(
            COMPLETION_KEYMAP,
            character_cls=complete_end,
            invalid_cls=complete_end)
        self.commands["complete"] = complete
        self.commands["complete-next"] = complete_next
        self.commands["complete_end"] = complete_end

    def collect_keymap(self):
        for (key, command) in super(CompletingReader, self).collect_keymap():
            yield (key, command)
        yield ("\\t", "complete")

    def calc_screen(self):
        screen = super(CompletingReader, self).calc_screen()
        if self.completion_menu_visible:
            lineno = self.lxy[1] + 1
            screen[lineno:lineno] = self.completion_menu
            self.screeninfo[lineno:lineno] = [(0, [])] * len(self.completion_menu)
        return screen

    def after_command(self, cmd):
        super(CompletingReader, self).after_command(cmd)
        if not isinstance(cmd, complete):
            self.reset_completion()
            self.dirty = True

    def finish(self):
        super(CompletingReader, self).finish()
        self.reset_completion()

    def reset_completion(self):
        self.selected_completion_entry = -1
        self.completion_menu_visible = False

    def get_stem(self):
        st = self.syntax_table
        b = self.buffer
        p = self.pos - 1
        while p >= 0 and st.get(b[p], SYNTAX_WORD) == SYNTAX_WORD:
            p -= 1
        return ''.join(b[p + 1:self.pos])


class complete(Command):
    def do(self):
        reader = self.reader
        last_was_complete = reader.last_command_is(type(self))
        stem = reader.get_stem()
        # XXX don't pass stem?
        completions = reader.get_completions(stem)
        if len(completions) == 1:
            reader.insert(completions[0][len(stem):])
        elif completions:
            prefix = os.path.commonprefix(completions)
            if prefix:
                reader.insert(prefix[len(stem):])
            if last_was_complete:
                reader.completion_menu, _ = build_menu(
                    reader.console, completions,
                    reader.selected_completion_entry, True)
                reader.completion_menu_visible = True
                reader.dirty = True
                reader.push_input_trans(reader.completion_input_translator)


class complete_next(Command):
    def do(self):
        reader = self.reader
        completions = reader.get_completions(reader.get_stem())
        reader.selected_completion_entry = (
            reader.selected_completion_entry + 1) % len(completions)
        reader.completion_menu, _ = build_menu(
            reader.console, completions, reader.selected_completion_entry,
            True)
        reader.dirty = True


class complete_end(Command):
    def do(self):
        self.reader.reset_completion()
        self.reader.pop_input_trans()
        self.reader.dirty = True
