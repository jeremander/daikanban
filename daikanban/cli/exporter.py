from enum import Enum
from importlib import import_module
from pathlib import Path
from typing import Optional

from daikanban import logger
from daikanban.cli import _load_board
from daikanban.io import BaseExporter


class ExportFormat(str, Enum):
    """Enumeration of known BoardExporter export formats."""
    daikanban = 'daikanban'
    taskwarrior = 'taskwarrior'

    @property
    def exporter(self) -> BaseExporter:
        """Gets the BaseExporter class associated with this format."""
        mod = import_module(f'daikanban.ext.{self.name}')
        return mod.EXPORTER


def export_board(export_format: ExportFormat, board_file: Optional[Path] = None, output_file: Optional[Path] = None) -> None:
    """Exports a board to a file using the given format."""
    board = _load_board(board_file)
    logger.info(f'Board has {board._num_proj_num_task_str}')
    if output_file is None:
        output_file = Path('/dev/stdout')
    logger.info(f'Exporting to {output_file}')
    with logger.catch_errors(Exception):
        export_format.exporter.export_board(board, output_file)
