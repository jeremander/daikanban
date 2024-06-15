import typer

from daikanban.cli import APP_KWARGS


APP = typer.Typer(**APP_KWARGS)

@APP.command(short_help='create a new config file')
def new() -> None:
    """Create a new config file."""

@APP.command(short_help='print out path to the configurations')
def path() -> None:
    """Print out path to the configurations."""

@APP.command(short_help='show the configurations')
def show() -> None:
    """Show the configurations."""
