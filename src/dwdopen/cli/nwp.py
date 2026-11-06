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
