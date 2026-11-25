import os
import re
import urllib.request
import urllib.parse

data = urllib.parse.urlencode({
    "KEY": os.environ["QRZ_API_KEY"],
    "ACTION": "FETCH",
    "OPTION": "ALL,TYPE:ADIF"
}).encode()

request = urllib.request.Request(
    "https://logbook.qrz.com/api",
    data=data,
    headers={
        "User-Agent": "KQ4SBZ-LiveQSOMap/1.0 (KQ4SBZ)"
    }
)

with urllib.request.urlopen(request, timeout=60) as response:
    result = urllib.parse.parse_qs(response.read().decode())

if result.get("RESULT", [""])[0] != "OK":
    raise SystemExit("QRZ retrieval failed")

adif = result.get("ADIF", [""])[0]

if not adif:
    raise SystemExit("No ADIF data received")

records = re.findall(r"<EOR>", adif, re.IGNORECASE)

print("QRZ retrieval successful")
print("QSOs retrieved:", len(records))
print("ADIF size:", len(adif), "characters")
print("Latitude fields:", len(re.findall(r"<LAT:", adif, re.I)))
print("Longitude fields:", len(re.findall(r"<LON:", adif, re.I)))
print("Grid square fields:", len(re.findall(r"<GRIDSQUARE:", adif, re.I)))
