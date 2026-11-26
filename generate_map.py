import os
import re
import math
import html
import json
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

import folium
from folium.plugins import Fullscreen, MeasureControl

# Retrieve QRZ logbook
data = urllib.parse.urlencode({
    "KEY": os.environ["QRZ_API_KEY"],
    "ACTION": "FETCH",
    "OPTION": "ALL"
}).encode()

request = urllib.request.Request(
    "https://logbook.qrz.com/api",
    data=data,
    headers={
        "User-Agent": "KQ4SBZ-LiveQSOMap/1.0"
    }
)

with urllib.request.urlopen(request, timeout=60) as response:
    raw = response.read().decode()

decoded = html.unescape(urllib.parse.unquote(raw))

def parse_records(text):
    return [
        record
        for record in re.split(r"<EOR>", text, flags=re.I)
        if re.search(r"<CALL:\d+", record, re.I)
    ]

records = parse_records(decoded)

if not records:
    raise SystemExit("No QSO records extracted")

def field(record, name):
    match = re.search(
        rf"<{name}:(\d+)(?::[^>]*)?>",
        record,
        re.I
    )
    if not match:
        return ""
    start = match.end()
    return record[start:start + int(match.group(1))].strip()

def coordinate(value):
    try:
        return float(value)
    except ValueError:
        pass

    match = re.fullmatch(
        r"([NSEW])\s*(\d+)\s+([\d.]+)",
        value.strip(),
        re.I
    )

    if not match:
        return None

    direction, degrees, minutes = match.groups()
    result = float(degrees) + float(minutes) / 60

    if direction.upper() in ("S", "W"):
        result = -result

    return result

def grid_center(grid):
    grid = grid.strip().upper()

    if not re.fullmatch(
        r"[A-R]{2}[0-9]{2}([A-X]{2}([0-9]{2})?)?",
        grid
    ):
        return None

    lon = (ord(grid[0]) - 65) * 20 - 180
    lat = (ord(grid[1]) - 65) * 10 - 90

    lon += int(grid[2]) * 2
    lat += int(grid[3])

    width = 2
    height = 1

    if len(grid) >= 6:
        width /= 24
        height /= 24
        lon += (ord(grid[4]) - 65) * width
        lat += (ord(grid[5]) - 65) * height

    if len(grid) == 8:
        width /= 10
        height /= 10
        lon += int(grid[6]) * width
        lat += int(grid[7]) * height

    return lat + height / 2, lon + width / 2

def location(record, lat_field, lon_field, grid_field):
    lat = coordinate(field(record, lat_field))
    lon = coordinate(field(record, lon_field))

    if lat is not None and lon is not None:
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon

    return grid_center(field(record, grid_field))

def distance(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)

    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2)
        * math.sin((lon2 - lon1) / 2) ** 2
    )

    return 3958.76 * 2 * math.asin(
        math.sqrt(min(1, h))
    )

# Transmitting locations
CAMDEN = (36.3463161687504, -76.16453613386902)
HERTFORD = (36.172102, -76.281502)
MOVE_DATE = "20251219"

# Load POTA activation log
pota_file = Path("KQ4SBZ@US-8299-07142026.adi")

if not pota_file.is_file():
    raise SystemExit("POTA activation file not found")

pota_records = parse_records(
    pota_file.read_text(encoding="utf-8-sig")
)

if not pota_records:
    raise SystemExit("No POTA contacts extracted")

POTA = location(
    pota_records[0],
    "MY_LAT",
    "MY_LON",
    "MY_GRIDSQUARE"
)

if POTA is None:
    raise SystemExit("POTA station coordinates not found")

# Identify duplicate contacts across both logs
def qso_key(record):
    return (
        field(record, "CALL").upper(),
        field(record, "QSO_DATE"),
        field(record, "TIME_ON")[:4],
        field(record, "BAND").upper()
    )

pota_keys = {
    qso_key(record)
    for record in pota_records
}

# Prefer the POTA record when it exists in both logs
duplicates = sum(
    1 for record in records
    if qso_key(record) in pota_keys
)

records = [
    record for record in records
    if qso_key(record) not in pota_keys
]

records.extend(pota_records)

# Amateur bands: highest to lowest frequency
colors = {
    "70CM": "#34495e",
    "1.25M": "#ff4500",
    "2M": "#008b8b",
    "4M": "#daa520",
    "5M": "#4682b4",
    "6M": "#673ab7",
    "8M": "#c71585",
    "10M": "#e60000",
    "12M": "#e91e63",
    "15M": "#ff8800",
    "17M": "#76b900",
    "20M": "#008000",
    "30M": "#00bcd4",
    "40M": "#0066ff",
    "60M": "#607d8b",
    "80M": "#9c27b0",
    "160M": "#795548"
}

