from abc import ABC, abstractmethod
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, model_serializer
from typing_extensions import override

from daikanban.model import Duration, Task


class TaskScorer(ABC, BaseModel):
    """Interface for a class which scores tasks.
    Higher scores represent tasks more deserving of work."""

    name: ClassVar[str]  # name of the scorer
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
    units = 'pri'

    @override
    def __call__(self, task: Task) -> float:
        return task.priority


class PriorityDifficultyScorer(TaskScorer):
    """Scores tasks by multiplying priority by difficulty."""

    name = 'priority-difficulty'
    units = 'pri-diff'

    @override
    def __call__(self, task: Task) -> float:
        return task.priority * task.expected_difficulty


class PriorityRate(TaskScorer):
    """Scores tasks by dividing priority by the expected duration of the task."""

    name = 'priority-rate'
    units = 'pri/day'

    default_duration: Duration = 4.0

    @override
    def __call__(self, task: Task) -> float:
        duration = self.default_duration if (task.expected_duration is None) else task.expected_duration
        return task.priority / duration
