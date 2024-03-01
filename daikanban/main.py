#!/usr/bin/env python3

import json
from typing import Annotated

from typer import Option, Typer

from daikanban.model import DaiKanban


APP = Typer(
    add_completion=False,
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']}
)


@APP.command()
def schema(
    indent: Annotated[int, Option(help='JSON indentation level')] = 2
) -> None:
    """Print out the DaiKanban schema."""
    print(json.dumps(DaiKanban.model_json_schema(mode='serialization'), indent=indent))


if __name__ == '__main__':
    APP()
