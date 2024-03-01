import base64
from collections.abc import Collection
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal, Optional, TypeAlias, TypeVar
from uuid import uuid4

from pydantic import AnyUrl, PlainSerializer, RootModel, computed_field, model_validator
from pydantic.dataclasses import Field, dataclass


T = TypeVar('T')

Id: TypeAlias = Annotated[str, Field(min_length=12, max_length=12)]
TaskStatus = Literal['pending', 'active', 'paused', 'complete']
Datetime = Annotated[datetime, PlainSerializer(lambda dt: dt.isoformat()[:19], return_type=str)]


def _get_random_id() -> Id:
    """Generates a random 12-long base64 ID string."""
    return base64.b64encode(uuid4().bytes)[:12].decode()

def get_new_id(current_ids: Collection[Id]) -> Id:
    """Generates a new random ID string not in the set of current_ids."""
    while ((id_ := _get_random_id()) in current_ids):
        pass
    return id_


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


class JSONModel:
    """Base class for Pydantic dataclasses that can serialize themselves to JSON."""

    def _as_root_model(self: T) -> RootModel[T]:
        """Gets this object as a RootModel instance."""
        return RootModel[type(self)](self)  # type: ignore

    def to_dict(self, **kwargs: Any) -> dict[str, Any]:
        """Converts an object to a dict via pydantic RootModel."""
        return self._as_root_model().model_dump(**kwargs)  # type: ignore

    def to_json_string(self, **kwargs: Any) -> str:
        """Converts an object to a JSON string via pydantic RootModel."""
        return self._as_root_model().model_dump_json(**kwargs)


@dataclass(frozen=True)
class Project(JSONModel):
    """A project associated with multiple tasks."""
    name: str = Field(
        description='Project name'
    )
    description: Optional[str] = Field(
        default=None,
        description='Project description'
    )
    created_time: Datetime = Field(
        description='Time the project was created',
        default_factory=datetime.now
    )
    links: Optional[set[AnyUrl]] = Field(
        default=None,
        description='Links associated with the project'
    )


@dataclass(frozen=True)
class Task(JSONModel):
    """A task to be performed."""
    name: str = Field(
        description='Task name'
    )
    details: Optional[str] = Field(
        default=None,
        description='More detailed description of the task'
    )
    priority: float = Field(
        default=3.0,
        description='Priority of task on a 0-10 scale',
        ge=0.0,
        le=10.0
    )
    expected_complexity: float = Field(
        default=3.0,
        description='Estimated complexity of task on a 0-10 scale',
        ge=0.0,
        le=10.0
    )
    expected_duration: Optional[float] = Field(
        default=None,
        description='Expected number of days to complete task',
        ge=0.0
    )
    project_id: Optional[Id] = Field(
        default=None,
        description='Project ID'
    )
    created_time: Datetime = Field(
        description='Time the task was created',
        default_factory=datetime.now
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
    prior_time_worked: Optional[timedelta] = Field(
        default=None,
        description='Total time the task was worked on prior to last_started_time'
    )
    tags: Optional[set[str]] = Field(
        default=None,
        description='Tags associated with the task'
    )
    links: Optional[set[AnyUrl]] = Field(
        default=None,
        description='Links associated with the project'
    )

    @computed_field  # type: ignore
    @property
    def status(self) -> TaskStatus:
        """Gets the current status of the task."""
        if self.first_started_time is None:
            return 'pending'
        if (self.last_started_time is not None) and (self.completed_time is None):
            return 'active'
        if self.last_started_time is None:
            return 'paused'
        if self.completed_time is None:
            return 'active'
        return 'complete'

    @computed_field  # type: ignore
    @property
    def total_time_worked(self) -> timedelta:
        """Gets the total time worked on the task."""
        td = timedelta(0) if (self.prior_time_worked is None) else self.prior_time_worked
        if self.last_started_time is not None:
            td += datetime.now() - self.last_started_time
        return td

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
        if self.status in ['paused', 'completed']:
            assert self.prior_time_worked is not None
        return self

    def started(self) -> 'Task':
        """Returns a new started version of the Task, if its status is pending.
        Otherwise raises a TaskStatusError."""
        if self.status == 'pending':
            now = datetime.now()
            return replace(self, first_started_time=now, last_started_time=now)  # type: ignore
        raise TaskStatusError(f'cannot start Task with status {self.status!r}')

    def completed(self) -> 'Task':
        """Returns a new completed version of the Task, if its status is active.
        Otherwise raises a TaskStatusError."""
        if self.status == 'active':
            return replace(self, completed_time=datetime.now())  # type: ignore
        raise TaskStatusError(f'cannot complete Task with status {self.status!r}')

    def paused(self) -> 'Task':
        """Returns a new paused version of the Task, if its status is active.
        Otherwise raises a TaskStatusError."""
        if self.status == 'active':
            return replace(self, last_started_time=None, prior_time_worked=self.total_time_worked)  # type: ignore
        raise TaskStatusError(f'cannot pause Task with status {self.status!r}')

    def restarted(self) -> 'Task':
        """Returns a new restarted version of the Task, if its status is paused.
        Otherwise raises a TaskStatusError."""
        if self.status == 'paused':
            return replace(self, last_started_time=datetime.now())  # type: ignore
        raise TaskStatusError(f'cannot restart Task with status {self.status!r}')


@dataclass(frozen=True)
class DaiKanban(JSONModel):
    """A database of projects and tasks."""
    projects: dict[Id, Project]
    tasks: dict[Id, Task]
    version: Literal[0] = Field(
        default=0,
        description='version of the DaiKanban specification',
    )

    def create_project(self, project: Project) -> Id:
        """Adds a new project and returns its ID."""
        id_ = get_new_id(self.projects)
        self.projects[id_] = project
        return id_

    def get_project(self, project_id: Id) -> Project:
        """Gets a project with the given ID."""
        try:
            return self.projects[project_id]
        except KeyError:
            raise ProjectNotFoundError(project_id) from None

    def update_project(self, project_id: Id, **kwargs: Any) -> None:
        """Updates a project with the given keyword arguments."""
        proj = self.get_project(project_id)
        self.projects[project_id] = replace(proj, **kwargs)  # type: ignore

    def delete_project(self, project_id: Id) -> None:
        """Deletes a project with the given ID."""
        try:
            del self.projects[project_id]
        except KeyError:
            raise ProjectNotFoundError(project_id) from None

    def create_task(self, task: Task) -> Id:
        """Adds a new task and returns its ID."""
        id_ = get_new_id(self.tasks)
        self.tasks[id_] = task
        return id_

    def get_task(self, task_id: Id) -> Task:
        """Gets a task with the given ID."""
        try:
            return self.tasks[task_id]
        except KeyError:
            raise TaskNotFoundError(task_id) from None

    def update_task(self, task_id: Id, **kwargs: Any) -> None:
        """Updates a task with the given keyword arguments."""
        task = self.get_task(task_id)
        self.tasks[task_id] = replace(task, **kwargs)  # type: ignore

    def delete_task(self, task_id: Id) -> None:
        """Deletes a task with the given ID."""
        try:
            del self.tasks[task_id]
        except KeyError:
            raise TaskNotFoundError(task_id) from None
