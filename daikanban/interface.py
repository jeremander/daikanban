from collections import defaultdict
from dataclasses import Field, dataclass, field, fields, make_dataclass
from datetime import datetime, timedelta
from functools import cache, wraps
import json
from numbers import Real
from pathlib import Path
import readline  # improves shell interactivity  # noqa: F401
import shlex
import sys
from typing import TYPE_CHECKING, Annotated, Any, Callable, Generic, Iterable, Optional, Type, TypeVar, cast

import pendulum
import pendulum.parsing
from pydantic import ValidationError
from rich import print
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table
from typing_extensions import Concatenate, Doc, ParamSpec

from daikanban import PKG_DIR, logger
from daikanban.config import Config, get_config
from daikanban.model import Board, BoardFileError, DefaultColor, Id, KanbanError, Model, Project, Task, TaskStatus, TaskStatusAction, TaskStatusError, load_board, name_style, path_style, proj_id_style, status_style, task_id_style
from daikanban.prompt import FieldPrompter, Prompter, model_from_prompt, simple_input
from daikanban.utils import NotGiven, NotGivenType, UserInputError, err_style, fuzzy_match, get_current_time, get_duration_between, human_readable_duration, parse_key_value_pair, parse_string_set, prefix_match, style_str


if TYPE_CHECKING:
    from _typeshed import DataclassInstance


M = TypeVar('M')
T = TypeVar('T')
BI = TypeVar('BI', bound='BoardInterface')
P = ParamSpec('P')

BILLBOARD_ART_PATH = PKG_DIR / 'billboard_art.txt'


##########
# ERRORS #
##########

class BoardNotLoadedError(KanbanError):
    """Error type for when a board has not yet been loaded."""

class InvalidTaskStatusError(UserInputError):
    """Error type for when the user provides an invalid task status."""
    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(f'Invalid task status {status!r}')


####################
# HELPER FUNCTIONS #
####################

@cache
def get_billboard_art() -> str:
    """Loads billboard ASCII art from a file."""
    with open(BILLBOARD_ART_PATH) as f:
        return f.read()

def split_comma_list(s: str) -> list[str]:
    """Given a comma-separated list, splits it into a list of strings."""
    return [token for token in s.split(',') if token]

def parse_task_limit(s: str) -> Optional[int]:
    """Parses an integer task limit, raising a UserInputError if invalid.
    If the input string is 'none', returns None."""
    if s.strip().lower() == 'none':
        return None
    try:
        return int(s)
    except ValueError:
        raise UserInputError('Must select a positive whole number for task limit') from None


###########
# PARSING #
###########

def empty_is_none(s: str) -> Optional[str]:
    """Identity function on strings, except if the string is empty, returns None."""
    return s or None

def parse_date_as_string(s: str) -> Optional[str]:
    """Parses a string into a timestamp string.
    The input string can either specify a datetime directly, or a time duration from the present moment."""
    if not s.strip():
        return None
    config = get_config().time
    return config.render_datetime(config.parse_datetime(s))

def parse_duration(s: str) -> Optional[float]:
    """Parses a duration string into a number of days."""
    return get_config().time.parse_duration(s) if s.strip() else None

def _validate_project_or_task_name(name: str, obj_name: str) -> str:
    if not any(c.isalpha() for c in name):
        raise UserInputError(f'{obj_name.capitalize()} name {name_style(name)} is invalid, must have at least one letter')
    return name

def validate_project_name(name: str) -> str:
    """Given a project name, checks it is valid, raising a UserInputError otherwise."""
    return _validate_project_or_task_name(name, 'project')

def validate_task_name(name: str) -> str:
    """Given a task name, checks it is valid, raising a UserInputError otherwise."""
    return _validate_project_or_task_name(name, 'task')


###################
# PRETTY PRINTING #
###################

def make_table(tp: type['DataclassInstance'], rows: Iterable[M], suppress_cols: Optional[list[str]] = None, **kwargs: Any) -> Table:
    """Given a model type and a list of objects of that type, creates a Table displaying the data, with each object being a row.
    If a suppress_cols list is given, suppresses these columns from the table."""
    table = Table(**kwargs)
    flags = []  # indicates whether each field has any nontrivial element
    field_names = []
    suppress = set(suppress_cols) if suppress_cols else set()
    for fld in fields(tp):
        field_names.append(fld.name)
        flag = (fld.name not in suppress) and any(getattr(row, fld.name) is not None for row in rows)
        flags.append(flag)
        if flag:  # skip column if all values are trivial
            metadata = fld.metadata or {}  # type: ignore[var-annotated]
            title = metadata.get('title', fld.name)
            kw = {key: val for (key, val) in metadata.items() if (key != 'title')}
            table.add_column(title, **kw)
    config = get_config()
    for row in rows:
        vals = [config.pretty_value(getattr(row, name)) for (flag, name) in zip(flags, field_names) if flag]
        table.add_row(*vals)
    return table

@dataclass
class ProjectRow:
    """A display table row associated with a project.
    These rows are presented in the project list view."""
    id: str = field(metadata={'justify': 'right'})
    name: str
    created: str
    num_tasks: int = field(metadata={'title': '# tasks', 'justify': 'right'})

