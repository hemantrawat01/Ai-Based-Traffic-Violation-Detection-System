"""
Alert Management and Real-Time Event Dispatcher.
Manages alert creation, de-duplication/cooldown, notification webhooks,
and Server-Sent Events (SSE) broadcasting to the surveillance command center.
"""

import time
import json
import threading
import queue
import urllib.request
from datetime import datetime

import database

# Thread-safe event subscribers for SSE
_subscribers = []
_subscribers_lock = threading.Lock()

# Alert cooldown cache to prevent alert flooding: {(camera_id, normalized_plate): last_alert_time}
_alert_cooldowns = {}
COOLDOWN_SECONDS = 15.0


def subscribe_events():
    """Register a new SSE client queue."""
    q = queue.Queue(maxsize=100)
    with _subscribers_lock:
        _subscribers.append(q)
    return q


def unsubscribe_events(q):
    """Unregister an SSE client queue."""
    with _subscribers_lock:
        if q in _subscribers:
            _subscribers.remove(q)


def broadcast_event(event_type: str, data: dict):
    """Broadcast an event payload to all connected SSE clients."""
    payload = json.dumps({"type": event_type, "data": data, "timestamp": datetime.now().isoformat()})
    message = f"event: {event_type}\ndata: {payload}\n\n"
    with _subscribers_lock:
        for q in list(_subscribers):
            try:
                q.put_nowait(message)
            except queue.Full:
                pass


def trigger_vehicle_alert(camera_id, camera_name, detected_plate, ocr_conf, vehicle_info, match_score, snapshot_path=None, crop_path=None):
    """
    Evaluate if an alert should be triggered (handles cooldowns),
    logs the alert in the database, and broadcasts it across all channels.
    """
    now = time.time()
    norm_plate = database.normalize_plate_str(detected_plate)
    cache_key = (camera_id, norm_plate)

    # Check cooldown
    last_time = _alert_cooldowns.get(cache_key, 0)
    if (now - last_time) < COOLDOWN_SECONDS:
        # Cooldown active, suppress duplicate alert
        return None

    # Update cooldown
    _alert_cooldowns[cache_key] = now

    # 1. Log Detection in DB
    detection_id = database.log_detection(
        camera_id=camera_id,
        camera_name=camera_name,
        detected_plate=detected_plate,
        ocr_confidence=ocr_conf,
        is_match=True,
        matched_plate=vehicle_info.get("plate_number"),
        match_score=match_score,
        stolen_vehicle_id=vehicle_info.get("id"),
        snapshot_path=snapshot_path,
        plate_crop_path=crop_path
    )

    # 2. Create Incident Alert Record
    status_reason = vehicle_info.get("status", "STOLEN")
    severity = vehicle_info.get("severity", "HIGH")
    vehicle_desc = f"{vehicle_info.get('color', '')} {vehicle_info.get('make', '')} {vehicle_info.get('model', '')} ({vehicle_info.get('year', '')})".strip()

    alert_id = database.create_alert(
        detection_id=detection_id,
        vehicle_id=vehicle_info.get("id"),
        camera_id=camera_id,
        camera_name=camera_name,
        plate_number=vehicle_info.get("plate_number"),
        vehicle_desc=vehicle_desc,
        status_reason=status_reason,
        severity=severity,
        snapshot_path=snapshot_path,
        plate_crop_path=crop_path
    )

    # 3. Update Camera Stats
    database.update_camera_stats(camera_id, hit=True)

    # 4. Form Alert Payload
    alert_payload = {
        "alert_id": alert_id,
        "detection_id": detection_id,
        "camera_id": camera_id,
        "camera_name": camera_name,
        "detected_plate": detected_plate,
        "matched_plate": vehicle_info.get("plate_number"),
        "match_score": int(match_score * 100),
        "vehicle_desc": vehicle_desc,
        "status_reason": status_reason,
        "severity": severity,
        "case_number": vehicle_info.get("case_number", "UNKNOWN"),
        "reporting_station": vehicle_info.get("reporting_station", "Metropolitan Police"),
        "owner_name": vehicle_info.get("owner_name", "N/A"),
        "notes": vehicle_info.get("notes", ""),
        "snapshot_path": snapshot_path,
        "plate_crop_path": crop_path,
        "time": datetime.now().strftime("%H:%M:%S"),
        "date": datetime.now().strftime("%Y-%m-%d")
    }

    print(f"\n[POLICE ALERT TRIGGERED] Alert #{alert_id} | {status_reason} | Plate: {detected_plate} -> Matched: {vehicle_info.get('plate_number')} at {camera_name}")

    # 5. Broadcast to Web Command Center (UI)
    broadcast_event("HOTLIST_ALERT", alert_payload)

    # 6. Dispatch Webhook in background if configured
    settings = database.get_settings()
    webhook_url = settings.get("webhook_url", "").strip()
    if webhook_url:
        threading.Thread(target=_send_webhook, args=(webhook_url, alert_payload), daemon=True).start()

    return alert_id


def _send_webhook(url, payload):
    """Send alert payload to external HTTP webhook."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as response:
            print(f"[Webhook] Alert dispatched successfully to {url}, code: {response.status}")
    except Exception as e:
        print(f"[Webhook] Failed to send alert to {url}: {e}")
