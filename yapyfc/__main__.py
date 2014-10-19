from __future__ import print_function

import shlex
import sys

from click.exceptions import UsageError

from .commands import cli
from .reader import GioConsole, Reader
from .state import Session


def handle_line(console, connection, line):
    args = shlex.split(line)
    if args:
        with cli.make_context("", args, obj=connection) as ctx:
            try:
                progress_updater = cli.invoke(ctx)
            except SystemExit as exc:
                pass
            except UsageError as exc:
                print(str(exc.args[0]))
            else:
                if progress_updater is not None:
                    while progress_updater(console.main_context):
                        pass


def main(args=None):
    if args is None:
        args = sys.argv[1:]

    console = GioConsole(encoding=sys.stdin.encoding)
    reader = Reader(console=console)

    connection = Session(local_path=".")
    while True:
        try:
            line = reader.readline(returns_unicode=True)
        except EOFError:
            break
        else:
            handle_line(console, connection, line)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
