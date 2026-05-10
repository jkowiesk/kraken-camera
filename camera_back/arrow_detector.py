#!/usr/bin/env python3
"""Arrow shape detector using pure OpenCV (no ML).

Detects arrow contours in a BGR frame and returns their direction
(left / right / up / down).

Usage:
    from arrow_detector import detect_arrows

    arrows = detect_arrows(frame_bgr)
    for a in arrows:
        print(a["direction"], a["bbox"])
"""

from __future__ import annotations

import cv2
import numpy as np


def detect_arrows(frame_bgr: np.ndarray) -> list:
    """Detect arrow shapes via contour analysis + PCA.

    Works on both light-on-dark and dark-on-light arrows.
    Returns list of dicts: {direction, bbox (x1, y1, x2, y2)}.

    Key filters applied in order:
      1. Area range (0.7 % – 40 % of frame)
      2. Solidity  0.60 – 0.90  (concave but not shredded)
      3. Bounding-box elongation 1.15 – 4.0  (not square, not a line)
      4. 2–5 deep convexity defects (depth > 25 px)
      5. PCA eigenvalue ratio >= 1.3  (elongated; compact sign arrows ~1.4)
      6. Direction-consistent aspect ratio
      7. Symmetric defect geometry  (two deepest notches on
         opposite sides of the primary axis, at similar position
         along it)
    """
    h, w = frame_bgr.shape[:2]
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)

    min_area = h * w * 0.010  # >= 1.0 % of frame
    max_area = h * w * 0.40  # <= 40 % of frame

    found: list = []
    seen_boxes: list = []

    for invert in (False, True):
        img = cv2.bitwise_not(blurred) if invert else blurred.copy()
        _, thresh = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = np.ones((5, 5), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

        # RETR_LIST: return ALL contours (inner + outer).
        # RETR_EXTERNAL would miss arrows that are dark shapes inside
        # a lighter enclosing shape (e.g. dark arrow inside white circle).
        contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if not (min_area < area < max_area):
                continue

            # ── 1. Solidity ───────────────────────────────────────────────────
            hull_pts = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull_pts)
            if hull_area < 1:
                continue
            solidity = area / hull_area
            if not (0.60 < solidity < 0.90):
                continue

            # ── 2. Bounding-box elongation ────────────────────────────────────
            bx, by, bw_r, bh_r = cv2.boundingRect(cnt)
            elongation = max(bw_r, bh_r) / max(min(bw_r, bh_r), 1)
            if not (1.15 <= elongation <= 4.0):
                continue

            # ── 2b. Must be fully inside the frame (no border blobs) ──────────
            border = 5
            if (
                bx <= border
                or by <= border
                or (bx + bw_r) >= (w - border)
                or (by + bh_r) >= (h - border)
            ):
                continue

            # ── 3. Convexity defects: 2–5 deep notches ───────────────────────
            hull_idx = cv2.convexHull(cnt, returnPoints=False)
            if len(hull_idx) < 4:
                continue
            try:
                defects = cv2.convexityDefects(cnt, hull_idx)
            except cv2.error:
                continue
            if defects is None:
                continue
            sig = [d[0] for d in defects if d[0][3] / 256.0 > 25]
            if not (2 <= len(sig) <= 8):  # allow up to 8 for complex shapes
                continue

            # ── 4. PCA: eigenvalue elongation ratio ───────────────────────────
            pts = cnt.reshape(-1, 2).astype(np.float32)
            mean_pt, eigvecs, eigvals = cv2.PCACompute2(pts, mean=None)
            ev0, ev1 = float(eigvals.ravel()[0]), float(eigvals.ravel()[1])
            if ev1 > 0 and ev0 / ev1 < 1.3:
                continue
            primary = eigvecs[0]
            secondary = eigvecs[1]
            centered = pts - mean_pt
            proj = (centered @ primary).ravel()

            # ── 5. Asymmetry → tip direction ──────────────────────────────────
            p90 = float(np.percentile(np.abs(proj), 90))
            pos_ext = int(np.sum(proj > p90))
            neg_ext = int(np.sum(proj < -p90))
            tip = primary if pos_ext < neg_ext else -primary

            tip_flat = tip.ravel()
            angle = float(
                np.degrees(np.arctan2(float(tip_flat[1]), float(tip_flat[0])))
            )
            if -45 <= angle <= 45:
                direction = "right"
            elif 45 < angle <= 135:
                direction = "down"
            elif angle > 135 or angle <= -135:
                direction = "left"
            else:
                direction = "up"

            # ── 6. Aspect ratio must match direction ──────────────────────────
            if direction in ("left", "right") and bw_r < bh_r * 1.1:
                continue  # horizontal arrow must be wider than tall
            if direction in ("up", "down") and bh_r < bw_r * 1.1:
                continue  # vertical arrow must be taller than wide

            # ── 7. Symmetric defect geometry ──────────────────────────────────
            # The two deepest notches must be on OPPOSITE sides of the primary
            # axis and at roughly the SAME position along it.
            sig_sorted = sorted(sig, key=lambda d: d[3], reverse=True)[:2]
            far_pts = [
                cnt[d[2]][0].astype(np.float32) - mean_pt.ravel() for d in sig_sorted
            ]
            if len(far_pts) == 2:
                s0 = float(np.dot(far_pts[0], secondary))
                s1 = float(np.dot(far_pts[1], secondary))
                if s0 * s1 > 0:  # same side → not an arrow
                    continue
                p0 = float(np.dot(far_pts[0], primary))
                p1 = float(np.dot(far_pts[1], primary))
                obj_len = float(proj.max() - proj.min())
                if obj_len > 0 and abs(p0 - p1) > 0.22 * obj_len:
                    continue  # notches not at the same cross-section

            bbox = (bx, by, bx + bw_r, by + bh_r)

            # ── IoU deduplication ─────────────────────────────────────────────
            dup = False
            for sb in seen_boxes:
                ix1 = max(bbox[0], sb[0])
                iy1 = max(bbox[1], sb[1])
                ix2 = min(bbox[2], sb[2])
                iy2 = min(bbox[3], sb[3])
                if ix2 > ix1 and iy2 > iy1:
                    inter = (ix2 - ix1) * (iy2 - iy1)
                    union = area + (sb[2] - sb[0]) * (sb[3] - sb[1]) - inter
                    if union > 0 and inter / union > 0.4:
                        dup = True
                        break
            if dup:
                continue

            seen_boxes.append(bbox)
            found.append({"direction": direction, "bbox": bbox})

    return found
