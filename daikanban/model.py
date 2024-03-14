from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Annotated, Any, ClassVar, Counter, Iterator, Literal, Optional, TypeVar, cast

import pendulum
from pydantic import AfterValidator, AnyUrl, BaseModel, BeforeValidator, Field, PlainSerializer, computed_field, model_validator
from typing_extensions import Self, TypeAlias

from daikanban.utils import DATE_FORMAT, TIME_FORMAT, KanbanError, StrEnum, get_current_time, get_duration_between, human_readable_duration, parse_date


T = TypeVar('T')
M = TypeVar('M', bound=BaseModel)

NEARLY_DUE_THRESH = timedelta(days=1)


################
# TYPE ALIASES #
################

Id: TypeAlias = Annotated[int, Field(ge=0)]

def _check_name(name: str) -> str:
    if not any(c.isalpha() for c in name):
        raise ValueError('name must have at least one letter')
    return name

def _parse_date(obj: str | datetime) -> datetime:
    if isinstance(obj, str):
        try:  # prefer the standard datetime format
            return datetime.strptime(obj, TIME_FORMAT)
        except ValueError as e:  # attempt to parse string more flexibly
            try:
                dt = parse_date(obj)
                assert dt is not None
                return dt
            except Exception:
                raise e from None
    return obj


Name: TypeAlias = Annotated[str, AfterValidator(_check_name)]
Datetime: TypeAlias = Annotated[
    datetime,
    BeforeValidator(_parse_date),
    PlainSerializer(lambda dt: dt.strftime(TIME_FORMAT), return_type=str)
]
Duration: TypeAlias = Annotated[float, Field(description='duration (days)', ge=0.0)]
Score: TypeAlias = Annotated[float, Field(description='a score (positive number)', ge=0.0)]


##################
# ERROR HANDLING #
##################

class InconsistentTimestampError(KanbanError):
    """Error that occurs if a timestamp is inconsistent."""

class ProjectNotFoundError(KanbanError):
    """Error that occurs when a project ID is not found."""
    def __init__(self, project_id: Id) -> None:
        super().__init__(f'Project with id {project_id!r} not found')

class TaskNotFoundError(KanbanError):
    """Error that occurs when a task ID is not found."""
    def __init__(self, task_id: Id) -> None:
        super().__init__(f'Task with id {task_id!r} not found')

class TaskStatusError(KanbanError):
    """Error that occurs when a task's status is invalid for a certain operation."""


@contextmanager
def catch_key_error(cls: type[Exception]) -> Iterator[None]:
    """Catches a KeyError and rewraps it as an Exception of the given type."""
    try:
        yield
    except KeyError as e:
        raise cls(e.args[0]) from None


#########
# MODEL #
#########

def pretty_value(val: Any) -> str:
    """Gets a pretty representation of a value as a string.
    The representation will depend on its type."""
    if val is None:
        return '-'
    if isinstance(val, float):
        return str(int(val)) if (int(val) == val) else f'{val:.3g}'
    if isinstance(val, datetime):  # human-readable date
        # TODO: make time format configurable
        if (get_current_time() - val >= timedelta(days=7)):
            return val.strftime(DATE_FORMAT)
        return pendulum.instance(val).diff_for_humans()
    return str(val)


class Model(BaseModel):
    """Base class setting up pydantic configs."""
    class Config:  # noqa: D106
        frozen = True

    def _replace(self, **kwargs: Any) -> Self:
        """Creates a new copy of the object with the given kwargs replaced.
        Validation will be performed."""
        d = dict(self)
        for (key, val) in kwargs.items():
            if key not in d:  # do not allow extra fields
                raise TypeError(f'Unknown field {key!r}')
            d[key] = val
        return type(self)(**d)

    def _pretty_dict(self) -> dict[str, str]:
        """Gets a dict from fields to pretty values (as strings)."""
        return {
            **{field: pretty_value(val) for (field, val) in dict(self).items() if val is not None},
            **{field: pretty_value(val) for field in self.model_computed_fields if (val := getattr(self, field)) is not None}
        }


class TaskStatus(StrEnum):
    """Possible status a task can have."""
    todo = 'todo'
    active = 'active'
    paused = 'paused'
    complete = 'complete'

    @property
    def color(self) -> str:
        """Gets a rich color to be associated with the status."""
        if self == TaskStatus.todo:
            return 'bright_black'
        if self == TaskStatus.active:
            return 'bright_red'
        if self == TaskStatus.paused:
            return 'orange3'
        assert self == 'complete'
        return 'green'


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


