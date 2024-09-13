from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import fields
from datetime import datetime, timedelta
import itertools
import json
from pathlib import Path
from typing import Annotated, Any, ClassVar, Counter, Iterator, Literal, Optional, TypeVar, cast
from urllib.parse import urlparse
import uuid

from fancy_dataclass import JSONBaseDataclass
from pydantic import UUID4, AfterValidator, AnyUrl, BeforeValidator, Field, PlainSerializer, TypeAdapter, ValidationError, computed_field, model_validator
from pydantic.dataclasses import dataclass
from rich.markup import escape
from typing_extensions import Self, TypeAlias

from daikanban.config import Config, get_config
from daikanban.task import TaskStatus
from daikanban.utils import KanbanError, NameMatcher, StrEnum, exact_match, first_name_match, get_current_time, get_duration_between, human_readable_duration, parse_string_set, style_str


T = TypeVar('T')
M = TypeVar('M')

NEARLY_DUE_THRESH = timedelta(days=1)


################
# TYPE ALIASES #
################

Id: TypeAlias = Annotated[int, Field(ge=0)]

def _check_name(name: str) -> str:
    if not any(c.isalpha() for c in name):
        raise ValueError('Name must have at least one letter')
    return name

def _check_url(url: Any) -> str:
    parsed = urlparse(str(url))
    if (parsed.scheme in ['', 'http', 'https']) and ('.' not in parsed.netloc) and ('.' not in parsed.path):
        raise ValueError('Invalid URL')
    # if scheme is absent, assume https
    return url if parsed.scheme else f'https://{url}'

def _parse_datetime(obj: str | datetime) -> datetime:
    return get_config().time.parse_datetime(obj) if isinstance(obj, str) else obj

def _render_datetime(dt: datetime) -> str:
    return get_config().time.render_datetime(dt)

def _parse_duration(obj: str | float) -> float:
    return get_config().time.parse_duration(obj) if isinstance(obj, str) else obj

def _parse_optional(obj: Any) -> Any:
    if (obj is None) or (isinstance(obj, str) and (not obj)):
        return None
    return obj

def _parse_str_set(obj: str | set[str]) -> set[str]:
    return (parse_string_set(obj) or set()) if isinstance(obj, str) else obj

def _parse_url_set(obj: str | set[str]) -> set[AnyUrl]:
    if obj == '':
        return set()
    strings = parse_string_set(obj) if isinstance(obj, str) else obj
    return set(map(_check_url, strings))  # type: ignore[arg-type]


Name: TypeAlias = Annotated[str, AfterValidator(_check_name)]

Url: TypeAlias = Annotated[AnyUrl, BeforeValidator(_check_url)]

Datetime: TypeAlias = Annotated[
    datetime,
    BeforeValidator(_parse_datetime),
    PlainSerializer(_render_datetime, return_type=str)
]

OptionalDatetime: TypeAlias = Annotated[Optional[Datetime], BeforeValidator(_parse_optional)]

Duration: TypeAlias = Annotated[
    float,
    BeforeValidator(_parse_duration),
    Field(description='Duration (days)', ge=0.0)
]

OptionalDuration: TypeAlias = Annotated[Optional[Duration], BeforeValidator(_parse_optional)]

Score: TypeAlias = Annotated[float, Field(description='A score (positive number)', ge=0.0)]

OptionalScore: TypeAlias = Annotated[Optional[Score], BeforeValidator(_parse_optional)]

StrSet: TypeAlias = Annotated[set[str], BeforeValidator(_parse_str_set)]

UrlSet: TypeAlias = Annotated[set[Url], BeforeValidator(_parse_url_set)]


##################
# ERROR HANDLING #
##################

class InconsistentTimestampError(KanbanError):
    """Error that occurs if a timestamp is inconsistent."""

class ProjectNotFoundError(KanbanError):
    """Error that occurs when a project ID is not found."""
    def __init__(self, project_id: Id | UUID4) -> None:
        if isinstance(project_id, uuid.UUID):
            field = 'uuid'
            val: str | int = str(project_id)
        else:
            field, val = 'id', project_id
        super().__init__(f'Project with {field} {val!r} not found')

class TaskNotFoundError(KanbanError):
    """Error that occurs when a task ID is not found."""
    def __init__(self, task_id: Id | UUID4) -> None:
        if isinstance(task_id, uuid.UUID):
            field = 'uuid'
            val: str | int = str(task_id)
        else:
            field, val = 'id', task_id
        super().__init__(f'Task with {field} {val!r} not found')

class TaskStatusError(KanbanError):
    """Error that occurs when a task's status is invalid for a certain operation."""

class DuplicateProjectError(KanbanError):
    """Error that occurs when a duplicate project is added (same UUID)."""

class DuplicateProjectNameError(KanbanError):
    """Error that occurs when duplicate project names are encountered."""

