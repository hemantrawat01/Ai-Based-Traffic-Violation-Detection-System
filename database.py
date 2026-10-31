"""
Database access and ORM layer for the Stolen Vehicle Detection & Surveillance System (SV-DSS).
Handles SQLite storage for the police hotlist, real-time alerts, camera feeds, and detection logs.
"""

import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "surveillance.db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_plate_str(plate: str) -> str:
    """Normalize license plate: remove spaces, dashes, dots and convert to uppercase."""
    if not plate:
        return ""
    return "".join(ch for ch in plate if ch.isalnum()).upper()


def init_db():
    """Create database tables if they do not exist and seed initial data."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Police Hotlist / Stolen Vehicles
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stolen_vehicles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plate_number TEXT NOT NULL UNIQUE,
        normalized_plate TEXT NOT NULL,
        make TEXT NOT NULL,
        model TEXT NOT NULL,
        color TEXT NOT NULL,
        vehicle_type TEXT DEFAULT 'Sedan',
        year INTEGER DEFAULT 2022,
        status TEXT NOT NULL, -- STOLEN, WANTED_FELONY, AMBER_ALERT, UNAUTHORIZED, SUSPICIOUS, RECOVERED
        severity TEXT DEFAULT 'HIGH', -- CRITICAL, HIGH, MEDIUM, LOW
        case_number TEXT NOT NULL,
        reporting_station TEXT NOT NULL,
        reported_date TEXT NOT NULL,
        owner_name TEXT NOT NULL,
        notes TEXT,
        active INTEGER DEFAULT 1,
        created_at TEXT NOT NULL
    );
    """)

    # 2. Surveillance Camera Checkpoints
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS surveillance_cameras (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        location_name TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        status TEXT DEFAULT 'ONLINE',
        mode TEXT DEFAULT 'simulation', -- simulation, webcam, file
        total_scans INTEGER DEFAULT 0,
        hotlist_hits INTEGER DEFAULT 0,
        last_active TEXT
    );
    """)

    # 3. Detection Logs
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS detections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        camera_id TEXT NOT NULL,
        camera_name TEXT NOT NULL,
        detected_plate TEXT NOT NULL,
        normalized_plate TEXT NOT NULL,
        ocr_confidence REAL DEFAULT 0.0,
        is_match INTEGER DEFAULT 0,
        matched_plate TEXT,
        match_score REAL DEFAULT 0.0,
        stolen_vehicle_id INTEGER,
        snapshot_path TEXT,
        plate_crop_path TEXT,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (stolen_vehicle_id) REFERENCES stolen_vehicles(id)
    );
    """)

    # 4. Real-time Incident Alerts
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        detection_id INTEGER,
        vehicle_id INTEGER,
        camera_id TEXT NOT NULL,
        camera_name TEXT NOT NULL,
        plate_number TEXT NOT NULL,
        vehicle_desc TEXT NOT NULL,
        status_reason TEXT NOT NULL,
        severity TEXT NOT NULL,
        alert_status TEXT DEFAULT 'ACTIVE', -- ACTIVE, DISPATCHED, INTERCEPTED, FALSE_POSITIVE, RESOLVED
        dispatched_officer TEXT,
        dispatch_notes TEXT,
        snapshot_path TEXT,
        plate_crop_path TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        FOREIGN KEY (detection_id) REFERENCES detections(id),
        FOREIGN KEY (vehicle_id) REFERENCES stolen_vehicles(id)
    );
    """)

    # 5. System Settings
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)

    conn.commit()

    # Seed initial data if tables are empty
    seed_initial_data(conn)
    conn.close()


def seed_initial_data(conn):
    cursor = conn.cursor()

    # Seed Cameras
    cursor.execute("SELECT COUNT(*) FROM surveillance_cameras;")
    if cursor.fetchone()[0] == 0:
        cameras = [
            ("CAM-01", "Downtown Sector 4 - Central Ave", "Central Business District", 28.6139, 77.2090, "ONLINE", "simulation", 1420, 14),
            ("CAM-02", "North Highway Toll Plaza - Gate 3", "National Interstate 44", 28.7041, 77.1025, "ONLINE", "simulation", 2890, 29),
            ("CAM-03", "Airport Expressway Intercept", "Terminal 3 Access Road", 28.5562, 77.1000, "ONLINE", "simulation", 980, 8),
            ("CAM-04", "East Industrial Corridor Checkpoint", "Logistics Hub East", 28.6353, 77.2785, "ONLINE", "simulation", 650, 4)
        ]
        cursor.executemany("""
            INSERT INTO surveillance_cameras (id, name, location_name, latitude, longitude, status, mode, total_scans, hotlist_hits, last_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """, cameras)

    # Seed Stolen Vehicles (Police Hotlist)
    cursor.execute("SELECT COUNT(*) FROM stolen_vehicles;")
    if cursor.fetchone()[0] == 0:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stolen_records = [
            (
                "KA05MB9821", normalize_plate_str("KA05MB9821"), "Honda", "Civic", "Midnight Black", "Sedan", 2022,
                "STOLEN", "CRITICAL", "FIR-2026-8819", "Metro South Precinct", "2026-10-28 09:15:00",
                "Arjun Sharma", "Armed carjacking reported at gunpoint. Suspect believed to be armed and dangerous.", 1, now_str
            ),
            (
                "MH12DE1433", normalize_plate_str("MH12DE1433"), "Hyundai", "Creta", "Silver Metallic", "SUV", 2023,
                "STOLEN", "HIGH", "FIR-2026-4421", "Pune Central Police", "2026-10-29 14:30:00",
                "Neha Patil", "Stolen from mall parking lot. Tracker disabled 15 minutes post-theft.", 1, now_str
            ),
            (
                "DL03CA8921", normalize_plate_str("DL03CA8921"), "Maruti", "Swift", "Crimson Red", "Hatchback", 2021,
                "WANTED_FELONY", "CRITICAL", "CAS-2026-1092", "Anti-Robbery Squad", "2026-10-27 18:45:00",
                "Vikram Malhotra", "Getaway vehicle involved in primary commercial jewelry heist. Immediate intercept required.", 1, now_str
            ),
            (
                "CA7XYZ99", normalize_plate_str("CA7XYZ99"), "Ford", "F-150", "Oxford White", "Truck", 2020,
                "STOLEN", "HIGH", "CHP-2026-7731", "Highway Patrol District 7", "2026-10-25 11:20:00",
                "David Miller", "Vehicle stolen from residential driveway overnight.", 1, now_str
            ),
            (
                "NYK9821", normalize_plate_str("NYK9821"), "Toyota", "Camry", "Nautical Blue", "Sedan", 2022,
                "AMBER_ALERT", "CRITICAL", "AMB-2026-0043", "Child Protection Taskforce", "2026-10-30 06:10:00",
                "State Police", "URGENT AMBER ALERT: 7-year-old child reported inside vehicle. Stop and detain immediately.", 1, now_str
            ),
            (
                "HR26DQ5555", normalize_plate_str("HR26DQ5555"), "BMW", "3 Series", "Alpine White", "Sedan", 2024,
                "STOLEN", "HIGH", "FIR-2026-9923", "Cyberabad / Gurugram Auto Theft Unit", "2026-10-29 22:00:00",
                "Rohan Singhania", "Luxury vehicle theft ring target. Key cloning suspected.", 1, now_str
            ),
            (
                "TX4BKT11", normalize_plate_str("TX4BKT11"), "Dodge", "Charger", "Pitch Black", "Sedan", 2019,
                "UNAUTHORIZED", "MEDIUM", "REG-2026-5120", "Traffic Enforcement Bureau", "2026-10-20 16:00:00",
                "Marcus Vance", "Court impound order issued. Revoked registration and suspended driver license.", 1, now_str
            ),
            (
                "UP16BT9900", normalize_plate_str("UP16BT9900"), "Mahindra", "Scorpio-N", "Deep Forest Green", "SUV", 2023,
                "SUSPICIOUS", "HIGH", "INT-2026-3012", "Special Task Force", "2026-10-30 08:00:00",
                "Unknown / Cloned Plate", "Surveillance tag: Cloned plate detected on interstate border crossing.", 1, now_str
            ),
            (
                "FL909ZZ", normalize_plate_str("FL909ZZ"), "Chevrolet", "Camaro", "Bright Yellow", "Coupe", 2021,
                "STOLEN", "MEDIUM", "MIA-2026-6619", "Metro Transit Police", "2026-10-26 13:10:00",
                "Apex Car Rentals", "Commercial rental failure to return / grand theft vehicle declaration.", 1, now_str
            )
        ]

        cursor.executemany("""
            INSERT INTO stolen_vehicles (
                plate_number, normalized_plate, make, model, color, vehicle_type, year,
                status, severity, case_number, reporting_station, reported_date, owner_name, notes, active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, stolen_records)

    # Seed System Settings
    defaults = {
        "fuzzy_threshold": "0.82",
        "audio_alert_enabled": "true",
        "auto_dispatch": "false",
        "webhook_url": "",
        "police_station_name": "Metropolitan Police Joint Surveillance Command",
        "cad_channel": "DISPATCH_CHANNEL_1"
    }
    for k, v in defaults.items():
        cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?);", (k, v))

    conn.commit()


