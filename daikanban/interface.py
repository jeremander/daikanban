from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache, wraps
import json
from operator import attrgetter
from pathlib import Path
import re
import readline  # improves shell interactivity  # noqa: F401
import shlex
import sys
from typing import Any, Callable, Generic, Iterable, Optional, TypeVar, cast

import pendulum
import pendulum.parsing
from pydantic import BaseModel, Field, ValidationError, create_model
from pydantic_core import PydanticUndefined
import pytimeparse
from rich import print
from rich.prompt import Confirm, Prompt
from rich.table import Table

from daikanban.model import Board, Duration, Id, KanbanError, Project, Task
from daikanban.settings import BoardSettings
from daikanban.utils import DATE_FORMAT, SECS_PER_DAY, TIME_FORMAT, StrEnum, get_current_time, handle_error, prefix_match, to_snake_case


M = TypeVar('M', bound=BaseModel)
T = TypeVar('T')

PKG_DIR = Path(__file__).parent
BILLBOARD_ART_PATH = PKG_DIR / 'billboard_art.txt'


##########
# ERRORS #
##########

class UserInputError(KanbanError):
    """Class for user input errors."""

class BoardFileError(KanbanError):
    """Error reading or writing a board file."""

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


##########
# STYLES #
##########

class DefaultColor(StrEnum):
    """Enum for default color map."""
    proj_id = 'purple4'
    task_id = 'dark_orange3'
    path = 'dodger_blue2'
    error = 'red'
    faint = 'grey0'


def style_str(val: Any, color: str, bold: bool = False) -> str:
    """Renders a value as a string with a given color.
    If bold=True, make it bold."""
    tag = ('bold ' if bold else '') + color
    return f'[{tag}]{val}[/]'

def proj_id_style(id_: Id, bold: bool = False) -> str:
    """Renders a project ID as a rich-styled string."""
    return style_str(id_, DefaultColor.proj_id, bold=bold)

def task_id_style(id_: Id, bold: bool = False) -> str:
    """Renders a task ID as a rich-styled string."""
    return style_str(id_, DefaultColor.task_id, bold=bold)

def path_style(path: str | Path, bold: bool = False) -> str:
    """Renders a path as a rich-styled string."""
    return style_str(path, DefaultColor.path, bold=bold)

def err_style(obj: object) -> str:
    """Renders an error as a rich-styled string."""
    return style_str(obj, DefaultColor.error)


###########
# PARSING #
###########

def parse_string_set(s: str) -> Optional[set[str]]:
    """Parses a comma-separated string into a set of strings.
    Allows for quote delimiting so that commas can be escaped."""
    strings = set(list(csv.reader([s]))[0])
    return strings or None

def parse_duration(s: str) -> Optional[Duration]:
    """Parses a string into a time duration (number of days)."""
    if not s.strip():
        return None
    secs = pytimeparse.parse(s)
    if (secs is None):
        raise UserInputError('Invalid time duration.')
    return secs / SECS_PER_DAY

def parse_date(s: str) -> Optional[str]:
    """Parses a string into a timestamp string.
    The input string can either specify a datetime directly, or a time duration from the present moment."""
    if not s.strip():
        return None
    try:
        dt: datetime = pendulum.parse(s, strict=False, tz=pendulum.local_timezone())  # type: ignore
        assert isinstance(dt, datetime)
    except (AssertionError, pendulum.parsing.ParserError):
        # parse as a duration from now
        s = s.strip()
        is_past = s.endswith(' ago')
        s = s.removeprefix('in ').removesuffix(' from now').removesuffix(' ago').strip()
        secs = pytimeparse.parse(s)
        if secs is None:
            raise UserInputError('Invalid date') from None
        td = timedelta(seconds=secs)
        dt = get_current_time() + (-td if is_past else td)
    return dt.strftime(TIME_FORMAT)


#############
# PROMPTING #
#############

def validated_input(prompt: str, validator: Callable[[str], T], default: Any = None) -> T:
    """Prompts the user with the given string until the user's response passes a validator function with no error."""
    if default not in (None, PydanticUndefined):
        if isinstance(default, float) and (int(default) == default):
            default = int(default)
        default = str(default)
    while True:
        result = Prompt.ask(f'[bold]{prompt}[/]', default=default) or ''
        try:
            return validator(result)
        except Exception as e:
            print(err_style(e))

