from flask import Flask, jsonify, render_template, send_from_directory, abort
import requests
from google.transit import gtfs_realtime_pb2
import os
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(BASE_DIR, "icons")

app = Flask(__name__, template_folder="templates")

API_KEY = "5ad47c1d-0b29-4a6e-854e-ef21b2b76f94"
PB_URL  = f"https://go.bkk.hu/api/query/v1/ws/gtfs-rt/full/VehiclePositions.pb?key={API_KEY}"
TXT_URL = f"https://go.bkk.hu/api/query/v1/ws/gtfs-rt/full/VehiclePositions.txt?key={API_KEY}"

HEADERS = {"User-Agent": "bkk-realtime-map/1.0"}
REFRESH_SECONDS = 30

CACHE_LOCK = threading.Lock()
VEHICLES_CACHE = []   # mindig LISTA
CACHE_TS = 0
LAST_ERROR = None
_started = False


@app.route("/icons/<path:filename>")
def icons(filename):
    """Kiszolgálja az ikonokat az icons mappából. Kérés: /icons/busz -> busz vagy busz.png"""
    candidates = [filename, filename + ".png"]
    for name in candidates:
        full_path = os.path.join(ICON_DIR, name)
        if os.path.exists(full_path):
            return send_from_directory(ICON_DIR, name)
    abort(404)


@app.route("/")
def index():
    return render_template("index.html")


def parse_txt_feed():
    """TXT feed feldolgozása rendszám + típus információhoz."""
    try:
        text = requests.get(TXT_URL, timeout=20, headers=HEADERS).text
    except Exception:
        return {}

    mapping = {}
    current = {"id": None, "license_plate": None, "vehicle_model": None}

    def commit():
        if current["id"]:
            mapping[current["id"]] = {
                "license_plate": current["license_plate"] or "N/A",
                "vehicle_model": current["vehicle_model"] or "N/A",
            }

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('id: "'):
            commit()
            current = {"id": line.split('"')[1], "license_plate": None, "vehicle_model": None}
        elif line.startswith('license_plate: "'):
            current["license_plate"] = line.split('"')[1]
        elif 'vehicle_model:' in line:
            parts = line.split('"')
            if len(parts) >= 2:
                current["vehicle_model"] = parts[1]

    commit()
    return mapping


def fetch_vehicles_once():
    """PB+TXT letöltés és lista összeállítás."""
    txt_map = parse_txt_feed()

    r = requests.get(PB_URL, timeout=15, headers=HEADERS)
    r.raise_for_status()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(r.content)

    out = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        mv = entity.vehicle
        if not mv.HasField("position"):
            continue

        vehicle_id = getattr(mv.vehicle, "id", None)
        route_id = getattr(mv.trip, "route_id", "N/A")
        lat = getattr(mv.position, "latitude", None)
        lon = getattr(mv.position, "longitude", None)
        destination = getattr(mv.vehicle, "label", "N/A")

        try:
            lat = float(lat) if lat is not None else None
            lon = float(lon) if lon is not None else None
        except Exception:
            lat, lon = None, None

        license_plate = txt_map.get(vehicle_id, {}).get("license_plate", "N/A")
        vehicle_model = txt_map.get(vehicle_id, {}).get("vehicle_model", "N/A")

        out.append({
            "vehicle_id": vehicle_id,
            "route_id": route_id,
            "destination": destination,
            "license_plate": license_plate,
            "vehicle_model": vehicle_model,
            "latitude": lat,
            "longitude": lon
        })

    return out


def refresh_loop():
    global VEHICLES_CACHE, CACHE_TS, LAST_ERROR
    while True:
        try:
            data = fetch_vehicles_once()
            with CACHE_LOCK:
                VEHICLES_CACHE = data
                CACHE_TS = int(time.time())
                LAST_ERROR = None
        except Exception as e:
            with CACHE_LOCK:
                LAST_ERROR = repr(e)
        time.sleep(REFRESH_SECONDS)


def start_background_refresh_once():
    global _started, VEHICLES_CACHE, CACHE_TS, LAST_ERROR
    if _started:
        return
    _started = True

    # cold start: töltsünk azonnal, hogy ne legyen üres
    try:
        data = fetch_vehicles_once()
        with CACHE_LOCK:
            VEHICLES_CACHE = data
            CACHE_TS = int(time.time())
            LAST_ERROR = None
    except Exception as e:
        with CACHE_LOCK:
            LAST_ERROR = repr(e)

    threading.Thread(target=refresh_loop, daemon=True).start()


@app.before_request
def ensure_started():
    # Gunicorn/Render alatt biztosan indul az első kérésnél
    start_background_refresh_once()


@app.route("/vehicles")
def vehicles():
    # FONTOS: listát ad vissza (a frontend ezt várja)
    with CACHE_LOCK:
        return jsonify(VEHICLES_CACHE)


@app.route("/status")
def status():
    # Debug, ha kell: Renderen lásd, frissül-e és van-e hiba
    with CACHE_LOCK:
        return jsonify({"ts": CACHE_TS, "count": len(VEHICLES_CACHE), "error": LAST_ERROR})


if __name__ == "__main__":
    start_background_refresh_once()
    port = int(os.getenv("PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=True)
