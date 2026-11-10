"""The `dwdopen nwp` commands: numerical weather prediction models."""

from __future__ import annotations

import click

from dwdopen import DWD

__all__ = ["nwp"]


@click.group()
def nwp() -> None:
    """Forecasts of the ICON models (weather/nwp)."""


def open_dwd() -> DWD:
    """The client for one command."""
    options = click.get_current_context().obj
    return DWD(progress=options["progress"])


@nwp.command()
def models() -> None:
    """List the currently available models."""
    with open_dwd() as dwd:
        for name in dwd.nwp.models():
            click.echo(name)


@nwp.command()
@click.argument("model")
def params(model: str) -> None:
    """List the parameters of a given model."""
    with open_dwd() as dwd:
        for name in dwd.nwp.model(model).parameters():
            click.echo(name)