carto_url = os.environ["CARTO_TILE_URL"].strip()

m = folium.Map(
    location=HERTFORD,
    zoom_start=3,
    tiles=None,
    control_scale=True,
    world_copy_jump=True,
    zoom_snap=0.25,
    zoom_delta=0.5
)

folium.TileLayer(
    tiles=carto_url,
    attr='&copy; OpenStreetMap contributors &copy; CARTO',
    name="CARTO Voyager",
    overlay=False,
    control=True,
    show=True,
    max_zoom=19
).add_to(m)

folium.TileLayer(
    "OpenStreetMap",
    name="Street Map",
    show=False
).add_to(m)

# Preserve existing basemap appearance
m.get_root().header.add_child(folium.Element("""
<style>
.leaflet-tile-pane {
    filter: saturate(1.65) contrast(1.15) brightness(0.98);
}
</style>
"""))

Fullscreen().add_to(m)

MeasureControl(
    primary_length_unit="miles",
    secondary_length_unit="kilometers"
).add_to(m)

# Create active band layers in frequency order
active_bands = {
    field(record, "BAND").upper() or "UNKNOWN"
    for record in records
}

ordered_bands = [
    band for band in colors
    if band in active_bands
]

ordered_bands.extend(
    sorted(active_bands - set(colors))
)

layers = {}

for band in ordered_bands:
    layers[band] = folium.FeatureGroup(
        name=band,
        show=True
    )
    layers[band].add_to(m)

callsigns = set()
countries = set()
bounds = [CAMDEN, HERTFORD, POTA]

mapped = 0
camden_count = 0
hertford_count = 0
pota_count = 0
missing_dates = 0
longest_distance = 0
longest_call = ""
mapped_bands = set()

for record in records:

    call = field(record, "CALL")
    band = field(record, "BAND").upper() or "UNKNOWN"
    country = field(record, "COUNTRY")
    qso_date = field(record, "QSO_DATE")

    if country == "United States of America":
        country = "United States"

    destination = location(
        record, "LAT", "LON", "GRIDSQUARE"
    )

    if destination is None:
        continue

    if not re.fullmatch(r"\d{8}", qso_date):
        missing_dates += 1
        continue

    if qso_key(record) in pota_keys:
        origin = POTA
        station = "POTA US-8299, NY"
        pota_count += 1

    elif qso_date < MOVE_DATE:
        origin = CAMDEN
        station = "Camden, NC"
        camden_count += 1

    else:
        origin = HERTFORD
        station = "Hertford, NC"
        hertford_count += 1

    bounds.append(destination)
    callsigns.add(call.upper())
    mapped_bands.add(band)

    if country:
        countries.add(country)

    miles = distance(origin, destination)

    if miles > longest_distance:
        longest_distance = miles
        longest_call = call

    color = colors.get(band, "#888888")

    popup = "<b>" + html.escape(call) + "</b><br>"

    for label, tag in [
        ("Country", "COUNTRY"),
        ("Date", "QSO_DATE"),
        ("Time UTC", "TIME_ON"),
        ("Band", "BAND"),
        ("Frequency MHz", "FREQ"),
        ("Mode", "MODE"),
        ("Grid", "GRIDSQUARE"),
        ("RST Sent", "RST_SENT"),
        ("RST Received", "RST_RCVD")
    ]:
        value = field(record, tag)
        if value:
            popup += (
                html.escape(label) + ": "
                + html.escape(value) + "<br>"
            )

    popup += f"Transmitting Station: {station}<br>"
    popup += f"Distance: {miles:,.0f} miles"

    folium.PolyLine(
        [origin, destination],
        color=color,
        weight=2,
        opacity=0.75
    ).add_to(layers[band])

    folium.CircleMarker(
        destination,
        radius=5,
        color=color,
        weight=1.5,
        fill=True,
        fill_color=color,
        fill_opacity=0.95,
        tooltip=html.escape(call),
        popup=folium.Popup(popup, max_width=300)
    ).add_to(layers[band])

    mapped += 1

if mapped == 0:
    raise SystemExit("No mappable contacts found")

# Remove empty band layers
for band in list(layers):
    if band not in mapped_bands:
        m._children.pop(layers[band].get_name(), None)
        del layers[band]

folium.Marker(
    CAMDEN,
    tooltip="KQ4SBZ - Former Station, Camden, NC",
    popup=folium.Popup(
        f"<b>KQ4SBZ - Camden, NC</b><br>"
        f"Former transmitting station<br>"
        f"Before December 19, 2025<br>"
        f"QSOs: {camden_count}",
        max_width=300
    ),
    icon=folium.Icon(color="red", icon="home")
).add_to(m)

