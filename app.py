import os, sqlite3
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, session,
    url_for, jsonify, Response
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import cv2
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort

# Flask setup
app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DB_FILE = "zones.db"

# YOLO + DeepSORT
model = YOLO("yolov8n.pt")
tracker = DeepSort(max_age=30)

# --------- DB Init ---------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        email TEXT,
        password TEXT,
        contact TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS zones(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT,
        x1 INTEGER, y1 INTEGER, x2 INTEGER, y2 INTEGER,
        threshold INTEGER
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS counts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zone_id INTEGER,
        count INTEGER,
        detected_at TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

# --------- Helper: login_required ---------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper

def get_zones():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id,label,x1,y1,x2,y2,threshold FROM zones")
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": r[0], "label": r[1],
         "coords": [(r[2], r[3]), (r[4], r[5])],
         "threshold": r[6]} for r in rows
    ]

def log_count(zone_id, count):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT INTO counts(zone_id,count,detected_at) VALUES (?,?,?)",
                (zone_id, count, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# --------- Auth Routes ---------
@app.route("/")
def home():
    return redirect("/login")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        u = request.form["username"]
        e = request.form["email"]
        p = request.form["password"]
        cp = request.form["confirm_password"]
        c = request.form["contact"]

        if p != cp:
            return "Passwords do not match"

        # ✅ Correct hashing method
        hashed_pw = generate_password_hash(p, method="pbkdf2:sha256")

        try:
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute("INSERT INTO users(username,email,password,contact) VALUES (?,?,?,?)",
                        (u, e, hashed_pw, c))
            conn.commit()
            conn.close()
        except Exception as ex:
            return f"Error: {ex}"

        return redirect("/login")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT id, password FROM users WHERE username=?", (u,))
        row = cur.fetchone()
        conn.close()

        if row and check_password_hash(row[1], p):  # ✅ verify hash
            session["user"] = u
            return redirect("/index")
        return "Invalid username or password"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# --------- Index Page (Upload + Zones) ---------
@app.route("/index")
@login_required
def index():
    return render_template("index.html", user=session["user"], video_file=session.get("video_file"))

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    f = request.files["video"]
    filename = secure_filename(f.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    f.save(path)
    session["video_file"] = filename
    return redirect("/index")

# --------- Zones API ---------
@app.route("/zones", methods=["GET", "POST", "DELETE"])
@login_required
def zones():
    if request.method == "POST":
        d = request.json
        (x1, y1), (x2, y2) = d["coordinates"]
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("INSERT INTO zones(label,x1,y1,x2,y2,threshold) VALUES (?,?,?,?,?,?)",
                    (d["label"], x1, y1, x2, y2, d["threshold"]))
        conn.commit()
        conn.close()
        return jsonify({"status": "saved"})

    if request.method == "DELETE":
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT id FROM zones ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            cur.execute("DELETE FROM zones WHERE id=?", (row[0],))
            conn.commit()
            conn.close()
            return jsonify({"status": "deleted"})
        conn.close()
        return jsonify({"status": "no_zones"})

    return jsonify(get_zones())

@app.route("/zone_counts")
@login_required
def zone_counts():
    zones = get_zones()
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    counts = {}
    total = 0
    for z in zones:
        cur.execute("SELECT count FROM counts WHERE zone_id=? ORDER BY id DESC LIMIT 1", (z["id"],))
        row = cur.fetchone()
        c = int(row[0]) if row else 0
        counts[z["label"]] = c
        total += c
    conn.close()

    alerts = []
    for z in zones:
        if counts.get(z["label"], 0) > z["threshold"]:
            alerts.append(f"⚠ Zone {z['label']} exceeded threshold")

    return jsonify({"total": total, "zones": counts, "alerts": alerts})

# --------- Streaming ---------
def stream(path):
    cap = cv2.VideoCapture(path)
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        res = model(frame, verbose=False)
        dets = []
        for r in res:
            for b in r.boxes:
                if int(b.cls[0]) == 0:
                    x1, y1, x2, y2 = map(int, b.xyxy[0])
                    dets.append(([x1, y1, x2 - x1, y2 - y1], float(b.conf[0]), "person"))

        tracks = tracker.update_tracks(dets, frame=frame)
        for t in tracks:
            if not t.is_confirmed():
                continue
            tx1, ty1, tx2, ty2 = map(int, t.to_ltrb())
            cv2.rectangle(frame, (tx1, ty1), (tx2, ty2), (0, 255, 0), 2)
            cv2.putText(frame, f"ID {t.track_id}", (tx1, ty1 - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        zones = get_zones()
        for z in zones:
            (x1, y1), (x2, y2) = z["coords"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
            cv2.putText(frame, z["label"], (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
            cnt = 0
            for t in tracks:
                if not t.is_confirmed():
                    continue
                a1, b1, a2, b2 = map(int, t.to_ltrb())
                cx, cy = (a1 + a2) // 2, (b1 + b2) // 2
                if x1 <= cx <= x2 and y1 <= cy <= y2:
                    cnt += 1
            log_count(z["id"], cnt)

        _, buf = cv2.imencode(".jpg", frame)
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")
    cap.release()

@app.route("/process")
@login_required
def process():
    if "video_file" not in session:
        return "No video"
    return Response(stream(os.path.join(UPLOAD_FOLDER, session["video_file"])),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

# --------- Live Dashboard (Charts) ---------
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("live_dashboard.html", user=session["user"])

@app.route("/chart_data")
@login_required
def chart_data():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""SELECT z.label, c.count, c.detected_at
                   FROM counts c JOIN zones z ON z.id = c.zone_id
                   ORDER BY c.id DESC LIMIT 50""")
    rows = cur.fetchall()
    conn.close()
    return jsonify(rows)

if __name__ == "__main__":
    app.run(debug=True)



















