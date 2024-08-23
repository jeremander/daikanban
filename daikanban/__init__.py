import logging
from pathlib import Path

from rich.logging import RichHandler


__version__ = '0.2.0'

PKG_DIR = Path(__file__).parent
PROG = PKG_DIR.name


###########
# LOGGING #
###########

LOG_FMT = '%(message)s'

handler = RichHandler(
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
logger = logging.getLogger(PROG)
