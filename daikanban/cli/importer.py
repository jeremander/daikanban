from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import Any, Optional, cast

from daikanban import logger
from daikanban.cli import _load_board, _save_board
from daikanban.config import get_config
from daikanban.io import BaseImporter
from daikanban.utils import count_fmt


class ImportFormat(str, Enum):
    """Enumeration of known BoardImporter import formats."""
    daikanban = 'daikanban'
    taskwarrior = 'taskwarrior'

    @property
    def importer(self) -> BaseImporter[Any]:
        """Gets the BaseImporter class associated with this format."""
        mod = import_module(f'daikanban.ext.{self.name}')
        return cast(BaseImporter[Any], mod.IMPORTER)


def import_board(import_format: ImportFormat, board_name_or_path: Optional[str | Path] = None, input_file: Optional[Path] = None) -> None:
    """Imports a board from another format, then merges it with the current board and saves the updated board."""
    cfg = get_config()
    board_path = None if (board_name_or_path is None) else cfg.board.resolve_board_name_or_path(board_name_or_path)
    board = _load_board(board_path)
    num_projects = board.num_projects
    num_tasks = board.num_tasks
    logger.info(f'Current board has {board._num_proj_num_task_str}')
    if input_file is None:
        input_file = Path('/dev/stdin')
    output_file = Path('/dev/stdout') if (board_path is None) else board_path
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
