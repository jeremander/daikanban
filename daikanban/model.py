from contextlib import contextmanager
from datetime import datetime
from typing import Annotated, Any, Counter, Iterator, Literal, Optional, TypeVar

from pydantic import AfterValidator, AnyUrl, BaseModel, BeforeValidator, Field, PlainSerializer, computed_field, model_validator

from daikanban.utils import TIME_FORMAT, StrEnum, get_current_time, get_duration_between


T = TypeVar('T')


################
# TYPE ALIASES #
################

Id = Annotated[int, Field(ge=0)]

def _check_name(name: str) -> str:
    if not any(c.isalpha() for c in name):
        raise ValueError('name must have at least one letter')
    return name

Name = Annotated[str, AfterValidator(_check_name)]
Datetime = Annotated[
    datetime,
    BeforeValidator(lambda s: datetime.strptime(s, TIME_FORMAT)),
    PlainSerializer(lambda dt: dt.strftime(TIME_FORMAT), return_type=str)
]
Duration = Annotated[float, Field(description='duration (days)', ge=0.0)]
Score = Annotated[float, Field(description='a score (positive number)', ge=0.0)]


##################
# ERROR HANDLING #
##################

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


class Model(BaseModel):
    """Base class setting up pydantic configs."""
    class Config:  # noqa: D106
        frozen = True


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
    def check_consistent_times(self) -> 'Task':  # noqa: C901
        """Checks that created_time <= first_started_time <= last_started_time <= completed_time."""
        def _invalid(msg: str) -> ValueError:
            return ValueError(f'{msg}\n\t{self}')
        if self.first_started_time is not None:
            if self.first_started_time < self.created_time:
                raise _invalid('task start time cannot precede created time')
        if self.last_started_time is not None:
            if self.first_started_time is None:
                raise _invalid('task missing first started time')
            if self.last_started_time < self.first_started_time:
                raise _invalid('task last started time cannot precede first started time')
        if self.completed_time is not None:
            if self.last_started_time is None:
                raise _invalid('task missing last started time')
            if self.completed_time < self.last_started_time:
                raise _invalid('task completed time cannot precede last started time')
        # task is paused or completed => task has prior time worked
        if (self.status == TaskStatus.paused) and (self.prior_time_worked is None):
            raise _invalid('task in paused or completed status must set prior time worked')
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
