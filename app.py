from flask import Flask, jsonify, render_template, send_from_directory, abort
import requests
from google.transit import gtfs_realtime_pb2
import os

app = Flask(__name__, template_folder="templates")

API_KEY = "5ad47c1d-0b29-4a6e-854e-ef21b2b76f94"
PB_URL  = f"https://go.bkk.hu/api/query/v1/ws/gtfs-rt/full/VehiclePositions.pb?key={API_KEY}"
TXT_URL = f"https://go.bkk.hu/api/query/v1/ws/gtfs-rt/full/VehiclePositions.txt?key={API_KEY}"

# 📁 Itt vannak a képek – pontosan ebben a mappában a duplán .png-s nevekkel
ICON_DIR = os.path.abspath(r"C:/Users/minix/Desktop/bkk2/icons")

@app.route("/icons/<path:filename>")
def icons(filename):
    # ha valaki pl. /icons/busz.png-t kér, de csak busz.png.png létezik, megtaláljuk
    candidates = [filename, filename + ".png"]
    for name in candidates:
        full_path = os.path.join(ICON_DIR, name)
        if os.path.exists(full_path):
            print(f"✅ Ikon megtalálva: {full_path}")
            return send_from_directory(ICON_DIR, name)
    print(f"❌ Ikon nem található: {filename}")
    abort(404)

@app.route("/")
def index():
    return render_template("index.html")

def parse_txt_feed():
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
        route_id   = getattr(mv.trip, "route_id", "N/A")
        lat        = getattr(mv.position, "latitude", None)
        lon        = getattr(mv.position, "longitude", None)
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

if __name__ == "__main__":
    print("🚍 BKK járműkövető fut: http://127.0.0.1:5000")
    print(f"📁 Ikonmappa: {ICON_DIR}")
    if os.path.exists(ICON_DIR):
        print("📂 Ikonok ebben a mappában:")
        for f in os.listdir(ICON_DIR):
            print("   -", f)
    else:
        print("❌ Ikonmappa nem található!")
    app.run(debug=True)
