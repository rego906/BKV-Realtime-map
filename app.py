from flask import Flask, jsonify, render_template, send_from_directory, abort
import requests, os
from google.transit import gtfs_realtime_pb2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(BASE_DIR, "icons")

app = Flask(__name__, template_folder="templates")

API_KEY = "IDE_A_SAJAT_API_KULCSOD"
PB_URL  = f"https://go.bkk.hu/api/query/v1/ws/gtfs-rt/full/VehiclePositions.pb?key={API_KEY}"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/icons/<path:filename>")
def icons(filename):
    # ékezet normalizálás
    safe = (
        filename
        .replace("é", "e")
        .replace("É", "E")
        .replace("%C3%A9", "e")
    )

    for name in [filename, safe]:
        path = os.path.join(ICON_DIR, name)
        if os.path.exists(path):
            return send_from_directory(ICON_DIR, name)

    abort(404)

@app.route("/vehicles")
def vehicles():
    feed = gtfs_realtime_pb2.FeedMessage()
    out = []

    try:
        r = requests.get(PB_URL, timeout=10)
        r.raise_for_status()
        feed.ParseFromString(r.content)
    except Exception as e:
        print(e)
        return jsonify([])

    for e in feed.entity:
        if not e.HasField("vehicle"):
            continue
        v = e.vehicle
        if not v.HasField("position"):
            continue

        out.append({
            "vehicle_id": getattr(v.vehicle, "id", None),
            "route_id": getattr(v.trip, "route_id", "N/A"),
            "license_plate": getattr(v.vehicle, "label", "N/A"),
            "latitude": v.position.latitude,
            "longitude": v.position.longitude
        })

    return jsonify(out)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
