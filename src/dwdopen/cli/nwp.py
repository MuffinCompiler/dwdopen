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
@click.argument("filter", required=False)
def params(model: str, filter: str | None) -> None:
    """List the parameters of a given model.

    When FILTER is provided, only the param names that contain
    the provided filter are listed.
    """
    with open_dwd() as dwd:
        for name in dwd.nwp.model(model).parameters():
            if filter is None or filter.lower() in name.lower():
                click.echo(name)


@nwp.command()
@click.argument("model")
@click.option("-p", "--param", help="List the runs of this parameter only.")
def runs(model: str, param: str | None) -> None:
    """List the runs of a given model, oldest first.
    A run can be listed while DWD is still publishing it.
    """
    with open_dwd() as dwd:
        for run in dwd.nwp.model(model).runs(parameter=param):
            click.echo(str(run))
