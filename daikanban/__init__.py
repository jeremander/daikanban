from collections.abc import Iterator
from contextlib import contextmanager
import logging
from pathlib import Path
import sys
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler


__version__ = '0.2.0'

PKG_DIR = Path(__file__).parent
PROG = PKG_DIR.name


###########
# LOGGING #
###########

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
