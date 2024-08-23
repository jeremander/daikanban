#!/usr/bin/env python3

from pathlib import Path
from typing import Annotated, Optional

from rich import print
import typer

from daikanban import __version__, logger
from daikanban.cli import APP_KWARGS
import daikanban.cli.config
from daikanban.cli.export import ExportFormat
from daikanban.interface import BoardInterface
from daikanban.model import Board, load_board


APP = typer.Typer(**APP_KWARGS)

APP.add_typer(
    daikanban.cli.config.APP,
    name='config',
    help='Manage configurations.',
    short_help='manage configurations',
)

@APP.command(short_help='export board')
def export(
    format: Annotated[ExportFormat, typer.Option('-f', '--format', show_default=False, help='Export format')],  # noqa: A002
    # TODO: make this optional once there is a default board
    # board: Annotated[Optional[Path], typer.Option('--board', '-b', help='DaiKanban board JSON file')] = None
    board: Annotated[str, typer.Option('--board', '-b', show_default=False, help='DaiKanban board name or path')],
    output_file: Annotated[Optional[Path], typer.Option('-o', '--output-file')] = None,
) -> None:
    """Export board to another format."""
    logger.info(f'Loading board: {board}')
    board_obj = load_board(board)
    if output_file is None:
        output_file = Path('/dev/stdout')
    logger.info(f'Exporting to {output_file}')
    with logger.catch_errors(Exception):
        format.exporter.export_board(board_obj, output_file)
    logger.done()

@APP.command(short_help='create new board')
def new() -> None:
    """Create a new DaiKanban board."""
    BoardInterface().new_board()

@APP.command(short_help='display JSON schema')
def schema(
    indent: Annotated[int, typer.Option(help='JSON indentation level')] = 2
) -> None:
    """Print out the DaiKanban schema."""
    BoardInterface.show_schema(Board, indent=indent)

@APP.command(short_help='enter interactive shell')
def shell(
    board: Annotated[Optional[Path], typer.Option('--board', '-b', help='DaiKanban board JSON file')] = None
) -> None:
    """Launch the DaiKanban shell."""
    BoardInterface().launch_shell(board_path=board)

@APP.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option('--version', help='show version number')] = False
) -> None:
    """A kanban-style project task queue."""
    if ctx.invoked_subcommand is None:
        if version:
            print(__version__)
        else:
            ctx.get_help()


if __name__ == '__main__':
    APP()
