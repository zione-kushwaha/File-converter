import math
import cv2
import numpy as np
from typing import List, Tuple, Dict, Any

class GeometryEngine:
    """
    Advanced CAD Geometry Extraction & Regularization Engine.
    Transforms pixelated, rasterized sketches and blueprints into clean,
    straight, orthogonal, and editable CAD lines (AutoCAD LINE/LWPOLYLINE).
    """

    @staticmethod
    def detect_straight_lines(
        cleaned_image: np.ndarray,
        min_length: float = 12.0,
        ortho_snap: bool = True,
        ortho_angle_tol_deg: float = 8.0,
        merge_collinear: bool = True,
        collinear_dist_tol: float = 5.0,
        collinear_gap_tol: float = 18.0,
        snap_corners: bool = True,
        corner_snap_radius: float = 8.0,
        max_segments: int = 2000
    ) -> List[Dict[str, Any]]:
        """
        Extracts clean, regularized straight CAD lines using sub-pixel Line Segment Detection (LSD),
        orthogonal rectification (0°/90°/180°/270°), collinear merging, and corner snapping.
        """
        if len(cleaned_image.shape) == 3:
            gray = cv2.cvtColor(cleaned_image, cv2.COLOR_BGR2GRAY)
        else:
            gray = cleaned_image

        # Run Line Segment Detector
        lsd = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
        lines, _, _, _ = lsd.detect(gray)

        if lines is None or len(lines) == 0:
            return []

        raw_segments = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if not (math.isfinite(x1) and math.isfinite(y1) and math.isfinite(x2) and math.isfinite(y2)):
                continue
            length = math.hypot(x2 - x1, y2 - y1)
            if length >= min_length:
                raw_segments.append([float(x1), float(y1), float(x2), float(y2), length])

        if not raw_segments:
            return []

        # Sort by length descending and cap max segments for fast performance
        raw_segments.sort(key=lambda s: s[4], reverse=True)
        if len(raw_segments) > max_segments:
            raw_segments = raw_segments[:max_segments]

        # Extract [x1, y1, x2, y2]
        segments = [[s[0], s[1], s[2], s[3]] for s in raw_segments]

        # 1. Orthogonal Rectification (0°, 90°, 180°, 270°)
        if ortho_snap:
            rectified = []
            angle_tol_rad = math.radians(ortho_angle_tol_deg)
            for seg in segments:
                x1, y1, x2, y2 = seg
                dx = x2 - x1
                dy = y2 - y1
                angle = math.atan2(dy, dx)
                
                # Near horizontal
                if abs(angle) <= angle_tol_rad or abs(abs(angle) - math.pi) <= angle_tol_rad:
                    avg_y = (y1 + y2) / 2.0
                    rectified.append([x1, avg_y, x2, avg_y])
                # Near vertical
                elif abs(abs(angle) - math.pi / 2.0) <= angle_tol_rad:
                    avg_x = (x1 + x2) / 2.0
                    rectified.append([avg_x, y1, avg_x, y2])
                else:
                    rectified.append([x1, y1, x2, y2])
            segments = rectified

        # 2. Merge Collinear & Overlapping Segments
        if merge_collinear and len(segments) > 1:
            segments = GeometryEngine._merge_collinear_lines(
                segments, collinear_dist_tol, collinear_gap_tol
            )

        # 3. Snap Corners and T-Junctions
        if snap_corners and len(segments) > 1:
            segments = GeometryEngine._snap_intersections(
                segments, corner_snap_radius
            )

        # Build output structure
        entities = []
        for seg in segments:
            x1, y1, x2, y2 = seg
            length = math.hypot(x2 - x1, y2 - y1)
            if length >= min_length:
                entities.append({
                    "type": "line",
                    "points": [[round(x1, 2), round(y1, 2)], [round(x2, 2), round(y2, 2)]],
                    "is_closed": False,
                    "length": round(length, 2)
                })

        return entities

    @staticmethod
    def _merge_collinear_lines(
        segments: List[List[float]],
        dist_tol: float = 5.0,
        gap_tol: float = 18.0
    ) -> List[List[float]]:
        merged = []
        used = [False] * len(segments)

        for i in range(len(segments)):
            if used[i]:
                continue
            
            p1_x, p1_y, p2_x, p2_y = segments[i]
            dx = p2_x - p1_x
            dy = p2_y - p1_y
            base_len = math.hypot(dx, dy)
            if base_len == 0:
                continue

            ux = dx / base_len
            uy = dy / base_len

            cluster_points = [(0.0, p1_x, p1_y), (base_len, p2_x, p2_y)]
            used[i] = True

            for j in range(i + 1, min(len(segments), i + 400)):
                if used[j]:
                    continue
                
                q1_x, q1_y, q2_x, q2_y = segments[j]
                q_dx = q2_x - q1_x
                q_dy = q2_y - q1_y
                q_len = math.hypot(q_dx, q_dy)
                if q_len == 0:
                    continue

                q_ux = q_dx / q_len
                q_uy = q_dy / q_len

                # Parallel check
                dot = abs(ux * q_ux + uy * q_uy)
                if dot < 0.985:
                    continue

                # Project q1 and q2 onto base line
                proj1 = (q1_x - p1_x) * ux + (q1_y - p1_y) * uy
                proj2 = (q2_x - p1_x) * ux + (q2_y - p1_y) * uy

                perp_dist1 = abs((q1_x - p1_x) * -uy + (q1_y - p1_y) * ux)
                perp_dist2 = abs((q2_x - p1_x) * -uy + (q2_y - p1_y) * ux)

                if max(perp_dist1, perp_dist2) <= dist_tol:
                    min_proj = min(proj1, proj2)
                    max_proj = max(proj1, proj2)

                    curr_min = min(pt[0] for pt in cluster_points)
                    curr_max = max(pt[0] for pt in cluster_points)

                    if not (min_proj > curr_max + gap_tol or max_proj < curr_min - gap_tol):
                        cluster_points.append((proj1, q1_x, q1_y))
                        cluster_points.append((proj2, q2_x, q2_y))
                        used[j] = True

            cluster_points.sort(key=lambda item: item[0])
            start_pt = cluster_points[0]
            end_pt = cluster_points[-1]
            merged.append([start_pt[1], start_pt[2], end_pt[1], end_pt[2]])

        return merged

    @staticmethod
    def _snap_intersections(
        segments: List[List[float]],
        snap_radius: float = 8.0
    ) -> List[List[float]]:
        snapped = [list(s) for s in segments]
        n = len(snapped)

        # 1. Endpoint-to-Endpoint Snapping (L-corners)
        for i in range(n):
            for j in range(i + 1, min(n, i + 300)):
                pairs = [
                    (0, 1, 0, 1),
                    (0, 1, 2, 3),
                    (2, 3, 0, 1),
                    (2, 3, 2, 3),
                ]
                for x1_idx, y1_idx, x2_idx, y2_idx in pairs:
                    p1x, p1y = snapped[i][x1_idx], snapped[i][y1_idx]
                    p2x, p2y = snapped[j][x2_idx], snapped[j][y2_idx]
                    dist = math.hypot(p2x - p1x, p2y - p1y)
                    if 0 < dist <= snap_radius:
                        mid_x = (p1x + p2x) / 2.0
                        mid_y = (p1y + p2y) / 2.0
                        snapped[i][x1_idx] = mid_x
                        snapped[i][y1_idx] = mid_y
                        snapped[j][x2_idx] = mid_x
                        snapped[j][y2_idx] = mid_y

        # 2. Endpoint-to-Line T-Junction Snapping
        for i in range(n):
            for end_idx in [(0, 1), (2, 3)]:
                ex, ey = snapped[i][end_idx[0]], snapped[i][end_idx[1]]
                for j in range(max(0, i - 100), min(n, i + 100)):
                    if i == j:
                        continue
                    lx1, ly1, lx2, ly2 = snapped[j]
                    ldx = lx2 - lx1
                    ldy = ly2 - ly1
                    llen_sq = ldx * ldx + ldy * ldy
                    if llen_sq == 0:
                        continue

                    t = ((ex - lx1) * ldx + (ey - ly1) * ldy) / llen_sq
                    if 0.05 < t < 0.95:
                        proj_x = lx1 + t * ldx
                        proj_y = ly1 + t * ldy
                        dist = math.hypot(ex - proj_x, ey - proj_y)
                        if dist <= snap_radius:
                            snapped[i][end_idx[0]] = proj_x
                            snapped[i][end_idx[1]] = proj_y

        return snapped
