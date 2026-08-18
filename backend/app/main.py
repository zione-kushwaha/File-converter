import os
import io
import time
import uuid
import base64
from pathlib import Path
from typing import Optional

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
    denoise_strength: int = Form(DEFAULT_DENOISE_STRENGTH),
    threshold_mode: str = Form(DEFAULT_THRESHOLD_MODE),
    manual_threshold: int = Form(DEFAULT_MANUAL_THRESHOLD),
    invert: bool = Form(DEFAULT_INVERT),
    speckle_size: int = Form(DEFAULT_MIN_CONTOUR_AREA),
    approx_tolerance: float = Form(DEFAULT_APPROX_TOLERANCE),
    vector_mode: str = Form(DEFAULT_VECTOR_MODE),
    ortho_snap: bool = Form(DEFAULT_ORTHO_SNAP),
    min_line_len: float = Form(DEFAULT_MIN_LINE_LEN),
    corner_snap_radius: float = Form(DEFAULT_CORNER_SNAP_RADIUS),
    scale: float = Form(1.0)
):
    """
    Process image with custom noise removal and geometric CAD regularization parameters.
    """
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{file_ext}'. Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    t0 = time.time()
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        # Step 1: Denoise & Clean Image
        cleaned_mask, skeleton_mask, clean_stats = ImageCleaner.preprocess_image(
            image_bytes=image_bytes,
            denoise_strength=denoise_strength,
            threshold_mode=threshold_mode,
            manual_threshold=manual_threshold,
            invert=invert,
            speckle_size=speckle_size
        )

        w = clean_stats["original_width"]
        h = clean_stats["original_height"]

        # Step 2: Vectorize geometry with Smart CAD regularization
        entities, vec_stats = Vectorizer.vectorize(
            cleaned_mask=cleaned_mask,
            skeleton_mask=skeleton_mask,
            mode=vector_mode,
            approx_tolerance=approx_tolerance,
            ortho_snap=ortho_snap,
            min_line_len=min_line_len,
            corner_snap_radius=corner_snap_radius
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
            scale=scale
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

        return {
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
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image conversion failed: {str(e)}")

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
