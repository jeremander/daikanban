import base64
from collections.abc import Collection
from dataclasses import replace
from datetime import datetime
from typing import Annotated, Any, Literal, Optional, TypeAlias
from uuid import uuid4

from pydantic import computed_field, model_validator
from pydantic.dataclasses import Field, dataclass


Id: TypeAlias = Annotated[str, Field(min_length=12, max_length=12)]
TaskStatus = Literal['pending', 'started', 'complete']

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


@dataclass
class Project:
    """A project associated with multiple tasks."""
    name: str = Field(
        description='Project name'
    )
    description: Optional[str] = Field(
        default=None,
        description='Project description'
    )
    created_time: datetime = Field(
        description='Time the project was created',
        default_factory=datetime.now
    )


@dataclass
class Task:
    """A task to be performed."""
    priority: float = Field(
        description='Priority of task on a 0-10 scale',
        ge=0.0,
        le=10.0
    )
    expected_complexity: float = Field(
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
    tags: Optional[list[str]] = Field(
        default=None,
        description='Tags associated with the task'
    )
    created_time: datetime = Field(
        description='Time the task was created',
        default_factory=datetime.now
    )
    started_time: Optional[datetime] = Field(
        default=None,
        description='Time the task was started'
    )
    finished_time: Optional[datetime] = Field(
        default=None,
        description='Time the task was finished'
    )

    @model_validator(mode='after')
    def check_consistent_times(self) -> 'Task':
        """Checks that created_time <= started_time <= finished_time."""
        if self.started_time is not None:
            assert self.started_time >= self.created_time
        if self.finished_time is not None:
            assert self.started_time is not None
            assert self.finished_time >= self.started_time
        return self

    @computed_field  # type: ignore
    @property
    def status(self) -> TaskStatus:
        """Gets the current status of the task."""
        if self.started_time is None:
            return 'pending'
        if self.finished_time is None:
            return 'started'
        return 'complete'


@dataclass
class Kanban:
    """A database of projects and tasks."""
    projects: dict[Id, Project]
    tasks: dict[Id, Task]

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
