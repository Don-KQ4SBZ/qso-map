import os
import re
import urllib.request
import urllib.parse

data = urllib.parse.urlencode({
    "KEY": os.environ["QRZ_API_KEY"],
    "ACTION": "FETCH"
}).encode()

request = urllib.request.Request(
    "https://logbook.qrz.com/api",
    data=data
)

with urllib.request.urlopen(request, timeout=60) as response:
    result = urllib.parse.parse_qs(
        response.read().decode(),
        keep_blank_values=True
    )

print("API status:", result.get("RESULT"))
print("Record count:", result.get("COUNT"))
print("ADIF length:", len(result.get("ADIF", [""])[0]))

adif = result.get("ADIF", [""])[0]

if not adif:
    raise SystemExit("No ADIF data received")

print("QSOs retrieved:", len(re.findall(r"<EOR>", adif, re.I)))
print("Latitude fields:", len(re.findall(r"<LAT:", adif, re.I)))
print("Longitude fields:", len(re.findall(r"<LON:", adif, re.I)))
print("Grid squares:", len(re.findall(r"<GRIDSQUARE:", adif, re.I)))
