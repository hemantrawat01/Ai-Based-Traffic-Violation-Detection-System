# 🚓 AEGIS-ALPR: Stolen Vehicle Detection & Surveillance System

An enterprise-grade, real-time **Automated License Plate Recognition (ALPR / ANPR)** and **Stolen Vehicle Surveillance System**. Designed for law enforcement tactical command centers, traffic checkpoints, and toll plazas, it automatically reads license plates from video streams, cross-references them against a police "Hotlist" database in under 45ms, and triggers multi-channel real-time alerts.

---

## 🌟 Key Features

### 1. 🎯 Neural ALPR & Fuzzy Cross-Referencing
- **High-Speed Neural Inference**: Uses YOLOv9 plate detection and ONNX Runtime plate OCR via `fast-alpr`.
- **Character Confusion Correction Matrix**: Resolves standard OCR optical ambiguities (e.g., `O` vs `0`, `I` vs `1`, `B` vs `8`, `Z` vs `2`, `S` vs `5`).
- **Fuzzy Levenshtein Cross-Referencing**: Catches plates even when partially obscured, muddy, or misread by 1-2 characters with configurable similarity score matching (default 82%).

### 2. 🚨 Tactical Real-Time Visual Alerts
- **Non-Intrusive Tactical Alerts**: Silent, high-contrast visual indicators replacing loud audio interruptions.
- **Flashing HUD Banners & Reticles**: Video bounding boxes immediately highlight stolen vehicles in bold crimson red with case numbers and severity indicators.
- **Incident Snapshot Archiving**: Automatically archives high-resolution vehicle photos and cropped plate thumbnails to disk with timestamp watermarks.
- **Server-Sent Events (SSE)**: Instant, zero-latency streaming of hotlist detections to all connected screens.

### 3. 🗺️ Citywide Tactical GIS Surveillance Map (`/map`)
- **Dedicated Fullscreen GIS Operations Map**: Interactive dark CartoDB Leaflet map tracking checkpoints, patrol units, and hotlist detections across the city.
- **Live Video Stream Popups**: Click any surveillance camera checkpoint on the map to stream real-time video directly inside the map popup!
- **Field of View (FOV) Coverage Cones**: Translucent optical coverage cones showing each camera's roadway detection cone.
- **Police Patrol Fleet Tracking**: Positions of active interceptor cruisers (`Interceptor Alpha`, `Highway Interceptor 7`, `Rapid Response`) with direct dispatch controls.
- **Interstate Pursuit Corridors**: Directional trajectory vectors connecting checkpoints along major transit highways.
- **Radar Beacon Pings**: Real-time expanding red radar beacon rings when a stolen vehicle is spotted.

### 3. 📹 Multi-Camera Surveillance Network & Simulator
- **4 Simultaneous Camera Feeds**:
  - `CAM-01`: Downtown Sector 4 (Central Ave)
  - `CAM-02`: North Highway Toll Plaza (Gate 3)
  - `CAM-03`: Airport Expressway Intercept
  - `CAM-04`: East Industrial Corridor Checkpoint
- **Realistic Synthetic Traffic Simulator**: Renders 3D perspective roads, lane dividers, passing civilian vehicles, and periodic stolen car incursions.
- **Physical Webcam Integration**: Easily switch any camera node to your computer's USB webcam to scan live printed plates or phones.
- **Interactive Injection Drill Buttons**: Instant one-click triggers to inject Stolen Cars, Amber Alerts, or Robbery Getaway vehicles into the camera's path to demonstrate the system live.

### 4. 🗄️ Police Hotlist & Case Management
- Full CRUD management of wanted vehicles (`STOLEN`, `WANTED_FELONY`, `AMBER_ALERT`, `UNAUTHORIZED`, `SUSPICIOUS`).
- Store case numbers, reporting stations, owner information, crime notes, and severity ratings.
- Interactive test query simulator to verify fuzzy matching.

### 5. 🔍 Forensic Image Scanner
- Drag-and-drop static image uploader for inspecting CCTV captures, traffic camera photos, or crime scene snapshots.
- Pre-loaded with 5 instant test scenarios (Stolen Honda Civic, Stolen Hyundai Creta, Wanted Maruti Swift, Amber Alert Camry, Clean Sedan).

