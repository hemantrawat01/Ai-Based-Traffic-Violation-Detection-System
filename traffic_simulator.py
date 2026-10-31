"""
Surveillance Camera Traffic Simulator.
Generates realistic multi-camera synthetic traffic video streams with moving vehicles,
rendered license plates, dynamic roadway environments, and controlled hotlist vehicle injections.
"""

import time
import math
import random
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import alpr_engine
import alert_manager
import database

# Cache for Windows TrueType font
try:
    FONT_PATH = "C:\\Windows\\Fonts\\arialbd.ttf"
    _PLATE_FONT_32 = ImageFont.truetype(FONT_PATH, 32)
    _PLATE_FONT_24 = ImageFont.truetype(FONT_PATH, 24)
except Exception:
    _PLATE_FONT_32 = None
    _PLATE_FONT_24 = None

# Civilian / Clean plate generator pool
CIVILIAN_PLATES = [
    "KA01AB1122", "MH02CD3344", "DL04EF5566", "UP32GH7788",
    "HR26JK9900", "TN07LM1234", "CA4ABC99", "TX9XYZ12",
    "NY5BEE88", "FL7CAR01", "KA03MM4501", "MH14ZZ8822"
]

VEHICLE_COLORS = [
    {"name": "Silver Metallic", "bgr": (185, 185, 190)},
    {"name": "Midnight Black", "bgr": (25, 25, 28)},
    {"name": "Crimson Red", "bgr": (30, 30, 185)},
    {"name": "Alpine White", "bgr": (235, 235, 240)},
    {"name": "Nautical Blue", "bgr": (170, 70, 20)},
    {"name": "Forest Green", "bgr": (40, 110, 40)},
    {"name": "Solar Yellow", "bgr": (20, 210, 240)},
    {"name": "Charcoal Grey", "bgr": (75, 75, 80)}
]


class SimulatedVehicle:
    """Represents a moving vehicle on a surveillance camera roadway."""

    def __init__(self, plate_number, is_hotlist=False, hotlist_info=None, lane=1, speed=4.5):
        self.plate_number = plate_number
        self.is_hotlist = is_hotlist
        self.hotlist_info = hotlist_info
        self.lane = lane # 0: left, 1: center, 2: right
        self.progress = 0.0 # 0.0 (far) to 1.0 (passed camera)
        self.speed = speed # speed multiplier

        if is_hotlist and hotlist_info:
            color_name = hotlist_info.get("color", "Silver")
            matched_color = next((c for c in VEHICLE_COLORS if c["name"].lower() in color_name.lower()), VEHICLE_COLORS[0])
            self.color = matched_color["bgr"]
            self.model_type = hotlist_info.get("vehicle_type", "Sedan")
        else:
            col_choice = random.choice(VEHICLE_COLORS)
            self.color = col_choice["bgr"]
            self.model_type = random.choice(["Sedan", "SUV", "Truck", "Hatchback"])

        self.scanned = False


