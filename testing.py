from dwdopen import DWD

with DWD() as dwd:
    print(dwd.nwp.models())
    icon_eu = dwd.nwp.model("icon-eu")
    print(icon_eu.parameters())
    print(icon_eu.latest_run(probe="T_2M"))


from pathlib import Path

from dwdopen._fileserver.http import HttpClient
from dwdopen._fileserver.listing import parse_listing
from dwdopen._fileserver.paths import build_path

http = HttpClient("https://opendata.dwd.de")
try:
    where = (("m", "icon-eu"), ("p", "T_2M"))

    runs = parse_listing(http.get_listing(build_path(*where, key="r")))
    print(runs)
    run = runs[-1].name
    print(run)

    steps = parse_listing(http.get_listing(build_path(*where, ("r", run), key="s")))
    print(f"run {run}: {len(steps)} steps, first is {steps[0].name}")

    data = http.get_asset(
        build_path(*where, ("r", run), ("s", steps[0].name), directory=False)
    )
    Path("C:\\Users\\Christoph\\xygrib\\grib\\t2m.grib2").write_bytes(data)
    print(f"{len(data)} bytes, starts with {data[:4]!r}, ends with {data[-4:]!r}")
finally:
    http.close()