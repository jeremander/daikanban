from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import Optional

from daikanban import logger
from daikanban.cli import _load_board, _save_board
from daikanban.io import BaseImporter
from daikanban.utils import count_fmt


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
    num_projects = board.num_projects
    num_tasks = board.num_tasks
    logger.info(f'Current board has {board._num_proj_num_task_str}')
    if input_file is None:
        input_file = Path('/dev/stdin')
    output_file = Path('/dev/stdout') if (board_file is None) else board_file
    logger.info(f'Importing from {input_file}')
    with logger.catch_errors(Exception):
        imported_board = import_format.importer.import_board(input_file)
    logger.info(f'Imported board has {imported_board._num_proj_num_task_str}')
    # merge new board with current board
    board.update_with_board(imported_board)
    num_new_projects = board.num_projects - num_projects
    num_new_tasks = board.num_tasks - num_tasks
    new_proj_str = count_fmt(num_new_projects, 'new project')
    new_task_str = count_fmt(num_new_tasks, 'new task')
    logger.info(f'Added {new_proj_str}, {new_task_str}.')
    _save_board(board, output_file)
