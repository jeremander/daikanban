from pathlib import Path
from typing import Any, Optional

from daikanban import logger
from daikanban.config import get_config
from daikanban.model import Board, BoardFileError, load_board


# default settings for typer app
APP_KWARGS: dict[str, Any] = {
    'add_completion': False,
    'context_settings': {
        'help_option_names': ['-h', '--help']
    },
    # if True, display "pretty" (but very verbose) exceptions
    'pretty_exceptions_enable': False
}

@logger.catch_errors(BoardFileError)
def _load_board(board_path: Optional[Path] = None) -> Board:
    if board_path:
        logger.info(f'Loading board: {board_path}')
        return load_board(board_path)
    # TODO: use default board (for now, an empty board)
    return Board(name='')

def _save_board(board: Board, board_path: Path) -> None:
    logger.info(f'Saving board: {board_path}')
    json_indent = get_config().file.json_indent
    board.save(board_path, indent=json_indent)