@dataclass
class TaskRow:
    """A display table row associated with a task.
    These rows are presented in the task list view."""
    id: str = field(metadata={'justify': 'right'})
    name: str = field(metadata={'min_width': 15})
    project: Optional[str]
    priority: Optional[float] = field(metadata={'title': 'pri…ty'})
    difficulty: Optional[float] = field(metadata={'title': 'diff…ty'})
    duration: Optional[str]
    create: str
    start: Optional[str]
    complete: Optional[str]
    due: Optional[str]
    status: str

def simple_task_row_type(*fields: str) -> type:
    """Given a list of fields associated with a task, creates a dataclass that will be used to display a simplified row for each task.
    These rows are presented in the DaiKanban board view."""
    kwargs: dict[str, Any] = {}
    for name in fields:
        if name == 'id':
            val: tuple[Any, Optional[Field]] = (str, field(metadata={'justify': 'right'}))
        elif name == 'name':
            val = (str, None)
        elif name == 'project':
            val = (Optional[str], None)
        elif name == 'priority':
            val = (Optional[float], field(metadata={'title': 'pri…ty'}))
        elif name == 'difficulty':
            val = (Optional[float], field(metadata={'title': 'diff…ty'}))
        elif name == 'completed_time':
            val = (Optional[datetime], field(metadata={'title': 'completed'}))
        elif name == 'score':
            val = (float, field(metadata={'justify': 'right'}))
        elif name == 'status':
            val = (TaskStatus, None)
        # TODO: add more fields
        else:
            raise ValueError(f'Unrecognized Task field {name}')
        kwargs[name] = val
    items = [(name, tp) if (fld is None) else (name, tp, fld) for (name, (tp, fld)) in kwargs.items()]
    return make_dataclass('SimpleTaskRow', items)  # type: ignore[arg-type]


@dataclass
class TaskColSettings(Generic[M]):
    """Class responsible for simplifying task info for displaying it in a DaiKanban board subtable."""
    column: str  # name of task column
    task_row_type: type[M]  # type of task row to display
    get_task_info: Callable[[Id, Task], dict[str, Any]]  # given ID and task, returns data for task row
    get_col_header: Callable[[int], str]  # given task count, returns column header

    def get_task_row(self, id_: Id, task: Task) -> M:
        """Given a task ID and Task, returns a simplified task row object."""
        return self.task_row_type(**self.get_task_info(id_, task))

    def sort_task_rows(self, task_rows: list[M]) -> None:
        """Sorts, in-place, a list of task rows."""
        config = get_config().display
        sort_keys = config.get_column_sort_keys(self.column)
        for (key, asc) in sort_keys[::-1]:
            # prioritize sort order from left to right (i.e. perform sorts in reverse order)
            task_rows.sort(key=key, reverse=(not asc))


###################
# BOARD INTERFACE #
###################

def require_board(func: Callable[Concatenate[BI, P], None]) -> Callable[Concatenate[BI, P], None]:
    """Decorator for a method which makes it raise a BoardNotLoadedError if a board path is not set."""
    @wraps(func)
    def wrapped(self: BI, *args: P.args, **kwargs: P.kwargs) -> None:
        if self.board is None:
            raise BoardNotLoadedError("No board has been loaded.\nRun 'board load' to load a board.")
        func(self, *args, **kwargs)
    return wrapped