class DuplicateTaskError(KanbanError):
    """Error that occurs when a duplicate task is added (same UUID)."""

class DuplicateTaskNameError(KanbanError):
    """Error that occurs when duplicate task names are encountered."""

class AmbiguousProjectNameError(KanbanError):
    """Error that occurs when a provided project name matches multiple names."""

class AmbiguousTaskNameError(KanbanError):
    """Error that occurs when provided task name matches multiple names."""

class UUIDError(KanbanError):
    """Error related to UUIDs."""

class UUIDImmutableError(UUIDError):
    """Error that occurs when trying to modify a UUID."""

class BoardFileError(KanbanError):
    """Error reading or writing a board file."""

class VersionMismatchError(KanbanError):
    """Error occurring when there is a version mismatch between two boards."""


@contextmanager
def catch_key_error(cls: type[Exception]) -> Iterator[None]:
    """Catches a KeyError and rewraps it as an Exception of the given type."""
    try:
        yield
    except KeyError as e:
        raise cls(e.args[0]) from None


##########
# STYLES #
##########

class DefaultColor(StrEnum):
    """Enum for default color map."""
    name = 'magenta'
    field_name = 'deep_pink4'
    proj_id = 'purple4'
    task_id = 'dark_orange3'
    path = 'dodger_blue2'
    error = 'red'
    faint = 'bright_black'

def name_style(name: str) -> str:
    """Renders a project/task/board name as a rich-styled string."""
    return style_str(name, DefaultColor.name)

def proj_id_style(id_: Id, bold: bool = False) -> str:
    """Renders a project ID as a rich-styled string."""
    return style_str(id_, DefaultColor.proj_id, bold=bold)

def task_id_style(id_: Id, bold: bool = False) -> str:
    """Renders a task ID as a rich-styled string."""
    return style_str(id_, DefaultColor.task_id, bold=bold)

def path_style(path: str | Path, bold: bool = False) -> str:
    """Renders a path as a rich-styled string."""
    return style_str(path, DefaultColor.path, bold=bold)

def status_style(status: TaskStatus) -> str:
    """Renders a TaskStatus as a rich-styled string with the appropriate color."""
    return style_str(status, status.color)


########
# JSON #
########

_BaseEncoder = JSONBaseDataclass.json_encoder()

class ModelJSONEncoder(_BaseEncoder):  # type: ignore[misc, valid-type]
    """Custom JSONEncoder used by default with model classes."""

    def default(self, obj: Any) -> Any:
        """Customizes JSON encoding so that sets can be represented as lists."""
        if isinstance(obj, AnyUrl):
            return str(obj)
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, set):
            return sorted(obj)
        return super().default(obj)


#########
# MODEL #
#########

class Model(JSONBaseDataclass, suppress_none=True, store_type='off', validate=False):
    """Base class setting up pydantic configs."""

    def _include_field(self, field: str, val: Any) -> bool:
        return val is not None

    @classmethod
    def _computed_fields(cls) -> list[str]:
        """Gets the list of computed fields (properties marked with the `computed_field` decorator)."""
        schema = TypeAdapter(cls).core_schema['schema']
        while 'schema' in schema:  # weirdly, 'dataclass-args' schema may be nested in a 'dataclass' schema
            schema = schema['schema']
        return [d['property_name'] for d in schema.get('computed_fields', [])]

    def _pretty_dict(self) -> dict[str, str]:
        """Gets a dict from fields to pretty values (as strings)."""
        config = get_config()
        return {
            **{field: config.pretty_value(val) for (field, val) in self.to_dict().items() if self._include_field(field, val)},
            **{field: config.pretty_value(val) for field in self._computed_fields() if self._include_field(field, (val := getattr(self, field)))}
        }

    @classmethod
    def json_schema(cls, **kwargs: Any) -> dict[str, Any]:
        """Produces a JSON schema based on the Model subtype."""
        return TypeAdapter(cls).json_schema(**kwargs)

    def _replace(self, **kwargs: Any) -> Self:
        d = {fld.name: getattr(self, fld.name) for fld in fields(self)}  # type: ignore[arg-type]
        for (key, val) in kwargs.items():
            if key in d:
                d[key] = val
            else:
                raise TypeError(f'Unknown field {key!r}')
        return type(self)(**d)

    @classmethod
    def json_encoder(cls) -> type[json.JSONEncoder]:
        """Returns the custom JSON encoder for Model classes."""
        return ModelJSONEncoder


class TaskStatusAction(StrEnum):
    """Actions which can change a task's status."""
    start = 'start'
    complete = 'complete'
    pause = 'pause'
    resume = 'resume'

    def past_tense(self) -> str:
        """Gets the action in the past tense."""
        if self == TaskStatusAction.start:
            return 'started'
        return f'{self}d'


# mapping from action to resulting status
STATUS_ACTION_MAP = {
    'start': TaskStatus.active,
    'complete': TaskStatus.complete,
    'pause': TaskStatus.paused,
    'resume': TaskStatus.active
}


