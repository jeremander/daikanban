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
    if not s.strip():
        return None
    try:
        dt: datetime = pendulum.parse(s, strict=False, tz=pendulum.local_timezone())  # type: ignore
        assert isinstance(dt, datetime)
    except (AssertionError, pendulum.parsing.ParserError):
        # parse as a duration from now
        s = convert_number_words_to_digits(s.strip())
        is_past = s.endswith(' ago')
        s = s.removeprefix('in ').removesuffix(' from now').removesuffix(' ago').strip()
        secs = pytimeparse.parse(s)
        if secs is None:
            raise UserInputError('Invalid date') from None
        td = timedelta(seconds=secs)
        dt = get_current_time() + (-td if is_past else td)
    return dt

def human_readable_duration(days: float) -> str:
    """Given a duration (in days), converts it to a human-readable string.
    This rounds to the nearest minute."""
    if days == 0:
        return '0 seconds'
    s = pendulum.Duration(days=days).in_words()
    # hacky way to round to the nearest minute
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