class Project(Model):
    """A project associated with multiple tasks."""
    name: Name = Field(
        description='Project name'
    )
    description: Optional[str] = Field(
        default=None,
        description='Project description'
    )
    created_time: Datetime = Field(
        default_factory=get_current_time,
        description='Time the project was created'
    )
    links: Optional[set[AnyUrl]] = Field(
        default=None,
        description='Links associated with the project'
    )


class Log(Model):
    """A piece of information associated with a task at a particular time."""
    created_time: Datetime = Field(
        default_factory=get_current_time,
        description='Time the log was created'
    )
    note: Optional[str] = Field(
        default=None,
        description='Textual content of the log'
    )
    rating: Optional[Score] = Field(
        default=None,
        description="Rating of the task's current progress"
    )


class Task(Model):
    """A task to be performed."""
    name: Name = Field(
        description='Task name'
    )
    description: Optional[str] = Field(
        default=None,
        description='Task description'
    )
    priority: Score = Field(
        default=3.0,
        description='Priority of task'
    )
    expected_difficulty: Score = Field(
        default=3.0,
        description='Estimated difficulty of task'
    )
    expected_duration: Optional[Duration] = Field(
        default=None,
        description='Expected number of days to complete task'
    )
    due_date: Optional[Datetime] = Field(
        default=None,
        description='Date the task is due'
    )
    project_id: Optional[Id] = Field(
        default=None,
        description='Project ID'
    )
    tags: Optional[set[str]] = Field(
        default=None,
        description='Tags associated with the task'
    )
    links: Optional[set[AnyUrl]] = Field(
        default=None,
        description='Links associated with the project'
    )
    created_time: Datetime = Field(
        default_factory=get_current_time,
        description='Time the task was created'
    )
    first_started_time: Optional[Datetime] = Field(
        default=None,
        description='Time the task was first started'
    )
    last_started_time: Optional[Datetime] = Field(
        default=None,
        description='Time the task was last started (if not paused)'
    )
    last_paused_time: Optional[Datetime] = Field(
        default=None,
        description='Time the task was last paused'
    )
    completed_time: Optional[Datetime] = Field(
        default=None,
        description='Time the task was completed'
    )
    prior_time_worked: Optional[Duration] = Field(
        default=None,
        description='Total time (in days) the task was worked on prior to last_started_time'
    )
    blocked_by: Optional[set[Id]] = Field(
        default=None,
        description='IDs of other tasks that block the completion of this one'
    )
    logs: Optional[list[Log]] = Field(
        default=None,
        description='List of dated logs related to the task'
    )

    # fields that are reset to None when a Task is reset
    RESET_FIELDS: ClassVar[list[str]] = ['due_date', 'first_started_time', 'last_started_time', 'last_paused_time', 'completed_time', 'completed_time', 'prior_time_worked', 'blocked_by', 'logs']
    DURATION_FIELDS: ClassVar[list[str]] = ['expected_duration', 'prior_time_worked', 'total_time_worked', 'lead_time']

    def _pretty_dict(self) -> dict[str, str]:
        d = super()._pretty_dict()
        for field in self.DURATION_FIELDS:
            # make durations human-readable
            if (field in d):
                val = getattr(self, field)
                if (val is not None):
                    assert isinstance(val, float)
                    d[field] = '-' if (val == 0) else human_readable_duration(val)
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
    def lead_time(self) -> Optional[Duration]:
        """If the task is completed, returns the lead time (in days), which is the elapsed time from started to completed.
        Otherwise, returns None."""
        if self.status == TaskStatus.complete:
            assert self.first_started_time is not None
            assert self.completed_time is not None
            return get_duration_between(self.first_started_time, self.completed_time)
        return None

    @computed_field  # type: ignore[misc]
    @property
    def is_overdue(self) -> bool:
        """Returns True if the task is overdue (i.e. it was not completed before the due date)."""
        if self.due_date is None:
            return False
        eval_date = self.completed_time or get_current_time()
        return eval_date > self.due_date

    @property
    def time_till_due(self) -> Optional[timedelta]:
        """Returns the time interval between the current time and the due date, or None if there is no due date."""
        if self.due_date is None:
            return None
        return self.due_date - get_current_time()

    @property
    def status_icons(self, nearly_due_thresh: Optional[timedelta] = None) -> Optional[str]:
        """Gets one or more icons (emoji) representing the status of the task, or None if there is none.
        If nearly_due_threshold is given, this is the time threshold before the due date within which to show a status warning."""
        nearly_due_thresh = NEARLY_DUE_THRESH if (nearly_due_thresh is None) else nearly_due_thresh
        status = self.status
        td = self.time_till_due
        icons = []
        if (status != TaskStatus.complete) and (td is not None):
            if td < timedelta(0):  # overdue
                icons.append('🚨')
            elif td < nearly_due_thresh:  # due soon
                icons.append('👀')
            else:  # has a future due date
                icons.append('⏱️ ')
        if status == TaskStatus.paused:
            icons.append('⏸️ ')
        return ' '.join(icons) if icons else None

    @model_validator(mode='after')
    def check_consistent_times(self) -> 'Task':  # noqa: C901
        """Checks the consistence of various timestamps stored in the Task.
        If any is invalid, raises an InconsistentTimestampError."""
        def _invalid(msg: str) -> InconsistentTimestampError:
            return InconsistentTimestampError(f'{msg}\n\t{self}')
        if self.first_started_time is not None:
            if self.first_started_time < self.created_time:
                raise _invalid('task start time cannot precede created time')
        if self.last_started_time is not None:
            if self.first_started_time is None:
                raise _invalid('task missing first started time')
            if self.last_started_time < self.first_started_time:
                raise _invalid('task last started time cannot precede first started time')
        if self.last_paused_time is not None:
            if self.first_started_time is None:
                raise _invalid('task missing first started time')
            if self.last_started_time is not None:
                raise _invalid('task cannot have both a last started and last paused time')
            if self.last_paused_time < self.first_started_time:
                raise _invalid('task last paused time cannot precede first started time')
        if self.completed_time is not None:
            if self.first_started_time is None:
                raise _invalid('task missing first started time')
            if self.completed_time < self.first_started_time:
                raise _invalid('task completed time cannot precede first started time')
            if self.last_started_time and (self.completed_time < self.last_started_time):
                raise _invalid('task completed time cannot precede last started time')
        # task is paused or completed => task has prior time worked
        if (self.status == TaskStatus.paused) and (self.prior_time_worked is None):
            raise _invalid('task in paused or completed status must set prior time worked')
        return self

    def started(self, dt: Optional[Datetime] = None) -> 'Task':
        """Returns a new started version of the Task, if its status is todo.
        Otherwise raises a TaskStatusError."""
        if self.status == TaskStatus.todo:
            dt = dt or get_current_time()
            if dt < self.created_time:
                raise TaskStatusError('cannot start a task before its creation time')
            return self.model_copy(update={'first_started_time': dt})
        raise TaskStatusError(f"cannot start task with status '{self.status}'")

    def completed(self, dt: Optional[datetime] = None) -> 'Task':
        """Returns a new completed version of the Task, if its status is active.
        Otherwise raises a TaskStatusError."""
        if self.status == TaskStatus.active:
            dt = dt or get_current_time()
            last_started_time = cast(datetime, self.last_started_time or self.first_started_time)
            if dt < last_started_time:
                raise TaskStatusError('cannot complete a task before its last started time')
            return self.model_copy(update={'completed_time': dt})
        raise TaskStatusError(f"cannot complete task with status '{self.status}'")

    def paused(self, dt: Optional[datetime] = None) -> 'Task':
        """Returns a new paused version of the Task, if its status is active.
        Otherwise raises a TaskStatusError."""
        if self.status == TaskStatus.active:
            dt = dt or get_current_time()
            last_started_time = cast(datetime, self.last_started_time or self.first_started_time)
            if dt < last_started_time:
                raise TaskStatusError('cannot pause a task before its last started time')
            dur = 0.0 if (self.prior_time_worked is None) else self.prior_time_worked
            dur += get_duration_between(last_started_time, dt)
            return self.model_copy(update={'last_started_time': None, 'last_paused_time': dt, 'prior_time_worked': dur})
        raise TaskStatusError(f"cannot pause task with status '{self.status}'")

    def resumed(self, dt: Optional[datetime] = None) -> 'Task':
        """Returns a new resumed version of the Task, if its status is paused.
        Otherwise raises a TaskStatusError."""
        status = self.status
        if status in [TaskStatus.paused, TaskStatus.complete]:
            dt = dt or get_current_time()
            if status == TaskStatus.paused:
                assert self.last_paused_time is not None
                if dt < self.last_paused_time:
                    raise TaskStatusError('cannot resume a task before its last paused time')
                return self.model_copy(update={'last_started_time': dt, 'last_paused_time': None})
            else:  # complete
                assert self.completed_time is not None
                if dt < self.completed_time:
                    raise TaskStatusError('cannot resume a task before its completed time')
                return self.model_copy(update={'last_started_time': dt, 'prior_time_worked': self.total_time_worked, 'completed_time': None})
        raise TaskStatusError(f"cannot resume task with status '{self.status}'")

    def apply_status_action(self, action: TaskStatusAction, dt: Optional[datetime] = None, first_dt: Optional[datetime] = None) -> 'Task':
        """Applies a status action to the Task.
            dt: datetime at which the action occurred (if consisting of two consecutive actions, the latter one)
            first_dt: if the action consists of two consecutive actions, the datetime at which the first action occurred
        If the action is invalid for the Task's current state, raises a TaskStatusError."""
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
        return self.resumed()

    def reset(self) -> 'Task':
        """Resets a task to the 'todo' state, regardless of its current state.
        This will preserve the original creation metadata except for timestamps, due date, blocking tasks, and logs."""
        kwargs = {field: None for field in self.RESET_FIELDS}
        return self._replace(**kwargs)


