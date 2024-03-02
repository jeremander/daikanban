#!/usr/bin/env python3

import json
from pathlib import Path
import re
from typing import Annotated, Optional

from rich import print
from rich.prompt import Confirm, Prompt
import typer

from daikanban.model import DaiKanban


APP = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    context_settings={'help_option_names': ['-h', '--help']}
)


def simple_input(prompt: str, default: Optional[str] = None, match: str = '.*') -> str:
    """Prompts the user with the given string until the user's response matches a certain regex."""
    regex = re.compile(match)
    while True:
        result = Prompt.ask(prompt, default=default) or ''
        if regex.fullmatch(result):
            break
    return result

def to_snake_case(name: str) -> str:
    """Converts an arbitrary string to snake case."""
    return re.sub(r'[^\w]+', '_', name.strip()).lower()


@APP.command()
def new() -> None:
    """Create a new DaiKanban board."""
    print('Creating new DaiKanban board.\n')
    name = simple_input('Board name', match=r'.*[^\s].*')
    default_path = to_snake_case(name) + '.json'
    path = simple_input('Output filename', default=default_path).strip()
    path = path or default_path
    if Path(path).exists():
        overwrite = Confirm.ask(f'A file named {path} already exists.\n\tOverwrite?')
    else:
        overwrite = True
    if overwrite:
        description = simple_input('Board description').strip() or None
        dk = DaiKanban(name=name, description=description)
        with open(path, 'w') as f:
            f.write(dk.model_dump_json(indent=2))
        print(f'Saved DaiKanban board {name!r} to [deep_sky_blue3]{path}[/]')


@APP.command()
def schema(
    indent: Annotated[int, typer.Option(help='JSON indentation level')] = 2
) -> None:
    """Print out the DaiKanban schema."""
    print(json.dumps(DaiKanban.model_json_schema(mode='serialization'), indent=indent))


if __name__ == '__main__':
    APP()
