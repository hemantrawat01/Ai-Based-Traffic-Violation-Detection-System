"""
Stolen Vehicle Detection & Surveillance System (SV-DSS) - Web Application.
Provides RESTful APIs, low-latency multi-camera MJPEG video streaming,
Server-Sent Events (SSE) real-time alert broadcasts, and responsive tactical command center UI.
"""

import os
import io
import time
import json
import csv
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, send_from_directory
import cv2
import numpy as np

import database
import alpr_engine
import alert_manager
from traffic_simulator import stream_manager

app = Flask(__name__)
app.config["SECRET_KEY"] = "police-surveillance-secure-key-2026"
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Initialize database on startup
database.init_db()


# ==========================================
# PAGE ROUTES
# ==========================================

@app.route("/")
def index():
    """Police Command Center Dashboard."""
    return render_template("index.html")


@app.route("/hotlist")
def hotlist_page():
    """Stolen Vehicle Database & Case Management."""
    return render_template("hotlist.html")


@app.route("/scanner")
def scanner_page():
    """Static Image & Video File Scanner Tool."""
    return render_template("scanner.html")


@app.route("/alerts")
def alerts_page():
    """Incident Alert Feed, Evidence Dossiers & Interceptions."""
    return render_template("alerts_history.html")


@app.route("/analytics")
def analytics_page():
    """Surveillance Analytics, Heatmaps & Reports."""
    return render_template("analytics.html")


@app.route("/map")
def map_page():
    """Tactical City GIS Surveillance Map."""
    return render_template("map.html")


@app.route("/api/map/data")
def get_map_gis_data():
    """Return comprehensive GIS surveillance data: cameras, FOV cones, patrol units, and pursuit corridors."""
    cameras = database.get_all_cameras()
    
    # Enrich cameras with geographic FOV polygons and stream URLs
    enriched_cams = []
    fov_offsets = {
        "CAM-01": [[0.005, -0.004], [0.007, 0.004]],
        "CAM-02": [[0.006, -0.005], [0.008, 0.003]],
        "CAM-03": [[-0.005, -0.004], [-0.007, 0.003]],
        "CAM-04": [[0.004, 0.005], [0.007, 0.003]]
    }
    
    for c in cameras:
        cid = c["id"]
        lat = c["latitude"]
        lng = c["longitude"]
        offsets = fov_offsets.get(cid, [[0.005, -0.003], [0.005, 0.003]])
        fov_polygon = [
            [lat, lng],
            [lat + offsets[0][0], lng + offsets[0][1]],
            [lat + offsets[1][0], lng + offsets[1][1]]
        ]
        enriched_cams.append({
            "id": cid,
            "name": c["name"],
            "location_name": c["location_name"],
            "lat": lat,
            "lng": lng,
            "status": c["status"],
            "mode": c["mode"],
            "total_scans": c["total_scans"],
            "hotlist_hits": c["hotlist_hits"],
            "stream_url": f"/api/stream/{cid}",
            "fov_cone": fov_polygon
        })

    patrol_units = [
        {
            "id": "UNIT-101",
            "callsign": "Interceptor Alpha",
            "type": "Pursuit Cruiser",
            "lat": 28.6180,
            "lng": 77.2010,
            "status": "ON_PATROL",
            "officer": "Sgt. Miller & Off. Vance",
            "zone": "Downtown Sector 4"
        },
        {
            "id": "UNIT-204",
            "callsign": "Highway Interceptor 7",
            "type": "High-Speed Interceptor",
            "lat": 28.6920,
            "lng": 77.1120,
            "status": "READY_STANDBY",
            "officer": "Lt. Chen",
            "zone": "Interstate 44 Tollway"
        },
        {
            "id": "UNIT-305",
            "callsign": "Expressway Rapid Response",
            "type": "Tactical SUV",
            "lat": 28.5680,
            "lng": 77.1080,
            "status": "EN_ROUTE",
            "officer": "Off. Ramirez",
            "zone": "Airport Expressway Corridor"
        },
        {
            "id": "UNIT-412",
            "callsign": "East Corridor Patrol",
            "type": "Standard Cruiser",
            "lat": 28.6310,
            "lng": 77.2690,
            "status": "ON_PATROL",
            "officer": "Off. Washington",
            "zone": "East Industrial District"
        }
    ]

    corridors = [
        {
            "name": "Interstate Transit Corridor (CAM-01 to CAM-02)",
            "route": [
                [28.6139, 77.2090],
                [28.6350, 77.1850],
                [28.6650, 77.1450],
                [28.7041, 77.1025]
            ],
            "speed_limit": "80 km/h",
            "status": "ACTIVE_MONITORING"
        },
        {
            "name": "Airport Expressway Flyover (CAM-01 to CAM-03)",
            "route": [
                [28.6139, 77.2090],
                [28.5850, 77.1650],
                [28.5562, 77.1000]
            ],
            "speed_limit": "90 km/h",
            "status": "HIGH_ALERT"
        },
        {
            "name": "East Industrial Bypass (CAM-01 to CAM-04)",
            "route": [
                [28.6139, 77.2090],
                [28.6250, 77.2450],
                [28.6353, 77.2785]
            ],
            "speed_limit": "60 km/h",
            "status": "ACTIVE_MONITORING"
        }
    ]

    # Recent hotlist alerts
    recent_alerts = database.get_alerts(limit=10)

    return jsonify({
        "status": "success",
        "cameras": enriched_cams,
        "patrol_units": patrol_units,
        "corridors": corridors,
        "recent_alerts": recent_alerts
    })