@dataclass(frozen=True)
class Project(Model):
    """A project associated with multiple tasks."""
    name: Name = Field(
        description='Project name'
    )
    uuid: UUID4 = Field(
        default_factory=uuid.uuid4,
        description='UUID (uniquely identifying project)'
    )
    description: Optional[str] = Field(
        default=None,
        description='Project description'
    )
    created_time: Datetime = Field(
        default_factory=get_current_time,
        description='Time the project was created'
    )
    modified_time: Datetime = Field(
        default_factory=get_current_time,
        description='Time the project was last modified'
    )
    links: Optional[UrlSet] = Field(
        default=None,
        description='Links associated with the project'
    )
    parent: Optional[Id] = Field(
        default=None,
        description='ID of parent project, if one exists'
    )
    notes: Optional[list[str]] = Field(
        default=None,
        description='Additional notes about the project'
    )
    extra: Optional[dict[str, Any]] = Field(
        default=None,
        description='Any extra data attached to the project'
    )

    def modified(self, dt: Optional[Datetime] = None) -> Self:
        """Returns a new version of the project whose 'modified_time' attribute is altered.
        If no datetime is provided, uses the current time."""
        return self._replace(modified_time=dt or get_current_time())

    def _map_project_ids(self, proj_id_map: Mapping[Id, Id]) -> Self:
        """Given a mapping from old project IDs to new ones, applies that mapping to any stored IDs."""
        return self if (self.parent is None) else self._replace(parent=proj_id_map.get(self.parent, self.parent))


@dataclass(frozen=True)
class Log(Model):
    """A piece of information associated with a task at a particular time.
    This is typically used to record events."""
    time: Optional[Datetime] = Field(
        default_factory=get_current_time,
        description='Time the log was created'
    )
    type: Optional[str] = Field(
        default=None,
        description='Type of the log'
    )
    note: Optional[str] = Field(
        default=None,
        description='Textual content of the log'
    )
    rating: OptionalScore = Field(
        default=None,
        description="Rating of the task's current progress"
    )