class Board(Model):
    """A DaiKanban board (collection of projects and tasks)."""
    name: str = Field(description='name of DaiKanban board')
    description: Optional[str] = Field(
        default=None,
        description='description of the DaiKanban board'
    )
    created_time: Optional[Datetime] = Field(
        default_factory=get_current_time,
        description='Time the board was created'
    )
    projects: dict[Id, Project] = Field(
        default_factory=dict,
        description='mapping from IDs to projects'
    )
    tasks: dict[Id, Task] = Field(
        default_factory=dict,
        description='mapping from IDs to tasks'
    )
    version: Literal[0] = Field(
        default=0,
        description='version of the DaiKanban specification',
    )

    def new_project_id(self) -> Id:
        """Gets an available integer as a project ID."""
        return max(self.projects) + 1 if self.projects else 0

    def new_task_id(self) -> Id:
        """Gets an available integer as a task ID."""
        return max(self.tasks) + 1 if self.tasks else 0

    def create_project(self, project: Project) -> Id:
        """Adds a new project and returns its ID."""
        id_ = self.new_project_id()
        self.projects[id_] = project
        return id_

    @catch_key_error(ProjectNotFoundError)
    def get_project(self, project_id: Id) -> Project:
        """Gets a project with the given ID."""
        return self.projects[project_id]

    def update_project(self, project_id: Id, **kwargs: Any) -> None:
        """Updates a project with the given keyword arguments."""
        proj = self.get_project(project_id)
        self.projects[project_id] = proj._replace(**kwargs)

    @catch_key_error(ProjectNotFoundError)
    def delete_project(self, project_id: Id) -> None:
        """Deletes a project with the given ID."""
        del self.projects[project_id]

    def create_task(self, task: Task) -> Id:
        """Adds a new task and returns its ID."""
        id_ = self.new_task_id()
        self.tasks[id_] = task
        return id_

    @catch_key_error(TaskNotFoundError)
    def get_task(self, task_id: Id) -> Task:
        """Gets a task with the given ID."""
        return self.tasks[task_id]

    def update_task(self, task_id: Id, **kwargs: Any) -> None:
        """Updates a task with the given keyword arguments."""
        task = self.get_task(task_id)
        self.tasks[task_id] = task._replace(**kwargs)

    @catch_key_error(TaskNotFoundError)
    def delete_task(self, task_id: Id) -> None:
        """Deletes a task with the given ID."""
        del self.tasks[task_id]

    @catch_key_error(TaskNotFoundError)
    def reset_task(self, task_id: Id) -> None:
        """Resets a task with the given ID to the 'todo' state, regardless of its current state.
        This will preserve the original creation metadata except for timestamps, due date, blocking tasks, and logs."""
        task = self.get_task(task_id)
        self.tasks[task_id] = task.reset()

    @catch_key_error(TaskNotFoundError)
    def add_blocking_task(self, blocking_task_id: Id, blocked_task_id: Id) -> None:
        """Adds a task ID to the list of blocking tasks for another."""
        _ = self.get_task(blocking_task_id)  # ensure blocking task exists
        blocked_task = self.get_task(blocked_task_id)
        blocked_by = set(blocked_task.blocked_by) if blocked_task.blocked_by else set()
        blocked_by.add(blocking_task_id)
        self.tasks[blocked_task_id] = blocked_task.model_copy(update={'blocked_by': blocked_by})

    @property
    def num_tasks_by_project(self) -> Counter[Id]:
        """Gets a map from project IDs to the number of tasks associated with it."""
        return Counter(task.project_id for task in self.tasks.values() if task.project_id is not None)
