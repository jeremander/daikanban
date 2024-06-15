from typing import Any


# default settings for typer app
APP_KWARGS: dict[str, Any] = {
    'add_completion': False,
    'context_settings': {
        'help_option_names': ['-h', '--help']
    }
}
