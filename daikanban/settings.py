from typing import Optional

from pydantic import Field

from daikanban.model import Model, TaskStatus
from daikanban.score import PriorityRate, TaskScorer


DEFAULT_STATUS_GROUPS = {
    'todo': [TaskStatus.todo],
    'active': [TaskStatus.active, TaskStatus.paused],
    'complete': [TaskStatus.complete]
}


class BoardSettings(Model):
    """Settings for a DaiKanban board."""
    limit: Optional[int] = Field(
        default=None,
        description='max number of tasks to display',
        ge=0
    )
    status_groups: dict[str, list[str]] = Field(
        default=DEFAULT_STATUS_GROUPS,
        description='map from board columns (groups) to task statuses'
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