# ==========================================
# VIDEO STREAMING ENDPOINTS
# ==========================================

def generate_stream_frames(camera_id):
    """Generator for MJPEG stream."""
    while True:
        try:
            frame_bytes = stream_manager.get_frame(camera_id)
            if frame_bytes:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
            time.sleep(0.04) # ~25 FPS
        except Exception as e:
            time.sleep(0.1)


@app.route("/api/stream/<camera_id>")
def video_stream(camera_id):
    """Live MJPEG video stream with real-time ALPR bounding box overlay."""
    return Response(
        generate_stream_frames(camera_id),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/api/cameras", methods=["GET"])
def get_cameras():
    """Get all surveillance camera nodes."""
    cameras = database.get_all_cameras()
    return jsonify({"status": "success", "cameras": cameras})


@app.route("/api/cameras/<camera_id>/inject", methods=["POST"])
def inject_stolen_vehicle(camera_id):
    """Force-inject a stolen vehicle into a camera's video stream."""
    data = request.get_json() or {}
    plate = data.get("plate_number")
    success = stream_manager.inject_hotlist_vehicle(camera_id, plate)
    return jsonify({"status": "success" if success else "error", "camera_id": camera_id, "injected_plate": plate})


@app.route("/api/cameras/<camera_id>/mode", methods=["POST"])
def set_camera_mode(camera_id):
    """Toggle between simulation and hardware webcam mode."""
    data = request.get_json() or {}
    mode = data.get("mode", "simulation")
    enable_webcam = (mode == "webcam")
    ok = stream_manager.toggle_webcam(camera_id, enable_webcam)
    return jsonify({"status": "success" if ok else "error", "mode": mode, "camera_id": camera_id})


# ==========================================
# REAL-TIME SERVER-SENT EVENTS (SSE)
# ==========================================

@app.route("/api/events")
def sse_events():
    """Server-Sent Events endpoint streaming real-time hotlist alerts to clients."""
    def event_stream():
        q = alert_manager.subscribe_events()
        try:
            # Send initial keepalive
            yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'timestamp': datetime.now().isoformat()})}\n\n"
            while True:
                try:
                    msg = q.get(timeout=25.0)
                    yield msg
                except Exception:
                    # Keepalive ping to prevent connection timeout
                    yield f": keepalive\n\n"
        finally:
            alert_manager.unsubscribe_events(q)

    return Response(event_stream(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive"
    })


@app.route("/api/alerts/test", methods=["POST"])
def trigger_manual_test_alert():
    """Trigger a test alert for audio/visual siren verification."""
    test_veh = {
        "id": 1,
        "plate_number": "KA05MB9821",
        "make": "Honda",
        "model": "Civic",
        "color": "Midnight Black",
        "year": 2022,
        "status": "STOLEN",
        "severity": "CRITICAL",
        "case_number": "FIR-2026-8819",
        "reporting_station": "Metro South Precinct",
        "owner_name": "Arjun Sharma",
        "notes": "ARMED CARJACKING TEST DRILL"
    }
    alert_id = alert_manager.trigger_vehicle_alert(
        camera_id="CAM-01",
        camera_name="Downtown Sector 4 - Central Ave",
        detected_plate="KA05MB9821",
        ocr_conf=0.98,
        vehicle_info=test_veh,
        match_score=1.0,
        snapshot_path="/static/sample_images/sample_1_stolen_civic.jpg",
        crop_path="/static/sample_images/sample_1_stolen_civic.jpg"
    )
    return jsonify({"status": "success", "alert_id": alert_id})


