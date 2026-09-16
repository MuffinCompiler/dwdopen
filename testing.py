from dwdopen import DWD

with DWD() as dwd:
    print(dwd.nwp.models())
    icon_eu = dwd.nwp.model("icon-eu")
    print(icon_eu.parameters())
    print(icon_eu.latest_run(probe="T_2M"))