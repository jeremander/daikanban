#!/usr/bin/env python3

from pathlib import Path
from typing import Annotated, Optional

from rich import print
import typer

from daikanban import __version__, logger
from daikanban.board import Board
from daikanban.cli import APP_KWARGS
import daikanban.cli.config
from daikanban.cli.exporter import ExportFormat, export_board
from daikanban.cli.importer import ImportFormat, import_board
from daikanban.config import get_config
from daikanban.errors import KanbanError
from daikanban.interface import BoardInterface, list_boards


#######
# APP #
#######

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
    board: Annotated[Optional[Path], typer.Option('--board', '-b', help='DaiKanban board JSON file')] = None,
    output_file: Annotated[Optional[Path], typer.Option('-o', '--output-file')] = None,
) -> None:
    """Export board to another format."""
    export_board(format, board_file=board, output_file=output_file)
    logger.done()

@APP.command(name='import', short_help='import board')
def import_(
    format: Annotated[ImportFormat, typer.Option('-f', '--format', show_default=False, help='Import format')],  # noqa: A002
    board: Annotated[Optional[Path], typer.Option('-b', '--board', show_default=False, help='DaiKanban board name or path to update')] = None,
    input_file: Annotated[Optional[Path], typer.Option('-i', '--input-file', show_default=False, help='file to import')] = None,
) -> None:
    """Import board from another format."""
    import_board(format, board_file=board, input_file=input_file)
    logger.done()

@APP.command(name='list', short_help='list all boards')
def list_() -> None:
    """List all board files."""
    cfg = get_config()
    default_board_path = cfg.board.default_board_path
    list_boards(cfg, active_board_path=default_board_path)

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


@logger.catch_errors(KanbanError)
def run_app() -> None:
    """Runs the main daikanban app."""
    APP()

if __name__ == '__main__':
    run_app()
