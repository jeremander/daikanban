from contextlib import contextmanager
import sys
from typing import Iterator, Optional

import rich


@contextmanager
def handle_error(*errtypes: type[Exception], msg: Optional[str] = None) -> Iterator[None]:
    """Context manager for catching an error of a certain type (or types), optionally displaying a message, then exiting the program."""
    try:
        yield
    except errtypes as e:
        msg = str(e) if (msg is None) else msg
        rich.print(f'[bold red]ERROR: {msg}[/]', file=sys.stderr)
        sys.exit(1)