@dataclass(frozen=True)
class Task(Model):
    """A task to be performed."""
    name: Name = Field(
        description='Task name'
    )
    uuid: UUID4 = Field(
        default_factory=uuid.uuid4,
        description='UUID (uniquely identifying task)'
    )
    description: Optional[str] = Field(
        default=None,
        description='Task description'
    )
    priority: OptionalScore = Field(
        default=None,
        description='Priority of task'
    )
    expected_difficulty: OptionalScore = Field(
        default=None,
        description='Estimated difficulty of task'
    )
    expected_duration: OptionalDuration = Field(
        default=None,
        description='Expected number of days to complete task'
    )
    due_time: OptionalDatetime = Field(
        default=None,
        description='Time the task is due'
    )
    project_id: Optional[Id] = Field(
        default=None,
        description='Project ID'
    )
    tags: Optional[StrSet] = Field(
        default=None,
        description='Tags associated with the task'
    )
    links: Optional[UrlSet] = Field(
        default=None,
        description='Links associated with the project'
    )
    created_time: Datetime = Field(
        default_factory=get_current_time,
        description='Time the task was created'
    )
    modified_time: Datetime = Field(
        default_factory=get_current_time,
        description='Time the task was last modified'
    )
    first_started_time: OptionalDatetime = Field(
        default=None,
        description='Time the task was first started'
    )
    last_started_time: OptionalDatetime = Field(
        default=None,
        description='Time the task was last started (if not paused)'
    )
    last_paused_time: OptionalDatetime = Field(
        default=None,
        description='Time the task was last paused'
    )
    completed_time: OptionalDatetime = Field(
        default=None,
        description='Time the task was completed'
    )
    prior_time_worked: OptionalDuration = Field(
        default=None,
        description='Total time (in days) the task was worked on prior to last_started_time'
    )
    blocked_by: Optional[set[Id]] = Field(
        default=None,
        description='IDs of other tasks that block the completion of this one'
    )
    parent: Optional[Id] = Field(
        default=None,
        description='ID of parent task, if one exists'
    )
    logs: Optional[list[Log]] = Field(
        default=None,
        description='List of dated logs related to the task'
    )
    notes: Optional[list[str]] = Field(
        default=None,
        description='Additional notes about the task'
    )
    extra: Optional[dict[str, Any]] = Field(
        default=None,
        description='Any extra data attached to the task'
    )

    # fields that are reset to None when a Task is reset
    RESET_FIELDS: ClassVar[list[str]] = ['due_time', 'first_started_time', 'last_started_time', 'last_paused_time', 'completed_time', 'completed_time', 'prior_time_worked', 'blocked_by', 'parent', 'logs']
    # fields whose type is duration
    DURATION_FIELDS: ClassVar[list[str]] = ['expected_duration', 'prior_time_worked', 'lead_time', 'cycle_time', 'total_time_worked']

    def _include_field(self, field: str, val: Any) -> bool:
        return (val is not None) or (field == 'project_id')

    def _pretty_dict(self) -> dict[str, str]:
        d = super()._pretty_dict()
        for field in self.DURATION_FIELDS:
            # make durations human-readable
            if field in d:
                val = getattr(self, field)
                if (val is not None):
                    assert isinstance(val, float)
                    d[field] = '-' if (val == 0) else human_readable_duration(val)
        if self.project_id is None:
            d['project_id'] = '-'
        return d

    @computed_field  # type: ignore[misc]
    @property
    def status(self) -> TaskStatus:
        """Gets the current status of the task."""
        if self.first_started_time is None:
            return TaskStatus.todo
        if self.last_paused_time is not None:
            return TaskStatus.paused
        if self.completed_time is not None:
            return TaskStatus.complete
        return TaskStatus.active

    @computed_field  # type: ignore[misc]
    @property
    def lead_time(self) -> Optional[Duration]:
        """If the task is completed, returns the lead time (in days), which is the elapsed time from created to completed.
        Otherwise, returns None."""
        if self.status == TaskStatus.complete:
            assert self.created_time is not None
            assert self.completed_time is not None
            return get_duration_between(self.created_time, self.completed_time)
        return None

    @computed_field  # type: ignore[misc]
    @property
    def cycle_time(self) -> Optional[Duration]:
        """If the task is completed, returns the cycle time (in days), which is the elapsed time from started to completed.
        Otherwise, returns None."""
        if self.status == TaskStatus.complete:
            assert self.first_started_time is not None
            assert self.completed_time is not None
            return get_duration_between(self.first_started_time, self.completed_time)
        return None

    @computed_field  # type: ignore[misc]
    @property
    def total_time_worked(self) -> Duration:
        """Gets the total time (in days) worked on the task."""
        dur = self.prior_time_worked or 0.0
        if self.last_paused_time is None:  # active or complete
            last_started_time = self.last_started_time or self.first_started_time
            if last_started_time is not None:
                final_time = self.completed_time or get_current_time()
                dur += get_duration_between(last_started_time, final_time)
        return dur

    @computed_field  # type: ignore[misc]
    @property
    def is_overdue(self) -> bool:
        """Returns True if the task is overdue (i.e. it was not completed before the due time)."""
        if self.due_time is None:
            return False
        eval_time = self.completed_time or get_current_time()
        return eval_time > self.due_time

    @property
    def time_till_due(self) -> Optional[timedelta]:
        """Returns the time interval between the current time and the due time, or None if there is no due time."""
        if self.due_time is None:
            return None
        return self.due_time - get_current_time()

    @property
    def status_icons(self, nearly_due_thresh: Optional[timedelta] = None) -> Optional[str]:
        """Gets one or more icons (emoji) representing the status of the task, or None if there is none.
        If nearly_due_threshold is given, this is the time threshold before the due time within which to show a status warning."""
        nearly_due_thresh = NEARLY_DUE_THRESH if (nearly_due_thresh is None) else nearly_due_thresh
        status = self.status
        td = self.time_till_due
        icons = []
        if (status != TaskStatus.complete) and (td is not None):
            if td < timedelta(0):  # overdue
                icons.append('🚨')
            elif td < nearly_due_thresh:  # due soon
                icons.append('👀')
            else:  # has a future due time
                icons.append('⏱️ ')
        if status == TaskStatus.paused:
            icons.append('⏸️ ')
        return ' '.join(icons) if icons else None

    @model_validator(mode='after')
    def check_consistent_times(self) -> Self:  # noqa: C901
        """Checks the consistence of various timestamps stored in the Task.
        If any is invalid, raises an InconsistentTimestampError."""
        def _invalid(msg: str) -> InconsistentTimestampError:
            return InconsistentTimestampError(f'{msg}\n\t{self}')
        if self.first_started_time is not None:
            if self.first_started_time < self.created_time:
                raise _invalid('Task start time cannot precede created time')
        if self.last_started_time is not None:
            if self.first_started_time is None:
                raise _invalid('Task missing first started time')
            if self.last_started_time < self.first_started_time:
                raise _invalid('Task last started time cannot precede first started time')
        if self.last_paused_time is not None:
            if self.first_started_time is None:
                raise _invalid('Task missing first started time')
            if self.last_started_time is not None:
                raise _invalid('Task cannot have both a last started and last paused time')
            if self.last_paused_time < self.first_started_time:
                raise _invalid('Task last paused time cannot precede first started time')
        if self.completed_time is not None:
            if self.first_started_time is None:
                raise _invalid('Task missing first started time')
            if self.completed_time < self.first_started_time:
                raise _invalid('Task completed time cannot precede first started time')
            if self.last_started_time and (self.completed_time < self.last_started_time):
                raise _invalid('Task completed time cannot precede last started time')
        # task is paused or completed => task has prior time worked
        if (self.status == TaskStatus.paused) and (self.prior_time_worked is None):
            raise _invalid('Task in paused or completed status must set prior time worked')
        return self

    def modified(self, dt: Optional[Datetime] = None) -> Self:
        """Returns a new version of the task whose 'modified_time' attribute is altered.
        If no datetime is provided, uses the current time."""
        return self._replace(modified_time=dt or get_current_time())

    def started(self, dt: Optional[Datetime] = None) -> Self:
        """Returns a new started version of the task, if its status is todo.
        Otherwise raises a TaskStatusError."""
        if self.status == TaskStatus.todo:
            cur_time = get_current_time()
            dt = dt or cur_time
            if dt < self.created_time:
                dt_str = get_config().time.render_datetime(self.created_time)
                raise TaskStatusError(f'cannot start a task before its creation time ({dt_str})')
            return self._replace(first_started_time=dt, modified_time=cur_time)
        raise TaskStatusError(f"cannot start task with status '{self.status}'")

    def completed(self, dt: Optional[datetime] = None) -> Self:
        """Returns a new completed version of the task, if its status is active.
        Otherwise raises a TaskStatusError."""
        if self.status == TaskStatus.active:
            cur_time = get_current_time()
            dt = dt or cur_time
            last_started_time = cast(datetime, self.last_started_time or self.first_started_time)
            if dt < last_started_time:
                raise TaskStatusError('cannot complete a task before its last started time')
            return self._replace(completed_time=dt, modified_time=cur_time)
        raise TaskStatusError(f"cannot complete task with status '{self.status}'")

    def paused(self, dt: Optional[datetime] = None) -> Self:
        """Returns a new paused version of the task, if its status is active.
        Otherwise raises a TaskStatusError."""
        if self.status == TaskStatus.active:
            cur_time = get_current_time()
            dt = dt or cur_time
            last_started_time = cast(datetime, self.last_started_time or self.first_started_time)
            if dt < last_started_time:
                raise TaskStatusError('cannot pause a task before its last started time')
            dur = 0.0 if (self.prior_time_worked is None) else self.prior_time_worked
            dur += get_duration_between(last_started_time, dt)
            return self._replace(last_started_time=None, last_paused_time=dt, prior_time_worked=dur, modified_time=cur_time)
        raise TaskStatusError(f"cannot pause task with status '{self.status}'")

    def resumed(self, dt: Optional[datetime] = None) -> Self:
        """Returns a new resumed version of the task, if its status is paused.
        Otherwise raises a TaskStatusError."""
        status = self.status
        if status in [TaskStatus.paused, TaskStatus.complete]:
            cur_time = get_current_time()
            dt = dt or cur_time
            if status == TaskStatus.paused:
                assert self.last_paused_time is not None
                if dt < self.last_paused_time:
                    raise TaskStatusError('cannot resume a task before its last paused time')
                return self._replace(last_started_time=dt, last_paused_time=None, modified_time=cur_time)
            else:  # complete
                assert self.completed_time is not None
                if dt < self.completed_time:
                    raise TaskStatusError('cannot resume a task before its completed time')
                return self._replace(last_started_time=dt, prior_time_worked=self.total_time_worked, completed_time=None, modified_time=cur_time)
        raise TaskStatusError(f"cannot resume task with status '{self.status}'")

    def apply_status_action(self, action: TaskStatusAction, dt: Optional[datetime] = None, first_dt: Optional[datetime] = None) -> Self:
        """Applies a status action to the task, returning the new task.
            dt: datetime at which the action occurred (if consisting of two consecutive actions, the latter one)
            first_dt: if the action consists of two consecutive actions, the datetime at which the first action occurred
        If the action is invalid for the task's current state, raises a TaskStatusError."""
        if action == TaskStatusAction.start:
            return self.started(dt=dt)
        if action == TaskStatusAction.complete:
            if self.status == TaskStatus.todo:
                return self.started(dt=first_dt).completed(dt=dt)
            if self.status in [TaskStatus.active, TaskStatus.complete]:
                return self.completed(dt=dt)
            assert self.status == TaskStatus.paused
            return self.resumed(dt=first_dt).completed(dt=dt)
        if action == TaskStatusAction.pause:
            if self.status == TaskStatus.todo:
                return self.started(dt=first_dt).paused(dt=dt)
            return self.paused(dt=dt)
        assert action == TaskStatusAction.resume
        return self.resumed(dt=dt)

    def reset(self) -> Self:
        """Resets a task to the 'todo' state, regardless of its current state.
        This will preserve the original creation metadata except for timestamps, due time, blocking tasks, and logs."""
        kwargs: dict[str, Any] = {field: None for field in self.RESET_FIELDS}
        kwargs['modified_time'] = get_current_time()
        return self._replace(**kwargs)

    def _map_project_ids(self, proj_id_map: Mapping[Id, Id]) -> Self:
        """Given a mapping from old project IDs to new ones, applies that mapping to any stored project IDs."""
        return self if (self.project_id is None) else self._replace(project_id=proj_id_map.get(self.project_id, self.project_id))

    def _map_task_ids(self, task_id_map: Mapping[Id, Id]) -> Self:
        """Given a mapping from old task IDs to new ones, applies that mapping to any stored task IDs."""
        kwargs: dict[str, Any] = {}
        if self.blocked_by:
            kwargs['blocked_by'] = {task_id_map.get(id_, id_) for id_ in self.blocked_by}
        if self.parent is not None:
            kwargs['parent'] = task_id_map.get(self.parent, self.parent)
        return self if (kwargs is None) else self._replace(**kwargs)


