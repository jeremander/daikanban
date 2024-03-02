from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, ClassVar, Iterator, Literal, Optional, TypeAlias, TypeVar

from pydantic import AnyUrl, BaseModel, BeforeValidator, Field, PlainSerializer, computed_field, model_validator

from daikanban.utils import get_current_time, get_duration_between


T = TypeVar('T')

TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ%z'
SECS_PER_DAY = 3600 * 24


################
# TYPE ALIASES #
################

Id: TypeAlias = Annotated[int, Field(ge=0)]
Datetime: TypeAlias = Annotated[
    datetime,
    BeforeValidator(lambda s: datetime.strptime(s, TIME_FORMAT)),
    PlainSerializer(lambda dt: dt.strftime(TIME_FORMAT), return_type=str)
]
# duration (in days)
Duration: TypeAlias = Annotated[float, Field(ge=0.0)]
# a score between 0 and 10
Score: TypeAlias = Annotated[float, Field(ge=0.0, le=10.0)]


###############
# ERROR HANDLING #
###############

class KanbanError(ValueError):
    """Custom error type for Kanban errors."""

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

class TaskStatus(str, Enum):
    """Possible status a task can have."""
    todo = 'todo'
    active = 'active'
    paused = 'paused'
    complete = 'complete'


class Model(BaseModel):
    """Base class setting up pydantic configs."""
    class Config:  # noqa: D106
        frozen = True


class Project(Model):
    """A project associated with multiple tasks."""
    name: str = Field(
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
    name: str = Field(
        description='Task name'
    )
    details: Optional[str] = Field(
        default=None,
        description='More detailed description of the task'
    )
    priority: Score = Field(
        default=3.0,
        description='Priority of task on a 0-10 scale'
    )
    expected_difficulty: Score = Field(
        default=3.0,
        description='Estimated difficulty of task on a 0-10 scale'
    )
    expected_duration: Optional[float] = Field(
        default=None,
        description='Expected number of days to complete task',
        ge=0.0
    )
    due_date: Optional[Datetime] = Field(
        default=None,
        description='Date the task is due'
    )
    project_id: Optional[Id] = Field(
        default=None,
        description='Project ID'
    )
    created_time: Datetime = Field(
        description='Time the task was created',
        default_factory=get_current_time
    )
    first_started_time: Optional[Datetime] = Field(
        default=None,
        description='Time the task was first started'
    )
    last_started_time: Optional[Datetime] = Field(
        default=None,
        description='Time the task was last started (if not paused)'
    )
    completed_time: Optional[Datetime] = Field(
        default=None,
        description='Time the task was completed'
    )
    prior_time_worked: Optional[Duration] = Field(
        default=None,
        description='Total time (in days) the task was worked on prior to last_started_time'
    )
    tags: Optional[set[str]] = Field(
        default=None,
        description='Tags associated with the task'
    )
    links: Optional[set[AnyUrl]] = Field(
        default=None,
        description='Links associated with the project'
    )
    blocked_by: Optional[set[Id]] = Field(
        default=None,
        description='IDs of other tasks that block the completion of this one'
    )
    logs: list[Log] = Field(
        default_factory=list,
        description='List of dated logs related to the task'
    )

    @computed_field  # type: ignore[misc]
    @property
    def status(self) -> TaskStatus:
        """Gets the current status of the task."""
        if self.first_started_time is None:
            return TaskStatus.todo
        if (self.last_started_time is not None) and (self.completed_time is None):
            return TaskStatus.active
        if self.last_started_time is None:
            return TaskStatus.paused
        if self.completed_time is None:
            return TaskStatus.active
        return TaskStatus.complete

    @computed_field  # type: ignore[misc]
    @property
    def total_time_worked(self) -> Duration:
        """Gets the total time (in days) worked on the task."""
        dur = 0.0 if (self.prior_time_worked is None) else self.prior_time_worked
        if self.last_started_time is not None:
            dur += get_duration_between(self.last_started_time, get_current_time())
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

    @model_validator(mode='after')
    def check_consistent_times(self) -> 'Task':
        """Checks that created_time <= first_started_time <= last_started_time <= completed_time."""
        if self.first_started_time is not None:
            assert self.first_started_time >= self.created_time
        if self.last_started_time is not None:
            assert self.first_started_time is not None
            assert self.last_started_time >= self.first_started_time
        if self.completed_time is not None:
            assert self.last_started_time is not None
            assert self.completed_time >= self.last_started_time
        # task is paused or completed => task has prior time worked
        if self.status in [TaskStatus.paused, TaskStatus.complete]:
            assert self.prior_time_worked is not None
        return self

    def started(self) -> 'Task':
        """Returns a new started version of the Task, if its status is todo.
        Otherwise raises a TaskStatusError."""
        if self.status == TaskStatus.todo:
            now = get_current_time()
            update = {'first_started_time': now, 'last_started_time': now}
            return self.model_copy(update=update)
        raise TaskStatusError(f'cannot start Task with status {self.status!r}')

    def completed(self) -> 'Task':
        """Returns a new completed version of the Task, if its status is active.
        Otherwise raises a TaskStatusError."""
        if self.status == TaskStatus.active:
            return self.model_copy(update={'completed_time': get_current_time()})
        raise TaskStatusError(f'cannot complete Task with status {self.status!r}')

    def paused(self) -> 'Task':
        """Returns a new paused version of the Task, if its status is active.
        Otherwise raises a TaskStatusError."""
        if self.status == TaskStatus.active:
            return self.model_copy(update={'last_started_time': None, 'prior_time_worked': self.total_time_worked})
        raise TaskStatusError(f'cannot pause Task with status {self.status!r}')

    def restarted(self) -> 'Task':
        """Returns a new restarted version of the Task, if its status is paused.
        Otherwise raises a TaskStatusError."""
        if self.status == TaskStatus.paused:
            return self.model_copy(update={'last_started_time': get_current_time()})
        raise TaskStatusError(f'cannot restart Task with status {self.status!r}')


class DaiKanban(Model):
    """A database of projects and tasks."""
    name: str = Field(description='name of DaiKanban board')
    description: Optional[str] = Field(
        default=None,
        description='description of the DaiKanban board'
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
        self.projects[project_id] = proj.model_copy(update=kwargs)

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
        self.tasks[task_id] = task.model_copy(update=kwargs)

    @catch_key_error(TaskNotFoundError)
    def delete_task(self, task_id: Id) -> None:
        """Deletes a task with the given ID."""
        del self.tasks[task_id]

    @catch_key_error(TaskNotFoundError)
    def add_blocking_task(self, blocking_task_id: Id, blocked_task_id: Id) -> None:
        """Adds a task ID to the list of blacking tasks for another."""
        _ = self.get_task(blocking_task_id)  # ensure blocking task exists
        blocked_task = self.get_task(blocked_task_id)
        blocked_by = set(blocked_task.blocked_by) if blocked_task.blocked_by else set()
        blocked_by.add(blocking_task_id)
        self.tasks[blocked_task_id] = blocked_task.model_copy(update={'blocked_by': blocked_by})


class TaskScorer(ABC):
    """Interface for a class which scores tasks.
    Higher scores represent tasks more deserving of work."""

    name: ClassVar[str]  # name of the scorer
    units: ClassVar[Optional[str]] = None  # unit of measurement for the scorer

    @abstractmethod
    def __call__(self, task: Task) -> float:
        """Override this to implement task scoring."""
