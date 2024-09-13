from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import Optional

from daikanban import logger
from daikanban.cli import _load_board, _save_board
from daikanban.io import BaseImporter


class ImportFormat(str, Enum):
    """Enumeration of known BoardImporter import formats."""
    daikanban = 'daikanban'
    taskwarrior = 'taskwarrior'

    @property
    def importer(self) -> BaseImporter:
        """Gets the BaseImporter class associated with this format."""
        mod = import_module(f'daikanban.ext.{self.name}')
        return mod.IMPORTER


def import_board(import_format: ImportFormat, board_file: Optional[Path] = None, input_file: Optional[Path] = None) -> None:
    """Imports a board from another format, then merges it with the current board and saves the updated board."""
    board = _load_board(board_file)
    if input_file is None:
        input_file = Path('/dev/stdin')
    output_file = Path('/dev/stdout') if (board_file is None) else board_file
    logger.info(f'Importing from {input_file}')
    with logger.catch_errors(Exception):
        imported_board = import_format.importer.import_board(input_file)
    # merge new board with current board
    board.update_with_board(imported_board)
    # TODO: print summary info
    _save_board(board, output_file)
