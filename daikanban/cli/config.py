import sys
from typing import Annotated

from rich.prompt import Confirm
import typer

from daikanban.cli import APP_KWARGS
from daikanban.config import Config, get_config, user_config_path


APP = typer.Typer(**APP_KWARGS)

@APP.command(short_help='create a new config file')
def new(
    stdout: Annotated[bool, typer.Option('--stdout', help='output config file to stdout')] = False
) -> None:
    """Create a new config file."""
    path = user_config_path()
    if not stdout:
        if path.exists():
            prompt = f'Config file {path} already exists. Overwrite with the default?'
            if not Confirm.ask(prompt):
                return
        if not path.parent.exists():
            prompt = f'Directory {path.parent} does not exist. Create it?'
            if Confirm.ask(prompt):
                path.parent.mkdir(parents=True)
            else:
                return
    cfg = Config()
    if stdout:
        print('\n' + cfg.to_toml_string())
    else:
        cfg.save(path)
        print(f'Saved default config file to {path}', file=sys.stderr)

@APP.command(short_help='print out path to the configurations')
def path() -> None:
    """Print out path to the configurations."""
    print(user_config_path())

@APP.command(short_help='show the configurations')
def show() -> None:
    """Show the configurations."""
    print(get_config().to_toml_string())
