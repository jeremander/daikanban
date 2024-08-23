import csv
from datetime import datetime, timezone
from enum import Enum
import operator
import re
from typing import Any, Callable, Iterable, Optional

import pendulum
from typing_extensions import TypeAlias


SECS_PER_HOUR = 3600
HOURS_PER_DAY = 24
DAYS_PER_WEEK = 7
SECS_PER_DAY = SECS_PER_HOUR * HOURS_PER_DAY


#########
# ENUMS #
#########

class StrEnum(str, Enum):
    """Enum class whose __str__ representation is just a plain string value.
    NOTE: this class exists in the standard library in Python >= 3.11."""

    def __str__(self) -> str:
        return self.value


class NotGivenType(Enum):
    """Sentinel class for a value of "not given," when needed to distinguish it from None."""
    NotGiven = 'NotGiven'


NotGiven = NotGivenType.NotGiven


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

# function which matches a queried name against an existing name
NameMatcher: TypeAlias = Callable[[str, str], bool]
exact_match: NameMatcher = operator.eq

def whitespace_insensitive_match(name1: str, name2: str) -> bool:
    """Matches two strings, leading/trailing-whitespace-insensitively."""
    return name1.strip() == name2.strip()

def case_insensitive_match(name1: str, name2: str) -> bool:
    """Matches two strings, case- and leading/trailing-whitespace-insensitively."""
    return name1.strip().casefold() == name2.strip().casefold()

def fuzzy_match(name1: str, name2: str) -> bool:
    """Matches a queried name against a stored name, case-insensitively.
    This allows the first string to be a prefix of the second, if it is at least three characters long."""
    s1 = name1.strip().casefold()
    s2 = name2.strip().casefold()
    return (s1 == s2) or ((len(s1) >= 3) and s2.startswith(s1))

def first_name_match(matcher: NameMatcher, name1: str, names2: Iterable[str]) -> Optional[str]:
    """Given a NameMatcher, query name, and an iterable of names to compare against, returns the first name that matches (if there is one), otherwise None."""
    return next((name2 for name2 in names2 if matcher(name1, name2)), None)

def parse_string_set(s: str) -> Optional[set[str]]:
    """Parses a comma-separated string into a set of strings.
    Allows for quote delimiting so that commas can be escaped.
    Strips any leading or trailing whitespace from each string."""
    return {string.strip() for string in list(csv.reader([s]))[0]} or None


############
# DATETIME #
############

def get_current_time() -> datetime:
    """Gets the current time (timezone-aware)."""
    return datetime.now(timezone.utc).astimezone()

def get_duration_between(dt1: datetime, dt2: datetime) -> float:
    """Gets the duration (in days) between two datetimes."""
    return (dt2 - dt1).total_seconds() / SECS_PER_DAY

def human_readable_duration(days: float, prefer_days: bool = False) -> str:
    """Given a duration (in days), converts it to a human-readable string.
    This goes out to minute precision only.
    If prefer_days=True, show days and not weeks."""
    if days == 0:
        return '0 seconds'
    dur = pendulum.Duration(days=days)
    s = dur.in_words()
    if prefer_days and ('week' in s):
        s = re.sub(r'\d+ weeks?( \d+ days?)?', f'{dur.days} days', s)
    # hacky way to truncate the seconds
    return re.sub(r'\s+\d+ seconds?', '', s)

def replace_relative_day(s: str) -> str:
    """Given a time string containing yesterday/today/tomorrow, or an expression like "last Friday" or "next Tuesday", replaces it with the appropriate date."""
    pattern1 = '(yesterday|today|tomorrow)'
    def replace1(match: re.Match) -> str:
        now = pendulum.now()
        expr = match.group(0)
        if expr == 'yesterday':
            day = now.subtract(days=1)
        elif expr == 'today':
            day = now
        else:  # tomorrow
            day = now.add(days=1)
        return day.to_date_string()
    pattern2 = r'(last|next)\s+(mon|tues?|wed(nes)?|thu(rs?)?|fri|sat(ur)?|sun)(day)?'
    weekday_map = {day: i for (i, day) in enumerate(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'])}
    def replace2(match: re.Match) -> str:
        now = pendulum.now()
        groups = match.groups()
        past = (groups[0] == 'last')
        i = weekday_map[groups[1][:3]]
        diff = now.weekday() - i
        if past:
            diff = -diff if (diff > 0) else -(7 + diff)
        else:
            diff = (7 - diff) if (diff >= 0) else -diff
        return now.add(days=diff).to_date_string()
    return re.sub(pattern2, replace2, re.sub(pattern1, replace1, s))

def replace_relative_time_expression(s: str) -> str:
    """Resolves a relative time expression to an absolute one."""
    s = replace_relative_day(s)
    pattern = r'(in\s+)?(\d+)\s+(sec(ond)?|min(ute)?|hr|hour|day|week|month|yr|year)s?(\s+(ago|from\s+now))?'
    def replace(match: re.Match) -> str:
        groups = match.groups()
        is_future = (groups[0] is not None) and ('in' in groups[0])
        is_past = (groups[-1] == 'ago')
        is_future |= (groups[-1] is not None) and ('from' in groups[-1])
        if is_past and is_future:  # invalid, so bail
            return match.string
        amount = int(groups[1])
        unit = groups[2]
        now = pendulum.now()
        diff_func = now.subtract if is_past else now.add
        if unit == 'sec':
            return diff_func(seconds=amount).to_datetime_string()
        elif unit == 'min':
            return diff_func(minutes=amount).to_datetime_string()
        elif unit in ['hr', 'hour']:
            return diff_func(hours=amount).to_datetime_string()
        elif unit == 'day':
            return diff_func(days=amount).to_date_string()
        elif unit == 'week':
            return diff_func(weeks=amount).to_date_string()
        elif unit == 'month':
            return diff_func(months=amount).to_date_string()
        else:
            assert unit in ['yr', 'year']
            return diff_func(years=amount).to_date_string()
    return re.sub(pattern, replace, s)


#########
# STYLE #
#########

def style_str(val: Any, color: str, bold: bool = False, italic: bool = False) -> str:
    """Renders a value as a rich-formatted string with a given color, bold, and italic settings."""
    tags = [('' if bold else 'not ') + 'bold', ('' if italic else 'not ') + 'italic', color]
    tag = ' '.join(tags)
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
