import cv2
import numpy as np
from typing import List, Tuple, Dict, Any
from app.services.geometry_engine import GeometryEngine

class Vectorizer:
    """
    Converts raster masks into clean CAD entities (Straight Lines, Polylines, Contours)
    suitable for AutoCAD DXF/DWG export and browser SVG preview.
    """

    @staticmethod
    def rdp_simplify(points: np.ndarray, epsilon: float) -> np.ndarray:
        """Ramer-Douglas-Peucker polyline simplification"""
        if len(points) < 3:
            return points
        pts_cv = points.reshape((-1, 1, 2)).astype(np.float32)
        simplified = cv2.approxPolyDP(pts_cv, epsilon, False)
        return simplified.reshape((-1, 2))

    @staticmethod
    def extract_contours(binary_mask: np.ndarray, approx_epsilon: float = 1.5, min_area: float = 20.0) -> List[Dict[str, Any]]:
        """
        Extracts closed boundary contours from binary mask.
        Ideal for solid regions, mechanical cutouts, and wall thickness.
        """
        contours, hierarchy = cv2.findContours(
            binary_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_KCOS
        )
        
        vector_contours = []
        if contours is None:
            return vector_contours

        for i, cnt in enumerate(contours):
            area = cv2.contourArea(cnt)
            if area < min_area or len(cnt) < 3:
                continue
            
            # Approximate polygon to reduce node density
            approx = cv2.approxPolyDP(cnt, approx_epsilon, True)
            pts = approx.reshape(-1, 2).tolist()
            
            if len(pts) >= 3:
                is_hole = hierarchy[0][i][3] != -1 if hierarchy is not None else False
                vector_contours.append({
                    "points": pts,
                    "is_closed": True,
                    "is_hole": is_hole,
                    "type": "contour",
                    "area": float(area)
                })
                
        return vector_contours

    @staticmethod
    def extract_skeleton_paths(skeleton_mask: np.ndarray, approx_epsilon: float = 1.5) -> List[Dict[str, Any]]:
        """
        Extracts centerline paths from a 1-pixel wide skeletonized image.
        """
        contours, _ = cv2.findContours(
            skeleton_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE
        )

        paths = []
        if contours is None:
            return paths

        for cnt in contours:
            pts = cnt.reshape(-1, 2)
            if len(pts) < 2:
                continue
            
            pts_cv = pts.reshape((-1, 1, 2)).astype(np.float32)
            approx = cv2.approxPolyDP(pts_cv, approx_epsilon, False)
            approx_pts = approx.reshape(-1, 2).tolist()

            if len(approx_pts) >= 2:
                paths.append({
                    "points": approx_pts,
                    "is_closed": False,
                    "type": "centerline"
                })

        return paths

    @staticmethod
    def vectorize(
        cleaned_mask: np.ndarray,
        skeleton_mask: np.ndarray,
        mode: str = "smart_cad",
        approx_tolerance: float = 1.5,
        ortho_snap: bool = True,
        min_line_len: float = 12.0,
        corner_snap_radius: float = 8.0
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Performs full CAD vectorization:
        - 'smart_cad' (Recommended): Sub-pixel LSD straight lines + Ortho 0°/90° rectification + Collinear merging + Corner snapping.
        - 'centerline': Single-stroke skeleton centerlines.
        - 'contours': Clean boundary outlines.
        - 'both': Centerlines + contours.
        """
        h, w = cleaned_mask.shape
        entities = []

        if mode == "smart_cad":
            # 1. Detect clean straight CAD lines
            lines = GeometryEngine.detect_straight_lines(
                cleaned_image=cleaned_mask,
                min_length=min_line_len,
                ortho_snap=ortho_snap,
                ortho_angle_tol_deg=8.0,
                merge_collinear=True,
                collinear_dist_tol=5.0,
                collinear_gap_tol=18.0,
                snap_corners=True,
                corner_snap_radius=corner_snap_radius
            )
            entities.extend(lines)

            # 2. Add major closed boundary contours (e.g. fixtures, furniture, room boxes)
            contours = Vectorizer.extract_contours(cleaned_mask, approx_tolerance * 1.2, min_area=40.0)
            entities.extend(contours)

        elif mode == "centerline":
            centerlines = Vectorizer.extract_skeleton_paths(skeleton_mask, approx_tolerance)
            entities.extend(centerlines)

        elif mode == "contours":
            contours = Vectorizer.extract_contours(cleaned_mask, approx_tolerance)
            entities.extend(contours)

        elif mode in ("both", "all"):
            lines = GeometryEngine.detect_straight_lines(
                cleaned_image=cleaned_mask,
                min_length=min_line_len,
                ortho_snap=ortho_snap
            )
            entities.extend(lines)
            contours = Vectorizer.extract_contours(cleaned_mask, approx_tolerance)
            entities.extend(contours)

        total_points = sum(len(e["points"]) for e in entities)
        stats = {
            "entity_count": len(entities),
            "total_nodes": total_points,
            "canvas_width": w,
            "canvas_height": h,
            "vector_mode": mode
        }

        return entities, stats

    @staticmethod
    def generate_svg_preview(entities: List[Dict[str, Any]], width: int, height: int) -> str:
        """Generates an SVG string representation for fast, lossless browser preview"""
        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
            f'width="100%" height="100%" class="cad-svg-preview">'
        ]
        
        # AutoCAD CAD dark background grid pattern
        svg_parts.append('<defs><pattern id="cad-grid" width="25" height="25" patternUnits="userSpaceOnUse">'
                         '<path d="M 25 0 L 0 0 0 25" fill="none" stroke="#1e293b" stroke-width="0.75"/>'
                         '</pattern></defs>')
        svg_parts.append(f'<rect width="{width}" height="{height}" fill="#0b0f17" />')
        svg_parts.append(f'<rect width="{width}" height="{height}" fill="url(#cad-grid)" />')

        for ent in entities:
            pts = ent["points"]
            if not pts or len(pts) < 2:
                continue
            
            ent_type = ent.get("type", "line")
            if ent_type == "line":
                # Clean straight CAD line
                p1, p2 = pts[0], pts[1]
                svg_parts.append(
                    f'<line x1="{p1[0]:.2f}" y1="{p1[1]:.2f}" x2="{p2[0]:.2f}" y2="{p2[1]:.2f}" '
                    f'stroke="#38bdf8" stroke-width="1.8" stroke-linecap="round" />'
                )
            else:
                d_cmd = "M " + " L ".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts)
                if ent.get("is_closed"):
                    d_cmd += " Z"
                    stroke_color = "#4ade80"  # Emerald for contours/boxes
                    stroke_width = "1.5"
                else:
                    stroke_color = "#facc15"  # Yellow for centerlines
                    stroke_width = "1.2"

                svg_parts.append(
                    f'<path d="{d_cmd}" fill="none" stroke="{stroke_color}" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round" />'
                )

        svg_parts.append('</svg>')
        return "".join(svg_parts)
