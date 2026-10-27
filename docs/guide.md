# dwdopen guide

The examples assume a client and a model:

```python
from dwdopen import DWD, Between, Every, hours, minutes

with DWD() as dwd:
    icon_eu = dwd.nwp.model("icon-eu")
    ...
```

Use the model and its queries inside the `with` block. After it, the connection is
closed and every call raises `ClientClosedError`.

- [Discovery](#discovery)
- [Selecting](#selecting): [steps](#forecast-steps), [levels](#vertical-levels),
  [members](#ensemble-members), [wavelengths](#icon-art-wavelengths)
- [Runs and complete data](#runs-and-complete-data)
- [Inspecting a plan](#inspecting-a-plan)
- [Downloading](#downloading)
- [Regridding](#regridding)
- [Caching](#caching)
- [Logging](#logging)
- [Errors](#errors)

## Discovery

Nothing about the models is hard-coded. Everything below is read from the server.

```python
dwd.nwp.models()                    # every model DWD currently publishes
icon_eu.parameters()                # every parameter of one model, sorted

info = icon_eu.parameter("T")
info.level_types                    # pressure (100) and model (150)
info.wavelengths                    # () for everything except two ICON-ART fields

icon_eu.levels("T", "pressure")     # [50, 70, ..., 1000], in hPa
icon_eu.levels("T", "model")        # [1, 2, ..., 74], level indices

icon_eu.runs()                      # the runs DWD currently lists, oldest first
icon_eu.runs(parameter="T")         # the runs listed for one parameter
```

Model and parameter names ignore case: `"ICON-EU"` and `"t_2m"` work. A name that does not
exist raises `UnknownModelError` or `UnknownParameterError` with the closest matches.

`runs()[-1]` is the newest run *listed*. DWD lists a run as soon as its first files are
there, so it may still be incomplete. Use [`query.latest_run()`](#runs-and-complete-data)
for the newest run that has everything you ask for. DWD keeps runs for about a day:
8 runs for ICON-EU, 32 for ICON-D2-RUC.

## Selecting

`select()` describes what to download. It checks the names and options right away, but
does not look at runs yet, so one query can be used with several runs.

```python
query = icon_eu.select("T_2M", steps=["6h"])
query = icon_eu.select(["T_2M", "PMSL"], steps=Every("0h", "24h", "3h"))
print(query)
# Query('icon-eu', ['T_2M', 'PMSL'], steps=Every(start='0h', stop='24h', every='3h'))
```

Anything left out means "all of it": every step, every level, every member.

### Forecast steps

Steps are **durations** since the run started. ICON-D2 publishes some fields every
15 minutes and ICON-D2-RUC every 5, so a plain number would be ambiguous and is refused.

```python
steps="6h"                        # exactly this step
steps=["0h", "3h", "6h"]          # exactly these
steps=Every("0h", "48h", "3h")    # every 3 hours, both ends included
steps=Between("0h", "48h")        # whatever exists in the interval
steps="all"                       # everything published

steps="15m"                       # minutes, for ICON-D2 and ICON-D2-RUC
steps="1h30m"                     # hours and minutes together
steps=Every("0h", "2h", "15m")    # every 15 minutes for the first 2 hours

steps=hours(0, 6, 12, 18)         # from plain numbers
steps=hours(range(0, 121, 3))     # or any iterable of them
steps=minutes(0, 15, 30)          # for the sub-hourly models
```

`hours()` and `minutes()` turn a single number into a single duration, so they combine
with the others: `Every(hours(0), hours(48), hours(3))`.

The difference between `Every` and `Between` matters for
[complete runs](#runs-and-complete-data): `Every` names the steps you expect, `Between`
takes whatever is there.

### Vertical levels

```python
icon_eu.select("T", level_type="pressure", levels=[850, 500])
icon_eu.select("T", level_type="model", levels=Between(60, 74))
icon_eu.select("T_SO", level_type="soil", levels="all")
```

Levels are in hPa for pressure, the level index for model levels, metres below ground
for soil (`0.005`, `0.02`, ...).

`level_type` takes a name (`"pressure"`, `"model"`, `"soil"`) or a GRIB code (`100`). It may
be left out only while the selection is unambiguous. `T` exists on pressure and model
levels, so leaving it out raises `AmbiguousSelectionError`. A 2-D field such as `T_2M`
takes no level type at all.

Time-invariant fields such as `HSURF`, `FR_LAND`, `CLAT` and `CLON` are published under
every run with a single step, `0h`. `HHL`, the height of the model half levels, is
one of them too, but on model levels:

```python
icon_d2.select("HSURF")
icon_d2.select("HHL", level_type="model", levels="all")
```

### Ensemble members

The `-eps` models publish each member separately. Members are plain integers.

```python
eps = dwd.nwp.model("icon-eu-eps")
eps.select("T_2M", members=[1, 2, 5])
eps.select("T_2M", members=Between(1, 10))
eps.select("T_2M")                         # every member
```

`members=` on a deterministic model raises `InvalidSelectorError`.

### ICON-ART wavelengths

Two ICON-ART parameters, `SAT_BSC_DUST` and `CEIL_BSC_DUST`, are published per
wavelength (532 and 1064 nm). Leaving `wavelengths` out downloads both. Every other
parameter has no wavelengths, and giving `wavelengths=` for one raises
`InvalidSelectorError`.

```python
art = dwd.nwp.model("icon-art")
art.parameter("SAT_BSC_DUST").wavelengths   # (532, 1064)
art.select("SAT_BSC_DUST", levels=Between(100, 120), wavelengths=532)
```

## Runs and complete data

DWD publishes a run step by step over time. `download()` and `resolve()` without
`run=` use `query.latest_run()`: the newest run that has every requested field and whose
files have stopped changing for 90 seconds (`settle=`).

```python
query.latest_run()                         # Run(2026-10-27T06:00Z)
query.download("f.grib2", run="2026-10-27T00:00")   # a specific run
```

By default (`require="complete"`) a specific run that lacks a requested field raises
`IncompleteRunError`, which lists what is missing. `require="partial"` takes what is
there and lists the rest in `plan.missing`, with a warning in the log.

What "every requested field" means depends on how the steps are selected:

- **Named steps** (`Every(...)`, a list, a single step) are checked exactly: each of them
  on every requested level and member.
- **`"all"` and `Between()`** mean "what DWD has published so far". The server does not
  say which steps a run will have, so dwdopen can only notice a step that some levels or
  members have and others lack. A run that stops at +48 h on every level looks complete.

To be sure you get the full forecast, name the steps: `Every("0h", "120h", "1h")`.

If no run qualifies, `NoMatchingRunError` says why each of the newest runs was skipped:

```
no run of 'icon-eu' satisfies this query (9 runs were checked, newest first):
  run 2026-10-27T06:00:00+00:00 is missing 1 requested step(s): T_2M 999h
  run 2026-10-27T03:00:00+00:00 is missing 1 requested step(s): T_2M 999h
  ...
```

## Inspecting a plan

`resolve()` fixes a query to one run and returns a plan without downloading anything. A
plan never switches to a newer run later, so what you inspected is what you get. If DWD
deletes the run in the meantime, the download fails instead.

```python
plan = icon_eu.select("T", level_type="pressure", levels=[850, 500], steps="12h").resolve()
print(plan)
# ResolvedRequest(run=2026-10-27T06:00:00+00:00, 2 assets, 1.8 MB, T, on pressure (100),
#                 2 levels, steps 12h)
plan.assets[0]          # Asset(T, 500 hPa, 12h, 913.9 KB)
plan.total_size         # bytes to download
plan.missing            # what require="partial" left out
plan.download("t.grib2")
```

## Downloading

```python
query.download("forecast.grib2")                    # one file
query.download("forecast/")                         # one file, with a generated name
query.download("params/", combine="parameter")      # one file per parameter
query.download("members/", combine="member")        # one file per ensemble member
query.download("forecast/", combine="none")         # one file per GRIB message, as on the server
```

A destination ending in `/`, or an existing directory, gets a generated name. It contains
the model, run, parameters, level type, steps and a short hash of the selection:

```python
plan.suggested_name()
# 'icon-eu_2026-10-27T0600_TOT_PREC+T_2M_single_0h-24h_ec484355.grib2'
```

`~` means your home directory: `download("~/data/")`.

Combined files are sorted time-major (all fields of one step, then the next), which is
the order CDO expects.

### Already downloaded files

Files are skipped instead of downloaded again in two cases:

- A combined file with a **generated name** that already exists. The hash in the name
  says it was made from the same selection and run.
- `combine="none"`: each file whose size matches the server and that starts with `GRIB`
  and ends with `7777`.

A user-specified file name, such as `"forecast.grib2"`, is always downloaded again and
replaced. `DownloadResult.assets_skipped` says how many were already there, which is
worth checking in a scheduled job.

### Safety and speed

Downloads run concurrently. Each file is written to a temporary name and renamed into
place, so a partial file is never mistaken for a finished one, and several processes can
write to the same directory at once. Interrupted downloads clean up after themselves.
`temp_dir=` puts the temporary files elsewhere, for example on a fast scratch disk.

Directory listings are tried up to 3 times when the server times out, drops the
connection or answers with 429 or 5xx.

## Regridding

DWD publishes every model on the unstructured triangular ICON grid.
The files have one dimension of cells and no latitude/longitude axes. To get a regular
lat-lon grid, regrid with [CDO](https://code.mpimet.mpg.de/projects/cdo).

### DWD's ready-made weights

DWD provides target grids and weights in
[weather/lib/cdo](https://opendata.dwd.de/weather/lib/cdo/) for two grids:

- the ICON global grid, which AICON uses too
- the ICON-D2 grid, which ICON-D2-EPS, ICON-D2-RUC and ICON-D2-RUC-EPS use too

```bash
# ICON and AICON, 0.25° world. For 0.125°, replace 025 with 0125 everywhere:
# in the archive name and in both file names inside it.
curl -O https://opendata.dwd.de/weather/lib/cdo/ICON_GLOBAL2WORLD_025_EASY.tar.bz2
tar -xjf ICON_GLOBAL2WORLD_025_EASY.tar.bz2
w=ICON_GLOBAL2WORLD_025_EASY
cdo -f nc remap,$w/target_grid_world_025.txt,$w/weights_icogl2world_025.nc t_2m.grib2 t_2m.nc

# ICON-D2, 0.02°. Despite its name this archive is not compressed: use tar -xf
curl -O https://opendata.dwd.de/weather/lib/cdo/ICON_D2_002_EASY.tar.bz2
tar -xf ICON_D2_002_EASY.tar.bz2
w=ICON_D2_002_EASY
cdo -f nc remap,$w/target_grid_icon_d2_002.txt,$w/weights_icon_d2_002.nc t_2m.grib2 t_2m.nc
```

The ICON-D2 domain is not a lat-lon rectangle, so the corners of the result are missing
values.

### ICON-EU and the others: from CLAT and CLON

For ICON-EU, ICON-EU-EPS, ICON-EPS and the ICON-ART models DWD has no ready-made weights.
Every model except AICON publishes the cell centres as the time-invariant fields `CLAT`
and `CLON`, and CDO can use those. The models have different grids, even an ensemble
and its deterministic model (ICON-EU-EPS is coarser than ICON-EU), so download them once
per model:

```python
icon_eu.select(["CLAT", "CLON"]).download("icon-eu_coords.grib2")
```

Turn them into a CDO grid description, once:

```bash
coords=icon-eu_coords.grib2
{
  echo "gridtype = unstructured"
  echo "gridsize = $(cdo -s ngridpoints -selname,CLAT $coords | head -1)"
  echo "xvals = $(cdo -s outputf,%.5f,1 -selname,CLON $coords | tr '\n' ' ')"
  echo "yvals = $(cdo -s outputf,%.5f,1 -selname,CLAT $coords | tr '\n' ' ')"
} > icon-eu_grid.txt
```

Describe the lat-lon grid you want, for example 0.0625° over the ICON-EU area, in
`europe.txt`:

```
gridtype = lonlat
xsize    = 1377
ysize    = 657
xfirst   = -23.5
xinc     = 0.0625
yfirst   = 29.5
yinc     = 0.0625
```

Then regrid any file of that model:

```bash
cdo -f nc remapnn,europe.txt -setgrid,icon-eu_grid.txt t_2m.grib2 t_2m.nc
```

`remapnn` takes the nearest cell and `remapdis` an inverse distance average. Methods
that need the cell corners, such as `remapcon`, need the full grid file instead.

Keep the target grid inside the model's area. Outside of it, `remapnn` can copy the
nearest edge cell instead of leaving the point empty, so the values there look valid
but are not.

## Caching

Directory listings are cached to keep the number of requests to the server low. The
structure of a model (parameters, level types, levels) is kept for the lifetime of the
`DWD` client, because it only changes when DWD changes the model. Runs and steps change
all the time as runs are published and deleted, so they are read again for every call.
One `resolve()` sees one consistent view of the server.

## Logging

dwdopen logs through the `dwdopen` logger and by default prints what it downloads.

```python
import logging, dwdopen

dwdopen.set_log_level(logging.DEBUG)    # a line per file
dwdopen.set_log_level(logging.WARNING)  # only retries and warnings
dwdopen.set_log_level(None)             # no dwdopen output of its own
```

## Errors

Every error dwdopen raises is a `DWDOpenError`, so one `except DWDOpenError` catches them
all. Below it:

- `CatalogueError`: the server could not be read (`CatalogueUnavailableError`), or a
  model or parameter does not exist (`UnknownModelError`, `UnknownParameterError`).
- `SelectionError`: the selection is wrong (`InvalidSelectorError`) or needs a level type
  (`AmbiguousSelectionError`). Raised by `select()`, before anything is downloaded.
- `ResolutionError`: no run fits (`NoMatchingRunError`), a run lacks fields
  (`IncompleteRunError`), a run or file is gone (`RunExpiredError`, `MissingAssetError`).
- `DownloadError`: a download failed.
- `ClientClosedError`: the client was used after its `with` block.
