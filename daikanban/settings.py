from typing import Optional

from pydantic import Field

from daikanban.model import Model, TaskStatus
from daikanban.score import PriorityRate, TaskScorer


class BoardSettings(Model):
    """Settings for a DaiKanban board."""
    limit: Optional[int] = Field(
        default=None,
        description='max number of tasks to display',
        ge=0
    )
    statuses: set[TaskStatus] = Field(
        default_factory=lambda: {TaskStatus.todo, TaskStatus.active, TaskStatus.complete},
        description='set of task statuses to display'
    )
    json_indent: Optional[int] = Field(
        default=2,
        description='indentation level for displaying JSON'
    )
    task_scorer: TaskScorer = Field(
        description='method used for scoring & sorting tasks',
        default_factory=PriorityRate
    )


DEFAULT_BOARD_SETTINGS = BoardSettings()
