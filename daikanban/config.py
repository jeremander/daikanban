from datetime import date, datetime, timedelta
import re
from typing import Annotated, Any, Callable, Optional

from fancy_dataclass import ConfigDataclass
import pendulum
from pydantic import Field
from pydantic.dataclasses import dataclass
import pytimeparse
from typing_extensions import Doc

from daikanban.task import DEFAULT_TASK_STATUS_GROUPS, TaskConfig
from daikanban.utils import HOURS_PER_DAY, SECS_PER_DAY, NameMatcher, UserInputError, case_insensitive_match, convert_number_words_to_digits, get_current_time, replace_relative_time_expression, whitespace_insensitive_match


DEFAULT_DATE_FORMAT = '%m/%d/%y'  # USA-based format
DEFAULT_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ%z'

DEFAULT_HOURS_PER_WORK_DAY = 8
DEFAULT_DAYS_PER_WORK_WEEK = 5


@dataclass
class TimeConfig:
    """Time configurations."""
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

    def parse_datetime(self, s: str) -> datetime:
        """Parses a datetime from a string."""
        s = s.lower().strip()
        if not s:
            raise UserInputError('Empty date string') from None
        s = convert_number_words_to_digits(s)
        err = UserInputError(f'Invalid time {s!r}')
        if s.isdigit():
            raise err from None
        if (replaced := replace_relative_time_expression(s)) != s:
            # replace yesterday/today/tomorrow with date
            return self.parse_datetime(replaced)
        try:  # prefer the standard datetime format
            return datetime.strptime(s, self.datetime_format)
        except ValueError:  # attempt to parse string more flexibly
            # pendulum doesn't allow single-digit hours for some reason, so pad it with a zero
            tokens = s.split()
            if (len(tokens) >= 2) and (tok := tokens[-1]).isdigit() and (len(tok) == 1):
                s = ' '.join(tokens[:-1] + ['0' + tok])
            try:
                dt: datetime = pendulum.parse(s, strict=False, tz=pendulum.local_timezone())  # type: ignore
                assert isinstance(dt, datetime)
                return dt
            except (AssertionError, pendulum.parsing.ParserError):
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


@dataclass
class FileConfig:
    """File configurations."""
    json_indent: Optional[int] = Field(
        default=2,
        description='indentation level for formatting JSON'
    )


@dataclass
class DisplayConfig:
    """Display configurations."""
    max_tasks: Optional[int] = Field(
        default=None,
        description='max number of tasks to display per column',
        ge=0
    )
    completed_age_off: Optional[timedelta] = Field(
        default=timedelta(days=30),
        description='length of time after which to stop displaying completed tasks'
    )
    status_groups: dict[str, list[str]] = Field(
        default=DEFAULT_TASK_STATUS_GROUPS,
        description='map from board columns (groups) to task statuses'
    )


@dataclass
class Config(ConfigDataclass):
    """Collection of global configurations."""
    case_sensitive: Annotated[bool, Doc('whether names are case-sensitive')] = Field(default=False)
    time: Annotated[TimeConfig, Doc('time configs')] = Field(default_factory=TimeConfig)
    file: Annotated[FileConfig, Doc('file configs')] = Field(default_factory=FileConfig)
    task: Annotated[TaskConfig, Doc('task configs')] = Field(default_factory=TaskConfig)
    display: Annotated[DisplayConfig, Doc('display configs')] = Field(default_factory=DisplayConfig)

    @property
    def name_matcher(self) -> NameMatcher:
        """Gets a function which matches names, with case-sensitivity dependent on the configs."""
        return whitespace_insensitive_match if self.case_sensitive else case_insensitive_match

    def pretty_value(self, val: Any) -> str:
        """Gets a pretty representation of a value as a string.
        The representation will depend on its type and the configs."""
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


def get_config() -> Config:
    """Gets the current global configurations."""
    config = Config.get_config()
    if config is None:
        # TODO: load from user's config file, if exists
        config = Config()
        config.update_config()
    return config
