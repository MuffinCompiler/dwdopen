# dwdopen

Python library to access [DWD Open Data](https://opendata.dwd.de/) numerical weather
prediction (NWP) data: discover what data is currently offered, define what you want,
and download it.

> Still in "pre-alpha", not everything works yet.
> See [Not yet implemented](#not-yet-implemented).

## Install

Requires **Python 3.12+**.

```bash
pip install git+https://github.com/MuffinCompiler/dwdopen@v0.1.0
```

## Quickstart

```python
from dwdopen import DWD

with DWD() as dwd:
    icon_eu = dwd.nwp.model("icon-eu")

    query = icon_eu.select(parameters=["T_2M", "PMSL"], steps="6h")
    query.download("forecast.grib2")
```

Nothing touches the network until a call needs availability information.

### Investigate your request before you download

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

### Discovery

```python
dwd.nwp.models()                    # every model DWD currently publishes
icon_eu.parameters()                # every parameter of one model
icon_eu.parameter("T").level_types  # (pressure (100), model (150))
icon_eu.levels("T", "pressure")     # available level values
```

Everything comes from the live catalogue, so a parameter
DWD adds should show up without a new dwdopen release.

## Selecting

### Forecast steps

Steps are **durations**, ICON-D2 publishes precipitation every
15 minutes and ICON-D2-RUC every 5.

```python
from dwdopen import Between, Every

steps="6h"                        # exactly this step
steps=["0h", "3h", "6h"]          # exactly these
steps=Every("0h", "48h", "3h")    # interval, inclusive at both ends
steps=Between("0h", "48h")        # whatever exists in the interval
steps="all"                       # everything published
```

`Every` names exact steps, so a missing one makes the request incomplete. `Between` and
`"all"` ask for whatever is there and can never be incomplete.

Note that DWD publishes data incrementally on the server, so a run might just be halfway
available. If you use `Between`, you might just get what's already available, not the full
data.

### Vertical levels

| level type | you pass | path holds |
|---|---|---|
| `"pressure"` (100) | hPa — `850` | Pa — `85000` |
| `"model"` (150) | the index — `60` | `60` |
| `"soil"` (106) | metres — `0.18` | `0.18` |

```python
icon_eu.select(parameters="T", level_type="pressure", levels=[850, 500])
icon_eu.select(parameters="T", level_type="model", levels=Between(60, 74))
icon_eu.select(parameters="T_SO", level_type="soil", levels="all")
```

`level_type` may be left out only while the selection is unambiguous. `T` is available on
both pressure and model levels, so omitting it raises `AmbiguousSelectionError` rather
than guessing. A 2-D field such as `T_2M` needs no level type at all.

## Downloading

```python
query.download("forecast.grib2")                    # one combined file
query.download("forecast/", combine="none")         # one file per message
query.download("f.grib2", temp_dir="/scratch")      # partial downloads before combining elsewhere
```

`combine="all"` concatenates the messages into a single GRIB2 file, which is valid
because GRIB2 messages are self-delimiting.

Messages are sorted time-major: every field of one forecast step together, steps
ascending. Some programs like CDO require grib files to be sorted by time to work
correctly.

Downloads run concurrently, are written to a temporary name and renamed into place, so a
partial file is never mistaken for a finished one. Several processes may write the same
directory at once.

`temp_dir` must be on the same filesystem as the destination, because publishing a
finished file is a rename and a rename cannot cross filesystems.

## Logging

The library logs through the standard `dwdopen` logger. It never prompts or reads from
stdin as the library is meant to run unattended.

```python
import logging
logging.basicConfig(level=logging.INFO)
```

`INFO` reports what is about to be downloaded and how large it is. `WARNING` covers
retries and mixed level types.

## Not yet implemented

- [ ] Resume and skip existing files. A failed run currently re-downloads from scratch.
- [ ] Automatic generation of download file name (see get_task_name on NRT)
- [ ] Ensemble members** (`-eps` models, the `e/<NN>/` path segment).
- [ ] `combine="member"` and `combine="parameter"`.
- [ ] Listing cache. Every call re-reads the catalogue today.
- [ ] Feedback of download progress (bar, text, visual?)
- [ ] ICON-ART wavelengths (the `wvl1` segment).
- [ ] A command-line interface.
- [ ] Automatic probe parameter for `Model.latest_run()`, which needs `probe=` at the moment.

## License

MIT. See [LICENSE](LICENSE).

Forecast data itself is provided by Deutscher Wetterdienst (DWD) under its own
[terms of use](https://www.dwd.de/EN/service/copyright/copyright_node.html).