class CameraStreamManager:
    """Manages active streams for all 4 surveillance camera nodes."""

    def __init__(self):
        self.cameras = {
            "CAM-01": {
                "name": "Downtown Sector 4 - Central Ave",
                "env": "city",
                "lanes": 2,
                "vehicles": [],
                "last_spawn": time.time(),
                "fps": 24,
                "forced_injection": None,
                "webcam_active": False,
                "webcam_cap": None
            },
            "CAM-02": {
                "name": "North Highway Toll Plaza - Gate 3",
                "env": "highway",
                "lanes": 3,
                "vehicles": [],
                "last_spawn": time.time(),
                "fps": 24,
                "forced_injection": None,
                "webcam_active": False,
                "webcam_cap": None
            },
            "CAM-03": {
                "name": "Airport Expressway Intercept",
                "env": "expressway",
                "lanes": 2,
                "vehicles": [],
                "last_spawn": time.time(),
                "fps": 24,
                "forced_injection": None,
                "webcam_active": False,
                "webcam_cap": None
            },
            "CAM-04": {
                "name": "East Industrial Corridor Checkpoint",
                "env": "checkpoint",
                "lanes": 2,
                "vehicles": [],
                "last_spawn": time.time(),
                "fps": 24,
                "forced_injection": None,
                "webcam_active": False,
                "webcam_cap": None
            }
        }
        self.frame_counters = {cid: 0 for cid in self.cameras}
        self.width = 640
        self.height = 480

    def inject_hotlist_vehicle(self, cam_id, plate_number=None):
        """Force a stolen vehicle to spawn immediately on a specific camera."""
        if cam_id not in self.cameras:
            cam_id = "CAM-01"

        hotlist = database.get_all_stolen_vehicles(active_only=True)
        if not hotlist:
            return False

        if plate_number:
            target = next((v for v in hotlist if v["plate_number"] == plate_number), hotlist[0])
        else:
            target = random.choice(hotlist)

        veh = SimulatedVehicle(
            plate_number=target["plate_number"],
            is_hotlist=True,
            hotlist_info=target,
            lane=random.randint(0, self.cameras[cam_id]["lanes"] - 1),
            speed=4.0
        )
        self.cameras[cam_id]["vehicles"].insert(0, veh)
        print(f"[Simulator] Injected hotlist vehicle {target['plate_number']} ({target['make']} {target['model']}) onto {cam_id}")
        return True

    def toggle_webcam(self, cam_id, enable=True):
        """Switch camera between simulation and physical PC webcam."""
        if cam_id not in self.cameras:
            return False

        cam = self.cameras[cam_id]
        if enable:
            if cam["webcam_cap"] is None:
                cap = cv2.VideoCapture(0)
                if cap.isOpened():
                    cam["webcam_cap"] = cap
                    cam["webcam_active"] = True
                    database.update_setting(f"cam_{cam_id}_mode", "webcam")
                    return True
                else:
                    return False
        else:
            if cam["webcam_cap"] is not None:
                cam["webcam_cap"].release()
                cam["webcam_cap"] = None
            cam["webcam_active"] = False
            database.update_setting(f"cam_{cam_id}_mode", "simulation")
            return True

    def get_frame(self, cam_id):
        """Generate or capture the next frame for a camera, run ALPR, and return JPEG bytes."""
        if cam_id not in self.cameras:
            cam_id = "CAM-01"

        cam = self.cameras[cam_id]
        self.frame_counters[cam_id] += 1
        frame_idx = self.frame_counters[cam_id]

        # 1. Physical Webcam Mode
        if cam["webcam_active"] and cam["webcam_cap"] is not None:
            ret, frame = cam["webcam_cap"].read()
            if ret and frame is not None:
                frame = cv2.resize(frame, (self.width, self.height))
                annotated, detections = alpr_engine.process_frame(frame, camera_id=cam_id, camera_name=cam["name"])
                # Handle any hotlist detections
                for det in detections:
                    if det["is_match"] and det["vehicle"]:
                        alert_manager.trigger_vehicle_alert(
                            camera_id=cam_id,
                            camera_name=cam["name"],
                            detected_plate=det["plate_number"],
                            ocr_conf=det["confidence"],
                            vehicle_info=det["vehicle"],
                            match_score=det["match_score"],
                            snapshot_path=det["snapshot_path"],
                            crop_path=det["crop_path"]
                        )
                self._draw_stream_hud(annotated, cam_id, cam["name"], is_webcam=True)
                _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
                return jpeg.tobytes()

        # 2. Synthetic Traffic Simulation Mode
        # Update vehicles
        now = time.time()
        if now - cam["last_spawn"] > random.uniform(3.5, 6.0):
            self._spawn_vehicle(cam_id)
            cam["last_spawn"] = now

        # Render background environment
        frame = self._render_environment(cam["env"], frame_idx, cam["lanes"])

        # Update and render vehicles
        active_vehicles = []
        for veh in cam["vehicles"]:
            veh.progress += (0.015 * veh.speed)
            if veh.progress < 1.15:
                self._render_vehicle(frame, veh, cam["lanes"])
                active_vehicles.append(veh)

                # Trigger ALPR scan in the optimal detection window (progress 0.45 to 0.75)
                if 0.45 <= veh.progress <= 0.75 and not veh.scanned:
                    veh.scanned = True
                    database.update_camera_stats(cam_id, hit=veh.is_hotlist)
                    if veh.is_hotlist and veh.hotlist_info:
                        # Produce high-fidelity evidence snapshot
                        snap_rel, crop_rel = alpr_engine.save_incident_snapshots(
                            frame, None, veh.plate_number, cam_id, veh.hotlist_info
                        )
                        alert_manager.trigger_vehicle_alert(
                            camera_id=cam_id,
                            camera_name=cam["name"],
                            detected_plate=veh.plate_number,
                            ocr_conf=0.96,
                            vehicle_info=veh.hotlist_info,
                            match_score=0.98,
                            snapshot_path=snap_rel,
                            crop_path=crop_rel
                        )
                    else:
                        # Log clean scan in detection logs
                        database.log_detection(
                            camera_id=cam_id,
                            camera_name=cam["name"],
                            detected_plate=veh.plate_number,
                            ocr_confidence=0.92,
                            is_match=False
                        )

        cam["vehicles"] = active_vehicles

        # Run ALPR to draw dynamic HUD bounding boxes
        annotated, detections = alpr_engine.process_frame(frame, camera_id=cam_id, camera_name=cam["name"], save_snapshots=False)

        # Overlay Camera HUD
        self._draw_stream_hud(annotated, cam_id, cam["name"], is_webcam=False)

        _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return jpeg.tobytes()

    def _spawn_vehicle(self, cam_id):
        cam = self.cameras[cam_id]
        lanes_count = cam["lanes"]
        lane = random.randint(0, lanes_count - 1)

        # 25% chance of spawning a hotlist stolen vehicle naturally
        if random.random() < 0.25:
            hotlist = database.get_all_stolen_vehicles(active_only=True)
            if hotlist:
                target = random.choice(hotlist)
                veh = SimulatedVehicle(
                    plate_number=target["plate_number"],
                    is_hotlist=True,
                    hotlist_info=target,
                    lane=lane,
                    speed=random.uniform(3.5, 4.8)
                )
                cam["vehicles"].append(veh)
                return

        # Regular civilian vehicle
        plate = random.choice(CIVILIAN_PLATES)
        veh = SimulatedVehicle(
            plate_number=plate,
            is_hotlist=False,
            lane=lane,
            speed=random.uniform(3.8, 5.2)
        )
        cam["vehicles"].append(veh)

    def _render_environment(self, env_type, frame_idx, lanes_count):
        """Draw realistic roadway, lane markers, horizon and surroundings."""
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)

        # Sky / Horizon
        if env_type == "city":
            # Urban night/dusk setting
            frame[:180, :] = (40, 30, 25) # Dark blue-grey sky
            # City skyline silhouettes
            for i in range(0, self.width, 40):
                bh = 50 + ((i * 37) % 70)
                frame[180 - bh:180, i:i + 35] = (25, 20, 18)
                # Building windows
                if i % 3 == 0:
                    cv2.rectangle(frame, (i + 8, 180 - bh + 15), (i + 25, 180 - 15), (70, 140, 200), -1)
        elif env_type == "highway":
            # Highway open sky
            frame[:160, :] = (55, 45, 35)
            # Distant tree line
            cv2.rectangle(frame, (0, 140), (self.width, 160), (25, 50, 20), -1)
            # Overhead Toll Gantry
            cv2.rectangle(frame, (40, 60), (self.width - 40, 85), (80, 80, 85), -1)
            cv2.rectangle(frame, (35, 60), (55, 180), (60, 60, 65), -1)
            cv2.rectangle(frame, (self.width - 55, 60), (self.width - 35, 180), (60, 60, 65), -1)
            cv2.putText(frame, "TOLL PLAZA 3 - AUTOMATED ANPR LANES", (90, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 1)
        else:
            # Expressway / Checkpoint
            frame[:170, :] = (45, 35, 30)
            cv2.rectangle(frame, (0, 150), (self.width, 170), (35, 45, 35), -1)

        # Asphalt Road Surface (Perspective trapezoid)
        road_pts = np.array([
            [self.width * 0.28, 170],
            [self.width * 0.72, 170],
            [self.width + 50, self.height],
            [-50, self.height]
        ], np.int32)
        cv2.fillPoly(frame, [road_pts], (55, 55, 60))

        # Road shoulders & curbs
        cv2.line(frame, (int(self.width * 0.28), 170), (-50, self.height), (220, 220, 220), 4)
        cv2.line(frame, (int(self.width * 0.72), 170), (self.width + 50, self.height), (220, 220, 220), 4)

        # Animated Lane Divider Dashes
        offset = (frame_idx * 6) % 60
        lane_step = 1.0 / lanes_count
        for l in range(1, lanes_count):
            ratio = l * lane_step
            # Top point
            tx = int(self.width * 0.28 + ratio * (self.width * 0.44))
            # Bottom point
            bx = int(-50 + ratio * (self.width + 100))

            # Draw dashed lines
            for y in range(180, self.height, 40):
                dash_y = (y + offset)
                if dash_y > self.height:
                    continue
                t = (dash_y - 170) / (self.height - 170)
                cur_x = int(tx + t * (bx - tx))
                dash_len = int(12 + t * 25)
                thick = max(1, int(1 + t * 3))
                cv2.line(frame, (cur_x, dash_y), (cur_x, min(self.height, dash_y + dash_len)), (240, 240, 240), thick)

        return frame

    def _render_vehicle(self, frame, veh, lanes_count):
        """Render a 3D perspective vehicle with embossed license plate."""
        t = veh.progress
        if t <= 0.05 or t > 1.05:
            return

        # Perspective scale: starts small at top of road (t=0.1) and grows large (t=1.0)
        scale = 0.35 + (t * 0.95)

        # Calculate Lane X position
        lane_ratio = (veh.lane + 0.5) / lanes_count
        tx = self.width * 0.28 + lane_ratio * (self.width * 0.44)
        bx = -50 + lane_ratio * (self.width + 100)
        x = int(tx + t * (bx - tx))

        # Y position
        y = int(170 + t * (self.height - 170))

        # Vehicle Dimensions
        vw = int(240 * scale)
        vh = int(130 * scale)
        color = veh.color

        # Vehicle Shadow
        shadow_pts = np.array([
            [x - vw // 2 - 10, y + vh // 2 + 10],
            [x + vw // 2 + 10, y + vh // 2 + 10],
            [x + vw // 2 - 15, y + vh // 2 - 5],
            [x - vw // 2 + 15, y + vh // 2 - 5]
        ], np.int32)
        cv2.fillPoly(frame, [shadow_pts], (25, 25, 25))

        # Car Body (Rear View)
        cv2.rectangle(frame, (x - vw // 2, y - vh // 2), (x + vw // 2, y + vh // 2), color, -1)
        # Rounded bevels on bumper
        cv2.circle(frame, (x - vw // 2 + 10, y + vh // 2 - 10), 10, color, -1)
        cv2.circle(frame, (x + vw // 2 - 10, y + vh // 2 - 10), 10, color, -1)

        # Cabin / Roof
        cw = int(vw * 0.78)
        ch = int(vh * 0.55)
        cabin_top = y - vh // 2 - ch
        cabin_pts = np.array([
            [x - cw // 2 + int(15 * scale), cabin_top],
            [x + cw // 2 - int(15 * scale), cabin_top],
            [x + cw // 2, y - vh // 2],
            [x - cw // 2, y - vh // 2]
        ], np.int32)
        cv2.fillPoly(frame, [cabin_pts], color)

        # Rear Windshield
        glass_pts = np.array([
            [x - cw // 2 + int(20 * scale), cabin_top + int(8 * scale)],
            [x + cw // 2 - int(20 * scale), cabin_top + int(8 * scale)],
            [x + cw // 2 - int(8 * scale), y - vh // 2 - int(6 * scale)],
            [x - cw // 2 + int(8 * scale), y - vh // 2 - int(6 * scale)]
        ], np.int32)
        cv2.fillPoly(frame, [glass_pts], (35, 30, 25))

        # Taillights
        tl_w = max(10, int(32 * scale))
        tl_h = max(6, int(18 * scale))
        cv2.rectangle(frame, (x - vw // 2 + 6, y - int(10 * scale)), (x - vw // 2 + 6 + tl_w, y - int(10 * scale) + tl_h), (0, 0, 220), -1)
        cv2.rectangle(frame, (x + vw // 2 - 6 - tl_w, y - int(10 * scale)), (x + vw // 2 - 6, y - int(10 * scale) + tl_h), (0, 0, 220), -1)

        # License Plate Rendering (Bumper mounted)
        pw = int(140 * scale)
        ph = int(42 * scale)
        py = y + int(vh * 0.12)

        if pw > 45 and ph > 14:
            self._draw_plate_graphic(frame, x, py, pw, ph, veh.plate_number, scale)

    def _draw_plate_graphic(self, frame, cx, cy, pw, ph, plate_text, scale):
        """Draw a high-contrast license plate with security strip and bold characters."""
        x1 = cx - pw // 2
        y1 = cy - ph // 2
        x2 = cx + pw // 2
        y2 = cy + ph // 2

        # Plate Mount Cavity
        cv2.rectangle(frame, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4), (15, 15, 15), -1)

        # Plate White Reflective Face
        cv2.rectangle(frame, (x1, y1), (x2, y2), (250, 250, 250), -1)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (20, 20, 20), 2)

        # Left Blue Security Strip (EU / IND / US style)
        strip_w = max(4, int(pw * 0.12))
        cv2.rectangle(frame, (x1 + 1, y1 + 1), (x1 + strip_w, y2 - 1), (180, 60, 20), -1)

        # Format plate text with standard center space
        fmt_text = plate_text
        if len(plate_text) == 10:
            fmt_text = f"{plate_text[:2]} {plate_text[2:4]} {plate_text[4:]}"

        # Draw Characters
        font_scale = 0.52 * scale
        thick = max(1, int(1.8 * scale))
        (tw, th), _ = cv2.getTextSize(fmt_text, cv2.FONT_HERSHEY_DUPLEX, font_scale, thick)
        tx = x1 + strip_w + max(2, (pw - strip_w - tw) // 2)
        ty = cy + th // 2
        cv2.putText(frame, fmt_text, (tx, ty), cv2.FONT_HERSHEY_DUPLEX, font_scale, (10, 10, 10), thick, cv2.LINE_AA)

    def _draw_stream_hud(self, frame, cam_id, cam_name, is_webcam=False):
        """Draw tactical law enforcement surveillance metadata overlay."""
        h, w = frame.shape[:2]

        # Top Banner Overlay
        cv2.rectangle(frame, (0, 0), (w, 36), (15, 15, 20), -1)
        cv2.line(frame, (0, 36), (w, 36), (0, 200, 255), 1)

        # Red recording pulse indicator
        pulse = int(time.time() * 2) % 2 == 0
        rec_color = (0, 0, 240) if pulse else (80, 80, 80)
        cv2.circle(frame, (16, 18), 6, rec_color, -1)
        cv2.putText(frame, "LIVE ANPR", (30, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (240, 240, 240), 1)

        # Camera Name & ID
        cam_label = f"[{cam_id}] {cam_name.upper()}"
        cv2.putText(frame, cam_label, (125, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 220, 255), 1)

        # Timecode
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, now_str, (w - 180, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)

        # Bottom Status Overlay
        cv2.rectangle(frame, (0, h - 26), (w, h), (15, 15, 20), -1)
        mode_str = "MODE: HARDWARE WEBCAM (USB)" if is_webcam else "MODE: SURVEILLANCE FEED (ACTIVE)"
        cv2.putText(frame, mode_str, (12, h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
        cv2.putText(frame, "CROSS-REF: POLICE NCIC / CCTNS HOTLIST (ARMED)", (w - 360, h - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 120), 1)


# Global singleton manager
stream_manager = CameraStreamManager()

