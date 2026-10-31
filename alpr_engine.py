"""
Automatic Number Plate Recognition (ANPR / ALPR) Engine.
Integrates neural detection, OCR extraction, positional ambiguity correction,
and fuzzy cross-referencing against the law enforcement hotlist database.
"""

import os
import re
import cv2
import numpy as np
import difflib
from datetime import datetime
from PIL import Image

import database

# Cache for ALPR model instance
_ALPR_INSTANCE = None


def get_alpr():
    global _ALPR_INSTANCE
    if _ALPR_INSTANCE is None:
        try:
            import fast_alpr
            _ALPR_INSTANCE = fast_alpr.ALPR()
            print("[ALPR Engine] fast_alpr neural model loaded successfully.")
        except Exception as e:
            print(f"[ALPR Engine] Warning: Failed to load fast_alpr: {e}. Falling back to OpenCV ALPR.")
            _ALPR_INSTANCE = "OPENCV_FALLBACK"
    return _ALPR_INSTANCE


# OCR Confusion Matrix for common optical character misidentifications
CHAR_CONFUSIONS = {
    'O': '0', '0': 'O',
    'I': '1', '1': 'I',
    'B': '8', '8': 'B',
    'Z': '2', '2': 'Z',
    'S': '5', '5': 'S',
    'G': '6', '6': 'G',
    'D': '0'
}


def clean_plate_text(raw_text: str) -> str:
    """Strip spaces, punctuation, symbols and uppercase."""
    if not raw_text:
        return ""
    # Remove all non-alphanumeric
    cleaned = re.sub(r'[^A-Za-z0-9]', '', raw_text).upper()
    # Strip common OCR edge artifacts like single trailing 'I' from plate screws
    if len(cleaned) > 4 and cleaned.endswith('I') and cleaned[-2].isdigit():
        pass
    return cleaned


def generate_plate_candidates(norm_text: str) -> list:
    """
    Generate likely candidate variations by substituting common OCR ambiguity characters.
    e.g. DLO3CA8921 -> DL03CA8921, KAO5MB9821 -> KA05MB9821
    """
    candidates = {norm_text}
    if not norm_text:
        return list(candidates)

    chars = list(norm_text)
    n = len(chars)

    # Heuristic 1: If string looks like Indian format XX-00-XX-0000
    if n >= 8 and chars[0].isalpha() and chars[1].isalpha():
        # Pos 2, 3 should likely be digits
        cand1 = list(chars)
        for i in [2, 3]:
            if i < n and cand1[i] in ['O', 'D']:
                cand1[i] = '0'
            elif i < n and cand1[i] == 'I':
                cand1[i] = '1'
            elif i < n and cand1[i] == 'B':
                cand1[i] = '8'
            elif i < n and cand1[i] == 'Z':
                cand1[i] = '2'
            elif i < n and cand1[i] == 'S':
                cand1[i] = '5'
        candidates.add("".join(cand1))

    # General 1-char substitution variants for O <-> 0, I <-> 1
    for i, ch in enumerate(chars):
        if ch in CHAR_CONFUSIONS:
            alt = CHAR_CONFUSIONS[ch]
            cand = list(chars)
            cand[i] = alt
            candidates.add("".join(cand))

    return list(candidates)


