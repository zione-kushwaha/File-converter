import os
import io
import time
import uuid
import base64
import traceback
from pathlib import Path
from typing import Optional, Union

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import (
    UPLOAD_DIR, OUTPUT_DIR, FRONTEND_DIR, ALLOWED_EXTENSIONS,
    DEFAULT_DENOISE_STRENGTH, DEFAULT_THRESHOLD_MODE, DEFAULT_MANUAL_THRESHOLD,
    DEFAULT_INVERT, DEFAULT_MIN_CONTOUR_AREA, DEFAULT_APPROX_TOLERANCE,
    DEFAULT_VECTOR_MODE, DEFAULT_ORTHO_SNAP, DEFAULT_MIN_LINE_LEN,
    DEFAULT_CORNER_SNAP_RADIUS
)
from app.services.image_cleaner import ImageCleaner
from app.services.vectorizer import Vectorizer
from app.services.cad_exporter import CadExporter

app = FastAPI(
    title="VectorCAD Studio API",
    description="Vectorize images and blueprints to clean AutoCAD DXF/DWG with noise removal and geometric regularization",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

conversion_cache = {}

def parse_bool(val: Union[bool, str, int]) -> bool:
    """Safely converts form values to boolean"""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes", "on")
    if isinstance(val, (int, float)):
        return bool(val)
    return False

@app.get("/api/health")
async def health_check():
    """Health check endpoint for Docker and cloud monitoring"""
    return {
        "status": "healthy",
        "service": "vectorcad-converter",
        "version": "1.1.0"
    }

@app.post("/api/process")
async def process_image_endpoint(
    file: UploadFile = File(...),
    denoise_strength: str = Form(str(DEFAULT_DENOISE_STRENGTH)),
    threshold_mode: str = Form(DEFAULT_THRESHOLD_MODE),
    manual_threshold: str = Form(str(DEFAULT_MANUAL_THRESHOLD)),
    invert: str = Form("false"),
    speckle_size: str = Form(str(DEFAULT_MIN_CONTOUR_AREA)),
    approx_tolerance: str = Form(str(DEFAULT_APPROX_TOLERANCE)),
    vector_mode: str = Form(DEFAULT_VECTOR_MODE),
    ortho_snap: str = Form("true"),
    min_line_len: str = Form(str(DEFAULT_MIN_LINE_LEN)),
    corner_snap_radius: str = Form(str(DEFAULT_CORNER_SNAP_RADIUS)),
    scale: str = Form("1.0")
):
    """
    Process image with custom noise removal and geometric CAD regularization parameters.
    """
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Unsupported file format '{file_ext}'. Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}"}
        )

    t0 = time.time()
    try:
        image_bytes = await file.read()
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": f"Failed to read uploaded file: {str(e)}"})

    if not image_bytes:
        return JSONResponse(status_code=400, content={"detail": "Uploaded file is empty."})

    try:
        # Parse inputs safely
        parsed_denoise = int(float(denoise_strength))
        parsed_manual_thresh = int(float(manual_threshold))
        parsed_invert = parse_bool(invert)
        parsed_speckle = int(float(speckle_size))
        parsed_approx = float(approx_tolerance)
        parsed_ortho = parse_bool(ortho_snap)
        parsed_min_line = float(min_line_len)
        parsed_corner_snap = float(corner_snap_radius)
        parsed_scale = float(scale)

        # Step 1: Denoise & Clean Image
        cleaned_mask, skeleton_mask, clean_stats = ImageCleaner.preprocess_image(
            image_bytes=image_bytes,
            denoise_strength=parsed_denoise,
            threshold_mode=threshold_mode,
            manual_threshold=parsed_manual_thresh,
            invert=parsed_invert,
            speckle_size=parsed_speckle
        )

        w = clean_stats["original_width"]
        h = clean_stats["original_height"]

        # Step 2: Vectorize geometry with Smart CAD regularization
        entities, vec_stats = Vectorizer.vectorize(
            cleaned_mask=cleaned_mask,
            skeleton_mask=skeleton_mask,
            mode=vector_mode,
            approx_tolerance=parsed_approx,
            ortho_snap=parsed_ortho,
            min_line_len=parsed_min_line,
            corner_snap_radius=parsed_corner_snap
        )

        # Step 3: Generate SVG preview
        svg_preview = Vectorizer.generate_svg_preview(entities, w, h)

        # Step 4: Encode preview image as base64
        cleaned_png_bytes = ImageCleaner.encode_image_png(cleaned_mask)
        cleaned_b64 = f"data:image/png;base64,{base64.b64encode(cleaned_png_bytes).decode('utf-8')}"

        # Step 5: Save DXF with native CAD LINE entities
        job_id = str(uuid.uuid4())
        safe_stem = "".join(c for c in Path(file.filename or "drawing").stem if c.isalnum() or c in ('_', '-')) or "drawing"
        dxf_filename = f"{safe_stem}_{job_id[:8]}.dxf"
        dxf_path = str(OUTPUT_DIR / dxf_filename)
        
        CadExporter.export_dxf_file(
            entities=entities,
            img_width=w,
            img_height=h,
            output_filepath=dxf_path,
            scale=parsed_scale
        )

        # Step 6: DWG check
        dwg_filename = f"{safe_stem}_{job_id[:8]}.dwg"
        dwg_path = str(OUTPUT_DIR / dwg_filename)
        dwg_available = CadExporter.try_convert_to_dwg(dxf_path, dwg_path)

        total_time_ms = round((time.time() - t0) * 1000, 1)

        conversion_cache[job_id] = {
            "dxf_path": dxf_path,
            "dxf_filename": dxf_filename,
            "dwg_path": dwg_path if dwg_available else None,
            "dwg_filename": dwg_filename if dwg_available else None,
            "created_at": time.time()
        }

        return JSONResponse(content={
            "success": True,
            "job_id": job_id,
            "dxf_filename": dxf_filename,
            "dwg_available": dwg_available,
            "dwg_filename": dwg_filename if dwg_available else None,
            "cleaned_preview_url": cleaned_b64,
            "svg_preview": svg_preview,
            "stats": {
                **clean_stats,
                **vec_stats,
                "processing_time_ms": total_time_ms
            }
        })

    except Exception as e:
        print("Processing error traceback:", traceback.format_exc())
        return JSONResponse(
            status_code=500,
            content={"detail": f"Image processing error: {str(e)}"}
        )

@app.get("/api/download/{job_id}/{format_type}")
async def download_cad_file(job_id: str, format_type: str):
    """
    Downloads the generated DXF or DWG file by job ID.
    """
    job = conversion_cache.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Conversion job expired or not found")

    if format_type.lower() == "dwg" and job.get("dwg_path") and os.path.exists(job["dwg_path"]):
        return FileResponse(
            path=job["dwg_path"],
            filename=job["dwg_filename"],
            media_type="application/acad"
        )
    elif format_type.lower() in ("dxf", "dwg") and os.path.exists(job["dxf_path"]):
        return FileResponse(
            path=job["dxf_path"],
            filename=job["dxf_filename"],
            media_type="application/dxf"
        )
    else:
        raise HTTPException(status_code=404, detail="Requested CAD file not found")

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