folium.Marker(
    HERTFORD,
    tooltip="KQ4SBZ - Current Station, Hertford, NC",
    popup=folium.Popup(
        f"<b>KQ4SBZ - Hertford, NC</b><br>"
        f"Current transmitting station<br>"
        f"December 19, 2025 onward<br>"
        f"QSOs: {hertford_count}",
        max_width=300
    ),
    icon=folium.Icon(color="red", icon="home")
).add_to(m)

folium.Marker(
    POTA,
    tooltip="KQ4SBZ - POTA US-8299",
    popup=folium.Popup(
        f"<b>KQ4SBZ - POTA US-8299</b><br>"
        f"Parks on the Air activation<br>"
        f"New York, USA<br>"
        f"July 14, 2026<br>"
        f"Grid: FN13XB<br>"
        f"QSOs: {pota_count}",
        max_width=300
    ),
    icon=folium.Icon(
        color="green",
        icon="tree",
        prefix="fa"
    )
).add_to(m)

# Automatically frame all contacts
m.fit_bounds(
    [
        [
            min(point[0] for point in bounds),
            min(point[1] for point in bounds)
        ],
        [
            max(point[0] for point in bounds),
            max(point[1] for point in bounds)
        ]
    ],
    padding=(60, 60),
    max_zoom=4
)

folium.LayerControl(collapsed=False).add_to(m)

# Match band checkbox colors to lines and pins
band_colors = {
    band: colors.get(band, "#888888")
    for band in layers
}

checkbox_script = """
<script>
document.addEventListener("DOMContentLoaded", function () {
    const bandColors = BAND_COLORS;

    function colorBandCheckboxes() {
        document.querySelectorAll(
            ".leaflet-control-layers-overlays label"
        ).forEach(function (label) {
            const band = label.textContent.trim().toUpperCase();

            const checkbox = label.querySelector(
                'input[type="checkbox"]'
            );

            if (checkbox && bandColors[band]) {
                checkbox.style.accentColor = bandColors[band];
            }
        });
    }

    colorBandCheckboxes();

    const observer = new MutationObserver(
        colorBandCheckboxes
    );

    document.querySelectorAll(
        ".leaflet-control-layers-overlays"
    ).forEach(function (container) {
        observer.observe(container, {
            childList: true,
            subtree: true
        });
    });
});
</script>
""".replace("BAND_COLORS", json.dumps(band_colors))

m.get_root().html.add_child(
    folium.Element(checkbox_script)
)

updated = datetime.now(timezone.utc).strftime(
    "%Y-%m-%d %H:%M UTC"
)

stats = f"""
<div style="
    position: fixed;
    bottom: 25px;
    left: 15px;
    z-index: 9999;
    background: white;
    color: #172334;
    padding: 15px;
    border: 2px solid #164b75;
    border-radius: 8px;
    font-family: Arial, sans-serif;
    font-size: 13px;
    box-shadow: 0 2px 8px #0004;
">
    <strong style="font-size: 18px; color:#164b75;">
        KQ4SBZ Live QSO Map
    </strong>
    <hr>
    Total QSOs: <b>{len(records)}</b><br>
    Mapped QSOs: <b>{mapped}</b><br>
    Unique Callsigns: <b>{len(callsigns)}</b><br>
    Countries Worked: <b>{len(countries)}</b><br>
    Bands: <b>{len(layers)}</b><br>
    Longest Contact: <b>{html.escape(longest_call)}</b><br>
    Distance: <b>{longest_distance:,.0f} miles</b><br>
    <hr>
    Camden QSOs: <b>{camden_count}</b><br>
    Hertford QSOs: <b>{hertford_count}</b><br>
    POTA QSOs: <b>{pota_count}</b><br>
    Transmitting Stations: <b>3</b><br>
    <hr>
    Last Updated:<br>{updated}
</div>
"""

m.get_root().html.add_child(
    folium.Element(stats)
)

Path("public").mkdir(exist_ok=True)
m.save("public/index.html")

print("Total QSOs:", len(records))
print("QSOs mapped:", mapped)
print("Unique callsigns:", len(callsigns))
print("Countries:", len(countries))
print("Camden QSOs:", camden_count)
print("Hertford QSOs:", hertford_count)
print("POTA QSOs:", pota_count)
print("Cross-log duplicates removed:", duplicates)
print("Contacts skipped for missing dates:", missing_dates)
print("Transmitting stations: 3")
print("Interactive map generated successfully!")