def simple_input(prompt: str, default: Optional[str] = None, match: str = '.*') -> str:
    """Prompts the user with the given string until the user's response matches a certain regex."""
    regex = re.compile(match)
    while True:
        result = Prompt.ask(f'[bold]{prompt}[/]', default=default) or ''
        if regex.fullmatch(result):
            break
    return result

@dataclass
class FieldParser(Generic[M, T]):
    """Bundle of parameters for how to parse a field from a string."""
    model_type: type[M]
    field: str
    prompt: Optional[str] = None
    parse: Optional[Callable[[str], T]] = None

    @property
    def readable_name(self) -> str:
        """Gets a readable version of the field name."""
        return self.field.replace('_', ' ').capitalize()

    @property
    def default(self) -> T:
        """Gets the default value for the particular field."""
        info = self.model_type.model_fields[self.field]
        # TODO: default_factory?
        return info.default

    def validate(self, val: Any) -> None:
        """Validates the field value."""
        if val == PydanticUndefined:
            raise UserInputError('This field is required.')
        try:
            self.model_type.__pydantic_validator__.validate_assignment(self.model_type.model_construct(), self.field, val)
        except ValidationError as e:
            msg = '\n'.join(d['msg'] for d in e.errors())
            raise UserInputError(msg) from None

    def parse_field(self, s: str) -> T:
        """Given a BaseModel type and string, parses the field value from a string and validates it."""
        val = s if (self.parse is None) else self.parse(s)
        self.validate(val)
        return val  # type: ignore

    def prompt_field(self) -> T:
        """Given a BaseModel type, prompts the user for the field until a valid one is entered."""
        prompt = self.prompt or self.readable_name
        return validated_input(prompt, self.parse_field, default=self.default)


def model_from_prompt(model_type: type[M], parsers: dict[str, FieldParser] = {}) -> M:  # noqa: B006
    """Given a BaseModel type and collection of FieldParsers, constructs an instance of the type from a sequence of user prompts."""
    kwargs: dict[str, Any] = {}
    for (field, parser) in parsers.items():
        kwargs[field] = parser.prompt_field()
    return model_type(**kwargs)


###################
# PRETTY PRINTING #
###################

def _render_cell(val: Any) -> str:
    if val is None:
        return '-'
    if isinstance(val, float):
        return str(int(val)) if (int(val) == val) else f'{val:.3g}'
    return str(val)

def make_table(tp: type[M], rows: Iterable[M], **kwargs: Any) -> Table:
    """Given a BaseModel type and a list of elements of that type, creates a Table displaying the data."""
    table = Table(**kwargs)
    for (name, info) in tp.model_fields.items():
        title = info.title or name
        kw = cast(dict, info.json_schema_extra) or {}
        table.add_column(title, **kw)
    for row in rows:
        table.add_row(*(_render_cell(val) for (_, val) in row))
    return table

class ProjectRow(BaseModel):
    """A display table row associated with a project.
    These rows are presented in the project list view."""
    id: str = Field(justify='right')  # type: ignore[call-arg]
    name: str
    created: str
    num_tasks: int = Field(title='# tasks', justify='right')  # type: ignore[call-arg]

class TaskRow(BaseModel):
    """A display table row associated with a task.
    These rows are presented in the task list view."""
    id: str = Field(justify='right')    # type: ignore[call-arg]
    name: str = Field(min_width=15)  # type: ignore[call-arg]
    project: Optional[str]
    priority: float = Field(title="pri…ty")
    difficulty: float = Field(title="diff…ty")
    duration: Optional[str]
    create: str
    start: Optional[str]
    complete: Optional[str]
    due: Optional[str]
    status: str

def simple_task_row_type(*fields: str) -> type[BaseModel]:
    """Given a list of fields associated with a task, creates a BaseModel subclass that will be used to display a simplified row for each task.
    These rows are presented in the DaiKanban board view."""
    kwargs: dict[str, Any] = {}
    for field in fields:
        if field == 'id':
            val: tuple[type, Any] = (str, Field(justify='right'))  # type: ignore[call-arg]
        elif field == 'name':
            val = (str, ...)
        elif field == 'project':
            val = (Optional[str], ...)  # type: ignore
        elif field == 'priority':
            val = (float, Field(title="pri…ty"))
        elif field == 'difficulty':
            val = (float, Field(title="diff…ty"))
        elif field == 'score':
            val = (float, Field(justify='right'))  # type: ignore[call-arg]
        # TODO: add more fields
        else:
            raise ValueError(f'unrecognized Task field {field}')
        kwargs[field] = val
    return create_model('SimpleTaskRow', **kwargs)


