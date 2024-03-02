import json
from pathlib import Path
from typing import Annotated, Optional

import rich
import typer

from daikanban.model import DaiKanban
from daikanban.utils import handle_error


def shell(
    board: Annotated[Optional[Path], typer.Option(help='DaiKanban board JSON file')] = None
) -> None:
    """Activate the DaiKanban shell."""
    rich.print('[cyan]Activating DaiKanban shell...[/]')
    if board is None:
        dk = None
    else:
        with handle_error(OSError):
            with open(board) as f:
                dk = DaiKanban(**json.load(f))
    rich.print(dk)
