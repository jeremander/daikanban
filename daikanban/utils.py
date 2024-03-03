from contextlib import contextmanager
from datetime import datetime, timezone
import re
import sys
from typing import Iterator, Optional

import rich


SECS_PER_DAY = 3600 * 24


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

def get_current_time() -> datetime:
    """Gets the current time (timezone-aware)."""
    return datetime.now(timezone.utc).astimezone()

def get_duration_between(dt1: datetime, dt2: datetime) -> float:
    """Gets the duration (in days) between two datetimes."""
    return (dt2 - dt1).total_seconds() / SECS_PER_DAY

def to_snake_case(name: str) -> str:
    """Converts an arbitrary string to snake case."""
    return re.sub(r'[^\w]+', '_', name.strip()).lower()

def prefix_match(token: str, match: str, minlen: int = 1) -> bool:
    """Returns true if token is a prefix of match and has length at least minlen."""
    n = len(token)
    return (n >= minlen) and (match[:n] == token)
