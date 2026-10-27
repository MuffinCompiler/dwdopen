# dwdopen

Python library to download numerical weather prediction (NWP) data from
[DWD Open Data](https://opendata.dwd.de/). List currently available models,
parameters, and runs. Select what data you want and download it as GRIB2 file(s).

> Still in alpha, the API may change before 1.0. See the [roadmap](#roadmap).

## Install

Requires Python 3.11 or newer.

```bash
pip install dwdopen
```

## Quickstart

```python
from dwdopen import DWD, Every

with DWD() as dwd:
    icon_eu = dwd.nwp.model("icon-eu")
    query = icon_eu.select(["T_2M", "TOT_PREC"], steps=Every("0h", "24h", "3h"))
    query.download("forecast.grib2")
```

This downloads 2 m temperature and total precipitation for the next 24 hours, every
3 hours, from the newest ICON-EU run that is completely published, into one GRIB2 file.

## Discovery

```python
dwd.nwp.models()                    # ['aicon', 'icon', 'icon-art', ..., 'icon-eu-eps']
icon_eu.parameters()                # ['ALB_RAD', 'ALHFL_S', ..., 'T_2M', ...]
icon_eu.parameter("T")              # on pressure (100) and model (150) levels
icon_eu.levels("T", "pressure")     # [50, 70, 100, ..., 850, ..., 1000]  (hPa)
icon_eu.runs()                      # [..., Run(2026-10-27T06:00Z)], oldest first
```

## Examples

These continue inside the `with DWD() as dwd:` block of the quickstart.

Upper air: temperature on 850 and 500 hPa at +12 h.

```python
upper_air = icon_eu.select("T", level_type="pressure", levels=[850, 500], steps=["12h"])
upper_air.download("t.grib2")
```

Ensemble: the first 5 members of ICON-EU-EPS, one file per member, into a directory.

```python
from dwdopen import Between

eps = dwd.nwp.model("icon-eu-eps")
ensemble = eps.select("T_2M", members=Between(1, 5), steps="24h")
ensemble.download("members/", combine="member")
```

A scheduled job: give a directory instead of a file name, and the file is named after
the model, run and selection. Running the job again for the same run downloads nothing.
`query` is the one from the quickstart.

```python
result = query.download("/data/icon-eu/")
# /data/icon-eu/icon-eu_2026-10-27T0600_TOT_PREC+T_2M_single_0h-24h_ec484355.grib2
result.assets_skipped   # 18 on the second run: the file was already there
```

Look before you download: `resolve()` freezes a query against one run and gives you a
plan to inspect. The plan never switches to a newer run later.

```python
plan = query.resolve()
print(plan)
# ResolvedRequest(run=2026-10-27T06:00Z, 18 assets, 12.1 MB, TOT_PREC, T_2M,
#                 9 steps 0h..24h)
plan.download("forecast.grib2")
```

## The data is on the native ICON grid

DWD publishes every model on the unstructured triangular ICON grid. To get a regular
lat-lon grid, regrid with [CDO](https://code.mpimet.mpg.de/projects/cdo). For ICON
global, DWD provides ready-made weights:

```bash
# from https://opendata.dwd.de/weather/lib/cdo/ICON_GLOBAL2WORLD_025_EASY.tar.bz2
cdo -f nc remap,target_grid_world_025.txt,weights_icogl2world_025.nc t_2m.grib2 t_2m.nc
```

For ICON-EU and the other models see
[Regridding](https://github.com/MuffinCompiler/dwdopen/blob/master/docs/guide.md#regridding)
in the guide.

## Features

The [guide](https://github.com/MuffinCompiler/dwdopen/blob/master/docs/guide.md) explains
each of these in detail.

- Every ICON model on DWD Open Data: ICON, ICON-EU, ICON-D2, ICON-D2-RUC, their
  ensembles, ICON-ART and AICON. Nothing is hard-coded.
- Steps as durations: `"6h"`, `["0h", "3h"]`, `Every("0h", "48h", "3h")`,
  `Between("0h", "48h")`, `"all"`, and 15 or 5 minute steps for ICON-D2 and ICON-D2-RUC.
- Vertical levels: pressure levels in hPa, model levels and soil levels.
- Ensemble members: `members=[1, 2, 5]`, `Between(1, 10)`, or all of them.
- ICON-ART wavelengths: `wavelengths=532` for the dust backscatter fields.
- Complete runs only: by default a run that DWD is still publishing is skipped, and
  `require="partial"` takes what is there and reports the rest.
- Combining: return one file, one per parameter, one per ensemble member, or one file per
  GRIB message.
- Safe, resumable downloads: concurrent, written atomically, already downloaded files
  are skipped, with a progress bar.
- Clear errors: every error is a `DWDOpenError`, and typos in names and options are
  caught before anything is downloaded.

## Roadmap

### After 1.0

- [ ] A command-line interface.

### Long term

The goal is a complete Python interface to DWD Open Data:

- [ ] Observations and current station reports (`weather/weather_reports`).
- [ ] Radar: composites and single-site products (`weather/radar`).
- [ ] Point forecasts: MOSMIX (`weather/local_forecasts`).
- [ ] Weather warnings (`weather/alerts`).
- [ ] Satellite products (`weather/satellite`).

## License

MIT. See [LICENSE](https://github.com/MuffinCompiler/dwdopen/blob/master/LICENSE).

Forecast data itself is provided by Deutscher Wetterdienst (DWD) under its own
[terms of use](https://www.dwd.de/EN/service/copyright/copyright_node.html).
