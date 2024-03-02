import json
from pathlib import Path
from typing import Annotated, Optional

import rich
import typer

from daikanban.model import Board
from daikanban.utils import handle_error


PKG_DIR = Path(__file__).parent
BILLBOARD_ART_PATH = PKG_DIR / 'billboard_art.txt'

def get_billboard_art() -> str:
    """Loads billboard ASCII art from a file."""
    with open(BILLBOARD_ART_PATH) as f:
        return f.read()


def shell(
    board: Annotated[Optional[Path], typer.Option(help='DaiKanban board JSON file')] = None
) -> None:
    """Activate the DaiKanban shell."""
    rich.print(get_billboard_art())
    rich.print('[italic cyan]Welcome to DaiKanban![/]')
    if board is None:
        dk = None
    else:
        with handle_error(OSError):
            with open(board) as f:
                dk = Board(**json.load(f))
    rich.print(dk)