### 6. 🗺️ Tactical GIS Map & Operational Analytics
- Interactive dark-mode map (Leaflet.js) displaying camera checkpoints across the city with pulsing red radar beacons when an alert is triggered.
- Comprehensive charts (Chart.js) showing crime category breakdown, camera hit rankings, and downloadable CSV audit reports.

---

## 🚀 Quick Start

### 1. Launch with One Click (Windows)
Double-click `run.bat` or run:
```powershell
.\run.ps1
```
Or directly via Python:
```bash
python app.py
```

### 2. Open Command Center
Open your web browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 🧪 Demonstration Walkthrough

1. **Observe Live Surveillance Stream**:
   - The primary monitor renders live passing vehicles at 25 FPS with tactical HUD overlays.
   - Clean civilian vehicles show emerald green brackets: `CLEAN: [PLATE]`.
2. **Trigger an Interception Drill**:
   - Click the **"🚨 Spawn Stolen Car"** or **"⚠️ Spawn Amber Alert"** button on the dashboard toolbar.
   - Within seconds, the vehicle drives into the ANPR camera cone.
   - The bounding box turns bold crimson red: `ALERT: STOLEN [KA05MB9821] (100% match)`.
   - The police siren sounds and a voice announces the intercept.
   - A real-time incident card appears in the right sidebar.
   - The camera checkpoint pulses with an expanding red radar beacon on the tactical map!
3. **Dispatch Officer or Confirm Intercept**:
   - Click **"Dossier & Dispatch"** on the alert card to inspect full high-res photo evidence, vehicle owner, and case number.
   - Click **"Dispatch Patrol Unit"** or **"Confirm Intercepted & Detained"** to update status.
4. **Test the Forensic Scanner**:
   - Click the **"Forensic Scanner"** tab in the top navigation.
   - Click any of the 5 quick test scenarios (e.g. *Stolen Honda Civic*) to view instant OCR bounding boxes, character readouts, and database hit dossiers.
5. **Manage the Police Hotlist**:
   - Click **"Police Hotlist"** to add custom plates, search, or test OCR ambiguity (e.g. `DLO3CA8921`).
6. **Export Audit Reports**:
   - Navigate to **"Incident Logs"** or **"Analytics"** and click **"Download CSV Audit Log"**.

---

## 🏛️ Project Structure

```
Mini Hemant/
├── app.py                  # Flask web server, REST API, MJPEG stream generator
├── alpr_engine.py          # ALPR neural detection, OCR, normalization & fuzzy matcher
├── database.py             # SQLite schema, migrations, CRUD, and seed records
├── traffic_simulator.py    # Multi-camera roadway renderer and vehicle animator
├── alert_manager.py        # Cooldown de-duplication, SSE broadcast, webhook dispatcher
├── create_samples.py       # Helper to generate test vehicle scenarios
├── requirements.txt        # Python dependency manifest
├── run.bat                 # One-click Windows batch launcher
├── run.ps1                 # PowerShell launcher
├── static/
│   ├── css/style.css       # Tactical dark command center styling
│   ├── js/
│   │   ├── dashboard.js    # Real-time SSE stream, modal actions, camera switcher
│   │   ├── audio_alerts.js # Web Audio API siren & TTS voice synthesizer
│   │   └── map_view.js     # Leaflet.js tactical map & radar beacon animation
│   ├── snapshots/          # Auto-saved incident photo evidence archives
│   └── sample_images/      # Pre-generated sample cars for instant scanning
└── templates/
    ├── base.html           # Tactical law enforcement master layout
    ├── index.html          # Main Surveillance Command Center
    ├── hotlist.html        # Police Stolen Vehicle Database Manager
    ├── scanner.html        # Forensic Image Scanner & Scenario Tester
    ├── alerts_history.html # Incident Logs, Evidence Archives & Dispatches
    └── analytics.html      # Intelligence Analytics & Chart Heatmaps
```

---

## 🛡️ License
Built for Law Enforcement and Traffic Surveillance Automation demonstration.

