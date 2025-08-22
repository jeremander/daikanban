from dataclasses import field
from datetime import date, datetime, timedelta
from operator import attrgetter
from pathlib import Path
import re
from typing import Annotated, Any, Callable, Optional

from fancy_dataclass import ConfigDataclass, TOMLDataclass
import pendulum
from pydantic import Field
from pydantic.dataclasses import dataclass
import pytimeparse  # type: ignore[import-untyped]
from typing_extensions import Doc

from daikanban import PROG
from daikanban.errors import UserInputError
from daikanban.task import TaskConfig, TaskStatus
from daikanban.utils import HOURS_PER_DAY, SECS_PER_DAY, NameMatcher, case_insensitive_match, convert_number_words_to_digits, fix_datetime_string, get_current_time, replace_relative_time_expression, whitespace_insensitive_match


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
    return Path.home() / '.config' / PROG

def user_config_path() -> Path:
    """Gets the path to the user's config file."""
    return user_dir() / 'config.toml'

def user_config_exists() -> bool:
    """Returns True if the user's config file exists."""
    return user_config_path().is_file()

DEFAULT_BOARD_DIR = 'boards'


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
class BoardConfig(TOMLDataclass):
    """Board configurations."""
    board_dir: Annotated[
        str,
        Doc('directory for board files (can be a path relative to ~/.config/daikanban)')
    ] = DEFAULT_BOARD_DIR
    default_board: Annotated[
        str,
        Doc('name of default board')
    ] = 'board.json'

    @property
    def board_dir_path(self) -> Path:
        """Gets the absolute path to the board directory."""
        if (path := Path(self.board_dir)).is_absolute():
            return path
        return user_dir() / self.board_dir

    def resolve_board_name_or_path(self, name: str | Path) -> Path:
        """Given the name or path to a board file, returns the absolute path."""
        if (path := Path(name)).is_absolute():
            return path
        # user entered a name or relative filename, so resolve it relative to the board directory
        if Path(name).suffix.lower() != '.json':
            name = str(name) + '.json'
        return self.board_dir_path / name

    @property
    def default_board_path(self) -> Path:
        """Gets the absolute path to the default board file."""
        return self.resolve_board_name_or_path(self.default_board)

    @property
    def all_board_paths(self) -> list[Path]:
        """Gets a list of absolute paths of all JSON files in the board directory."""
        return sorted([p for p in self.board_dir_path.glob('*') if str(p).lower().endswith('.json')])


@dataclass
class TimeConfig(TOMLDataclass):
    """Time configurations."""
    date_format: Annotated[
        str,
        Doc('preferred format for dates')
    ] = DEFAULT_DATE_FORMAT
    datetime_format: Annotated[
        str,
        Doc('preferred format for datetimes')
    ] = DEFAULT_DATETIME_FORMAT
    hours_per_work_day: Annotated[
        float,
        Doc('number of hours per work day'),
        Field(gt=0, le=24)
    ] = DEFAULT_HOURS_PER_WORK_DAY
    days_per_work_week: Annotated[
        float,
        Doc('number of days per work week'),
        Field(gt=0, le=7)
    ] = DEFAULT_DAYS_PER_WORK_WEEK

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
            # pendulum has some parsing quirks, so preprecess its input
            s = fix_datetime_string(s)
            try:
                dt: datetime = pendulum.parse(s, strict=False, tz=pendulum.local_timezone())  # type: ignore
                assert isinstance(dt, datetime)
                return dt
            except (AssertionError, pendulum.parsing.exceptions.ParserError):
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
        def _repl(func: Callable[[float], float]) -> Callable[[re.Match[str]], str]:
            def _get_day_str(match: re.Match[str]) -> str:
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
        return float(secs) / SECS_PER_DAY


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
        keys = self.sort_by if isinstance(self.sort_by, list | tuple) else [self.sort_by]
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
        Doc('max number of tasks to display per column'),
        Field(ge=0)
    ] = None
    completed_age_off: Annotated[
        Optional[float],
        Doc('length of time (in days) after which to stop displaying completed tasks'),
        Field(ge=0)
    ] = 30
    columns: Annotated[
        dict[str, ColumnConfig],
        Doc('settings for each board column')
    ] = field(default_factory=lambda: DEFAULT_COLUMN_CONFIGS)

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
class Config(ConfigDataclass, TOMLDataclass, doc_as_comment=True):
    """Global configurations for daikanban"""
    case_sensitive: Annotated[
        bool,
        Doc('whether to match names case-sensitively')
    ] = False
    board: BoardConfig = field(default_factory=BoardConfig)
    time: TimeConfig = field(default_factory=TimeConfig)
    file: FileConfig = field(default_factory=FileConfig)
    task: TaskConfig = field(default_factory=TaskConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)

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
            if get_current_time() - val >= timedelta(days=7):
                return val.strftime(self.time.date_format)
            return pendulum.instance(val).diff_for_humans()
        if isinstance(val, date):
            tzinfo = get_current_time().tzinfo
            return self.pretty_value(datetime(year=val.year, month=val.month, day=val.day, tzinfo=tzinfo))
        if isinstance(val, list | set):  # display comma-separated list
            vals = sorted(val) if isinstance(val, set) else val
            return ', '.join(map(self.pretty_value, vals))
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
