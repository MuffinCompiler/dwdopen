# Changelog

Versions follow [semantic versioning](https://semver.org/).

## 0.3.0

- `combine="parameter"` implemented which writes one file per parameter. Refactored
   the combining so it can conceptually group by any "group" now.
- `runs()` and `latest_run()` no longer need parameter and level type. Using some
   2-D fields as basic "probing" parameters, that are available on all models DWD offers.

## 0.2.3

- Added proper logging, and print some download info by default, so users do not think
  that the application hangs.
- Generated file names now contain the level type.
- Asking for a parameter on a level type it is not available on is now refused at
  the `select()` stage.

## 0.2.2

- README updated.
- Releases now publish automatically from a version tag.

## 0.2.1

- Lowered floor to Python 3.11.
- Packaging: added project URLs.
- Simplified some code and sugar.
- Moved from pre-alpha to alpha, added this changelog.

## 0.2.0

- Add support to download ensemble members. `members=` on `select()`, taking a number,
  a list, `Between`, `Every` or `"all"`.
- **`combine="member"`** writes one combined file per member, each named after it.
- Plans report members in their repr and in generated file names.

## 0.1.5

- Already-downloaded files are skipped. A file counts as done when its size matches
  the catalogue and it starts with `GRIB` and ends with `7777`.
- Generated file names end in a hash of the plan, which is what makes the check possible.
- `DownloadResult.assets_skipped` reports on how much has been skipped and how much needs
  to transfer.
- Interrupted downloads clean up the temporary folder(s).

## 0.1.4

- Added support for time-invariant fields.

## 0.1.3

- Generated file names. Give `combine="all"` a directory and it names the file after the
  model, run, selection and step range.
- `ResolvedRequest` and `Asset` print a readable summary instead of listing every asset.

## 0.1.2

- Model and parameter names are matched ignoring case, so `t_2m` and `T_2M` both work.
- `hours()` and `minutes()` convenience functions from plain numbers.
- A bare number as a step is refused with a message, as it might be ambiguous.

## 0.1.1

- Vertical levels: `level_type=` and `levels=`, in hPa for pressure, indices for model
  levels and metres for soil.
- `AmbiguousSelectionError` when a parameter exists on several level types and none was
  named.
- Level listings are fetched concurrently.

## 0.1.0

- First release. Model and parameter discovery, step selection, run resolution, and
  parallel downloads with atomic writes.
- Messages in a combined file are sorted time-major.
