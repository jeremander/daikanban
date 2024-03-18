from contextlib import contextmanager
from datetime import date, datetime, timedelta
import re
from typing import Any, Callable, Iterator, Optional

import pendulum
from pydantic import BaseModel, Field, field_validator
import pytimeparse

from daikanban.score import TASK_SCORERS, TaskScorer
from daikanban.utils import HOURS_PER_DAY, SECS_PER_DAY, NameMatcher, StrEnum, UserInputError, case_insensitive_match, convert_number_words_to_digits, get_current_time, whitespace_insensitive_match


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
        description='number of hours per work day',
        gt=0,
        le=24
    )
    days_per_work_week: float = Field(
        default=DEFAULT_DAYS_PER_WORK_WEEK,
        description='number of days per work week',
        gt=0,
        le=7
    )

    def parse_datetime(self, s: str) -> datetime:  # noqa: C901
        """Parses a datetime from a string."""
        try:  # prefer the standard datetime format
            return datetime.strptime(s, self.datetime_format)
        except ValueError:  # attempt to parse string more flexibly
            err = UserInputError(f'Invalid time {s!r}')
            s = s.lower().strip()
            if not s:
                raise UserInputError('Empty date string') from None
            if s.isdigit():
                raise err from None
            now = pendulum.now()
            # for today/yesterday/tomorrow, just assume midnight
            # TODO: do regex replacements instead, so that times will be allowed
            if s == 'yesterday':
                s = now.subtract(days=1).to_date_string()
            elif s == 'today':
                s = now.to_date_string()
            elif s == 'tomorrow':
                s = now.add(days=1).to_date_string()
            try:
                dt: datetime = pendulum.parse(s, strict=False, tz=pendulum.local_timezone())  # type: ignore
                assert isinstance(dt, datetime)
                return dt
            except (AssertionError, pendulum.parsing.ParserError):
                # parse as a duration from now
                s = convert_number_words_to_digits(s.strip())
                is_past = s.endswith(' ago')
                s = s.removeprefix('in ').removesuffix(' from now').removesuffix(' ago').strip()
                secs = pytimeparse.parse(s)
                if secs is not None:
                    td = timedelta(seconds=secs)
                    return get_current_time() + (-td if is_past else td)
                diff_func = now.subtract if is_past else now.add
                if (match := re.fullmatch(r'(\d+)\s+months?', s)):
                    months = int(match.groups(0)[0])
                    return diff_func(months=months)
                elif (match := re.fullmatch(r'(\d+)\s+years?', s)):
                    years = int(match.groups(0)[0])
                    return diff_func(years=years)
                # TODO: handle work day/week?
                # (difficult since calculating relative times requires knowing which hours/days are work times
                raise err from None

    def render_datetime(self, dt: datetime) -> str:
        """Renders a datetime object as a string."""
        return dt.strftime(self.datetime_format)

    def _replace_work_durations(self, s: str) -> str:
        """Replaces units of "years", "months", "workweeks", or "workdays" with days."""
        float_regex = r'(\d+(\.\d+)?)'
        pat_years = float_regex + r'\s+years?'
        def from_years(years: float) -> float:
            return 365 * years
        pat_months = float_regex + r'\s+months?'
        def from_months(months: float) -> float:
            return 30 * months
        pat_work_days = float_regex + r'\s+work[-\s]*days?'
        def from_work_days(work_days: float) -> float:
            return self.hours_per_work_day * work_days / HOURS_PER_DAY
        pat_work_weeks = float_regex + r'\s+work[-\s]*weeks?'
        def from_work_weeks(work_weeks: float) -> float:
            return from_work_days(self.days_per_work_week * work_weeks)
        def _repl(func: Callable[[float], float]) -> Callable[[re.Match], str]:
            def _get_day_str(match: re.Match) -> str:
                val = float(match.groups(0)[0])
                return f'{func(val)} days'
            return _get_day_str
        for (pat, func) in [(pat_years, from_years), (pat_months, from_months), (pat_work_weeks, from_work_weeks), (pat_work_days, from_work_days)]:
            s = re.sub(pat, _repl(func), s)
        return s

    def parse_duration(self, s: str) -> float:
        """Parses a duration from a string."""
        s = s.strip()
        if not s:
            raise UserInputError('Empty duration string') from None
        s = self._replace_work_durations(convert_number_words_to_digits(s))
        try:
            secs = pytimeparse.parse(s)
            assert secs is not None
        except (AssertionError, ValueError):
            raise UserInputError('Invalid time duration') from None
        if secs < 0:
            raise UserInputError('Time duration cannot be negative')
        return secs / SECS_PER_DAY


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
    case_sensitive: bool = Field(default=False, description='whether names are case-sensitive')
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
        """Updates the global settings with this object."""
        global SETTINGS
        SETTINGS = self

    @contextmanager
    def change_global_settings(self) -> Iterator[None]:
        """Context manager for temporarily updating the global settings with this object."""
        try:
            orig_settings = self.global_settings()
            self.update_global_settings()
            yield
        finally:
            orig_settings.update_global_settings()

    def get_name_matcher(self) -> NameMatcher:
        """Gets a function which matches names, with case-sensitivity dependent on the settings."""
        return whitespace_insensitive_match if self.case_sensitive else case_insensitive_match

    def pretty_value(self, val: Any) -> str:
        """Gets a pretty representation of a value as a string.
        The representation will depend on its type and the settings."""
        if val is None:
            return '-'
        if isinstance(val, float):
            return str(int(val)) if (int(val) == val) else f'{val:.3g}'
        if isinstance(val, datetime):  # human-readable date
            if (get_current_time() - val >= timedelta(days=7)):
                return val.strftime(self.time.date_format)
            return pendulum.instance(val).diff_for_humans()
        if isinstance(val, date):
            tzinfo = get_current_time().tzinfo
            return self.pretty_value(datetime(year=val.year, month=val.month, day=val.day, tzinfo=tzinfo))
        if isinstance(val, (list, set)):  # display comma-separated list
            return ', '.join(map(self.pretty_value, val))
        return str(val)


# global object that may be updated by user's configuration file
SETTINGS = Settings()
