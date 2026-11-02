"""The dwdopen command line interface."""

from __future__ import annotations

import click

__all__ = ["main"]


@click.group()
def main() -> None:
    """Download weather data from DWD Open Data (https://opendata.dwd.de)."""