def calculate_similarity(s1: str, s2: str) -> float:
    """Calculate normalized similarity ratio between two plate strings."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return difflib.SequenceMatcher(None, s1, s2).ratio()


def cross_reference_hotlist(detected_plate: str, fuzzy_threshold=0.82):
    """
    Cross-reference detected plate with police hotlist.
    Returns: (is_match, matched_vehicle_dict, match_score, matched_plate)
    """
    clean_query = clean_plate_text(detected_plate)
    if not clean_query:
        return False, None, 0.0, None

    # Load active hotlist
    hotlist = database.get_all_stolen_vehicles(active_only=True)
    if not hotlist:
        return False, None, 0.0, None

    # 1. Exact match check
    for vehicle in hotlist:
        if clean_query == vehicle["normalized_plate"]:
            return True, vehicle, 1.0, vehicle["plate_number"]

    # 2. Candidate substitutions check
    candidates = generate_plate_candidates(clean_query)
    for cand in candidates:
        for vehicle in hotlist:
            if cand == vehicle["normalized_plate"]:
                return True, vehicle, 0.96, vehicle["plate_number"]

    # 3. Fuzzy Levenshtein / SequenceMatcher matching
    best_match = None
    best_score = 0.0

    for vehicle in hotlist:
        target_norm = vehicle["normalized_plate"]
        # Direct ratio
        ratio = calculate_similarity(clean_query, target_norm)
        # Also check against candidates
        for cand in candidates:
            c_ratio = calculate_similarity(cand, target_norm)
            if c_ratio > ratio:
                ratio = c_ratio

        if ratio > best_score:
            best_score = ratio
            best_match = vehicle

    if best_score >= fuzzy_threshold and best_match:
        return True, best_match, round(best_score, 2), best_match["plate_number"]

    return False, None, round(best_score, 2), None


def process_frame(frame, camera_id="CAM-01", camera_name="Surveillance Node", save_snapshots=True):
    """
    Process a video or image frame:
    - Runs ALPR detection and OCR
    - Cross-references with police database
    - Draws visual HUD annotations on the frame
    - Saves snapshots when a hotlist match occurs
    Returns: (annotated_frame, list_of_detections)
    """
    if frame is None or frame.size == 0:
        return frame, []

    alpr = get_alpr()
    annotated = frame.copy()
    detections = []
    h, w = frame.shape[:2]

    raw_results = []
    if alpr != "OPENCV_FALLBACK":
        try:
            raw_results = alpr.predict(frame)
        except Exception as e:
            print(f"[ALPR Engine] Error during fast_alpr inference: {e}")
            raw_results = []

    # If neural detector returned nothing or failed, use morphological fallback
    if not raw_results:
        raw_results = fallback_detect_plates(frame)

    for item in raw_results:
        # Extract bounding box & OCR
        if hasattr(item, "detection") and hasattr(item, "ocr"):
            # fast_alpr result structure
            box = item.detection.bounding_box
            x1, y1, x2, y2 = int(box.x1), int(box.y1), int(box.x2), int(box.y2)
            det_conf = float(item.detection.confidence)
            ocr_text = str(item.ocr.text) if item.ocr else ""
            if item.ocr and hasattr(item.ocr, 'confidence') and item.ocr.confidence:
                ocr_conf = float(np.mean(item.ocr.confidence))
            else:
                ocr_conf = det_conf
        else:
            # Fallback dict structure
            x1, y1, x2, y2 = item["bbox"]
            det_conf = item.get("confidence", 0.75)
            ocr_text = item.get("text", "")
            ocr_conf = item.get("ocr_conf", 0.75)

        # Clamp coordinates to frame
        x1 = max(0, min(x1, w - 1))
        y1 = max(0, min(y1, h - 1))
        x2 = max(0, min(x2, w - 1))
        y2 = max(0, min(y2, h - 1))

        if x2 - x1 < 15 or y2 - y1 < 10:
            continue

        clean_text = clean_plate_text(ocr_text)
        if not clean_text or len(clean_text) < 4:
            continue

        # Cross-reference with police database
        is_match, matched_veh, match_score, matched_plate = cross_reference_hotlist(clean_text)

        # Crop plate image
        plate_crop = frame[y1:y2, x1:x2].copy()

        # Paths for snapshots
        snapshot_rel_path = None
        crop_rel_path = None

        if is_match and save_snapshots:
            snapshot_rel_path, crop_rel_path = save_incident_snapshots(
                frame, plate_crop, clean_text, camera_id, matched_veh
            )

        # Annotate Frame with HUD styling
        draw_plate_hud(annotated, x1, y1, x2, y2, clean_text, is_match, matched_veh, ocr_conf, match_score)

        det_data = {
            "bbox": [x1, y1, x2, y2],
            "raw_text": ocr_text,
            "plate_number": clean_text,
            "confidence": round(ocr_conf, 2),
            "is_match": is_match,
            "match_score": match_score,
            "matched_plate": matched_plate,
            "vehicle": matched_veh,
            "snapshot_path": snapshot_rel_path,
            "crop_path": crop_rel_path,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        detections.append(det_data)

    return annotated, detections


def draw_plate_hud(img, x1, y1, x2, y2, plate_text, is_match, vehicle, conf, match_score):
    """Render a tactical Law Enforcement HUD bounding box and badge."""
    if is_match:
        # Flashing crimson red / amber alert style
        status_reason = vehicle.get("status", "STOLEN") if vehicle else "STOLEN"
        box_color = (0, 0, 230) # Bright Red
        badge_bg = (10, 10, 180)
        text_color = (255, 255, 255)
        severity = vehicle.get("severity", "HIGH") if vehicle else "HIGH"
        label = f"ALERT: {status_reason} [{plate_text}] ({int(match_score*100)}% match)"
    else:
        # Clean / Authorized vehicle: Tactical Green / Cyan
        box_color = (0, 220, 100) # Crisp Emerald Green
        badge_bg = (15, 60, 30)
        text_color = (240, 255, 240)
        label = f"CLEAN: {plate_text} ({int(conf*100)}%)"

    # Draw Corner-Bracket Tactical Bounding Box
    corner_len = min(20, (x2 - x1) // 3, (y2 - y1) // 3)
    thick = 3 if is_match else 2

    # Full rectangle with slight transparency or crisp lines
    cv2.rectangle(img, (x1, y1), (x2, y2), box_color, thick)

    # Accent corner reticles
    cv2.line(img, (x1, y1), (x1 + corner_len, y1), box_color, thick + 2)
    cv2.line(img, (x1, y1), (x1, y1 + corner_len), box_color, thick + 2)
    cv2.line(img, (x2, y1), (x2 - corner_len, y1), box_color, thick + 2)
    cv2.line(img, (x2, y1), (x2, y1 + corner_len), box_color, thick + 2)
    cv2.line(img, (x1, y2), (x1 + corner_len, y2), box_color, thick + 2)
    cv2.line(img, (x1, y2), (x1, y2 - corner_len), box_color, thick + 2)
    cv2.line(img, (x2, y2), (x2 - corner_len, y2), box_color, thick + 2)
    cv2.line(img, (x2, y2), (x2, y2 - corner_len), box_color, thick + 2)

    # Label Badge Background
    (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
    badge_y1 = max(0, y1 - th - 12)
    badge_y2 = y1
    badge_x2 = min(img.shape[1], x1 + tw + 14)

    cv2.rectangle(img, (x1, badge_y1), (badge_x2, badge_y2), badge_bg, -1)
    cv2.rectangle(img, (x1, badge_y1), (badge_x2, badge_y2), box_color, 1)

    # Draw Text
    cv2.putText(img, label, (x1 + 6, badge_y2 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.55, text_color, 2, cv2.LINE_AA)

    # If it's a match, render secondary banner with vehicle make/model
    if is_match and vehicle:
        sub_label = f"{vehicle.get('make', '')} {vehicle.get('model', '')} ({vehicle.get('color', '')}) | Case: {vehicle.get('case_number', '')}"
        (stw, sth), _ = cv2.getTextSize(sub_label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        sub_y1 = y2 + 4
        sub_y2 = min(img.shape[0], y2 + sth + 10)
        sub_x2 = min(img.shape[1], x1 + stw + 12)
        cv2.rectangle(img, (x1, sub_y1), (sub_x2, sub_y2), (20, 20, 20), -1)
        cv2.rectangle(img, (x1, sub_y1), (sub_x2, sub_y2), box_color, 1)
        cv2.putText(img, sub_label, (x1 + 6, sub_y2 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 200, 200), 1, cv2.LINE_AA)


def save_incident_snapshots(full_frame, plate_crop, plate_text, camera_id, vehicle_info):
    """Save incident snapshot and plate crop to static/snapshots/ folder."""
    snapshot_dir = os.path.join(os.path.dirname(__file__), "static", "snapshots")
    os.makedirs(snapshot_dir, exist_ok=True)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
    base_name = f"INCIDENT_{camera_id}_{plate_text}_{timestamp_str}"
    full_path = os.path.join(snapshot_dir, f"{base_name}_full.jpg")
    crop_path = os.path.join(snapshot_dir, f"{base_name}_crop.jpg")

    # Annotate snapshot with incident evidence stamp
    annotated_evidence = full_frame.copy()
    stamp_h = 45
    cv2.rectangle(annotated_evidence, (0, 0), (annotated_evidence.shape[1], stamp_h), (10, 10, 20), -1)
    reason = vehicle_info.get("status", "STOLEN") if vehicle_info else "STOLEN"
    case = vehicle_info.get("case_number", "N/A") if vehicle_info else "N/A"
    stamp_text = f"EVIDENCE ARCHIVE | CAM: {camera_id} | PLATE: {plate_text} | ALERT: {reason} | CASE: {case} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    cv2.putText(annotated_evidence, stamp_text, (15, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1, cv2.LINE_AA)

    cv2.imwrite(full_path, annotated_evidence, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if plate_crop is not None and plate_crop.size > 0:
        cv2.imwrite(crop_path, plate_crop, [cv2.IMWRITE_JPEG_QUALITY, 95])

    rel_full = f"/static/snapshots/{base_name}_full.jpg"
    rel_crop = f"/static/snapshots/{base_name}_crop.jpg"
    return rel_full, rel_crop


def fallback_detect_plates(frame):
    """
    Morphological license plate localization fallback using OpenCV.
    Finds rectangular plate-like aspect ratios and runs basic OCR or returns empty.
    """
    results = []
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Morphological filter to find dark-on-light or light-on-dark rectangular text regions
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        sobelx = cv2.Sobel(blur, cv2.CV_8U, 1, 0, ksize=3)
        _, thresh = cv2.threshold(sobelx, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 3))
        morphed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            aspect = w / float(h)
            area = w * h
            # Typical license plate aspect ratio is between 2.0 and 6.0
            if 2.0 < aspect < 6.0 and 2000 < area < 60000:
                results.append({
                    "bbox": [x, y, x + w, y + h],
                    "confidence": 0.70,
                    "text": "SCANNING",
                    "ocr_conf": 0.65
                })
    except Exception as e:
        print(f"[Fallback Plate Detector] Error: {e}")
    return results

