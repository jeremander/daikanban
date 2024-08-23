from typing import Any


# default settings for typer app
APP_KWARGS: dict[str, Any] = {
    'add_completion': False,
    'context_settings': {
        'help_option_names': ['-h', '--help']
    },
    # if True, display "pretty" (but very verbose) exceptions
    'pretty_exceptions_enable': False
}
