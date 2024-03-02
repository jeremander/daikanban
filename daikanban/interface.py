from functools import cache
import json
from pathlib import Path
import re
import sys
from typing import Optional

from pydantic import BaseModel, Field
from rich import print
from rich.prompt import Confirm, Prompt
from rich.table import Table

from daikanban.model import Board, BoardConfig, KanbanError
from daikanban.utils import handle_error


PKG_DIR = Path(__file__).parent
BILLBOARD_ART_PATH = PKG_DIR / 'billboard_art.txt'


class UserInputError(KanbanError):
    """Class for user input errors."""

class BoardNotLoadedError(KanbanError):
    """Error type for when a board has not yet been loaded."""


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

def prefix_match(token: str, match: str, minlen: int = 1) -> bool:
    """Returns true if token is a prefix of match and has length at least minlen."""
    n = len(token)
    return (n >= minlen) and (match[:n] == token)


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
    def show_help() -> None:
        """Displays the help menu listing various commands."""
        grid = Table.grid(expand=True)
        grid.add_column(style='bold grey0', width=5)
        grid.add_column(style='bold grey0', width=6)
        grid.add_column()
        grid.add_row('\[h]elp', '', 'show help menu')
        grid.add_row('\[q]uit', '', 'exit the shell')
        # TODO: global settings?
        # grid.add_row('settings', 'view/edit the settings')
        grid.add_row('\[b]oard', '\[n]new', 'create new board')
        grid.add_row('', '\[l]oad', 'load existing board')
        grid.add_row('', 'schema', 'show board JSON schema')
        grid.add_row('', '\[s]how', 'show current board, can provide extra filters like:')
        grid.add_row('', '', '  status:\[STATUSES] project:\[PROJECT_IDS] tags:\[TAGS] limit:\[SIZE]')
        # TODO: board config?
        print('[bold underline]User options[/]')
        print(grid)

    @staticmethod
    def show_schema(cls: type[BaseModel], indent: int = 2) -> None:
        """Prints out the JSON schema of the given type."""
        print(json.dumps(cls.model_json_schema(mode='serialization'), indent=indent))

    # BOARD

    def load(self, board_path: str | Path) -> None:
        """Loads a board from a JSON file."""
        with open(board_path) as f:
            self.board = Board(**json.load(f))
        self.board_path = Path(board_path)
        print(f'Loaded board from {self.board_path}')

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

    def show_board(self) -> None:
        """Displays the board to the screen using the current configurations."""
        # TODO: take kwargs to filter board contents
        # TODO: display pretty board rather than JSON
        if self.board is None:
            raise BoardNotLoadedError("No board has been loaded.\nRun 'board new' to create a new board or 'board load' to load an existing one.")
        print(self.board.model_dump_json(indent=self.config.json_indent))

    # SHELL

    def evaluate_prompt(self, prompt: str) -> None:
        """Given user prompt, takes a particular action."""
        prompt = prompt.strip()
        if not prompt:
            return None
        tokens = prompt.split()
        ntokens = len(tokens)
        tok0 = tokens[0]
        if prefix_match(tok0, 'board'):
            if ntokens > 1:
                tok1 = tokens[1]
                if prefix_match(tok1, 'show'):
                    return self.show_board()
                if prefix_match(tok1, 'schema', minlen=2):
                    return self.show_schema(Board)
        elif prefix_match(tok0, 'help'):
            return self.show_help()
        elif prefix_match(tok0, 'quit'):
            return self.quit_shell()
        raise UserInputError('Invalid input')

    @staticmethod
    def quit_shell() -> None:
        """Quits the shell and exits the program."""
        print('👋 Goodbye!')
        sys.exit(0)

    def launch_shell(self, board_path: Optional[Path] = None) -> None:
        """Launches an interactive shell to interact with a board.
        Optionally a board path may be provided, which will be loaded after the shell launches."""
        print(get_billboard_art())
        print('[italic cyan]Welcome to DaiKanban![/]')
        # TODO: load default board from global config
        if board_path is not None:
            with handle_error(json.JSONDecodeError, OSError):
                self.load(board_path)
        try:
            while True:
                try:
                    prompt = input('🚀 ')
                    self.evaluate_prompt(prompt)
                except KanbanError as e:
                    print(str(e))
        except KeyboardInterrupt:
            print('')
            self.quit_shell()
