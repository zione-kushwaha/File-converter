import cv2
import numpy as np
from typing import List, Tuple, Dict, Any

class Vectorizer:
    """
    Converts raster masks into vector entities (polylines, lines, contours)
    suitable for CAD format export and SVG preview.
    """

    @staticmethod
    def rdp_simplify(points: np.ndarray, epsilon: float) -> np.ndarray:
        """Ramer-Douglas-Peucker polyline simplification"""
        if len(points) < 3:
            return points
        # Use OpenCV's approxPolyDP
        pts_cv = points.reshape((-1, 1, 2)).astype(np.float32)
        simplified = cv2.approxPolyDP(pts_cv, epsilon, False)
        return simplified.reshape((-1, 2))

    @staticmethod
    def extract_contours(binary_mask: np.ndarray, approx_epsilon: float = 1.5) -> List[Dict[str, Any]]:
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
            if len(cnt) < 3:
                continue
            
            # Approximate polygon to reduce node density
            approx = cv2.approxPolyDP(cnt, approx_epsilon, True)
            pts = approx.reshape(-1, 2).tolist()
            
            if len(pts) >= 3:
                # Is hole (inner contour) or external
                is_hole = hierarchy[0][i][3] != -1 if hierarchy is not None else False
                vector_contours.append({
                    "points": pts,
                    "is_closed": True,
                    "is_hole": is_hole,
                    "type": "contour"
                })
                
        return vector_contours

    @staticmethod
    def extract_skeleton_paths(skeleton_mask: np.ndarray, approx_epsilon: float = 1.5) -> List[Dict[str, Any]]:
        """
        Extracts centerline paths from a 1-pixel wide skeletonized image.
        Traces graph branches to generate precise architectural / engineering CAD centerlines.
        """
        h, w = skeleton_mask.shape
        # Use findContours on skeleton with RETR_LIST to get all distinct linear segments
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
            
            # Simplify polyline
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
        mode: str = "centerline",
        approx_tolerance: float = 1.5
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Performs full vectorization based on selected mode:
        - 'centerline': single-stroke CAD line tracing (ideal for schematics/sketches)
        - 'contours': outline tracing (ideal for logos/cutouts/wall perimeters)
        - 'both': outputs both layers
        """
        h, w = cleaned_mask.shape
        entities = []

        if mode in ("centerline", "both"):
            centerlines = Vectorizer.extract_skeleton_paths(skeleton_mask, approx_tolerance)
            entities.extend(centerlines)

        if mode in ("contours", "both"):
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
        
        # Background grid styling
        svg_parts.append('<defs><pattern id="cad-grid" width="20" height="20" patternUnits="userSpaceOnUse">'
                         '<path d="M 20 0 L 0 0 0 20" fill="none" stroke="#2a3342" stroke-width="0.5"/>'
                         '</pattern></defs>')
        svg_parts.append(f'<rect width="{width}" height="{height}" fill="#111827" />')
        svg_parts.append(f'<rect width="{width}" height="{height}" fill="url(#cad-grid)" />')

        for ent in entities:
            pts = ent["points"]
            if not pts:
                continue
            
            d_cmd = "M " + " L ".join(f"{p[0]:.2f},{p[1]:.2f}" for p in pts)
            if ent.get("is_closed"):
                d_cmd += " Z"
                stroke_color = "#38bdf8"  # Cyan for contours
                stroke_width = "1.5"
            else:
                stroke_color = "#4ade80"  # Neon green for centerlines
                stroke_width = "1.2"

            svg_parts.append(
                f'<path d="{d_cmd}" fill="none" stroke="{stroke_color}" stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round" />'
            )

        svg_parts.append('</svg>')
        return "".join(svg_parts)