@dataclass
class BoardInterface:
    """Interactive user interface to view and manipulate a DaiKanban board.
    This object maintains a state containing the currently loaded board and configurations."""
    board_path: Annotated[Optional[Path], Doc('path of current board')] = None
    board: Annotated[Optional[Board], Doc('current DaiKanban board')] = None
    config: Annotated[Config, Doc('global configurations')] = field(default_factory=Config)

    def _parse_id(self, item_type: str, s: str) -> Optional[Id]:
        s = s.strip()
        if not s:
            return None
        if s.isdigit():
            d = getattr(self.board, f'{item_type}s')
            if (id_ := int(s)) in d:
                return id_
            raise UserInputError(f'{item_type.capitalize()} with ID {s} not found')
        raise UserInputError(f'Invalid {item_type} ID {s!r}')

    def _parse_id_or_name(self, item_type: str, s: str) -> Optional[Id]:
        assert self.board is not None
        s = s.strip()
        if not s:
            return None
        if s.isdigit():
            return self._parse_id(item_type, s)
        # otherwise, parse as a name
        method = getattr(self.board, f'get_{item_type}_id_by_name')
        if ((id_ := method(s, fuzzy_match)) is not None):
            return id_
        raise UserInputError(f'Invalid {item_type} name {name_style(s)}')

    def _parse_project_id(self, id_str: str) -> Optional[Id]:
        return self._parse_id('project', id_str)

    def _parse_project(self, id_or_name: str) -> Optional[Id]:
        """Given a project ID or name, returns the corresponding project ID.
        If the string is empty, returns None.
        If it is not valid, raises a UserInputError."""
        return self._parse_id_or_name('project', id_or_name)

    def _parse_task_id(self, id_str: str) -> Optional[Id]:
        return self._parse_id('task', id_str)

    def _parse_task(self, id_or_name: str) -> Optional[Id]:
        """Given a task ID or name, returns the corresponding task ID.
        If the string is empty, returns None.
        If it is not valid, raises a UserInputError."""
        return self._parse_id_or_name('task', id_or_name)

    def _prompt_and_parse_task(self, id_or_name: Optional[str]) -> Id:
        if id_or_name is None:
            id_or_name = simple_input('Task ID or name', match='.+')
        id_ = self._parse_task(id_or_name)
        assert id_ is not None
        return id_

    def _model_pretty(self, obj: Model, id_: Optional[Id] = None) -> Table:
        """Given a Model object (and optional ID), creates a two-column Table displaying its contents prettily."""
        assert self.board is not None
        table = Table(show_header=False)
        table.add_column('Field', style='bold')
        table.add_column('Value')
        if id_ is not None:
            if isinstance(obj, Project):
                id_str = proj_id_style(id_)
            elif isinstance(obj, Task):
                id_str = task_id_style(id_)
            else:
                id_str = str(id_)
            table.add_row('ID ', id_str)
        for (fld, pretty) in obj._pretty_dict().items():
            if fld == 'name':
                pretty = name_style(pretty)
            elif fld == 'project_id':  # also include the project name
                assert isinstance(obj, Task)
                fld = 'project'
                if obj.project_id is not None:
                    project_name = self.board.get_project(obj.project_id).name
                    id_str = proj_id_style(int(pretty))
                    pretty = f'[{id_str}] {project_name}'
            table.add_row(f'{fld}  ', pretty)
        return table

    # HELP/INFO

    def make_new_help_table(self) -> Table:
        """Creates a new 3-column rich table for displaying help menus."""
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style='bold')
        grid.add_column(style='bold')
        grid.add_column()
        return grid

    def add_board_help(self, grid: Table) -> None:
        """Adds entries to help menu related to boards."""
        statuses = ', '.join(TaskStatus)
        grid.add_row('\\[b]oard', '\\[d]elete', 'delete current board')
        grid.add_row('', '\\[n]ew', 'create new board')
        grid.add_row('', '\\[l]oad [not bold]\\[FILENAME][/]', 'load board from file')
        grid.add_row('', 'schema', 'show board JSON schema')
        grid.add_row('', '\\[s]how', 'show current board, can provide extra filters like:')
        # grid.add_row('', '', '  status=\\[STATUSES] project=\\[PROJECT_IDS] tag=\\[TAGS] limit=\\[SIZE] since=\\[WHEN]')
        grid.add_row('', '', f'  status=\\[STATUSES]  | list of statuses ({statuses})')
        grid.add_row('', '', '  project=\\[PROJECTS] | list of project names or IDs')
        grid.add_row('', '', '  tag=\\[TAGS]         | list of tags')
        grid.add_row('', '', '  limit=\\[SIZE]       | max number of tasks to show per column (a number, or "none" for no limit)')
        grid.add_row('', '', '  since=\\[WHEN]       | date/time expression (or "anytime" for no time limit), used to limit completed tasks only')

    def add_project_help(self, grid: Table) -> None:
        """Adds entries to help menu related to projects."""
        id_str = '[not bold]\\[ID/NAME][/]'
        grid.add_row('\\[p]roject', f'\\[d]elete {id_str}', 'delete a project')
        grid.add_row('', '\\[n]ew', 'create new project')
        grid.add_row('', '\\[s]how', 'show project list')
        grid.add_row('', f'\\[s]how {id_str}', 'show project info')
        grid.add_row('', f'set {id_str} [not bold]\\[FIELD] \\[VALUE][/]', 'change a project attribute')

    def add_task_help(self, grid: Table) -> None:
        """Adds entries to help menu related to tasks."""
        id_str = '[not bold]\\[ID/NAME][/]'
        grid.add_row('\\[t]ask', f'\\[d]elete {id_str}', 'delete a task')
        grid.add_row('', '\\[n]ew', 'create new task')
        grid.add_row('', '\\[s]how', 'show task list')
        grid.add_row('', f'\\[s]how {id_str}', 'show task info')
        grid.add_row('', f'set {id_str} [not bold]\\[FIELD] \\[VALUE][/]', 'change a task attribute')
        grid.add_row('', f'\\[b]egin {id_str}', 'begin a task')
        grid.add_row('', f'\\[c]omplete {id_str}', 'complete a started task')
        grid.add_row('', f'\\[p]ause {id_str}', 'pause a started task')
        grid.add_row('', f'\\[r]esume {id_str}', 'resume a paused or completed task')
        grid.add_row('', f'\\[t]odo {id_str}', "reset a task to the 'todo' state")

    def show_help(self) -> None:
        """Displays the main help menu listing various commands."""
        grid = self.make_new_help_table()
        grid.add_row('\\[h]elp', '', 'show help menu')
        grid.add_row('\\[q]uit', '', 'exit the shell')
        # TODO: global config?
        # grid.add_row('config', 'view/edit the configurations')
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
    def show_schema(cls: type[Model], indent: int = 2) -> None:
        """Prints out the JSON schema of the given type."""
        print(json.dumps(cls.json_schema(mode='serialization'), indent=indent))

    @require_board
    def _update_project_or_task(self, id_or_name: str, field: str, value: Optional[str], is_task: bool) -> None:
        """Updates an attribute of a project or task."""
        assert self.board is not None
        cls: Type[Model] = Task if is_task else Project  # type: ignore[assignment]
        name = cls.__name__.lower()
        id_field = f'{name}_id'
        if (field in cls._computed_fields()) or (field == id_field):
            raise UserInputError(f'Field {field!r} cannot be updated')
        id_ = getattr(self, f'_parse_{name}')(id_or_name)
        assert id_ is not None
        obj = getattr(self.board, f'get_{name}')(id_)
        # if field has a known parser, parse the value now
        parsers = getattr(self, f'_{name}_field_parsers')
        try:
            if (value is not None) and (field in parsers):
                value = parsers[field](value)
            # otherwise, defer the validation to object update via pydantic
            kwargs = {field: value}
            getattr(self.board, f'update_{name}')(id_, **kwargs)
        except (KanbanError, TypeError, ValidationError) as e:
            msg = e.errors()[0]['msg'] if isinstance(e, ValidationError) else str(e)
            msg = msg.splitlines()[0]
            raise UserInputError(msg) from e
        field_str = style_str(repr(field), DefaultColor.field_name)
        id_style = task_id_style if is_task else proj_id_style
        self.save_board()
        print(f'Updated field {field_str} for {name} {name_style(obj.name)} with ID {id_style(id_)}')

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
        print(f'Deleted project {name_style(proj.name)} with ID {proj_id_style(id_)}')

    @property
    def _project_field_parsers(self) -> dict[str, Callable[[str], Any]]:
        """Gets a dict from project fields to parser/validator functions that take a string and return a value for that field."""
        return {
            'name': validate_project_name,
            'description': empty_is_none,
            'links': parse_string_set,
            'parent': self._parse_project,
        }

    @require_board
    def new_project(self, name: Optional[str] = None) -> None:
        """Creates a new project."""
        assert self.board is not None
        parsers = self._project_field_parsers
        prompts = {
            'name': 'Project name',
            'description': 'Description',
            'links': 'Links [not bold]\\[optional, comma-separated][/]',
        }
        prompters: dict[str, FieldPrompter] = {}
        for (fld, prompt) in prompts.items():
            kwargs: dict[str, Any] = {'prompt': prompt}
            if fld in parsers:
                kwargs['parse'] = parsers[fld]
            prompters[fld] = FieldPrompter(Project, fld, **kwargs)
        if name is None:
            defaults = {}
        else:
            del prompters['name']
            defaults = {'name': validate_project_name(name)}
        try:
            proj = model_from_prompt(Project, prompters, defaults=defaults)
        except KeyboardInterrupt:  # go back to main REPL
            print()
            return
        id_ = self.board.create_project(proj)
        self.save_board()
        print(f'Created new project {name_style(proj.name)} with ID {proj_id_style(id_)}')

    @require_board
    def show_projects(self) -> None:
        """Shows project list."""
        assert self.board is not None
        num_tasks_by_project = self.board.num_tasks_by_project
        rows = [ProjectRow(id=proj_id_style(id_, bold=True), name=proj.name, created=proj.created_time.strftime('%Y-%m-%d'), num_tasks=num_tasks_by_project[id_]) for (id_, proj) in self.board.projects.items()]
        if rows:
            table = make_table(ProjectRow, rows)
            print(table)
        else:
            print(style_str('\\[No projects]', DefaultColor.faint, bold=True))

    @require_board
    def show_project(self, id_or_name: str) -> None:
        """Shows project info."""
        assert self.board is not None
        id_ = self._parse_project(id_or_name)
        assert id_ is not None
        proj = self.board.get_project(id_)
        print(self._model_pretty(proj, id_=id_))

    def update_project(self, id_or_name: str, field: str, value: Optional[str] = None) -> None:
        """Updates an attribute of a project."""
        return self._update_project_or_task(id_or_name, field, value, is_task=False)

    # TASK

    @require_board
    def change_task_status(self, action: TaskStatusAction, id_or_name: Optional[str] = None) -> None:
        """Changes a task to a new stage."""
        assert self.board is not None
        board: Board = self.board
        id_ = self._prompt_and_parse_task(id_or_name)
        task = board.get_task(id_)
        # fail early if the action is invalid for the status
        _ = task.apply_status_action(action)
        def parse_datetime(s: str) -> datetime:
            task = board.get_task(id_)
            config = get_config()
            dt = config.time.parse_datetime(s)
            if dt < task.created_time:
                created_str = config.time.render_datetime(task.created_time)
                dt_str = config.time.render_datetime(dt)
                Console().print(f'Time is earlier than task creation time ({created_str}).', highlight=False)
                overwrite = Confirm.ask(f'Set creation time to {dt_str}?')
                if overwrite:
                    board.update_task(id_, created_time=dt)
                else:
                    raise TaskStatusError(f'cannot start a task before its creation time ({created_str})')
            return dt
        # if valid, prompt the user for when the action took place
        # ask for time of intermediate status change, which occurs if:
        #   todo -> active -> complete
        #   todo -> active -> paused
        #   paused -> active -> complete
        intermediate_action_map = {
            (TaskStatus.todo, TaskStatusAction.complete): TaskStatusAction.start,
            (TaskStatus.todo, TaskStatusAction.pause): TaskStatusAction.start,
            (TaskStatus.paused, TaskStatusAction.complete): TaskStatusAction.resume
        }
        if (intermediate := intermediate_action_map.get((task.status, action))):
            prompt = f'When was the task {intermediate.past_tense()}? [not bold]\\[now][/] '
            prompter = Prompter(prompt, parse_datetime, validate=None, default=get_current_time)
            first_dt = prompter.loop_prompt(use_prompt_suffix=False, show_default=False)
            default_time: datetime | Callable[[], datetime] = first_dt
            now = get_current_time()
            if (now >= first_dt) and (now - first_dt < timedelta(seconds=15)):
                default_time_str = 'now'
            else:
                default_time_str = self.config.pretty_value(default_time)
        else:
            first_dt = None
            default_time = get_current_time
            default_time_str = 'now'
        # prompt user for time of latest status change
        prompt = f'When was the task {action.past_tense()}? [not bold]\\[{default_time_str}][/] '
        prompter = Prompter(prompt, parse_datetime, validate=None, default=default_time)
        try:
            dt = prompter.loop_prompt(use_prompt_suffix=False, show_default=False)
        except KeyboardInterrupt:  # go back to main REPL
            print()
            return
        task = board.apply_status_action(id_, action, dt=dt, first_dt=first_dt)
        self.save_board()
        print(f'Changed task {name_style(task.name)} [not bold]\\[{task_id_style(id_)}][/] to {status_style(task.status)} state')

    @require_board
    def delete_task(self, id_or_name: Optional[str] = None) -> None:
        """Deletes a task with the given ID or name."""
        assert self.board is not None
        id_ = self._prompt_and_parse_task(id_or_name)
        task = self.board.get_task(id_)
        self.board.delete_task(id_)
        self.save_board()
        print(f'Deleted task {name_style(task.name)} with ID {task_id_style(id_)}')

    @property
    def _task_field_parsers(self) -> dict[str, Callable[[str], Any]]:
        """Gets a dict from project fields to parser/validator functions that take a string and return a value for that field."""
        def _parse_task_set(s: str) -> Optional[set[Id]]:
            # parse comma-separated list of task IDs and/or names
            return {task_id for elt in (parse_string_set(s) or set()) if (task_id := self._parse_task(elt)) is not None} or None
        return {
            'name': validate_task_name,
            'description': empty_is_none,
            'project_id': self._parse_project_id,
            'project': self._parse_project,
            'priority': empty_is_none,
            'expected_difficulty': empty_is_none,
            'expected_duration': empty_is_none,
            'due': parse_date_as_string,
            'tags': parse_string_set,
            'links': parse_string_set,
            'blocked_by': _parse_task_set,
            'parent': self._parse_task,
        }

    @require_board
    def new_task(self, name: Optional[str] = None) -> None:
        """Creates a new task."""
        assert self.board is not None
        parsers = self._task_field_parsers
        prompts = {
            'name': 'Task name',
            'description': 'Description',
            'project_id': 'Project ID or name [not bold]\\[optional][/]',
            'priority': 'Priority [not bold]\\[optional, 0-10][/]',
            'expected_difficulty': 'Expected difficulty [not bold]\\[optional, 0-10][/]',
            'expected_duration': 'Expected duration [not bold]\\[optional, e.g. "3 days", "2 months"][/]',
            'due': 'Due date [not bold]\\[optional][/]',
            'tags': 'Tags [not bold]\\[optional, comma-separated][/]',
            'links': 'Links [not bold]\\[optional, comma-separated][/]',
        }
        # only prompt for the fields specified in the configs
        task_fields = set(self.config.task.new_task_fields)
        if name is None:
            defaults = {}
        else:
            task_fields.discard('name')
            defaults = {'name': validate_task_name(name)}
        prompters: dict[str, FieldPrompter] = {}
        for (fld, prompt) in prompts.items():
            if fld in task_fields:
                kwargs: dict[str, Any] = {'prompt': prompt}
                if fld in parsers:
                    kwargs['parse'] = parsers[fld]
                prompters[fld] = FieldPrompter(Task, fld, **kwargs)
        try:
            task = model_from_prompt(Task, prompters, defaults=defaults)
        except KeyboardInterrupt:  # go back to main REPL
            print()
            return
        id_ = self.board.create_task(task)
        self.save_board()
        print(f'Created new task {name_style(task.name)} with ID {task_id_style(id_)}')

    def _project_str_from_id(self, id_: Id) -> str:
        """Given a project ID, gets a string displaying both the project name and ID."""
        assert self.board is not None
        return f'\\[{proj_id_style(id_)}] {self.board.get_project(id_).name}'

    def _make_task_row(self, id_: Id, task: Task) -> TaskRow:
        """Given a Task ID and object, gets a TaskRow object used for displaying the task in the task list."""
        assert self.board is not None
        def _get_proj(task: Task) -> Optional[str]:
            return None if (task.project_id is None) else self._project_str_from_id(task.project_id)
        def _get_date(dt: Optional[datetime]) -> Optional[str]:
            return None if (dt is None) else dt.strftime(get_config().time.date_format)
        duration = None if (task.expected_duration is None) else pendulum.duration(days=task.expected_duration).in_words()
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
            due=_get_date(task.due_time),
            status=status_style(task.status)
        )

    @require_board
    def show_tasks(self) -> None:
        """Shows task list."""
        assert self.board is not None
        rows = [self._make_task_row(id_, task) for (id_, task) in self.board.tasks.items()]
        if rows:
            table = make_table(TaskRow, rows)
            print(table)
        else:
            print(style_str('\\[No tasks]', DefaultColor.faint, bold=True))

    @require_board
    def show_task(self, id_or_name: str) -> None:
        """Shows task info."""
        assert self.board is not None
        id_ = self._parse_task(id_or_name)
        if id_ is None:
            raise UserInputError('Invalid task')
        task = self.board.get_task(id_)
        print(self._model_pretty(task, id_=id_))

    def update_task(self, id_or_name: str, field: str, value: Optional[str] = None) -> None:
        """Updates an attribute of a task."""
        if field == 'project':  # allow a name or ID
            id_ = str(self._parse_project(value)) if value else None
            return self.update_task(id_or_name, 'project_id', id_)
        return self._update_project_or_task(id_or_name, field, value, is_task=True)

    @require_board
    def todo_task(self, id_or_name: Optional[str] = None) -> None:
        """Resets a task to the 'todo' state, regardless of its current state.
        This will preserve the original creation metadata but reset time worked to zero."""
        assert self.board is not None
        id_ = self._prompt_and_parse_task(id_or_name)
        task = self.board.get_task(id_)
        self.board.reset_task(id_)
        self.save_board()
        print(f"Reset task {name_style(task.name)} with ID {task_id_style(id_)} to the 'todo' state")

    # BOARD

    @require_board
    def delete_board(self) -> None:
        """Deletes the currently loaded board."""
        assert self.board_path is not None
        path = path_style(self.board_path)
        if not self.board_path.exists():
            raise BoardFileError(f'Board file {path_style(path)} does not exist')
        delete = Confirm.ask(f'Are you sure you want to delete {path}?')
        if delete:
            self.board_path.unlink()
            assert self.board is not None
            print(f'Deleted board {name_style(self.board.name)} from {path}')

    def load_board(self, name: Optional[str | Path] = None) -> None:
        """Loads a board from a JSON file.
        If none is provided, prompts the user interactively."""
        if name is None:
            # TODO: use default board instead of prompting, if one exists
            name = simple_input('Board name or file', match=r'.*\w.*')
        path = self.config.resolve_board_name_or_path(name)
        self.board = load_board(path, config=self.config)
        self.board_path = path
        print(f'Loaded board from {path_style(self.board_path)}')

    def save_board(self) -> None:
        """Saves the state of the current board to its JSON file."""
        if self.board is not None:
            assert self.board_path is not None
            # TODO: save in background if file size starts to get large?
            try:
                self.board.save(self.board_path, indent=self.config.file.json_indent)
            except OSError as e:
                raise BoardFileError(str(e)) from None

    def new_board(self) -> None:
        """Interactively creates a new DaiKanban board.
        Implicitly loads that board afterward."""
        print('Creating new DaiKanban board.\n')
        name = simple_input('Board name', match=r'.*[^\s].*')
        default_path = str(self.config.resolve_board_name_or_path(name))
        path = simple_input('Output filename', default=default_path).strip()
        path = path or default_path
        board_path = Path(path)
        create = (not board_path.exists()) or Confirm.ask(f'A file named {path_style(path)} already exists.\n\tOverwrite?')
        if create:
            description = simple_input('Board description').strip() or None
            self.board = Board(name=name, description=description)
            self.board_path = board_path
            self.save_board()
            print(f'Saved DaiKanban board {name_style(name)} to {path_style(path)}')

    def _column_info(self, statuses: Optional[list[str]] = None) -> tuple[dict[str, str], dict[str, str]]:
        """Given an optional list of statuses to include, returns a pair (col_by_status, col_colors).
        The former is a map from task statuses to columns.
        The latter is a map from columns to colors."""
        column_config = self.config.display.columns
        if statuses:
            status_set = set(statuses)
            valid_statuses = {str(status) for status in TaskStatus}
            for status in status_set:
                if status not in valid_statuses:
                    raise InvalidTaskStatusError(status)
            columns = {col: [status for status in cfg.statuses if (status in status_set)] for (col, cfg) in column_config.items()}
        else:
            columns = {col: cfg.statuses for (col, cfg) in column_config.items()}
        col_by_status = {}  # map from status to columns
        col_colors = {}  # map from group to color
        for (col, col_statuses) in columns.items():
            if col_statuses:
                # use the first listed status to define the group color
                status = col_statuses[0]
                try:
                    status = TaskStatus(status)
                    color = status.color
                except ValueError:
                    color = 'black'
                col_colors[col] = color
            for status in col_statuses:
                col_by_status[status] = col
        return (col_by_status, col_colors)

    def _filter_task_by_project_or_tag(self, projects: Optional[list[str]] = None, tags: Optional[list[str]] = None) -> Callable[[Task], bool]:
        """Given project names/IDs and tags, returns a function that filters tasks based on whether their projects or tags match any of the provided values."""
        filters = []
        if projects:
            project_id_set = {id_ for id_or_name in projects if (id_:= self._parse_project(id_or_name)) is not None}
            # show task if its project ID matches one in the list
            filters.append(lambda task: task.project_id in project_id_set)
        if tags:
            tag_set = set(tags)
            # show task if any tag matches one in the list
            filters.append(lambda task: task.tags and task.tags.intersection(tag_set))
        if filters:
            return lambda task: any(flt(task) for flt in filters)
        # no filters, so permit any task
        return lambda _: True

    def _get_task_limit(self, limit: int | None | NotGivenType) -> Optional[int]:
        if limit is NotGiven:
            limit = self.config.display.max_tasks
        if (limit is not None) and (limit <= 0):
            raise UserInputError('Must select a positive number for task limit')
        return limit

    def _get_completed_since(self, since: datetime | None | NotGivenType) -> Optional[datetime]:
        now = get_current_time()
        if since is NotGiven:
            if isinstance(self.config.display.completed_age_off, Real):
                since = now - timedelta(days=self.config.display.completed_age_off)
            else:
                return None
        if since and (since > now):
            raise UserInputError('Must provide a time in the past')
        return since

    def _get_task_col_settings(self, col: str, color: str, since: Optional[datetime]) -> TaskColSettings:
        def _get_task_kwargs(id_: Id, task: Task) -> dict[str, Any]:
            proj_str = None if (task.project_id is None) else self._project_str_from_id(task.project_id)
            icons = task.status_icons
            name = task.name + (f' {icons}' if icons else '')
            return {'id': task_id_style(id_, bold=True), 'name': name, 'project': proj_str, 'status': task.status}
        def _get_col_header(task_count: int) -> str:
            return style_str(col, color, bold=True) + style_str(f' ({task_count})', 'bright_black')
        if col == 'complete':
            fields = ('id', 'name', 'project', 'completed_time', 'status')
            def get_task_info(id_: Id, task: Task) -> dict[str, Any]:
                return {'completed_time': task.completed_time, **_get_task_kwargs(id_, task)}
            def get_col_header(task_count: int) -> str:
                header = _get_col_header(task_count)
                if since:
                    dur = get_duration_between(since, get_current_time())
                    since_str = human_readable_duration(dur, prefer_days=True)
                    header += style_str(f'\nlast {since_str}', 'bright_black', italic=True)
                return header
        else:
            fields = ('id', 'name', 'project', 'score', 'status')
            def get_task_info(id_: Id, task: Task) -> dict[str, Any]:
                return {'score': self.config.task.scorer(task), **_get_task_kwargs(id_, task)}
            def get_col_header(task_count: int) -> str:
                header = _get_col_header(task_count)
                return (header + '\n') if since else header
        # create dataclass type corresponding to a table row summarizing each Task
        task_row_type = simple_task_row_type(*fields)
        return TaskColSettings(col, task_row_type, get_task_info, get_col_header)

    def _get_column_settings_by_column(self,
        statuses: Optional[list[str]] = None,
        since: datetime | None | NotGivenType = NotGiven,
    ) -> dict[str, TaskColSettings]:
        """Gets a mapping from columns to TaskColSettings."""
        since = self._get_completed_since(since)
        (col_by_status, col_colors) = self._column_info(statuses)
        return {col: self._get_task_col_settings(col, col_colors[col], since) for col in col_by_status.values()}

    def _get_task_rows_by_column(self,
        statuses: Optional[list[str]] = None,
        projects: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        since: datetime | None | NotGivenType = NotGiven,
    ) -> dict[str, list[Any]]:
        """Gets a mapping from columns to lists of Tasks, sorted based on the current configurations."""
        assert self.board is not None
        task_filter = self._filter_task_by_project_or_tag(projects=projects, tags=tags)
        since = self._get_completed_since(since)
        (col_by_status, col_colors) = self._column_info(statuses)
        col_settings_by_col = self._get_column_settings_by_column(statuses=statuses, since=since)
        task_rows_by_col: dict[str, list[Any]] = defaultdict(list)
        for (id_, task) in self.board.tasks.items():
            if not task_filter(task):
                continue
            if since and (task.status == TaskStatus.complete) and (cast(datetime, task.completed_time) < since):
                continue
            if (col := col_by_status.get(task.status)):
                col_settings = col_settings_by_col[col]
                task_row = col_settings.get_task_row(id_, task)
                task_rows_by_col[col].append(task_row)
        # sort by the column's criterion, in reverse score order
        for (col, task_rows) in task_rows_by_col.items():
            col_settings = col_settings_by_col[col]
            col_settings.sort_task_rows(task_rows)
        return task_rows_by_col

    def show_board(self,
        statuses: Optional[list[str]] = None,
        projects: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        limit: int | None | NotGivenType = NotGiven,
        since: datetime | None | NotGivenType = NotGiven,
    ) -> None:
        """Displays the board to the screen using the current configurations."""
        if self.board is None:
            raise BoardNotLoadedError("No board has been loaded.\nRun 'board new' to create a new board or 'board load' to load an existing one.")
        limit = self._get_task_limit(limit)
        scorer = self.config.task.scorer
        (col_by_status, col_colors) = self._column_info(statuses)
        col_settings_by_col = self._get_column_settings_by_column(statuses=statuses, since=since)
        task_rows_by_col = self._get_task_rows_by_column(statuses=statuses, projects=projects, tags=tags, since=since)
        # count tasks in each column prior to limiting
        task_counts = {col: len(task_rows) for (col, task_rows) in task_rows_by_col.items()}
        if limit is not None:  # limit the number of tasks in each column
            task_rows_by_col = {col: task_rows[:limit] for (col, task_rows) in task_rows_by_col.items()}
        # build table
        if {'todo', 'active'} & set(task_rows_by_col):  # only show scorer name if showing scores
            caption = f'[not italic]Score[/]: {scorer.name}'
            if scorer.description:
                caption += f' ({scorer.description})'
        else:
            caption = None
        table = Table(title=self.board.name, title_style='bold italic blue', caption=caption)
        # make a subtable for each status column
        subtables = []
        for col in col_colors:
            if col in task_rows_by_col:
                col_settings = col_settings_by_col[col]
                task_count = task_counts[col]
                header = col_settings.get_col_header(task_count)
                table.add_column(header, justify='center')
                task_rows = task_rows_by_col[col]
                subtable: Table | str = make_table(col_settings.task_row_type, task_rows, suppress_cols=['status']) if task_rows else ''
                subtables.append(subtable)
        if subtables:
            table.add_row(*subtables)
            print(table)
        else:
            msg = 'No tasks'
            if (statuses is not None) or (projects is not None) or (tags is not None) or (limit is not None):
                msg += ' matching criteria'
            print(style_str(f'\\[{msg}]', DefaultColor.faint, bold=True))

    # SHELL

    def _parse_tokens_for_set_command(self, tokens: list[str]) -> dict[str, str]:
        if (ntokens := len(tokens)) < 2:
            raise UserInputError('Must provide [ID/NAME] [FIELD] [VALUE]')
        [id_or_name, field] = tokens[:2]
        if (pair := parse_key_value_pair(field, strict=False)):  # allow '=' to separate field and value
            (field, value) = pair
        else:
            value = tokens[2] if (ntokens >= 3) else None  # type: ignore[assignment]
        return {'id_or_name': id_or_name, 'field': field, 'value': value}

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
                # parse '='-delimited arguments
                d = dict([parse_key_value_pair(tok, strict=True) for tok in tokens[2:]])  # type: ignore[misc]
                kwargs: dict[str, Any] = {}
                _keys = set()
                for (singular, plural) in [('status', 'statuses'), ('project', 'projects'), ('tag', 'tags')]:
                    for (key, val) in d.items():
                        key_lower = key.lower()
                        if prefix_match(key_lower, singular, minlen=3) or prefix_match(key_lower, plural, minlen=3):
                            values = split_comma_list(val)
                            if not values:
                                raise UserInputError(f'Must provide at least one {singular}')
                            kwargs[plural] = values
                        elif prefix_match(key_lower, 'limit', minlen=3):
                            kwargs['limit'] = parse_task_limit(val)
                        elif key_lower == 'since':
                            none_vals = ['all', 'always', 'any', 'anytime']
                            since = None if (val.strip().lower() in none_vals) else self.config.time.parse_datetime(val)
                            kwargs['since'] = since
                        else:
                            continue
                        _keys.add(key)
                for key in d:
                    if key not in _keys:  # reject unknown keys
                        raise UserInputError(f'Invalid option: {key}')
                return self.show_board(**kwargs)
            if prefix_match(tok1, 'schema', minlen=2):
                return self.show_schema(Board)
        elif prefix_match(tok0, 'help') or (tok0 == 'info'):
            return self.show_help()
        elif prefix_match(tok0, 'project'):
            if (ntokens == 1) or prefix_match(tokens[1], 'help'):
                return self.show_project_help()
            tok1 = tokens[1]
            if prefix_match(tok1, 'new'):
                return self.new_project(None if (ntokens == 2) else tokens[2])
            if prefix_match(tok1, 'delete'):
                return self.delete_project(None if (ntokens == 2) else tokens[2])
            if prefix_match(tok1, 'show'):
                if ntokens == 2:
                    return self.show_projects()
                return self.show_project(tokens[2])
            if tok1 == 'set':
                kwargs = self._parse_tokens_for_set_command(tokens[2:5])
                return self.update_project(**kwargs)
        elif prefix_match(tok0, 'quit') or (tok0 == 'exit'):
            return self.quit_shell()
        elif prefix_match(tok0, 'task'):
            if (ntokens == 1) or prefix_match(tokens[1], 'help'):
                return self.show_task_help()
            tok1 = tokens[1]
            if prefix_match(tok1, 'new'):
                return self.new_task(None if (ntokens == 2) else tokens[2])
            if prefix_match(tok1, 'delete'):
                return self.delete_task(None if (ntokens == 2) else tokens[2])
            if prefix_match(tok1, 'show'):
                if ntokens == 2:
                    return self.show_tasks()
                return self.show_task(tokens[2])
            if tok1 == 'set':
                kwargs = self._parse_tokens_for_set_command(tokens[2:5])
                return self.update_task(**kwargs)
            action: Optional[TaskStatusAction] = None
            if prefix_match(tok1, 'begin'):
                # for convenience, use 'begin' instead of 'start' to avoid prefix collision with 'show'
                action = TaskStatusAction.start
            else:
                for act in [TaskStatusAction.complete, TaskStatusAction.pause, TaskStatusAction.resume]:
                    if prefix_match(tok1, act):
                        action = act
                        break
            if action:
                return self.change_task_status(action, None if (ntokens == 2) else tokens[2])
            if prefix_match(tok1, 'todo'):
                return self.todo_task(None if (ntokens == 2) else tokens[2])
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
        print(style_str("Type 'h' for help.", DefaultColor.faint))
        # TODO: load default board from global config
        if board_path is not None:
            with logger.catch_errors(BoardFileError):
                self.load_board(board_path)
        try:
            while True:
                try:
                    prompt = input('🚀 ')
                    self.evaluate_prompt(prompt)
                except KanbanError as e:
                    print(err_style(e))
        except KeyboardInterrupt:
            print()
            self.quit_shell()
