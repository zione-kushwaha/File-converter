import io
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
import ezdxf
from ezdxf import units

class CadExporter:
    """
    Exports vectorized geometric entities to standard AutoCAD DXF and DWG formats.
    Includes coordinate space conversion (Y-inversion from image space to CAD space)
    and structured layering.
    """

    @staticmethod
    def create_dxf(
        entities: List[Dict[str, Any]],
        img_width: int,
        img_height: int,
        dxf_version: str = "R2018",
        scale: float = 1.0
    ) -> ezdxf.document.Drawing:
        """
        Constructs an ezdxf Drawing document with organized layers and entities.
        """
        doc = ezdxf.new(dxfversion=dxf_version, setup=True)
        doc.units = units.MM  # Default metric millimeters
        
        # Configure modelspace
        msp = doc.modelspace()

        # Create structured CAD layers with standard AutoCAD ACI colors
        # Color 3 = Green, Color 4 = Cyan, Color 1 = Red, Color 7 = White
        if "CENTERLINES" not in doc.layers:
            doc.layers.add(name="CENTERLINES", color=3, linetype="CONTINUOUS")
        if "CONTOURS" not in doc.layers:
            doc.layers.add(name="CONTOURS", color=4, linetype="CONTINUOUS")
        if "BOUNDARY" not in doc.layers:
            doc.layers.add(name="BOUNDARY", color=1, linetype="CONTINUOUS")

        # Iterate over vectorized entities
        for ent in entities:
            raw_pts = ent.get("points", [])
            if len(raw_pts) < 2:
                continue

            # Convert from image coordinates (0,0 at top-left, Y downwards)
            # to CAD Cartesian coordinates (0,0 at bottom-left, Y upwards)
            cad_pts = [(p[0] * scale, (img_height - p[1]) * scale) for p in raw_pts]
            
            ent_type = ent.get("type", "centerline")
            is_closed = ent.get("is_closed", False)
            layer_name = "CONTOURS" if ent_type == "contour" else "CENTERLINES"

            # Add lightweight polyline to modelspace
            msp.add_lwpolyline(
                cad_pts,
                close=is_closed,
                dxfattribs={"layer": layer_name}
            )

        # Set drawing limits to image dimensions
        doc.header["$LIMMIN"] = (0.0, 0.0)
        doc.header["$LIMMAX"] = (img_width * scale, img_height * scale)

        return doc

    @staticmethod
    def export_dxf_bytes(
        entities: List[Dict[str, Any]],
        img_width: int,
        img_height: int,
        dxf_version: str = "R2018",
        scale: float = 1.0
    ) -> bytes:
        """Exports DXF document to binary bytes"""
        doc = CadExporter.create_dxf(entities, img_width, img_height, dxf_version, scale)
        stream = io.StringIO()
        doc.write(stream)
        return stream.getvalue().encode('utf-8')

    @staticmethod
    def export_dxf_file(
        entities: List[Dict[str, Any]],
        img_width: int,
        img_height: int,
        output_filepath: str,
        dxf_version: str = "R2018",
        scale: float = 1.0
    ) -> str:
        """Saves DXF document directly to a file on disk"""
        doc = CadExporter.create_dxf(entities, img_width, img_height, dxf_version, scale)
        doc.saveas(output_filepath)
        return output_filepath

    @staticmethod
    def try_convert_to_dwg(dxf_filepath: str, output_dwg_filepath: str) -> bool:
        """
        Attempts to convert DXF to binary DWG using external tools (ODA File Converter / LibreCAD)
        if available in the environment. If not present, returns False so application can serve DXF.
        """
        # Check for ODA File Converter in system PATH or common paths
        oda_executables = [
            "ODAFileConverter",
            "ODAFileConverter.exe",
            r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe",
            "/usr/bin/ODAFileConverter"
        ]
        
        oda_bin = None
        for path in oda_executables:
            if os.path.exists(path) or shutil_which(path):
                oda_bin = path
                break

        if oda_bin:
            try:
                input_dir = str(Path(dxf_filepath).parent)
                output_dir = str(Path(output_dwg_filepath).parent)
                input_filename = Path(dxf_filepath).name
                # ODA command: ODAFileConverter <input_dir> <output_dir> <out_version> <out_type> <recurse> <audit> [filter]
                cmd = [oda_bin, input_dir, output_dir, "ACAD2018", "DWG", "0", "1", input_filename]
                subprocess.run(cmd, check=True, timeout=30)
                expected_dwg = Path(output_dir) / (Path(dxf_filepath).stem + ".dwg")
                if expected_dwg.exists():
                    if str(expected_dwg) != output_dwg_filepath:
                        os.replace(expected_dwg, output_dwg_filepath)
                    return True
            except Exception as e:
                print(f"ODA DWG conversion warning: {e}")

        return False

def shutil_which(pgm: str) -> Optional[str]:
    import shutil
    return shutil.which(pgm)