# --- Stolen Vehicles (Hotlist) CRUD ---

def get_all_stolen_vehicles(search_query=None, status_filter=None, active_only=True):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM stolen_vehicles WHERE 1=1"
    params = []

    if active_only:
        query += " AND active = 1"
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    if search_query:
        query += " AND (plate_number LIKE ? OR make LIKE ? OR model LIKE ? OR case_number LIKE ? OR owner_name LIKE ?)"
        wildcard = f"%{search_query}%"
        params.extend([wildcard, wildcard, wildcard, wildcard, wildcard])

    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stolen_vehicle_by_id(vehicle_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stolen_vehicles WHERE id = ?", (vehicle_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_stolen_vehicle_by_plate(plate_number):
    normalized = normalize_plate_str(plate_number)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stolen_vehicles WHERE normalized_plate = ? AND active = 1", (normalized,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def add_stolen_vehicle(data):
    normalized = normalize_plate_str(data.get("plate_number", ""))
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO stolen_vehicles (
            plate_number, normalized_plate, make, model, color, vehicle_type, year,
            status, severity, case_number, reporting_station, reported_date, owner_name, notes, active, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
    """, (
        data.get("plate_number", "").upper().strip(),
        normalized,
        data.get("make", "Unknown"),
        data.get("model", "Unknown"),
        data.get("color", "Unknown"),
        data.get("vehicle_type", "Sedan"),
        int(data.get("year", 2022) or 2022),
        data.get("status", "STOLEN"),
        data.get("severity", "HIGH"),
        data.get("case_number", f"CASE-{datetime.now().strftime('%y%m%d%H%M')}"),
        data.get("reporting_station", "Metropolitan Police HQ"),
        data.get("reported_date", now_str),
        data.get("owner_name", "Anonymous"),
        data.get("notes", ""),
        now_str
    ))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_stolen_vehicle(vehicle_id, data):
    normalized = normalize_plate_str(data.get("plate_number", ""))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE stolen_vehicles SET
            plate_number = ?,
            normalized_plate = ?,
            make = ?,
            model = ?,
            color = ?,
            vehicle_type = ?,
            year = ?,
            status = ?,
            severity = ?,
            case_number = ?,
            reporting_station = ?,
            reported_date = ?,
            owner_name = ?,
            notes = ?,
            active = ?
        WHERE id = ?
    """, (
        data.get("plate_number", "").upper().strip(),
        normalized,
        data.get("make"),
        data.get("model"),
        data.get("color"),
        data.get("vehicle_type"),
        int(data.get("year", 2022) or 2022),
        data.get("status"),
        data.get("severity"),
        data.get("case_number"),
        data.get("reporting_station"),
        data.get("reported_date"),
        data.get("owner_name"),
        data.get("notes"),
        int(data.get("active", 1)),
        vehicle_id
    ))
    conn.commit()
    conn.close()
    return True


def delete_stolen_vehicle(vehicle_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM stolen_vehicles WHERE id = ?", (vehicle_id,))
    conn.commit()
    conn.close()
    return True


# --- Camera CRUD ---

def get_all_cameras():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM surveillance_cameras ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_camera_by_id(cam_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM surveillance_cameras WHERE id = ?", (cam_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_camera_stats(cam_id, hit=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    if hit:
        cursor.execute("""
            UPDATE surveillance_cameras 
            SET total_scans = total_scans + 1, hotlist_hits = hotlist_hits + 1, last_active = datetime('now', 'localtime')
            WHERE id = ?
        """, (cam_id,))
    else:
        cursor.execute("""
            UPDATE surveillance_cameras 
            SET total_scans = total_scans + 1, last_active = datetime('now', 'localtime')
            WHERE id = ?
        """, (cam_id,))
    conn.commit()
    conn.close()


# --- Detection Logs ---

def log_detection(camera_id, camera_name, detected_plate, ocr_confidence, is_match, matched_plate=None, match_score=0.0, stolen_vehicle_id=None, snapshot_path=None, plate_crop_path=None):
    normalized = normalize_plate_str(detected_plate)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO detections (
            camera_id, camera_name, detected_plate, normalized_plate,
            ocr_confidence, is_match, matched_plate, match_score,
            stolen_vehicle_id, snapshot_path, plate_crop_path, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        camera_id, camera_name, detected_plate, normalized,
        float(ocr_confidence), 1 if is_match else 0, matched_plate, float(match_score),
        stolen_vehicle_id, snapshot_path, plate_crop_path, now_str
    ))
    detection_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return detection_id


# --- Real-time Alerts ---

def create_alert(detection_id, vehicle_id, camera_id, camera_name, plate_number, vehicle_desc, status_reason, severity, snapshot_path, plate_crop_path):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO alerts (
            detection_id, vehicle_id, camera_id, camera_name, plate_number,
            vehicle_desc, status_reason, severity, alert_status,
            snapshot_path, plate_crop_path, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?)
    """, (
        detection_id, vehicle_id, camera_id, camera_name, plate_number,
        vehicle_desc, status_reason, severity, snapshot_path, plate_crop_path, now_str
    ))
    alert_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return alert_id


def get_alerts(status_filter=None, limit=50):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT a.*, v.case_number, v.reporting_station, v.owner_name, v.notes as vehicle_notes
        FROM alerts a
        LEFT JOIN stolen_vehicles v ON a.vehicle_id = v.id
        WHERE 1=1
    """
    params = []
    if status_filter and status_filter != 'ALL':
        query += " AND a.alert_status = ?"
        params.append(status_filter)
    query += " ORDER BY a.id DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_alert_status(alert_id, new_status, dispatched_officer=None, dispatch_notes=None):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE alerts SET
            alert_status = ?,
            dispatched_officer = COALESCE(?, dispatched_officer),
            dispatch_notes = COALESCE(?, dispatch_notes),
            resolved_at = CASE WHEN ? IN ('INTERCEPTED', 'RESOLVED', 'FALSE_POSITIVE') THEN ? ELSE resolved_at END
        WHERE id = ?
    """, (new_status, dispatched_officer, dispatch_notes, new_status, now_str, alert_id))
    conn.commit()
    conn.close()
    return True


# --- Analytics & Reporting ---

def get_system_analytics():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM detections")
    total_scans = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM alerts")
    total_alerts = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM alerts WHERE alert_status = 'ACTIVE'")
    active_alerts = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM alerts WHERE alert_status = 'INTERCEPTED'")
    intercepted_alerts = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM stolen_vehicles WHERE active = 1")
    hotlist_count = cursor.fetchone()[0]

    # Category breakdown
    cursor.execute("""
        SELECT status_reason, COUNT(*) as count 
        FROM alerts 
        GROUP BY status_reason
    """)
    category_breakdown = [dict(r) for r in cursor.fetchall()]

    # Camera breakdown
    cursor.execute("""
        SELECT camera_name, COUNT(*) as hit_count
        FROM alerts
        GROUP BY camera_id
        ORDER BY hit_count DESC
    """)
    camera_breakdown = [dict(r) for r in cursor.fetchall()]

    # Recent 24 hour detections count
    cursor.execute("""
        SELECT substr(timestamp, 12, 2) as hour, COUNT(*) as count
        FROM detections
        GROUP BY hour
        ORDER BY hour ASC
    """)
    hourly_trends = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return {
        "total_scans": total_scans,
        "total_alerts": total_alerts,
        "active_alerts": active_alerts,
        "intercepted_alerts": intercepted_alerts,
        "hotlist_count": hotlist_count,
        "category_breakdown": category_breakdown,
        "camera_breakdown": camera_breakdown,
        "hourly_trends": hourly_trends
    }


# --- Settings ---

def get_settings():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM system_settings")
    rows = cursor.fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def update_setting(key, value):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()
    return True

