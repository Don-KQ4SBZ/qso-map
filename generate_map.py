import os
import re
import urllib.request
import urllib.parse
import html

data = urllib.parse.urlencode({
    "KEY": os.environ["QRZ_API_KEY"],
    "ACTION": "FETCH",
    "OPTION": "MAX:1"
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

result = urllib.parse.parse_qs(raw, keep_blank_values=True)
decoded = html.unescape(urllib.parse.unquote(raw))

print("API status:", result.get("RESULT"))
print("Record count:", result.get("COUNT"))
print("Response length:", len(raw))
print("ADIF field present:", "ADIF" in result)
print("ADIF length:", len(result.get("ADIF", [""])[0]))
print("QSO records detected:", len(re.findall(r"<EOR>", decoded, re.I)))
print("Reason field present:", "REASON" in result)
