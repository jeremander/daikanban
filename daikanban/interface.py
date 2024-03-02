from functools import cache
import json
from pathlib import Path
import re
from typing import Optional

from pydantic import BaseModel, Field
from rich import print
from rich.prompt import Confirm, Prompt

from daikanban.model import Board, BoardConfig
from daikanban.utils import handle_error


PKG_DIR = Path(__file__).parent
BILLBOARD_ART_PATH = PKG_DIR / 'billboard_art.txt'


####################
# HELPER FUNCTIONS #
####################

@cache
def get_billboard_art() -> str:
    """Loads billboard ASCII art from a file."""
    with open(BILLBOARD_ART_PATH) as f:
        return f.read()

def simple_input(prompt: str, default: Optional[str] = None, match: str = '.*') -> str:
    """Prompts the user with the given string until the user's response matches a certain regex."""
    regex = re.compile(match)
    while True:
        result = Prompt.ask(f'[bold]{prompt}[/]', default=default) or ''
        if regex.fullmatch(result):
            break
    return result

def to_snake_case(name: str) -> str:
    """Converts an arbitrary string to snake case."""
    return re.sub(r'[^\w]+', '_', name.strip()).lower()


###################
# BOARD INTERFACE #
###################

class BoardInterface(BaseModel):
    """Interactive user interface to view and manipulate a DaiKanban board.
    This object maintains a state containing the currently loaded board and configurations."""
    board_path: Optional[Path] = Field(
        default=None,
        description='path of current board'
    )
    board: Optional[Board] = Field(
        default=None,
        description='current DaiKanban board'
    )
    config: BoardConfig = Field(
        default_factory=BoardConfig,
        description='board configurations'
    )

    # HELP/INFO

    @staticmethod
    def show_board_schema(indent: int = 2) -> None:
        """Prints out the DaiKanban board JSON schema."""
        print(json.dumps(Board.model_json_schema(mode='serialization'), indent=indent))

    # BOARD

    def load(self, board_path: str | Path) -> None:
        """Loads a board from a JSON file."""
        with open(board_path) as f:
            self.board = Board(**json.load(f))
        self.board_path = Path(board_path)

    def new_board(self) -> None:
        """Interactively creates a new DaiKanban board.
        Implicitly loads that board afterward."""
        print('Creating new DaiKanban board.\n')
        name = simple_input('Board name', match=r'.*[^\s].*')
        default_path = to_snake_case(name) + '.json'
        path = simple_input('Output filename', default=default_path).strip()
        path = path or default_path
        board_path = Path(path)
        create = (not board_path.exists()) or Confirm.ask(f'A file named {path} already exists.\n\tOverwrite?')
        if create:
            description = simple_input('Board description').strip() or None
            board = Board(name=name, description=description)
            with open(path, 'w') as f:
                f.write(board.model_dump_json(indent=2))
            print(f'Saved DaiKanban board {name!r} to [deep_sky_blue3]{path}[/]')
            self.board_path = board_path
            self.board = board

    # SHELL

    def launch_shell(self, board_path: Optional[Path] = None) -> None:
        """Launches an interactive shell to interact with a board.
        Optionally a board path may be provided, which will be loaded after the shell launches."""
        print(get_billboard_art())
        print('[italic cyan]Welcome to DaiKanban![/]')
        if board_path is not None:
            with handle_error(json.JSONDecodeError, OSError):
                self.load(board_path)
        print(self.board)