# ==========================================
# HOTLIST DATABASE CRUD API
# ==========================================

@app.route("/api/hotlist", methods=["GET"])
def list_hotlist():
    """List stolen vehicles with optional search and filters."""
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()
    vehicles = database.get_all_stolen_vehicles(
        search_query=search if search else None,
        status_filter=status if status and status != "ALL" else None
    )
    return jsonify({"status": "success", "count": len(vehicles), "vehicles": vehicles})


@app.route("/api/hotlist/<int:vehicle_id>", methods=["GET"])
def get_hotlist_item(vehicle_id):
    """Get single stolen vehicle dossier."""
    veh = database.get_stolen_vehicle_by_id(vehicle_id)
    if not veh:
        return jsonify({"status": "error", "message": "Vehicle not found"}), 404
    return jsonify({"status": "success", "vehicle": veh})


@app.route("/api/hotlist", methods=["POST"])
def create_hotlist_item():
    """Add a new stolen or wanted vehicle to the database."""
    data = request.get_json()
    if not data or not data.get("plate_number"):
        return jsonify({"status": "error", "message": "License plate number is required"}), 400

    try:
        new_id = database.add_stolen_vehicle(data)
        alert_manager.broadcast_event("HOTLIST_UPDATED", {"action": "added", "vehicle_id": new_id})
        return jsonify({"status": "success", "vehicle_id": new_id, "message": "Vehicle added to hotlist successfully"}), 201
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/hotlist/<int:vehicle_id>", methods=["PUT"])
def update_hotlist_item(vehicle_id):
    """Update stolen vehicle information."""
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    try:
        database.update_stolen_vehicle(vehicle_id, data)
        alert_manager.broadcast_event("HOTLIST_UPDATED", {"action": "updated", "vehicle_id": vehicle_id})
        return jsonify({"status": "success", "message": "Vehicle updated successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/hotlist/<int:vehicle_id>", methods=["DELETE"])
def delete_hotlist_item(vehicle_id):
    """Delete or archive stolen vehicle."""
    database.delete_stolen_vehicle(vehicle_id)
    alert_manager.broadcast_event("HOTLIST_UPDATED", {"action": "deleted", "vehicle_id": vehicle_id})
    return jsonify({"status": "success", "message": "Vehicle removed from hotlist"})


@app.route("/api/hotlist/seed", methods=["POST"])
def reseed_hotlist():
    """Reset database and seed original demo records."""
    conn = database.get_db_connection()
    conn.execute("DELETE FROM stolen_vehicles")
    conn.commit()
    database.seed_initial_data(conn)
    conn.close()
    return jsonify({"status": "success", "message": "Database successfully reseeded with standard cases"})


# ==========================================
# ALERTS & INCIDENT MANAGEMENT API
# ==========================================

@app.route("/api/alerts", methods=["GET"])
def list_alerts():
    """Get active and historical alerts."""
    status = request.args.get("status", "ALL")
    limit = int(request.args.get("limit", 50))
    alerts = database.get_alerts(status_filter=status, limit=limit)
    return jsonify({"status": "success", "count": len(alerts), "alerts": alerts})


@app.route("/api/alerts/<int:alert_id>/status", methods=["POST"])
def update_alert(alert_id):
    """Update incident status: DISPATCHED, INTERCEPTED, FALSE_POSITIVE, RESOLVED."""
    data = request.get_json() or {}
    new_status = data.get("status", "INTERCEPTED")
    officer = data.get("officer", "Patrol Unit")
    notes = data.get("notes", "")

    database.update_alert_status(alert_id, new_status, dispatched_officer=officer, dispatch_notes=notes)
    alert_manager.broadcast_event("ALERT_STATUS_CHANGED", {
        "alert_id": alert_id,
        "new_status": new_status,
        "officer": officer,
        "notes": notes
    })
    return jsonify({"status": "success", "alert_id": alert_id, "new_status": new_status})


# ==========================================
# STATIC IMAGE / FILE SCANNER API
# ==========================================

@app.route("/api/samples", methods=["GET"])
def list_samples():
    """List pre-generated vehicle samples for instant testing."""
    sample_dir = os.path.join(os.path.dirname(__file__), "static", "sample_images")
    files = []
    if os.path.exists(sample_dir):
        for fname in os.listdir(sample_dir):
            if fname.lower().endswith((".jpg", ".png", ".jpeg")):
                files.append({
                    "filename": fname,
                    "url": f"/static/sample_images/{fname}",
                    "name": fname.replace("sample_", "").replace(".jpg", "").replace("_", " ").title()
                })
    return jsonify({"status": "success", "samples": files})


@app.route("/api/scan", methods=["POST"])
def scan_image():
    """
    Process an uploaded image or sample path:
    Runs ALPR detection and cross-references against the police hotlist.
    """
    frame = None

    # Check for sample image path
    sample_path = request.form.get("sample_path")
    if sample_path:
        local_path = os.path.join(os.path.dirname(__file__), sample_path.lstrip("/\\"))
        if os.path.exists(local_path):
            frame = cv2.imread(local_path)

    # Check for file upload
    if frame is None and "file" in request.files:
        file = request.files["file"]
        if file.filename:
            file_bytes = np.frombuffer(file.read(), np.uint8)
            frame = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

    if frame is None or frame.size == 0:
        return jsonify({"status": "error", "message": "No valid image provided for scanning"}), 400

    # Process through ALPR Engine
    annotated, detections = alpr_engine.process_frame(
        frame,
        camera_id="MANUAL-SCAN",
        camera_name="Forensic Image Upload Scanner",
        save_snapshots=True
    )

    # Save annotated result image
    out_name = f"scan_result_{int(time.time() * 1000)}.jpg"
    out_rel = f"/static/snapshots/{out_name}"
    out_abs = os.path.join(os.path.dirname(__file__), "static", "snapshots", out_name)
    cv2.imwrite(out_abs, annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])

    # If any detection was a match, trigger alert record
    for det in detections:
        if det["is_match"] and det["vehicle"]:
            alert_manager.trigger_vehicle_alert(
                camera_id="MANUAL-SCAN",
                camera_name="Forensic Image Upload Scanner",
                detected_plate=det["plate_number"],
                ocr_conf=det["confidence"],
                vehicle_info=det["vehicle"],
                match_score=det["match_score"],
                snapshot_path=out_rel,
                crop_path=det["crop_path"]
            )

    return jsonify({
        "status": "success",
        "detections_count": len(detections),
        "detections": detections,
        "annotated_image_url": out_rel
    })


