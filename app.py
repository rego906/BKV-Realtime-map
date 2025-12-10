from flask import Flask, jsonify, render_template, send_from_directory, abort
import requests, os
from google.transit import gtfs_realtime_pb2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(BASE_DIR, "icons")

app = Flask(__name__, template_folder="templates")

API_KEY = "5ad47c1d-0b29-4a6e-854e-ef21b2b76f94"
PB_URL  = f"https://go.bkk.hu/api/query/v1/ws/gtfs-rt/full/VehiclePositions.pb?key={API_KEY}"
TXT_URL = f"https://go.bkk.hu/api/query/v1/ws/gtfs-rt/full/VehiclePositions.txt?key={API_KEY}"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/icons/<path:filename>")
def icons(filename):
    safe = (
        filename
        .replace("é","e")
        .replace("É","E")
        .replace("%C3%A9","e")
    )

    for name in [filename, safe]:
        path = os.path.join(ICON_DIR, name)
        if os.path.exists(path):
            return send_from_directory(ICON_DIR, name)

    abort(404)

def parse_txt():
    try:
        text = requests.get(TXT_URL, timeout=10).text
    except:
        return {}

    data = {}
    current_id = None

    for line in text.splitlines():
        l = line.strip()
        if l.startswith('id: "'):
            current_id = l.split('"')[1]
            data[current_id] = {
                "license_plate": "N/A",
                "vehicle_model": "N/A"
            }
        elif current_id and 'license_plate:' in l:
            data[current_id]["license_plate"] = l.split('"')[1]
        elif current_id and 'vehicle_model:' in l:
            data[current_id]["vehicle_model"] = l.split('"')[1]

    return data

@app.route("/vehicles")
def vehicles():
    txt_map = parse_txt()
    feed = gtfs_realtime_pb2.FeedMessage()
    out = []

    try:
        r = requests.get(PB_URL, timeout=10)
        feed.ParseFromString(r.content)
    except:
        return jsonify([])

    for e in feed.entity:
        if not e.HasField("vehicle"):
            continue
        v = e.vehicle
        if not v.HasField("position"):
            continue

        vid = getattr(v.vehicle, "id", None)
        extra = txt_map.get(vid, {})

        out.append({
            "vehicle_id": vid,
            "route_id": getattr(v.trip, "route_id", "N/A"),
            "destination": getattr(v.vehicle, "label", "N/A"),
            "license_plate": extra.get("license_plate", "N/A"),
            "vehicle_model": extra.get("vehicle_model", "N/A"),
            "latitude": v.position.latitude,
            "longitude": v.position.longitude
        })

    return jsonify(out)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
