from collections.abc import Iterator
from contextlib import contextmanager
import logging
import os
from pathlib import Path
import pdb  # noqa: T100
import sys
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler


__version__ = '0.2.1'

PKG_DIR = Path(__file__).parent
PROG = PKG_DIR.name


###########
# LOGGING #
###########

def is_debug_mode() -> bool:
    """Returns True if debug mode is active.
    For now, this means the DKB_DEBUG environment variable is set to true."""
    return os.getenv('DKB_DEBUG', '').lower() in ['1', 'on', 'true']


class Logger(logging.Logger):
    """Custom subclass of logging.Logger."""

    def done(self) -> None:
        """Logs a message indicating an operation is done."""
        self.info('[bold]DONE![/]')

    def exit_with_error(self, msg: str) -> None:
        """Exits the program with the given error message."""
        logger.error(msg)
        sys.exit(1)

    @contextmanager
    def catch_errors(self, *errtypes: type[Exception], msg: Optional[str] = None) -> Iterator[None]:
        """Context manager for catching an error of a certain type (or types), optionally displaying a message, then exiting the program."""
        if is_debug_mode():  # drop into debugger
            try:
                yield
            except Exception as e:  # noqa: F841
                pdb.post_mortem()
        else:
            try:
                yield
            except errtypes as e:
                msg = str(e) if (msg is None) else msg
                self.exit_with_error(msg)


LOG_FMT = '%(message)s'

handler = RichHandler(
    console=Console(stderr=True),
    show_time=False,
    show_level=True,
    show_path=False,
    markup=True,
)
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FMT,
    handlers=[handler]
)
logging.setLoggerClass(Logger)
# TODO: set level based on configs
logger: Logger = logging.getLogger(PROG)  # type: ignore[assignment]
