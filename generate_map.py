import os
import re
import math
import html
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

records = re.findall(
    r"<CALL:\d+[^>]*>.*?<EOR>",
    decoded,
    re.I | re.S
)

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
        r"[A-R]{2}[0-9]{2}([A-X]{2})?([0-9]{2})?",
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

colors = {
    "160M": "#795548",
    "80M": "#9c27b0",
    "60M": "#607d8b",
    "40M": "#2196f3",
    "30M": "#00bcd4",
    "20M": "#2e7d32",
    "17M": "#8bc34a",
    "15M": "#ff9800",
    "12M": "#e91e63",
    "10M": "#f44336",
    "6M": "#673ab7",
    "2M": "#009688",
    "70CM": "#455a64"
}

home = grid_center("FM16UE")

m = folium.Map(
    location=home,
    zoom_start=3,
    tiles="CartoDB positron",
    control_scale=True,
    world_copy_jump=True
)

folium.TileLayer(
    "OpenStreetMap",
    name="Street Map"
).add_to(m)

Fullscreen().add_to(m)
MeasureControl(
    primary_length_unit="miles",
    secondary_length_unit="kilometers"
).add_to(m)

layers = {}
callsigns = set()
countries = set()
origins = set()

mapped = 0
estimated_origins = 0
longest_distance = 0
longest_call = ""

for record in records:

    call = field(record, "CALL")
    band = field(record, "BAND").upper() or "UNKNOWN"
    country = field(record, "COUNTRY")

    destination = location(
        record, "LAT", "LON", "GRIDSQUARE"
    )

    origin = location(
        record, "MY_LAT", "MY_LON", "MY_GRIDSQUARE"
    )

    if origin is None:
        origin = home
        estimated_origins += 1

    if destination is None:
        continue

    callsigns.add(call)

    if country:
        countries.add(country)

    miles = distance(origin, destination)

    if miles > longest_distance:
        longest_distance = miles
        longest_call = call

    color = colors.get(band, "#888888")

    if band not in layers:
        layers[band] = folium.FeatureGroup(
            name=band,
            show=True
        )
        layers[band].add_to(m)

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

    popup += f"Distance: {miles:,.0f} miles"

    folium.PolyLine(
        [origin, destination],
        color=color,
        weight=1.5,
        opacity=0.45
    ).add_to(layers[band])

    folium.CircleMarker(
        destination,
        radius=4,
        color=color,
        fill=True,
        fill_opacity=0.85,
        tooltip=html.escape(call),
        popup=folium.Popup(popup, max_width=300)
    ).add_to(layers[band])

    if origin not in origins:
        folium.Marker(
            origin,
            tooltip="KQ4SBZ Transmitting Location",
            icon=folium.Icon(
                color="red",
                icon="home"
            )
        ).add_to(m)

        origins.add(origin)

    mapped += 1

if mapped == 0:
    raise SystemExit("No mappable contacts found")

folium.LayerControl(collapsed=False).add_to(m)

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
    color: #222;
    padding: 15px;
    border: 1px solid #aaa;
    border-radius: 8px;
    font-family: Arial, sans-serif;
    font-size: 13px;
    box-shadow: 0 2px 8px #0003;
">
    <strong style="font-size: 18px;">
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
    Last Updated:<br>{updated}
</div>
"""

m.get_root().html.add_child(folium.Element(stats))

Path("public").mkdir(exist_ok=True)
m.save("public/index.html")

print("Total QSOs retrieved:", len(records))
print("QSOs mapped:", mapped)
print("Unique callsigns:", len(callsigns))
print("Countries:", len(countries))
print("Estimated transmitting locations:", estimated_origins)
print("Interactive map generated successfully!")
