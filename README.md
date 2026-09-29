# dwdopen

Python library to access [DWD Open Data](https://opendata.dwd.de/) numerical weather
prediction (NWP) data: discover what data is currently offered, define what you want,
and download it.

> Still in "pre-alpha", not everything works yet.
> See [Not yet implemented](#not-yet-implemented).

## Install

Requires **Python 3.11 or newer**.

```bash
pip install dwdopen
```

## Quickstart

```python
from dwdopen import DWD

with DWD() as dwd:
    icon_eu = dwd.nwp.model("icon-eu")

    query = icon_eu.select(parameters=["T_2M", "PMSL"], steps="6h")
    query.download("forecast.grib2")
```

## Discovery

```python
dwd.nwp.models()                    # every model DWD currently publishes
icon_eu.parameters()                # every parameter of one model
icon_eu.parameter("T").level_types  # (pressure (100), model (150))
icon_eu.levels("T", "pressure")     # available level values
```

## Selecting

### Forecast steps

Steps are **durations**, ICON-D2 publishes precipitation every
15 minutes and ICON-D2-RUC every 5.

```python
from dwdopen import Between, Every, hours, minutes

steps="6h"                        # exactly this step
steps=["0h", "3h", "6h"]          # exactly these
steps=Every("0h", "48h", "3h")    # interval, inclusive at both ends
steps=Between("0h", "48h")        # whatever exists in the interval
steps="all"                       # everything published

steps=hours(0, 6, 12, 18)         # plain numbers, if that is what you have
steps=hours(range(0, 121, 3))     # or any iterable of them
steps=minutes(0, 15, 30)          # for the sub-hourly models
```

`hours()` and `minutes()` turn a single number into a single duration, so they compose
with the others too: `Every(hours(0), hours(48), hours(3))`.

`Every` names exact steps, so a missing one makes the request incomplete. `Between` and
`"all"` ask for whatever is there and can never be incomplete.

Note that DWD publishes data incrementally on the server, so a run might just be halfway
available. If you use `Between`, you might just get what's already available, not the full
data.

### Ensemble members

The `-eps` models publish each member separately. Members are plain integers; how many
there are differs per model (40 for ICON-EPS and ICON-EU-EPS, 20 for ICON-D2-EPS, 10 for
ICON-ART-EPS):

```python
eps.select(parameters="T_2M", members=[1, 2, 5])
eps.select(parameters="T_2M", members=Between(1, 10))
eps.select(parameters="T_2M")                       # every member
```

Leaving `members` out takes all of them, the same as levels and steps.

### Vertical levels

```python
icon_eu.select(parameters="T", level_type="pressure", levels=[850, 500])
icon_eu.select(parameters="T", level_type="model", levels=Between(60, 74))
icon_eu.select(parameters="T_SO", level_type="soil", levels="all")
```

`level_type` may be left out only while the selection is unambiguous. `T` is available on
both pressure and model levels, so omitting it raises `AmbiguousSelectionError` rather
than guessing. A 2-D field such as `T_2M` needs no level type at all. Time-invariant fields
need no level type either. These are published under every run with a single step.
`HHL` is the exception, being model half-level heights:

```python
icon_d2.select(parameters="HSURF", steps="0h")                      # no level type
icon_d2.select(parameters="HHL", level_type="model", levels="all")
```

## Investigate before you download

`resolve()` freezes a query against one run and hands back a plan you can inspect before
any download happens:

```python
plan = icon_eu.select(parameters="U", level_type="pressure").resolve()
print(plan)
# ResolvedRequest(run=2026-09-23T06:00:00+00:00, 1860 assets, 1.5 GB, U,
#                 on pressure (100), 20 levels, steps 0h..120h)

print(plan.assets[0])
# Asset(U, 50 hPa, 0h, 723.4 KB)

plan.download("u.grib2")
```

A plan never switches to a newer run later, so what you inspected is what you get.

## Downloading

```python
query.download("forecast.grib2")                    # one combined file
query.download("members/", combine="member")        # one file per ensemble member
query.download("forecast/", combine="none")         # one file per message
query.download("f.grib2", temp_dir="/scratch")      # partial downloads before combining elsewhere
```

`combine="all"` concatenates the messages into a single GRIB2 file.
You can also provide just a directory in this case and the name is
generated automatically.

```python
plan = query.resolve()
plan.suggested_name()            # 'icon-eu_2026-09-24T0600_PMSL+T_2M_0h-24h.grib2'
plan.download("/home/weather/")   # writes that name into the directory
```

Downloads run concurrently, are written to a temporary name and renamed into place, so a
partial file is never mistaken for a finished one. Several processes may write the same
directory at once. Already downloaded files are skipped.
`DownloadResult.assets_skipped` says how many were already there, which is worth
checking in a scheduled job.

## Logging

The library logs through the `dwdopen` logger. You can change the logging level via::

```python
import logging, dwdopen

dwdopen.set_log_level(logging.DEBUG)    # a line per file to download
dwdopen.set_log_level(logging.WARNING)  # only retries and warnings
dwdopen.set_log_level(None)             # disable the dwdopen logging
```

The handler is connected to the `dwdopen` logger. It will not override
the logging your application sets up for itself. If you do configure your own logger
and want to use that logger, call `set_log_level(None)`. That will uninstall the handler.

## Not yet implemented

- [ ] `combine="parameter"`.
- [ ] Listing cache. Every call re-reads the catalogue today.
- [ ] Feedback of download progress (bar, text, visual?)
- [ ] ICON-ART wavelengths (the `wvl1` segment).
- [ ] A command-line interface.
- [ ] Automatic parameter choice for `Model.latest_run()`, which needs
      `parameter=` at the moment.

## License

MIT. See [LICENSE](LICENSE).

Forecast data itself is provided by Deutscher Wetterdienst (DWD) under its own
[terms of use](https://www.dwd.de/EN/service/copyright/copyright_node.html).
