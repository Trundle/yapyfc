from __future__ import print_function, unicode_literals

import sys
from functools import update_wrapper
from threading import Event

from gi.repository import Gio, GLib

import click
from click.core import Context
from termcolor import colored
from .state import Session


pass_session = click.make_pass_decorator(Session)


def connection_required(f):
    """
    Annotates that a command requires a connection (local or remote,
    depending on the command name). The connection is passed as (first)
    argument. If no connection is established yet, an error message is
    printed an the wrapped function won't be called.
    """

    @click.pass_context
    def wrapper(*args, **kwargs):
        ctx = args[0]
        session = ctx.find_object(Session)
        if is_local_invocation(ctx):
            connection = session.local
        else:
            connection = session.remote
        if connection is not None:
            return ctx.invoke(f, connection, *args[1:], **kwargs)
        else:
            print(colored("Not connected yet!", "red"))

    return update_wrapper(wrapper, f)


def is_local_invocation(ctx):
    return (ctx.info_name == "l" + ctx.command.name)


def returns_new_connection(f):
    @click.pass_context
    def wrapper(*args, **kwargs):
        ctx = args[0]
        session = ctx.find_object(Session)
        connection = ctx.invoke(f, *args[1:], **kwargs)
        if is_local_invocation(ctx):
            session.local = connection
        else:
            session.remote = connection

    return update_wrapper(wrapper, f)


def also_local_command(f):
    f._is_local_command = True
    return f


class LocalGroup(click.Group):
    def get_all_commands(self):
        for (name, command) in self.commands.items():
            yield (name, command)
            if self.is_local_command(command):
                yield ("l" + name, command)

    def get_command(self, ctx, cmd_name):
        cmd = super(LocalGroup, self).get_command(ctx, cmd_name)
        if cmd is not None:
            return cmd
        elif cmd_name.startswith("l"):
            cmd = super(LocalGroup, self).get_command(ctx, cmd_name[1:])
            if cmd is not None and self.is_local_command(cmd):
                return cmd

    @staticmethod
    def is_local_command(cmd):
        f = cmd.callback
        while f is not None:
            if getattr(f, "_is_local_command", False):
                return True
            f = getattr(f, "__wrapped__", None)
        return False


@click.command(cls=LocalGroup)
def cli():
    pass


def _group_commands():
    """Returns a tuple (generic commands, local commands, remote commands)."""
    generic_commands = {}
    local_commands = {}
    remote_commands = {}
    for (name, command) in cli.get_all_commands():
        if name == "help":
            generic_commands[name] = command
            continue
        if LocalGroup.is_local_command(command):
            local_commands[name] = command
        remote_commands[name] = command
    for name in list(local_commands):
        if "l" + name in local_commands:
            del local_commands[name]
        elif name[1:] in remote_commands:
            del remote_commands[name]
    return (generic_commands, local_commands, remote_commands)


@cli.command(add_help_option=False)
@click.argument("command_name", metavar="command", required=False)
@click.pass_context
def help(ctx, command_name):
    """Prints the help."""
    if command_name:
        command = cli.get_command(ctx, command_name)
        cmd_ctx = Context(command, info_name=command_name)
        print(command.get_help(cmd_ctx))
    else:
        longest_name = max(len(name) for (name, _) in cli.get_all_commands())
        (generic_commands, local_commands, remote_commands) = _group_commands()
        commands = [
            ("Generic", generic_commands.items()),
            ("Local", local_commands.items()),
            ("Remote", remote_commands.items())
        ]
        for (i, (type_, commands)) in enumerate(commands):
            if i > 0:
                print("\n")
            print("{} commands:\n".format(type_))
            for (name, command) in sorted(commands):
                print("{:<{}} - {}".format(name, longest_name,
                                           command.short_help or "(unknown)"))


@cli.command(add_help_option=False)
@also_local_command
@click.argument("directory")
@connection_required
@returns_new_connection
def cd(connection, directory):
    """Change directory."""
    child = connection.get_child(directory)
    if child.query_exists():
        return child
    else:
        print(colored("Directory {!r} does not exist".format(directory),
                      "red"))


@cli.command(add_help_option=False)
@also_local_command
@click.argument("uri")
@returns_new_connection
def open(uri):
    """Connects to the given URI."""

    def mount_done(location, result, ignored):
        try:
            location.mount_enclosing_volume_finish(result)
        except GLib.GError as exc:
            print(colored("Could not connect: {}".format(exc.args[0]),
                          "red"))
        else:
            print("Connected to {} :-)".format(location.get_uri()))
        connected.set()

    # XXX disconnect first

    connection = Gio.file_new_for_uri(uri)
    if not connection.query_exists():
        connected = Event()
        mount_operation = Gio.MountOperation()
        connection.mount_enclosing_volume(
            Gio.MountMountFlags.NONE, mount_operation, None,
            mount_done, None)
        while not connected.is_set():
            GLib.main_context_default().iteration(False)
    else:
        print("Connected to", uri)

    return connection


@cli.command(add_help_option=False)
@also_local_command
@connection_required
def pwd(connection):
    """Prints name of the current/working directory."""
    print(connection.get_uri())


@cli.command(add_help_option=False)
@also_local_command
@connection_required
def ls(connection):
    """Lists directory contents."""
    children = connection.enumerate_children(
        Gio.FILE_ATTRIBUTE_STANDARD_NAME, Gio.FileQueryInfoFlags.NONE, None)
    print(" ".join(info.get_name() for info in children))


def get_file_size(file):
    info = file.query_info(
        Gio.FILE_ATTRIBUTE_STANDARD_SIZE, Gio.FileQueryInfoFlags.NONE, None)
    return info.get_size()


@cli.command(add_help_option=False)
@click.option("-R", "--resume", default=False, is_flag=True)
@click.argument("filename")
@pass_session
def get(session, resume, filename):
    if session.remote is None:
        print(colored("Not connected yet.", "red"))
        return
    remote_file = session.remote.get_child(filename)
    if not remote_file.query_exists():
        print(colored("File {!r} does not exist.".format(filename), "red"))
        return
    remote_size = get_file_size(remote_file)
    local_file = session.local.get_child(filename)
    already_exists = local_file.query_exists()
    if already_exists and not resume:
        # XXX ask whether to overwrite
        pass
    input_stream = remote_file.read()
    if resume:
        output_stream = local_file.append_to(Gio.FileCreateFlags.NONE, None)
        info = output_stream.query_info(Gio.FILE_ATTRIBUTE_STANDARD_SIZE, None)
        offset = info.get_size()
        input_stream.seek(offset, GLib.SeekType.SET, None)
    else:
        output_stream = local_file.create(Gio.FileCreateFlags.NONE, None)
    done = Event()
    output_stream.splice_async(
        input_stream,
        Gio.OutputStreamSpliceFlags.CLOSE_SOURCE
        | Gio.OutputStreamSpliceFlags.CLOSE_TARGET,
        GLib.PRIORITY_HIGH,
        None,
        lambda _unused_source, _unused_result, _unused_data: done.set(),
        None)
    return create_get_progress_updater(local_file, remote_size, done)


def create_get_progress_updater(file, size, done):
    def update_progress(context):
        context.iteration()
        current_size = get_file_size(file)
        print("\r{}/{} bytes transferred".format(current_size, size), end="")
        sys.stdout.flush()
        if done.is_set():
            print()
            return False
        return True
    return update_progress
