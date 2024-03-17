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

    default_priority: float = 1.0  # default priority if none is provided

    @override
    def __call__(self, task: Task) -> float:
        return self.default_priority if (task.priority is None) else task.priority


class PriorityDifficultyScorer(TaskScorer):
    """Scores tasks by multiplying priority by difficulty."""

    name = 'priority-difficulty'
    description = 'priority times difficulty'
    units = 'pri-diff'

    default_priority: float = 1.0  # default priority if none is provided
    default_difficulty: float = 1.0  # default difficulty if none is provided

    @override
    def __call__(self, task: Task) -> float:
        priority = self.default_priority if (task.priority is None) else task.priority
        difficulty = self.default_difficulty if (task.expected_difficulty is None) else task.expected_difficulty
        return priority * difficulty


class PriorityRateScorer(TaskScorer):
    """Scores tasks by dividing priority by the expected duration of the task."""

    name = 'priority-rate'
    description = 'priority divided by expected duration'
    units = 'pri/day'

    default_priority: float = 1.0  # default priority if none is provided
    default_duration: float = 4.0  # default duration (in days) if none is provided

    @override
    def __call__(self, task: Task) -> float:
        priority = self.default_priority if (task.priority is None) else task.priority
        duration = self.default_duration if (task.expected_duration is None) else task.expected_duration
        return priority / duration


# registry of available TaskScorers, keyed by name
_TASK_SCORER_CLASSES: list[type[TaskScorer]] = [PriorityScorer, PriorityDifficultyScorer, PriorityRateScorer]
TASK_SCORERS = {cls.name: cls() for cls in _TASK_SCORER_CLASSES}
