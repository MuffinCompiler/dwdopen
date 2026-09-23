import internal_api_mock

dwd = internal_api_mock.DWD()

# Discover available models
models = dwd.nwp.models()
icon_eu = dwd.nwp.model("icon-eu")

# Discover parameters
parameters = icon_eu.parameters()
t_info = icon_eu.parameter("T").describe()

# Super simple query
q = icon_eu.select(
    parameters="T_2M",
    steps="12h", # should that mean until 12h or every 12h TODO
)
# Everything the first 48h
q = icon_eu.select(
    parameters="T_2M",
    steps=slice("0h", "48h"),
)
# Only every 3h in the range
q = icon_eu.select(
    parameters="T_2M",
    steps=("0h", "48h", "3h"),
)

# Native model levels
q_model = icon_eu.select(
    parameters=["T", "U", "V"],
    level_type="model",
    levels="all",
    steps=slice("0h", "48h"),
)

# Pressure levels, in hPa TODO check if pressure levels are continued.
q_pressure = icon_eu.select(
    parameters=["T", "U", "V", "RELHUM"],
    level_type="pressure",
    levels=[850, 700, 500, 300],
    steps=("0h", "48h", "3h"),
)

# half-level data should also work like this?
q_hhl = icon_eu.select(
    parameters="HHL",
    levels="all",
)

# Surface products
q_surface = icon_eu.select(
    parameters=["PMSL", "T_2M", "TOT_PREC"],
    steps=slice("0h", "48h"),
)

# Composition of queries
q_all = q_model | q_surface | q_hhl

# Get the latest run for which the download is completely available
run = q_all.latest_run(require="complete")

# Resolve the query for the given run, creates a "plan" containing the files to download
# Resolving should give us also flexibility with potential API changes (EDR subsetting...)
plan = q_all.resolve(run=run)

# Download the plan
result = plan.download(
    "icon-eu.grib2",
    combine="all",
)

# Convenience to directly download the query
result = q_all.download(
    "icon-eu.grib2",
    run="latest",
    require="complete",
    combine="all",
)

# ICON-D2 precip has a grib message every 15min
icon_d2 = dwd.nwp.model("icon-d2")

q = icon_d2.select(
    parameters="TOT_PREC",
    steps=("0m", "48h", "15m"),
)
result = q.download(
    "icon-d2-tot-prec.grib2",
    run="latest",
    combine="all",
)

# ICON D2 RUC native 5-minute precipitation
ruc = dwd.nwp.model("icon-d2-ruc")

q = ruc.select(
    parameters=["TOT_PREC", "PREC_GSP"],
    steps=("0m", "6h", "5m"),
)
result = q.download(
    "ruc-precip.grib2",
    run="latest",
    combine="all",
)


# Ensemble: selected members
eps = dwd.nwp.model("icon-eu-eps")

q = eps.select(
    parameters="T_2M",
    members=[1, 2, 5],
    steps=slice("0h", "48h"),
)
result = q.download(
    "eps-selected.grib2",
    run="latest",
    combine="all", #  combine="member" to have one file per ens member
)


#Soil levels
icon = dwd.nwp.model("icon")
q = icon.select(
    parameters="T_SO",
    level_type="soil",
    levels="all",
    steps=slice("0h", "48h"),
)


# ICON ART composition, TODO check docs again if that is sufficient
art = dwd.nwp.model("icon-art")

q_532 = art.select(
    parameters="SAT_BSC_DUST",
    wavelength=532,
    level_type="model",
    levels=[20, 30, 40],
)

q_1064 = art.select(
    parameters="SAT_BSC_DUST",
    wavelength=1064,
    level_type="model",
    levels=[20, 30, 40],
)

q = q_532 | q_1064


# Check what happens before downloading
plan = q_all.resolve(run="latest")

print(plan.run)
print(plan.catalogue_time)
print(len(plan.assets)) # num files
print(plan.missing)
for asset in plan.assets[:5]:
    print(asset.url)

# Merge per parameter
result = q_all.download(
    "by-parameter-data/",
    run="latest",
    combine="parameter",
)

# This should throw some AmbiguousSelectionError as T isnt resolvable to an unambigious dataset
# (as avail on different level types)
icon_eu.select(parameters="T", levels=[30, 40]).resolve()