###################
# BOARD INTERFACE #
###################

def require_board(func):  # noqa
    """Decorator for a method which makes it raise a BoardNotLoadedError if a board path is not set."""
    @wraps(func)
    def wrapped(self, *args, **kwargs):  # noqa
        if self.board_path is None:
            raise BoardNotLoadedError("No board has been loaded.\nRun 'board load' to load a board.")
        func(self, *args, **kwargs)
    return wrapped


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
    settings: BoardSettings = Field(
        default_factory=BoardSettings,
        description='board settings'
    )

    def _parse_id_or_name(self, item_type: str, s: str) -> Optional[Id]:
        assert self.board is not None
        s = s.strip()
        if not s:
            return None
        d = getattr(self.board, f'{item_type}s')
        if s.isdigit():
            id_ = int(s)
            if (id_ in d):
                return id_
            raise UserInputError(f'Invalid {item_type} ID.')
        for (id_, proj) in d.items():
            if (proj.name.lower() == s.lower()):
                return id_
        raise UserInputError(f'Invalid {item_type} name.')

    def _parse_project(self, id_or_name: str) -> Optional[Id]:
        return self._parse_id_or_name('project', id_or_name)

    def _parse_task(self, id_or_name: str) -> Optional[Id]:
        return self._parse_id_or_name('task', id_or_name)

    def _model_json(self, model: BaseModel) -> str:
        return model.model_dump_json(indent=self.settings.json_indent, exclude_none=True)

    # HELP/INFO

    def make_new_help_table(self) -> Table:
        """Creates a new 3-column rich table for displaying help menus."""
        grid = Table.grid(expand=True)
        grid.add_column(style=f'bold {DefaultColor.faint}')
        grid.add_column(style=f'bold {DefaultColor.faint}')
        grid.add_column()
        return grid

    def add_board_help(self, grid: Table) -> None:
        """Adds entries to help menu related to boards."""
        grid.add_row('\[b]oard', '\[d]elete', 'delete current board')
        grid.add_row('', '\[n]ew', 'create new board')
        grid.add_row('', '\[l]oad [not bold]\[FILENAME][/]', 'load board from file')
        grid.add_row('', 'schema', 'show board JSON schema')
        grid.add_row('', '\[s]how', 'show current board, can provide extra filters like:')
        grid.add_row('', '', '  status:\[STATUSES] project:\[PROJECT_IDS] tags:\[TAGS] limit:\[SIZE]')

    def add_project_help(self, grid: Table) -> None:
        """Adds entries to help menu related to projects."""
        grid.add_row('\[p]roject', '\[d]elete [not bold]\[ID/NAME][/]', 'delete a project')
        grid.add_row('', '\[n]ew', 'create new project')
        grid.add_row('', '\[s]how', 'show project list')
        grid.add_row('', '\[s]how [not bold]\[ID/NAME][/]', 'show project info')

    def add_task_help(self, grid: Table) -> None:
        """Adds entries to help menu related to tasks."""
        grid.add_row('\[t]ask', '\[d]elete [not bold]\[ID/NAME][/]', 'delete a task')
        grid.add_row('', '\[n]ew', 'create new task')
        grid.add_row('', '\[s]how', 'show task list')
        grid.add_row('', '\[s]how [not bold]\[ID/NAME][/]', 'show task info')

    def show_help(self) -> None:
        """Displays the main help menu listing various commands."""
        grid = self.make_new_help_table()
        grid.add_row('\[h]elp', '', 'show help menu')
        grid.add_row('\[q]uit', '', 'exit the shell')
        # TODO: global settings?
        # grid.add_row('settings', 'view/edit the settings')
        self.add_board_help(grid)
        self.add_project_help(grid)
        self.add_task_help(grid)
        # TODO: board config?
        print('[bold underline]User options[/]')
        print(grid)

    def _show_subgroup_help(self, subgroup: str) -> None:
        grid = self.make_new_help_table()
        meth = f'add_{subgroup}_help'
        getattr(self, meth)(grid)
        print(f'[bold underline]{subgroup.capitalize()} options[/]')
        print(grid)

    def show_board_help(self) -> None:
        """Displays the board-specific help menu."""
        self._show_subgroup_help('board')

    def show_project_help(self) -> None:
        """Displays the project-specific help menu."""
        self._show_subgroup_help('project')

    def show_task_help(self) -> None:
        """Displays the task-specific help menu."""
        self._show_subgroup_help('task')

    @staticmethod
    def show_schema(cls: type[BaseModel], indent: int = 2) -> None:
        """Prints out the JSON schema of the given type."""
        print(json.dumps(cls.model_json_schema(mode='serialization'), indent=indent))

    # PROJECT

    @require_board
    def delete_project(self, id_or_name: Optional[str] = None) -> None:
        """Deletes a project with the given ID or name."""
        assert self.board is not None
        if id_or_name is None:
            id_or_name = simple_input('Project ID or name', match='.+')
        id_ = self._parse_project(id_or_name)
        assert id_ is not None
        proj = self.board.get_project(id_)
        self.board.delete_project(id_)
        self.save_board()
        print(f'Deleted project {proj.name!r} with ID {proj_id_style(id_)}')

    @require_board
    def new_project(self) -> None:
        """Creates a new project."""
        assert self.board is not None
        params: dict[str, dict[str, Any]] = {
            'name': {
                'prompt': 'Project name'
            },
            'description': {},
            'links': {
                'prompt': 'Links [not bold]\[optional, comma-separated][/]',
                'parse': parse_string_set
            }
        }
        parsers: dict[str, FieldParser] = {field: FieldParser(Project, field, **kwargs) for (field, kwargs) in params.items()}
        proj = model_from_prompt(Project, parsers)
        id_ = self.board.create_project(proj)
        self.save_board()
        print(f'Created new project with ID {proj_id_style(id_)}')

    @require_board
    def show_projects(self) -> None:
        """Shows project list."""
        assert self.board is not None
        num_tasks_by_project = self.board.num_tasks_by_project
        rows = [ProjectRow(id=proj_id_style(id_, bold=True), name=proj.name, created=proj.created_time.strftime('%Y-%m-%d'), num_tasks=num_tasks_by_project[id_]) for (id_, proj) in self.board.projects.items()]
        table = make_table(ProjectRow, rows)
        print(table)

    @require_board
    def show_project(self, id_or_name: str) -> None:
        """Shows project info."""
        assert self.board is not None
        id_ = self._parse_project(id_or_name)
        if id_ is None:
            raise UserInputError('Invalid project.')
        proj = self.board.get_project(id_)
        print(self._model_json(proj))

    # TASK

    @require_board
    def delete_task(self, id_or_name: Optional[str] = None) -> None:
        """Deletes a task with the given ID or name."""
        assert self.board is not None
        if id_or_name is None:
            id_or_name = simple_input('Project ID or name', match='.+')
        id_ = self._parse_task(id_or_name)
        assert id_ is not None
        task = self.board.get_task(id_)
        self.board.delete_task(id_)
        self.save_board()
        print(f'Deleted task {task.name!r} with ID {task_id_style(id_)}')

    @require_board
    def new_task(self) -> None:
        """Createas a new task."""
        assert self.board is not None
        params: dict[str, dict[str, Any]] = {
            'name': {
                'prompt': 'Task name'
            },
            'description': {},
            'priority': {
                'prompt': 'Priority [not bold]\[0-10][/]'
            },
            'expected_difficulty': {
                'prompt': 'Expected difficulty [not bold]\[0-10][/]'
            },
            'expected_duration': {
                'prompt': 'Expected duration [not bold]\[optional, e.g. "3 days", "2 months"][/]',
                'parse': parse_duration
            },
            'due_date': {
                'prompt': 'Due date [not bold]\[optional][/]',
                'parse': parse_date
            },
            'project_id': {
                'prompt': 'Project ID or name [not bold]\[optional][/]',
                'parse': self._parse_project
            },
            'tags': {
                'prompt': 'Tags [not bold]\[optional, comma-separated][/]',
                'parse': parse_string_set
            },
            'links': {
                'prompt': 'Links [not bold]\[optional, comma-separated][/]',
                'parse': parse_string_set
            }
        }
        parsers: dict[str, FieldParser] = {
            field: FieldParser(Task, field, **kwargs) for (field, kwargs) in params.items()
        }
        task = model_from_prompt(Task, parsers)
        id_ = self.board.create_task(task)
        self.save_board()
        print(f'Created new task with ID {task_id_style(id_)}')

    def _project_str_from_id(self, id_: Id) -> str:
        """Given a project ID, gets a string displaying both the project name and ID."""
        assert self.board is not None
        return f'\[{proj_id_style(id_)}] {self.board.projects[id_].name}'

    def _make_task_row(self, id_: Id, task: Task) -> TaskRow:
        """Given a Task ID and object, gets a TaskRow object used for displaying the task in the task list."""
        assert self.board is not None
        def _get_proj(task: Task) -> Optional[str]:
            return None if (task.project_id is None) else self._project_str_from_id(task.project_id)
        def _get_date(dt: Optional[datetime]) -> Optional[str]:
            return None if (dt is None) else dt.strftime(DATE_FORMAT)
        duration = None if (task.expected_duration is None) else pendulum.duration(days=task.expected_duration).in_words()
        status = f'[{task.status.color}]{task.status._value_}[/]'
        return TaskRow(
            id=task_id_style(id_, bold=True),
            name=task.name,
            project=_get_proj(task),
            priority=task.priority,
            difficulty=task.expected_difficulty,
            duration=duration,
            create=cast(str, _get_date(task.created_time)),
            start=_get_date(task.first_started_time),
            complete=_get_date(task.completed_time),
            due=_get_date(task.due_date),
            status=status
        )

    @require_board
    def show_tasks(self) -> None:
        """Shows task list."""
        assert self.board is not None
        rows = [self._make_task_row(id_, task) for (id_, task) in self.board.tasks.items()]
        table = make_table(TaskRow, rows)
        print(table)

    @require_board
    def show_task(self, id_or_name: str) -> None:
        """Shows task info."""
        assert self.board is not None
        id_ = self._parse_task(id_or_name)
        if id_ is None:
            raise UserInputError('Invalid task.')
        task = self.board.get_task(id_)
        print(self._model_json(task))

    # BOARD

    @require_board
    def delete_board(self) -> None:
        """Deletes the currently loaded board."""
        assert self.board_path is not None
        path = path_style(self.board_path)
        if not self.board_path.exists():
            raise BoardFileError(f'Board file {path} does not exist.')
        delete = Confirm.ask(f'Are you sure you want to delete {path}?')
        if delete:
            self.board_path.unlink()
            assert self.board is not None
            print(f'Deleted board {self.board.name!r} from {path}.')

    def load_board(self, board_path: Optional[str | Path] = None) -> None:
        """Loads a board from a JSON file.
        If none is provided, prompts the user interactively."""
        if board_path is None:
            board_path = simple_input('Board filename', match=r'.*\w.*')
        try:
            with open(board_path) as f:
                self.board = Board(**json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            msg = f'ERROR loading JSON {path_style(board_path)}: {e}'
            raise BoardFileError(msg) from None
        self.board_path = Path(board_path)
        print(f'Loaded board from {path_style(self.board_path)}.')

    def save_board(self) -> None:
        """Saves the state of the current board to its JSON file."""
        if self.board is not None:
            assert self.board_path is not None
            # TODO: save in background if file size starts to get large?
            try:
                with open(self.board_path, 'w') as f:
                    f.write(self._model_json(self.board))
            except OSError as e:
                raise BoardFileError(str(e)) from None

    def new_board(self) -> None:
        """Interactively creates a new DaiKanban board.
        Implicitly loads that board afterward."""
        print('Creating new DaiKanban board.\n')
        name = simple_input('Board name', match=r'.*[^\s].*')
        default_path = to_snake_case(name) + '.json'
        path = simple_input('Output filename', default=default_path).strip()
        path = path or default_path
        board_path = Path(path)
        create = (not board_path.exists()) or Confirm.ask(f'A file named {path_style(path)} already exists.\n\tOverwrite?')
        if create:
            description = simple_input('Board description').strip() or None
            self.board = Board(name=name, description=description)
            self.board_path = board_path
            self.save_board()
            print(f'Saved DaiKanban board {name!r} to {path_style(path)}')

    def _status_group_info(self, statuses: Optional[list[str]] = None) -> tuple[dict[str, str], dict[str, str]]:
        """Given an optional list of statuses to include, returns a pair (group_by_status, group_colors).
        The former is a map from task statuses to status groups.
        The latter is a map from status groups to colors."""
        status_groups = self.settings.status_groups
        if statuses:
            status_set = set(statuses)
            status_groups = {group: [status for status in group_statuses if (status in status_set)] for (group, group_statuses) in status_groups.items()}
        group_by_status = {}  # map from status to group
        group_colors = {}  # map from group to color
        for (group, group_statuses) in status_groups.items():
            if group_statuses:
                # use the first listed status to define the group color
                group_colors[group] = cast(str, getattr(group_statuses[0], 'color', None))
            for status in group_statuses:
                group_by_status[status] = group
        return (group_by_status, group_colors)

    def show_board(self,
        statuses: Optional[list[str]] = None,
        projects: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        limit: Optional[int] = None
    ) -> None:
        """Displays the board to the screen using the current configurations."""
        # TODO: take kwargs to filter board contents
        if self.board is None:
            raise BoardNotLoadedError("No board has been loaded.\nRun 'board new' to create a new board or 'board load' to load an existing one.")
        if projects or tags:
            raise NotImplementedError
        (group_by_status, group_colors) = self._status_group_info(statuses)
        # create BaseModel corresponding to a table row summarizing a Task
        # TODO: this class may be customized based on settings
        TaskInfo = simple_task_row_type('id', 'name', 'project', 'score')
        scorer = self.settings.task_scorer
        grouped_task_info = defaultdict(list)
        for (id_, task) in self.board.tasks.items():
            proj_str = None if (task.project_id is None) else self._project_str_from_id(task.project_id)
            task_info = TaskInfo(id=task_id_style(id_), name=task.name, project=proj_str, score=scorer(task))
            grouped_task_info[group_by_status[task.status]].append(task_info)
        # sort by the scoring criterion, in reverse score order
        for task_infos in grouped_task_info.values():
            task_infos.sort(key=attrgetter('score'), reverse=True)
        # build table
        caption = f'[not italic]Score[/]: {scorer.name}'
        if scorer.description:
            caption += f' ({scorer.description})'
        table = Table(title=self.board.name, title_style='bold italic blue', caption=caption)
        subtables = []
        for (group, color) in group_colors.items():
            # each status group is a main table column
            table.add_column(group, header_style=color, justify='center')
            task_infos = grouped_task_info[group]
            subtable: Table | str = make_table(TaskInfo, task_infos) if task_infos else ''
            subtables.append(subtable)
        table.add_row(*subtables)
        # TODO: status icons, etc.
        print(table)

    # SHELL

    def evaluate_prompt(self, prompt: str) -> None:  # noqa: C901
        """Given user prompt, takes a particular action."""
        prompt = prompt.strip()
        if not prompt:
            return None
        tokens = shlex.split(prompt)
        ntokens = len(tokens)
        tok0 = tokens[0]
        if prefix_match(tok0, 'board'):
            if (ntokens == 1) or prefix_match(tokens[1], 'help'):
                return self.show_board_help()
            tok1 = tokens[1]
            if prefix_match(tok1, 'delete'):
                return self.delete_board()
            if prefix_match(tok1, 'load'):
                board_path = tokens[2] if (ntokens >= 3) else None
                return self.load_board(board_path)
            if prefix_match(tok1, 'new'):
                return self.new_board()
            if prefix_match(tok1, 'show'):
                return self.show_board()
            if prefix_match(tok1, 'schema', minlen=2):
                return self.show_schema(Board)
        elif prefix_match(tok0, 'help') or (tok0 == 'info'):
            return self.show_help()
        elif prefix_match(tok0, 'project'):
            if (ntokens == 1) or prefix_match(tokens[1], 'help'):
                return self.show_project_help()
            tok1 = tokens[1]
            if prefix_match(tok1, 'new'):
                return self.new_project()
            if prefix_match(tok1, 'delete'):
                return self.delete_project(None if (ntokens == 2) else tokens[2])
            if prefix_match(tok1, 'show'):
                if ntokens == 2:
                    return self.show_projects()
                return self.show_project(tokens[2])
        elif prefix_match(tok0, 'quit') or (tok0 == 'exit'):
            return self.quit_shell()
        elif prefix_match(tok0, 'task'):
            if (ntokens == 1) or prefix_match(tokens[1], 'help'):
                return self.show_task_help()
            tok1 = tokens[1]
            if prefix_match(tok1, 'delete'):
                return self.delete_task(None if (ntokens == 2) else tokens[2])
            if prefix_match(tok1, 'new'):
                return self.new_task()
            if prefix_match(tok1, 'show'):
                if ntokens == 2:
                    return self.show_tasks()
                return self.show_task(tokens[2])
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
        print('[bold italic cyan]Welcome to DaiKanban![/]')
        print("[bright_black]Type 'h' for help.[/]")
        # TODO: load default board from global config
        if board_path is not None:
            with handle_error(BoardFileError):
                self.load_board(board_path)
        try:
            while True:
                try:
                    prompt = input('🚀 ')
                    self.evaluate_prompt(prompt)
                except KanbanError as e:
                    print(err_style(e))
        except KeyboardInterrupt:
            print('')
            self.quit_shell()
