import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent
UPLOAD_DIR = PROJECT_DIR / "uploads"
OUTPUT_DIR = PROJECT_DIR / "outputs"
FRONTEND_DIR = PROJECT_DIR / "frontend"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Allowed file types
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"}
MAX_FILE_SIZE_MB = 25

# Default Conversion & Geometry Regularization Parameters
DEFAULT_DENOISE_STRENGTH = 10
DEFAULT_THRESHOLD_MODE = "adaptive"  # "adaptive", "otsu", "manual"
DEFAULT_MANUAL_THRESHOLD = 128
DEFAULT_INVERT = False
DEFAULT_MIN_CONTOUR_AREA = 15        # Speckle filter (pixels)
DEFAULT_APPROX_TOLERANCE = 1.5       # Polyline RDP tolerance
DEFAULT_VECTOR_MODE = "smart_cad"    # "smart_cad", "centerline", "contours", "both"
DEFAULT_ORTHO_SNAP = True            # Snap 0°/90° walls
DEFAULT_MIN_LINE_LEN = 12.0          # Minimum length for straight lines
DEFAULT_CORNER_SNAP_RADIUS = 8.0     # Corner & T-junction snapping radius
