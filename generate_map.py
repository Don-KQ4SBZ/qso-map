    origin = location(
        record, "MY_LAT", "MY_LON", "MY_GRIDSQUARE"
    )

    if origin is None:
        origin = home
        estimated_origins += 1