@dataclass
class Board(Model):
    """A DaiKanban board (collection of projects and tasks)."""
    name: str = Field(description='Name of DaiKanban board')
    description: Optional[str] = Field(
        default=None,
        description='Description of the DaiKanban board'
    )
    created_time: OptionalDatetime = Field(
        default_factory=get_current_time,
        description='Time the board was created'
    )
    projects: dict[Id, Project] = Field(
        default_factory=dict,
        description='Mapping from IDs to projects'
    )
    tasks: dict[Id, Task] = Field(
        default_factory=dict,
        description='Mapping from IDs to tasks'
    )
    version: Literal[0] = Field(
        default=0,
        description='Version of the DaiKanban specification',
    )

    def __post_init__(self) -> None:
        # mappings from UUIDs to IDs
        self._project_uuid_to_id: dict[UUID4, Id] = {}
        self._task_uuid_to_id: dict[UUID4, Id] = {}

    @model_validator(mode='after')
    def check_valid_project_ids(self) -> Self:
        """Checks that project IDs associated with all tasks are in the set of projects."""
        for task in self.tasks.values():
            if task.project_id is not None:
                if task.project_id not in self.projects:
                    raise ProjectNotFoundError(task.project_id)
        return self

    def new_project_id(self) -> Id:
        """Gets an available integer as a project ID."""
        return next(filter(lambda id_: id_ not in self.projects, itertools.count()))

    def new_project_uuid(self) -> UUID4:
        """Gets a unique UUID to be used for a new project."""
        while (uuid_ := uuid.uuid4()) not in self._project_uuid_to_id:
            pass
        return uuid_

    def new_task_id(self) -> Id:
        """Gets an available integer as a task ID."""
        return next(filter(lambda id_: id_ not in self.tasks, itertools.count()))

    def new_task_uuid(self) -> UUID4:
        """Gets a unique UUID to be used for a new task."""
        while (uuid_ := uuid.uuid4()) not in self._task_uuid_to_id:
            pass
        return uuid_

    def _check_duplicate_project_name(self, name: str) -> None:
        """Checks whether the given project name matches an existing one.
        If so, raises a DuplicateProjectNameError."""
        matcher = get_config().name_matcher
        project_names = (p.name for p in self.projects.values())
        if (duplicate_name := first_name_match(matcher, name, project_names)) is not None:
            raise DuplicateProjectNameError(f'Duplicate project name {duplicate_name!r}')

    def create_project(self, project: Project) -> Id:
        """Adds a new project and returns its ID."""
        if project.uuid in self._project_uuid_to_id:
            raise DuplicateProjectError(f'Duplicate project UUID {str(project.uuid)!r}')
        self._check_duplicate_project_name(project.name)
        id_ = self.new_project_id()
        self.projects[id_] = project
        self._project_uuid_to_id[project.uuid] = id_
        return id_

    @catch_key_error(ProjectNotFoundError)
    def get_project(self, project_id: Id) -> Project:
        """Gets a project with the given ID."""
        return self.projects[project_id]

    @staticmethod
    def _filter_id_matches(pairs: list[tuple[Id, bool]]) -> list[Id]:
        if any(exact for (_, exact) in pairs):
            return [id_ for (id_, exact) in pairs if exact]
        return [id_ for (id_, _) in pairs]

    def get_project_id_by_name(self, name: str, matcher: NameMatcher = exact_match) -> Optional[Id]:
        """Gets the ID of the project with the given name, if it matches; otherwise, None."""
        pairs = [(id_, name == p.name) for (id_, p) in self.projects.items() if matcher(name, p.name)]
        ids = self._filter_id_matches(pairs)  # retain only exact matches, if present
        if ids:
            if len(ids) > 1:
                raise AmbiguousProjectNameError(f'Ambiguous project name {name!r}')
            return ids[0]
        return None

    def update_project(self, project_id: Id, **kwargs: Any) -> None:
        """Updates a project with the given keyword arguments."""
        if 'uuid' in kwargs:
            raise UUIDImmutableError("Cannot modify a project's UUID")
        proj = self.get_project(project_id)
        if 'name' in kwargs:
            matcher = get_config().name_matcher
            project_names = (p.name for (id_, p) in self.projects.items() if (id_ != project_id))
            if (duplicate_name := first_name_match(matcher, kwargs['name'], project_names)) is not None:
                raise DuplicateProjectNameError(f'Duplicate project name {duplicate_name!r}')
        kwargs = {'modified_time': get_current_time(), **kwargs}
        proj = proj._replace(**kwargs)
        self.projects[project_id] = proj

    @catch_key_error(ProjectNotFoundError)
    def delete_project(self, project_id: Id) -> None:
        """Deletes a project with the given ID."""
        del self._project_uuid_to_id[self.projects[project_id].uuid]
        del self.projects[project_id]
        # remove project ID from any tasks that have it
        for (task_id, task) in self.tasks.items():
            if task.project_id == project_id:
                self.tasks[task_id] = task._replace(project_id=None)

    def _check_duplicate_task_name(self, name: str) -> None:
        """Checks whether the given task name matches an existing name of an incomplete task.
        If so, raises a DuplicateTaskNameError."""
        matcher = get_config().name_matcher
        incomplete_task_names = (t.name for t in self.tasks.values() if (t.completed_time is None))
        if (duplicate_name := first_name_match(matcher, name, incomplete_task_names)) is not None:
            raise DuplicateTaskNameError(f'Duplicate task name {duplicate_name!r}')

    def create_task(self, task: Task) -> Id:
        """Adds a new task and returns its ID."""
        if task.uuid in self._task_uuid_to_id:
            raise DuplicateTaskError(f'Duplicate task UUID {str(task.uuid)!r}')
        if task.project_id is not None:  # validate project ID
            _ = self.get_project(task.project_id)
        self._check_duplicate_task_name(task.name)
        id_ = self.new_task_id()
        self.tasks[id_] = task
        self._task_uuid_to_id[task.uuid] = id_
        return id_

    @catch_key_error(TaskNotFoundError)
    def get_task(self, task_id: Id) -> Task:
        """Gets a task with the given ID."""
        return self.tasks[task_id]

    def get_task_id_by_name(self, name: str, matcher: NameMatcher = exact_match) -> Optional[Id]:
        """Gets the ID of the task with the given name, if it matches; otherwise, None.
        There may be multiple tasks with the same name, but at most one can be incomplete.
        Behavior is as follows:
            - If there is an incomplete task, chooses this one
            - If there is a single complete task, chooses this one
            - Otherwise, raises AmbiguousTaskNameError"""
        incomplete_pairs: list[tuple[Id, bool]] = []
        complete_pairs: list[tuple[Id, bool]] = []
        for (id_, t) in self.tasks.items():
            if matcher(name, t.name):
                pairs = incomplete_pairs if (t.completed_time is None) else complete_pairs
                pairs.append((id_, name == t.name))
        incomplete_ids = self._filter_id_matches(incomplete_pairs)
        complete_ids = self._filter_id_matches(complete_pairs)
        # prioritize exact matches, and incomplete over complete
        if any(exact for (_, exact) in incomplete_pairs):
            return incomplete_ids[0]
        def _get_id(ids: list[Id], err: str) -> Id:
            if len(ids) > 1:
                raise AmbiguousTaskNameError(err)
            return ids[0]
        if any(exact for (_, exact) in complete_pairs):
            return _get_id(complete_ids, f'Multiple completed tasks match name {name!r}')
        if incomplete_ids:
            return _get_id(incomplete_ids, f'Ambiguous task name {name!r}')
        if complete_ids:
            return _get_id(complete_ids, f'Multiple completed tasks match name {name!r}')
        return None

    def update_task(self, task_id: Id, **kwargs: Any) -> None:
        """Updates a task with the given keyword arguments."""
        if 'uuid' in kwargs:
            raise ValueError("Cannot modify a task's UUID")
        task = self.get_task(task_id)
        incomplete_task_names = (t.name for (id_, t) in self.tasks.items() if (id_ != task_id) and (t.completed_time is None))
        kwargs = {'modified_time': get_current_time(), **kwargs}
        task = task._replace(**kwargs)
        if task.project_id is not None:  # validate project ID
            _ = self.get_project(task.project_id)
        matcher = get_config().name_matcher
        if (duplicate_name := first_name_match(matcher, task.name, incomplete_task_names)) is not None:
            raise DuplicateTaskNameError(f'Duplicate task name {duplicate_name!r}')
        self.tasks[task_id] = task

    @catch_key_error(TaskNotFoundError)
    def delete_task(self, task_id: Id) -> None:
        """Deletes a task with the given ID."""
        del self._task_uuid_to_id[self.tasks[task_id].uuid]
        del self.tasks[task_id]

    @catch_key_error(TaskNotFoundError)
    def reset_task(self, task_id: Id) -> None:
        """Resets a task with the given ID to the 'todo' state, regardless of its current state.
        This will preserve the original creation metadata except for timestamps, due time, blocking tasks, and logs."""
        task = self.get_task(task_id)
        self.tasks[task_id] = task.reset()

    def apply_status_action(self, task_id: Id, action: TaskStatusAction, dt: Optional[datetime] = None, first_dt: Optional[datetime] = None) -> Task:
        """Changes a task to a new stage, based on the given action at the given time.
        Returns the new task."""
        task = self.get_task(task_id).apply_status_action(action, dt=dt, first_dt=first_dt)
        incomplete_task_names = {t.name for (id_, t) in self.tasks.items() if (id_ != task_id) and (t.completed_time is None)}
        if task.name in incomplete_task_names:
            raise DuplicateTaskNameError(f'Duplicate task name {task.name!r}')
        self.tasks[task_id] = task
        return task

    @catch_key_error(TaskNotFoundError)
    def add_blocking_task(self, blocking_task_id: Id, blocked_task_id: Id) -> None:
        """Adds a task ID to the list of blocking tasks for another."""
        _ = self.get_task(blocking_task_id)  # ensure blocking task exists
        blocked_task = self.get_task(blocked_task_id)
        blocked_by = set(blocked_task.blocked_by) if blocked_task.blocked_by else set()
        blocked_by.add(blocking_task_id)
        self.tasks[blocked_task_id] = blocked_task._replace(blocked_by=blocked_by)

    @property
    def num_tasks_by_project(self) -> Counter[Id]:
        """Gets a map from project IDs to the number of tasks associated with it."""
        return Counter(task.project_id for task in self.tasks.values() if task.project_id is not None)

    def update_with_board(self, other: Self) -> None:  # noqa: C901
        """Updates the contents of this board with another board, in-place.
        The basic board metadata (such as name) will remain the same as this board's.
        Exact duplicate projects/tasks will be deduplicated using this board's ID.
        Projects/tasks with the same UUID but different contents will be reconciled, using the given ConflictResolutionMode."""
        if other.version > self.version:  # assume backward (but not forward) compatibility
            raise VersionMismatchError(f'Attempted to update version {self.version} board with version {other.version} board')
        proj_id_map = {}  # map from old project IDs to new IDs
        for (other_id, other_proj) in other.projects.items():
            if other_proj.uuid in self._project_uuid_to_id:
                this_id = self._project_uuid_to_id[other_proj.uuid]
                if this_id != other_id:
                    proj_id_map[other_id] = this_id
                if other_proj != (this_proj := self.projects[this_id]):
                    # reconcile two different projects
                    # TODO: do this based on the ConflictResolutionMode
                    if other_proj.modified_time > this_proj.modified_time:  # replace with new project
                        kwargs = other_proj.to_dict()
                        del kwargs['uuid']
                        self.update_project(this_id, **kwargs)
            else:  # ignore other ID and create a new one
                proj_id_map[other_id] = self.create_project(other_proj)
        task_id_map = {}  # map from old task IDs to new IDs
        for (other_id, other_task) in other.tasks.items():
            if other_task.uuid in self._task_uuid_to_id:
                this_id = self._task_uuid_to_id[other_task.uuid]
                if this_id != other_id:
                    task_id_map[other_id] = this_id
                if other_task != (this_task := self.tasks[this_id]):
                    # reconcile two different tasks
                    # TODO: do this based on the ConflictResolutionMode
                    if other_task.modified_time > this_task.modified_time:  # replace with new task
                        kwargs = other_task.to_dict()
                        del kwargs['uuid']
                        self.update_task(this_id, **kwargs)
            else:
                task_id_map[other_id] = self.create_task(other_task)
        # for projects, map foreign project IDs to the new ones
        for proj_id in proj_id_map.values():
            self.projects[proj_id] = self.projects[proj_id]._map_project_ids(proj_id_map)
        # for tasks, map foreign project/task IDs to the new ones
        for task_id in task_id_map.values():
            self.tasks[task_id] = self.tasks[task_id]._map_project_ids(proj_id_map)._map_task_ids(task_id_map)


def load_board(name_or_path: str | Path, config: Optional[Config] = None) -> Board:
    """Given a board name or path, loads the board from a JSON file.
    If none is provided, prompts the user interactively."""
    config = config or get_config()
    path = config.resolve_board_name_or_path(name_or_path)
    if not path.exists():
        raise BoardFileError(f'Board file {path_style(path)} does not exist')
    try:
        return Board.load(path)
    except (json.JSONDecodeError, OSError, ValidationError) as e:
        e_str = escape(str(e)) if isinstance(e, ValidationError) else str(e)
        msg = f'When loading JSON {path_style(path)}: {e_str}'
        raise BoardFileError(msg) from None
