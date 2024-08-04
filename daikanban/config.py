from collections.abc import Sequence
from datetime import date, datetime, timedelta
from operator import attrgetter
from pathlib import Path
import re
from typing import Annotated, Any, Callable, Optional

from fancy_dataclass import ConfigDataclass, TOMLDataclass
import pendulum
from pydantic import Field
from pydantic.dataclasses import dataclass
import pytimeparse
from typing_extensions import Doc

from daikanban import PROG
from daikanban.task import TaskConfig, TaskStatus
from daikanban.utils import HOURS_PER_DAY, SECS_PER_DAY, NameMatcher, UserInputError, case_insensitive_match, convert_number_words_to_digits, get_current_time, replace_relative_time_expression, whitespace_insensitive_match


############
# DEFAULTS #
############

DEFAULT_DATE_FORMAT = '%m/%d/%y'  # USA-based format
DEFAULT_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ%z'

DEFAULT_HOURS_PER_WORK_DAY = 8
DEFAULT_DAYS_PER_WORK_WEEK = 5


#########
# PATHS #
#########

def user_dir() -> Path:
    """Gets the path to the user's directory where configs, etc. will be stored."""
    return Path.home() / f'.{PROG}'

def user_config_path() -> Path:
    """Gets the path to the user's config file."""
    return user_dir() / 'config.toml'

def user_config_exists() -> bool:
    """Returns True if the user's config file exists."""
    return user_config_path().is_file()


################
# TASK SORTING #
################

# map from Task fields to default sort ascending flag
_DEFAULT_ASCENDING_BY_FIELD = {
    'completed_time': False,
    'difficulty': True,
    'priority': False,
    'score': False,
    'status': True,
}

@dataclass
class TaskSortKey(TOMLDataclass):
    """Key for sorting tasks."""
    # field to sort on
    field: str
    # whether to sort ascending or not (if None, uses the default for the field)
    asc: Optional[bool] = None

    def __post_init__(self) -> None:
        if self.asc is None:
            self.asc = _DEFAULT_ASCENDING_BY_FIELD.get(self.field, True)


##########
# CONFIG #
##########

@dataclass
class TimeConfig(TOMLDataclass):
    """Time configurations."""
    date_format: Annotated[
        str,
        Doc('preferred format for dates')
    ] = Field(default=DEFAULT_DATE_FORMAT)
    datetime_format: Annotated[
        str,
        Doc('preferred format for datetimes')
    ] = Field(default=DEFAULT_DATETIME_FORMAT)
    hours_per_work_day: Annotated[
        float,
        Doc('number of hours per work day')
    ] = Field(default=DEFAULT_HOURS_PER_WORK_DAY, gt=0, le=24)
    days_per_work_week: Annotated[
        float,
        Doc('number of days per work week')
    ] = Field(default=DEFAULT_DAYS_PER_WORK_WEEK, gt=0, le=7)

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
class FileConfig(TOMLDataclass):
    """File configurations."""
    json_indent: Annotated[Optional[int], Doc('indentation level for JSON format')] = Field(default=2, ge=0)


@dataclass
class ColumnConfig(TOMLDataclass):
    """Configurations for an individual board column."""
    # task statuses to display in the column
    statuses: list[str]
    # criteria to sort tasks by
    sort_by: str | TaskSortKey | list[str | TaskSortKey]

    def get_sort_keys(self) -> list[TaskSortKey]:
        """Gets a list of sort keys with which to sort tasks."""
        keys = self.sort_by if isinstance(self.sort_by, Sequence) else [self.sort_by]
        return [TaskSortKey(key) if isinstance(key, str) else key for key in keys]


DEFAULT_COLUMN_CONFIGS = {
    'todo': ColumnConfig(statuses=[TaskStatus.todo], sort_by='score'),
    'active': ColumnConfig(statuses=[TaskStatus.active, TaskStatus.paused], sort_by=['status', 'score']),
    'complete': ColumnConfig(statuses=[TaskStatus.complete], sort_by='completed_time'),
}


@dataclass
class DisplayConfig(TOMLDataclass):
    """Display configurations."""
    max_tasks: Annotated[
        Optional[int],
        Doc('max number of tasks to display per column')
    ] = Field(default=None, ge=0)
    completed_age_off: Annotated[
        Optional[float],
        Doc('length of time (in days) after which to stop displaying completed tasks')
    ] = Field(default=30, ge=0)
    columns: Annotated[
        dict[str, ColumnConfig],
        Doc('settings for each board column')
    ] = Field(default=DEFAULT_COLUMN_CONFIGS)

    def get_column_sort_keys(self, column: str) -> list[tuple[Callable[[Any], Any], bool]]:
        """Given a board column, gets a list of (sort_key, ascending) pairs to be used for sorting tasks."""
        cfg = self.columns[column]
        sort_keys = cfg.get_sort_keys()
        pairs: list[tuple[Callable[[Any], Any], bool]] = []
        idx_by_status = {status: i for (i, status) in enumerate(cfg.statuses)}
        for sort_key in sort_keys:
            assert isinstance(sort_key.asc, bool)
            if sort_key.field == 'status':
                # sort order depends on board configs
                pairs.append((lambda obj: idx_by_status[obj.status], sort_key.asc))
            else:
                pairs.append((attrgetter(sort_key.field), sort_key.asc))
        return pairs


@dataclass
class Config(ConfigDataclass, TOMLDataclass):  # type: ignore[misc]
    """Collection of global configurations."""
    case_sensitive: bool = Field(default=False)
    time: TimeConfig = Field(default_factory=TimeConfig)
    file: FileConfig = Field(default_factory=FileConfig)
    task: TaskConfig = Field(default_factory=TaskConfig)
    display: DisplayConfig = Field(default_factory=DisplayConfig)

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
        config_path = user_config_path()
        if config_path.is_file():
            config = Config.load_config(config_path)
        else:  # use default config
            config = Config()
        config.update_config()  # set global value
    return config
