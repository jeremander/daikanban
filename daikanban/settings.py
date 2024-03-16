from typing import Optional

from pydantic import Field

from daikanban.model import Model, TaskStatus
from daikanban.score import PriorityRate, TaskScorer


# columns of DaiKanban board, and which task statuses are included
DEFAULT_STATUS_GROUPS = {
    'todo': [TaskStatus.todo],
    'active': [TaskStatus.active, TaskStatus.paused],
    'complete': [TaskStatus.complete]
}

# which Task fields to query when creating a new task
# (excluded fields will be set to their defaults)
DEFAULT_NEW_TASK_FIELDS = ['name', 'description', 'priority', 'expected_duration', 'due_date', 'tags']


class TaskSettings(Model):
    """Task settings."""
    new_task_fields: list[str] = Field(
        default_factory=lambda: DEFAULT_NEW_TASK_FIELDS,
        description='which fields to prompt for when creating a new task'
    )
    scorer: TaskScorer = Field(
        default_factory=PriorityRate,
        description='method used for scoring & sorting tasks'
    )


class BoardSettings(Model):
    """Overall board settings."""
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
    task: TaskSettings = Field(
        default_factory=TaskSettings,
        description='task settings'
    )


DEFAULT_BOARD_SETTINGS = BoardSettings()
