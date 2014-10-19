import shlex

from gi.repository import Gio, GLib
from pyrepl import commands
from pyrepl.historical_reader import HistoricalReader
from pyrepl.unix_console import UnixConsole
from termcolor import colored

# XXX move completions somewhere else
from .commands import cli
from .completing_reader import CompletingReader


class GioConsole(UnixConsole):
    def __init__(self, **kwargs):
        super(GioConsole, self).__init__(**kwargs)
        self.main_context = GLib.main_context_default()
        self.input_stream = Gio.UnixInputStream.new(self.input_fd, False)
        self._active = False
        self.input_stream.read_bytes_async(
            1, GLib.PRIORITY_HIGH, None, self._read_char, None)

    def prepare(self):
        super(GioConsole, self).prepare()
        self._active = True

    def restore(self):
        super(GioConsole, self).restore()
        self._active = False

    def get_event(self, block=True):
        self.main_context.iteration(block)
        if not self.event_queue.empty():
            return self.event_queue.get()

    def _read_char(self, input_stream, result, _unused):
        if self._active:
            char = input_stream.read_bytes_finish(result)
            self.push_char(char.get_data())
            self.input_stream.read_bytes_async(
                1, GLib.PRIORITY_HIGH, None, self._read_char, None)


class Reader(CompletingReader, HistoricalReader):
    def __init__(self, **kwargs):
        super(Reader, self).__init__(**kwargs)
        self.historyi = 0
        self.history = []
        self._add_commands()

    def _add_commands(self):
        self.commands["accept"] = maybe_accept

    def error(self, msg):
        """More pretty error messages."""
        self.msg = colored(msg, "red")
        self.dirty = True

    def get_completions(self, stem):
        return sorted(
            [name for (name, _) in cli.get_all_commands()
             if name.startswith(stem)])


class maybe_accept(commands.Command):
    def do(self):
        try:
            shlex.split(self.reader.get_unicode())
        except ValueError as exc:
            self.reader.msg = str(exc.args[0])
            self.reader.dirty = True
        else:
            self.finish = True


class complete(commands.Command):
    def do(self):
        pass
