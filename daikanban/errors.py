"""Module defining custom error types."""

from collections.abc import Iterator
from contextlib import contextmanager
import uuid

from pydantic import UUID4


class KanbanError(ValueError):
    """Custom error type for Kanban errors."""

class UserInputError(KanbanError):
    """Class for user input errors."""

class InconsistentTimestampError(KanbanError):
    """Error that occurs if a timestamp is inconsistent."""

class TaskStatusError(KanbanError):
    """Error that occurs when a task's status is invalid for a certain operation."""

class InvalidTaskStatusError(UserInputError):
    """Error type for when the user provides an invalid task status."""
    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(f'Invalid task status {status!r}')

class ProjectNotFoundError(KanbanError):
    """Error that occurs when a project ID is not found."""
    def __init__(self, project_id: int | UUID4) -> None:
        if isinstance(project_id, uuid.UUID):
            field = 'uuid'
            val: str | int = str(project_id)
        else:
            field, val = 'id', project_id
        super().__init__(f'Project with {field} {val!r} not found')

class TaskNotFoundError(KanbanError):
    """Error that occurs when a task ID is not found."""
    def __init__(self, task_id: int | UUID4) -> None:
        if isinstance(task_id, uuid.UUID):
            field = 'uuid'
            val: str | int = str(task_id)
        else:
            field, val = 'id', task_id
        super().__init__(f'Task with {field} {val!r} not found')

class DuplicateProjectError(KanbanError):
    """Error that occurs when a duplicate project is added (same UUID)."""

class DuplicateTaskError(KanbanError):
    """Error that occurs when a duplicate task is added (same UUID)."""

class AmbiguousProjectNameError(KanbanError):
    """Error that occurs when a provided project name matches multiple names."""

class AmbiguousTaskNameError(KanbanError):
    """Error that occurs when provided task name matches multiple names."""

class UUIDError(KanbanError):
    """Error related to UUIDs."""

class UUIDImmutableError(UUIDError):
    """Error that occurs when trying to modify a UUID."""

class VersionMismatchError(KanbanError):
    """Error occurring when there is a version mismatch between two boards."""

class BoardFileError(KanbanError):
    """Error reading or writing a board file."""

class BoardNotLoadedError(KanbanError):
    """Error type for when a board has not yet been loaded."""


@contextmanager
def catch_key_error(cls: type[Exception]) -> Iterator[None]:
    """Catches a KeyError and rewraps it as an Exception of the given type."""
    try:
        yield
    except KeyError as e:
        raise cls(e.args[0]) from None
