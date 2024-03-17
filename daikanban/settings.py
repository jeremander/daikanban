from typing import Optional

from pydantic import BaseModel, Field, field_validator

from daikanban.score import TASK_SCORERS, TaskScorer
from daikanban.utils import StrEnum


DEFAULT_DATE_FORMAT = '%m/%d/%y'  # USA-based format
DEFAULT_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ%z'

DEFAULT_HOURS_PER_WORK_DAY = 8
DEFAULT_DAYS_PER_WORK_WEEK = 5


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


# columns of DaiKanban board, and which task statuses are included
DEFAULT_STATUS_GROUPS = {
    'todo': [TaskStatus.todo],
    'active': [TaskStatus.active, TaskStatus.paused],
    'complete': [TaskStatus.complete]
}

# which Task fields to query when creating a new task
# (excluded fields will be set to their defaults)
DEFAULT_NEW_TASK_FIELDS = ['name', 'description', 'priority', 'expected_duration', 'due_date', 'tags']
DEFAULT_TASK_SCORER_NAME = 'priority-rate'


class TimeSettings(BaseModel):
    """Time settings."""
    date_format: str = Field(
        default=DEFAULT_DATE_FORMAT,
        description='preferred format for representing dates'
    )
    datetime_format: str = Field(
        default=DEFAULT_DATETIME_FORMAT,
        description='preferred format for representing datetimes'
    )
    hours_per_work_day: float = Field(
        default=DEFAULT_HOURS_PER_WORK_DAY,
        description='number of hours per work day'
    )
    days_per_work_week: float = Field(
        default=DEFAULT_DAYS_PER_WORK_WEEK,
        description='number of days per work week'
    )


class FileSettings(BaseModel):
    """File settings."""
    json_indent: Optional[int] = Field(
        default=2,
        description='indentation level for formatting JSON'
    )


class TaskSettings(BaseModel):
    """Task settings."""
    new_task_fields: list[str] = Field(
        default_factory=lambda: DEFAULT_NEW_TASK_FIELDS,
        description='which fields to prompt for when creating a new task'
    )
    scorer_name: str = Field(
        default=DEFAULT_TASK_SCORER_NAME,
        description='name of method used for scoring & sorting tasks'
    )

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


class DisplaySettings(BaseModel):
    """Display settings."""
    limit: Optional[int] = Field(
        default=None,
        description='max number of tasks to display',
        ge=0
    )
    status_groups: dict[str, list[str]] = Field(
        default=DEFAULT_STATUS_GROUPS,
        description='map from board columns (groups) to task statuses'
    )


class Settings(BaseModel):
    """Collection of global settings."""
    time: TimeSettings = Field(default_factory=TimeSettings, description='time settings')
    file: FileSettings = Field(default_factory=FileSettings, description='file settings')
    task: TaskSettings = Field(default_factory=TaskSettings, description='task settings')
    display: DisplaySettings = Field(default_factory=DisplaySettings, description='display settings')

    @classmethod
    def global_settings(cls) -> 'Settings':
        """Gets the global settings object."""
        global SETTINGS
        return SETTINGS

    def update_global_settings(self) -> None:
        """Updates the global settings object."""
        global SETTINGS
        SETTINGS = self


# global object that may be updated by user's configuration file
SETTINGS = Settings()
