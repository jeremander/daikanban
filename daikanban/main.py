#!/usr/bin/env python3

from pathlib import Path
from typing import Annotated, Optional

import typer

from daikanban.interface import BoardInterface
from daikanban.model import Board


APP = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']}
)


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


if __name__ == '__main__':
    APP()
