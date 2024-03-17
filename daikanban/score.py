from __future__ import annotations  # avoid import cycle with type-checking

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Optional

from pydantic import BaseModel, model_serializer
from typing_extensions import override


if TYPE_CHECKING:
    from daikanban.model import Task


class TaskScorer(ABC, BaseModel):
    """Interface for a class which scores tasks.
    Higher scores represent tasks more deserving of work."""

    name: ClassVar[str]  # name of the scorer
    description: ClassVar[Optional[str]] = None  # description of scorer
    units: ClassVar[Optional[str]] = None  # unit of measurement for the scorer

    @abstractmethod
    def __call__(self, task: Task) -> float:
        """Override this to implement task scoring."""

    @model_serializer
    def serialize(self) -> dict[str, Any]:
        """Serializes the model, including the class variables."""
        return {'name': self.name, 'units': self.units, **BaseModel.model_dump(self)}


class PriorityScorer(TaskScorer):
    """Scores tasks by their priority only."""

    name = 'priority'
    description = None
    units = 'pri'

    @override
    def __call__(self, task: Task) -> float:
        return task.priority


class PriorityDifficultyScorer(TaskScorer):
    """Scores tasks by multiplying priority by difficulty."""

    name = 'priority-difficulty'
    description = 'priority times difficulty'
    units = 'pri-diff'

    @override
    def __call__(self, task: Task) -> float:
        return task.priority * task.expected_difficulty


class PriorityRate(TaskScorer):
    """Scores tasks by dividing priority by the expected duration of the task."""

    name = 'priority-rate'
    description = 'priority divided by expected duration'
    units = 'pri/day'

    default_duration: float = 4.0  # default duration (in days) if none is provided

    @override
    def __call__(self, task: Task) -> float:
        duration = self.default_duration if (task.expected_duration is None) else task.expected_duration
        return task.priority / duration


# registry of available TaskScorers, keyed by name
_TASK_SCORER_CLASSES: list[type[TaskScorer]] = [PriorityScorer, PriorityDifficultyScorer, PriorityRate]
TASK_SCORERS = {cls.name: cls() for cls in _TASK_SCORER_CLASSES}
