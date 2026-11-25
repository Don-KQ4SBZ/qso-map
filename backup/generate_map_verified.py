import os
import re
import urllib.request
import urllib.parse
import html

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

print("Response size:", len(raw))
print("Total QSOs retrieved:", len(records))
print("Latitude fields:", len(re.findall(r"<LAT:", decoded, re.I)))
print("Longitude fields:", len(re.findall(r"<LON:", decoded, re.I)))
print("Grid squares:", len(re.findall(r"<GRIDSQUARE:", decoded, re.I)))

if not records:
    raise SystemExit("No QSO records extracted")

print("QRZ contact retrieval successful!")
