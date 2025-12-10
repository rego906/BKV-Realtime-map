from flask import Flask, jsonify, render_template, send_from_directory, abort
import requests, os
from google.transit import gtfs_realtime_pb2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(BASE_DIR, "icons")

app = Flask(__name__, template_folder="templates")

API_KEY = "IDE_A_SAJAT_KULCSOD"
PB_URL  = f"https://go.bkk.hu/api/query/v1/ws/gtfs-rt/full/VehiclePositions.pb?key={API_KEY}"
TXT_URL = f"https://go.bkk.hu/api/query/v1/ws/gtfs-rt/full/VehiclePositions.txt?key={API_KEY}"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/icons/<path:filename>")
def icons(filename):
    path = os.path.join(ICON_DIR, filename)
    if os.path.exists(path):
        return send_from_directory(ICON_DIR, filename)
    abort(404)

def parse_txt():
    try:
        text = requests.get(TXT_URL, timeout=10).text
    except:
        return {}

    data={}
    cur={}
    for l in text.splitlines():
        l=l.strip()
        if l.startswith('id: "'):
            cur={"id":l.split('"')[1]}
            data[cur["id"]]=cur
        elif 'license_plate:' in l:
            cur["license_plate"]=l.split('"')[1]
        elif 'vehicle_model:' in l:
            cur["vehicle_model"]=l.split('"')[1]
    return data

@app.route("/vehicles")
def vehicles():
    txt=parse_txt()
    feed=gtfs_realtime_pb2.FeedMessage()
    out=[]

    try:
        r=requests.get(PB_URL,timeout=10)
        feed.ParseFromString(r.content)
    except:
        return jsonify([])

    for e in feed.entity:
        if not e.HasField("vehicle"): continue
        v=e.vehicle
        if not v.HasField("position"): continue

        vid=getattr(v.vehicle,"id",None)
        t=txt.get(vid,{})

        out.append({
            "vehicle_id": vid,
            "route_id": getattr(v.trip,"route_id","N/A"),
            "destination": getattr(v.vehicle,"label","N/A"),
            "license_plate": t.get("license_plate","N/A"),
            "vehicle_model": t.get("vehicle_model","N/A"),
            "latitude": v.position.latitude,
            "longitude": v.position.longitude
        })
    return jsonify(out)

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=5001)
