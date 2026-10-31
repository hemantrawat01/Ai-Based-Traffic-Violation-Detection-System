import os
import cv2
import numpy as np

out_dir = os.path.join(os.path.dirname(__file__), "static", "sample_images")
os.makedirs(out_dir, exist_ok=True)

samples = [
    {
        "filename": "sample_1_stolen_civic.jpg",
        "plate": "KA05MB9821",
        "color": (25, 25, 30), # Midnight Black
        "title": "Stolen Honda Civic (Armed Carjacking)"
    },
    {
        "filename": "sample_2_stolen_creta.jpg",
        "plate": "MH12DE1433",
        "color": (180, 180, 185), # Silver
        "title": "Stolen Hyundai Creta (FIR-4421)"
    },
    {
        "filename": "sample_3_wanted_swift.jpg",
        "plate": "DL03CA8921",
        "color": (30, 30, 190), # Red
        "title": "Wanted Robbery Vehicle (CAS-1092)"
    },
    {
        "filename": "sample_4_amber_camry.jpg",
        "plate": "NYK9821",
        "color": (170, 70, 20), # Blue
        "title": "Amber Alert Vehicle (AMB-0043)"
    },
    {
        "filename": "sample_5_clean_sedan.jpg",
        "plate": "KA01AB1122",
        "color": (230, 230, 235), # White
        "title": "Clean Authorized Civilian Vehicle"
    }
]

w, h = 800, 600
for s in samples:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    # Scenery / Road
    img[:260, :] = (45, 40, 35)
    img[260:, :] = (55, 55, 60)
    # Road markings
    cv2.line(img, (150, 600), (320, 260), (220, 220, 220), 4)
    cv2.line(img, (650, 600), (480, 260), (220, 220, 220), 4)

    # Car body
    cx, cy = 400, 390
    bw, bh = 420, 210
    cv2.rectangle(img, (cx - bw//2, cy - bh//2), (cx + bw//2, cy + bh//2), s["color"], -1)

    # Windshield / Cabin
    cw, ch = 310, 120
    top_y = cy - bh//2 - ch
    cabin_pts = np.array([
        [cx - cw//2 + 30, top_y],
        [cx + cw//2 - 30, top_y],
        [cx + cw//2, cy - bh//2],
        [cx - cw//2, cy - bh//2]
    ], np.int32)
    cv2.fillPoly(img, [cabin_pts], s["color"])

    # Glass
    glass_pts = np.array([
        [cx - cw//2 + 40, top_y + 12],
        [cx + cw//2 - 40, top_y + 12],
        [cx + cw//2 - 12, cy - bh//2 - 8],
        [cx - cw//2 + 12, cy - bh//2 - 8]
    ], np.int32)
    cv2.fillPoly(img, [glass_pts], (30, 30, 25))

    # Taillights
    cv2.rectangle(img, (cx - bw//2 + 12, cy - 20), (cx - bw//2 + 70, cy + 15), (0, 0, 220), -1)
    cv2.rectangle(img, (cx + bw//2 - 70, cy - 20), (cx + bw//2 - 12, cy + 15), (0, 0, 220), -1)

    # License Plate
    pw, ph = 210, 60
    py = cy + 35
    x1, y1 = cx - pw//2, py - ph//2
    x2, y2 = cx + pw//2, py + ph//2

    cv2.rectangle(img, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4), (15, 15, 15), -1)
    cv2.rectangle(img, (x1, y1), (x2, y2), (250, 250, 250), -1)
    cv2.rectangle(img, (x1, y1), (x2, y2), (20, 20, 20), 2)
    cv2.rectangle(img, (x1 + 1, y1 + 1), (x1 + 25, y2 - 1), (180, 60, 20), -1)

    fmt_plate = s["plate"]
    if len(fmt_plate) == 10:
        fmt_plate = f"{fmt_plate[:2]} {fmt_plate[2:4]} {fmt_plate[4:]}"

    (tw, th), _ = cv2.getTextSize(fmt_plate, cv2.FONT_HERSHEY_DUPLEX, 0.8, 2)
    tx = x1 + 28 + (pw - 28 - tw)//2
    ty = py + th//2
    cv2.putText(img, fmt_plate, (tx, ty), cv2.FONT_HERSHEY_DUPLEX, 0.8, (10, 10, 10), 2, cv2.LINE_AA)

    out_path = os.path.join(out_dir, s["filename"])
    cv2.imwrite(out_path, img)
    print(f"Generated {s['filename']}")

print("All sample images created successfully!")