# ==========================================
# ANALYTICS & EXPORT API
# ==========================================

@app.route("/api/analytics", methods=["GET"])
def get_analytics():
    """Aggregate statistics for charts and command center overview."""
    stats = database.get_system_analytics()
    return jsonify({"status": "success", "analytics": stats})


@app.route("/api/export/csv")
def export_csv():
    """Export complete surveillance detection logs as downloadable CSV."""
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT d.id, d.camera_id, d.camera_name, d.timestamp, d.detected_plate,
               d.ocr_confidence, d.is_match, d.matched_plate, d.match_score,
               v.make, v.model, v.color, v.status, v.case_number
        FROM detections d
        LEFT JOIN stolen_vehicles v ON d.stolen_vehicle_id = v.id
        ORDER BY d.id DESC LIMIT 1000
    """)
    rows = cursor.fetchall()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow([
        "Scan ID", "Camera ID", "Camera Location", "Timestamp", "Detected Plate",
        "OCR Confidence", "Is Hotlist Hit", "Matched Plate", "Similarity Score",
        "Vehicle Make", "Vehicle Model", "Vehicle Color", "Police Status", "Case Number"
    ])

    for r in rows:
        cw.writerow([
            r["id"], r["camera_id"], r["camera_name"], r["timestamp"], r["detected_plate"],
            r["ocr_confidence"], "YES" if r["is_match"] else "NO", r["matched_plate"] or "N/A",
            r["match_score"], r["make"] or "N/A", r["model"] or "N/A", r["color"] or "N/A",
            r["status"] or "CLEAN", r["case_number"] or "N/A"
        ])

    output = io.BytesIO(si.getvalue().encode("utf-8"))
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=Surveillance_Audit_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"}
    )


# ==========================================
# SETTINGS API
# ==========================================

@app.route("/api/settings", methods=["GET", "POST"])
def handle_settings():
    if request.method == "POST":
        data = request.get_json() or {}
        for k, v in data.items():
            database.update_setting(k, v)
        return jsonify({"status": "success", "message": "Settings updated"})
    else:
        return jsonify({"status": "success", "settings": database.get_settings()})


if __name__ == "__main__":
    print("\n" + "=" * 65)
    print(" [AEGIS-ALPR] STOLEN VEHICLE SURVEILLANCE COMMAND CENTER")
    print(" Law Enforcement Real-Time Plate Interception & Alert System")
    print(" Access Web Dashboard at: http://127.0.0.1:5000")
    print("=" * 65 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
