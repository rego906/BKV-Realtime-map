from flask import Flask, jsonify, render_template, send_from_directory, abort
import requests
from google.transit import gtfs_realtime_pb2
import os
import threading
import time

# --- A PROJEKT ALAP MAPPÁJA ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- TEMPLATE FOLDER ÉS IKON FOLDER ---
app = Flask(__name__, template_folder="templates")
ICON_DIR = os.path.join(BASE_DIR, "icons")

API_KEY = "5ad47c1d-0b29-4a6e-854e-ef21b2b76f94"
PB_URL  = f"https://go.bkk.hu/api/query/v1/ws/gtfs-rt/full/VehiclePositions.pb?key={API_KEY}"
TXT_URL = f"https://go.bkk.hu/api/query/v1/ws/gtfs-rt/full/VehiclePositions.txt?key={API_KEY}"

# ---------------------------
# CACHE + BACKGROUND REFRESH
# ---------------------------
CACHE_LOCK = threading.Lock()
VEHICLES_CACHE = {
    "ts": 0,
    "data": [],
    "ok": False,
    "error": None
}

REFRESH_SECONDS = 30


@app.route("/icons/<path:filename>")
def icons(filename):
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
    """Kiegészítő TXT feed feldolgozása rendszám és típus információhoz."""
    try:
        text = requests.get(TXT_URL, timeout=15).text
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
    """Egyszeri letöltés + feldolgozás, visszaadja a listát."""
    txt_map = parse_txt_feed()
    feed = gtfs_realtime_pb2.FeedMessage()
    out = []

    r = requests.get(PB_URL, timeout=10)
    r.raise_for_status()
    feed.ParseFromString(r.content)

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
    """Háttérszál: 30 másodpercenként frissíti a cache-t."""
    while True:
        try:
            data = fetch_vehicles_once()
            with CACHE_LOCK:
                VEHICLES_CACHE["data"] = data
                VEHICLES_CACHE["ts"] = int(time.time())
                VEHICLES_CACHE["ok"] = True
                VEHICLES_CACHE["error"] = None
        except Exception as e:
            # Ha hiba van, a korábbi cache marad, csak jelöljük a hibát
            with CACHE_LOCK:
                VEHICLES_CACHE["ok"] = False
                VEHICLES_CACHE["error"] = str(e)

        time.sleep(REFRESH_SECONDS)


@app.route("/vehicles")
def vehicles():
    """Mindig a memóriában lévő cache-t adja vissza (gyors)."""
    with CACHE_LOCK:
        return jsonify({
            "ts": VEHICLES_CACHE["ts"],
            "ok": VEHICLES_CACHE["ok"],
            "error": VEHICLES_CACHE["error"],
            "data": VEHICLES_CACHE["data"],
        })


def start_background_refresh():
    t = threading.Thread(target=refresh_loop, daemon=True)
    t.start()


# --- Flask indítása Renderhez ---
if __name__ == "__main__":
    start_background_refresh()
    # induláskor érdemes egy első frissítést is megpróbálni (ne legyen üres az oldal):
    try:
        first = fetch_vehicles_once()
        with CACHE_LOCK:
            VEHICLES_CACHE["data"] = first
            VEHICLES_CACHE["ts"] = int(time.time())
            VEHICLES_CACHE["ok"] = True
            VEHICLES_CACHE["error"] = None
    except Exception as e:
        with CACHE_LOCK:
            VEHICLES_CACHE["ok"] = False
            VEHICLES_CACHE["error"] = str(e)

    app.run(host="0.0.0.0", port=5001, debug=True)
