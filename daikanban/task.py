from __future__ import annotations  # avoid import cycle with type-checking

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, ClassVar, Optional

from fancy_dataclass import DictDataclass, TOMLDataclass
from pydantic import Field, field_validator
import pydantic.dataclasses
from typing_extensions import Doc, override

from daikanban.utils import StrEnum


if TYPE_CHECKING:
    from daikanban.model import Task


##########
# STATUS #
##########

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


# which Task fields to query when creating a new task
# (excluded fields will be set to their defaults)
DEFAULT_NEW_TASK_FIELDS = ['name', 'description', 'project_id', 'priority', 'expected_duration', 'due_time', 'tags', 'links']
DEFAULT_TASK_SCORER_NAME = 'priority-rate'


###########
# SCORING #
###########

@dataclass
class TaskScorer(ABC, DictDataclass, suppress_defaults=False):
    """Interface for a class which scores tasks.
    Higher scores represent tasks more deserving of work."""

    name: ClassVar[
        Annotated[str, Doc('name of scorer')]
    ] = field(metadata={'suppress': False})
    description: ClassVar[
        Annotated[Optional[str], Doc('description of scorer')]
    ] = field(default=None, metadata={'suppress': False})
    units: ClassVar[
        Annotated[Optional[str], Doc('unit of measurement for scorer')]
    ] = field(default=None, metadata={'suppress': False})

    @abstractmethod
    def __call__(self, task: Task) -> float:
        """Override this to implement task scoring."""


@dataclass
class PriorityScorer(TaskScorer):
    """Scores tasks by their priority only."""

    name = 'priority'
    description = 'priority only'
    units = 'pri'

    default_priority: float = 1.0  # default priority if none is provided

    @override
    def __call__(self, task: Task) -> float:
        return self.default_priority if (task.priority is None) else task.priority


@dataclass
class PriorityDifficultyScorer(TaskScorer):
    """Scores tasks by multiplying priority by difficulty."""

    name = 'priority-difficulty'
    description = 'priority divided by difficulty'
    units = 'pri/diff'

    default_priority: float = 1.0  # default priority if none is provided
    default_difficulty: float = 1.0  # default difficulty if none is provided

    @override
    def __call__(self, task: Task) -> float:
        priority = self.default_priority if (task.priority is None) else task.priority
        difficulty = self.default_difficulty if (task.expected_difficulty is None) else task.expected_difficulty
        return priority / difficulty


@dataclass
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


@pydantic.dataclasses.dataclass
class TaskConfig(TOMLDataclass):
    """Task configurations."""
    new_task_fields: Annotated[
        list[str],
        Doc('which fields to prompt for when creating a new task')
    ] = Field(default_factory=lambda: DEFAULT_NEW_TASK_FIELDS)
    scorer_name: Annotated[
        str,
        Doc('name of method used for scoring & sorting tasks')
    ] = Field(default=DEFAULT_TASK_SCORER_NAME)

    @field_validator('scorer_name')
    @classmethod
    def check_scorer(cls, scorer_name: str) -> str:
        """Checks that the scorer name is valid."""
        if scorer_name not in TASK_SCORERS:
            raise ValueError(f'Unknown task scorer {scorer_name!r}')
        return scorer_name

    @property
    def scorer(self) -> TaskScorer:
        """Gets the TaskScorer object used to score tasks."""
        return TASK_SCORERS[self.scorer_name]
