from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
import re
import sys
from typing import Any, Iterator, Optional

import pendulum
import pytimeparse
import rich


SECS_PER_DAY = 3600 * 24
DATE_FORMAT = '%m/%d/%y'
TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ%z'


class StrEnum(str, Enum):
    """Enum class whose __str__ representation is just a plain string value.
    NOTE: this class exists in the standard library in Python >= 3.11."""

    def __str__(self) -> str:
        return self.value


###################
# STRING HANDLING #
###################

def to_snake_case(name: str) -> str:
    """Converts an arbitrary string to snake case."""
    name = name.replace('"', '').replace("'", '')
    return re.sub(r'[^\w]+', '_', name.strip()).lower()

def prefix_match(token: str, match: str, minlen: int = 1) -> bool:
    """Returns True if token is a prefix of match and has length at least minlen."""
    n = len(token)
    return (n >= minlen) and (match[:n] == token)

def convert_number_words_to_digits(s: str) -> str:
    """Replaces occurrences of number words like 'one', 'two', etc. to their digital equivalents."""
    words_to_numbers = {
        'zero': '0',
        'one': '1',
        'two': '2',
        'three': '3',
        'four': '4',
        'five': '5',
        'six': '6',
        'seven': '7',
        'eight': '8',
        'nine': '9',
    }
    pattern = re.compile(r'\b(' + '|'.join(words_to_numbers.keys()) + r')\b')
    return re.sub(pattern, lambda x: words_to_numbers[x.group()], s)

def fuzzy_match_names(name1: str, name2: str) -> bool:
    """Matches a queried name against a stored name, case-insensitively.
    This allows the first string to be a prefix of the second, if it is at least three characters long."""
    s1 = name1.strip().lower()
    s2 = name2.strip().lower()
    return (s1 == s2) or ((len(s1) >= 3) and s2.startswith(s1))


############
# DATETIME #
############

def get_current_time() -> datetime:
    """Gets the current time (timezone-aware)."""
    return datetime.now(timezone.utc).astimezone()

def get_duration_between(dt1: datetime, dt2: datetime) -> float:
    """Gets the duration (in days) between two datetimes."""
    return (dt2 - dt1).total_seconds() / SECS_PER_DAY

def parse_date(s: str) -> Optional[datetime]:
    """Parses a string into a datetime.
    The input string can either specify a datetime directly, or a time duration from the present moment."""
    err = UserInputError(f'Invalid date {s!r}')
    s = s.lower().strip()
    if not s:
        return None
    if s.isdigit():
        raise err
    now = pendulum.now()
    # for today/yesterday/tomorrow, just assume midnight
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
        if (match := re.fullmatch(r'(\d+) months?', s)):
            months = int(match.groups(0)[0])
            return now.subtract(months=months) if is_past else now.add(months=months)
        elif (match := re.fullmatch(r'(\d+) years?', s)):
            years = int(match.groups(0)[0])
            return now.subtract(years=years) if is_past else now.add(years=years)
        raise err from None

def parse_duration(s: str) -> Optional[float]:
    """Parses a string into a time duration (number of days)."""
    if not s.strip():
        return None
    secs = pytimeparse.parse(s)
    if (secs is None):
        raise UserInputError('Invalid time duration')
    return secs / SECS_PER_DAY

def human_readable_duration(days: float) -> str:
    """Given a duration (in days), converts it to a human-readable string.
    This goes out to minute precision only."""
    if days == 0:
        return '0 seconds'
    s = pendulum.Duration(days=days).in_words()
    # hacky way to truncate the seconds
    return re.sub(r'\s+\d+ seconds?', '', s)


#########
# STYLE #
#########

def style_str(val: Any, color: str, bold: bool = False) -> str:
    """Renders a value as a rich-formatted string with a given color.
    If bold=True, make it bold."""
    tag = ('' if bold else 'not ') + f'bold {color}'
    return f'[{tag}]{val}[/]'

def err_style(obj: object) -> str:
    """Renders an error as a rich-styled string."""
    s = str(obj)
    if s:
        s = s[0].upper() + s[1:]
    return style_str(s, 'red')


##########
# ERRORS #
##########

class KanbanError(ValueError):
    """Custom error type for Kanban errors."""

class UserInputError(KanbanError):
    """Class for user input errors."""


def exit_with_error(msg: str) -> None:
    """Exits the program with the given error message."""
    rich.print(f'[bold red]{msg}[/]', file=sys.stderr)
    sys.exit(1)

@contextmanager
def handle_error(*errtypes: type[Exception], msg: Optional[str] = None) -> Iterator[None]:
    """Context manager for catching an error of a certain type (or types), optionally displaying a message, then exiting the program."""
    try:
        yield
    except errtypes as e:
        msg = str(e) if (msg is None) else msg
        exit_with_error(msg)
