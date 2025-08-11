from collections.abc import Mapping
from dataclasses import fields
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Annotated, Any, ClassVar, Optional, TypeVar, cast
from urllib.parse import urlparse
import uuid

from fancy_dataclass import JSONBaseDataclass
from pydantic import UUID4, AfterValidator, AnyUrl, BeforeValidator, Field, PlainSerializer, TypeAdapter, computed_field
from pydantic.dataclasses import dataclass
from typing_extensions import Self, TypeAlias

from daikanban.config import get_config
from daikanban.errors import InconsistentTimestampError, TaskStatusError
from daikanban.task import TaskStatus
from daikanban.utils import StrEnum, get_current_time, get_duration_between, human_readable_duration, parse_string_set, style_str


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
    return str(url) if parsed.scheme else f'https://{url}'

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


##########
# STYLES #
##########

class DefaultColor(StrEnum):
    """Enum for default color map."""
    name = 'magenta'  # name of something
    field_name = 'deep_pink4'  # name of a project/task field
    proj_id = 'purple4'  # project ID
    task_id = 'dark_orange3'  # task ID
    path = 'dodger_blue2'  # path to a file
    cmd = 'green'  # command to run
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

def cmd_style(cmd: str) -> str:
    """Renders a command as a rich-styled string."""
    return style_str(cmd, DefaultColor.cmd)

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
class Relation(Model):
    """Class representing a relation between two things.
    A Relation will be attached to its "source" object, so only a "destination" Id needs to be stored."""
    type: str = Field(
        description='Type of the relation'
    )
    dest: Id = Field(
        description='Id of the destination of the relation'
    )
    extra: Optional[dict[str, Any]] = Field(
        default=None,
        description='Any extra data attached to the relation'
    )

    def _map_id(self, id_map: Mapping[Id, Id]) -> Self:
        """Given a mapping from old IDs to new ones, applies that mapping to the destination."""
        return self._replace(dest=id_map.get(self.dest, self.dest))


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
    relations: Optional[list[Relation]] = Field(
        default=None,
        description='Relations between this project and other objects'
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
        kwargs: dict[str, Any] = {}
        if self.parent is not None:
            kwargs['parent'] = proj_id_map.get(self.parent, self.parent)
        if self.relations:
            # TODO: could relations contain anything other than projects? If so, handle them separately.
            kwargs['relations'] = [relation._map_id(proj_id_map) for relation in self.relations]
        return self._replace(**kwargs) if kwargs else self


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
        description='Links associated with the task'
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
    relations: Optional[list[Relation]] = Field(
        default=None,
        description='Relations between this task and other objects'
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

    def __post_init__(self) -> None:
        self.check_consistent_times()

    def _include_field(self, field: str, val: Any) -> bool:
        return (val is not None) or (field == 'project_id')

    def _pretty_dict(self) -> dict[str, str]:
        d = super()._pretty_dict()
        for field in self.DURATION_FIELDS:
            # make durations human-readable
            if field in d:
                val = getattr(self, field)
                if val is not None:
                    assert isinstance(val, float)
                    d[field] = '-' if (val == 0) else human_readable_duration(val)
        if self.project_id is None:
            d['project_id'] = '-'
        return d

    @computed_field  # type: ignore[prop-decorator]
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def lead_time(self) -> Optional[Duration]:
        """If the task is completed, returns the lead time (in days), which is the elapsed time from created to completed.
        Otherwise, returns None."""
        if self.status == TaskStatus.complete:
            assert self.created_time is not None
            assert self.completed_time is not None
            return get_duration_between(self.created_time, self.completed_time)
        return None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cycle_time(self) -> Optional[Duration]:
        """If the task is completed, returns the cycle time (in days), which is the elapsed time from started to completed.
        Otherwise, returns None."""
        if self.status == TaskStatus.complete:
            assert self.first_started_time is not None
            assert self.completed_time is not None
            return get_duration_between(self.first_started_time, self.completed_time)
        return None

    @computed_field  # type: ignore[prop-decorator]
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

    @computed_field  # type: ignore[prop-decorator]
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

    def check_consistent_times(self) -> Self:  # noqa: C901
        """Checks the consistency of various timestamps stored in the Task.
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
        kwargs: dict[str, Any] = dict.fromkeys(self.RESET_FIELDS, None)
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
        if self.relations:
            kwargs['relations'] = [relation._map_id(task_id_map) for relation in self.relations]
        return self._replace(**kwargs) if kwargs else self
