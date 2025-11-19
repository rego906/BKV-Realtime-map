from flask import Flask, jsonify, render_template, send_from_directory, abort
import requests
from google.transit import gtfs_realtime_pb2
import os

# Templates mappa automatikus kezelése
app = Flask(__name__, template_folder="templates")

# API kulcs + feed URL-ek
API_KEY = "5ad47c1d-0b29-4a6e-854e-ef21b2b76f94"
PB_URL  = f"https://go.bkk.hu/api/query/v1/ws/gtfs-rt/full/VehiclePositions.pb?key={API_KEY}"
TXT_URL = f"https://go.bkk.hu/api/query/v1/ws/gtfs-rt/full/VehiclePositions.txt?key={API_KEY}"

# Ikonok helye → MOST MÁR MINDENHOL MŰKÖDIK (Render, Linux, Windows)
ICON_DIR = os.path.join(os.path.dirname(__file__), "icons")


@app.route("/icons/<path:filename>")
def icons(filename):
    """Kiszolgálja az ikonokat az icons mappából."""
    # Auto-keresi .png nélkül és .png-vel is
    candidates = [filename, filename + ".png", filename + ".png.png"]
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
    except Exception as e:
        print("❌ Hiba a .txt feed letöltésénél:", e)
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
    print(f"🧩 TXT kiegészítés betöltve: {len(mapping)} jármű.")
    return mapping


@app.route("/vehicles")
def vehicles():
    """GTFS-RT járműadatok JSON formában a frontend számára."""
    txt_map = parse_txt_feed()
    feed = gtfs_realtime_pb2.FeedMessage()
    out = []

    try:
        r = requests.get(PB_URL, timeout=10)
        r.raise_for_status()
        feed.ParseFromString(r.content)
    except Exception as e:
        print("❌ Hiba a .pb feed letöltésénél:", e)
        return jsonify([])

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

    print(f"✅ /vehicles: {len(out)} jármű küldve a kliensnek.")
    return jsonify(out)


# Lokál futtatás (Render NEM ezt használja)
if __name__ == "__main__":
    print("🚍 BKK járműkövető fut: http://127.0.0.1:5001")
    print(f"📁 Ikonmappa: {ICON_DIR}")

    app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False)
