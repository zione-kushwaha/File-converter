import io
import sys
from pathlib import Path
import cv2
import numpy as np
import pytest

# Ensure backend directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from fastapi.testclient import TestClient
from app.services.image_cleaner import ImageCleaner
from app.services.vectorizer import Vectorizer
from app.services.cad_exporter import CadExporter

client = TestClient(app)

def create_synthetic_noisy_test_image() -> bytes:
    """Generates an in-memory test image of a square and circle with salt-and-pepper noise"""
    img = np.full((300, 300), 255, dtype=np.uint8)
    
    # Draw geometric shapes (black lines on white paper)
    cv2.rectangle(img, (50, 50), (250, 250), 0, 3)
    cv2.circle(img, (150, 150), 40, 0, 2)

    # Add noise speckles
    for _ in range(500):
        rx = np.random.randint(0, 300)
        ry = np.random.randint(0, 300)
        img[ry, rx] = np.random.choice([0, 50, 200])

    _, buffer = cv2.imencode('.png', img)
    return buffer.tobytes()

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_image_cleaner():
    raw_bytes = create_synthetic_noisy_test_image()
    cleaned_mask, skeleton_mask, stats = ImageCleaner.preprocess_image(
        image_bytes=raw_bytes,
        denoise_strength=10,
        threshold_mode="adaptive",
        speckle_size=15
    )

    assert cleaned_mask is not None
    assert cleaned_mask.shape == (300, 300)
    assert skeleton_mask is not None
    assert skeleton_mask.shape == (300, 300)
    assert stats["original_width"] == 300
    assert stats["original_height"] == 300
    assert stats["noise_speckles_filtered"] >= 0
    assert stats["active_line_pixels"] > 0

    # Test raw speckle filter without prior bilateral blur
    _, _, raw_stats = ImageCleaner.preprocess_image(
        image_bytes=raw_bytes,
        denoise_strength=0,
        threshold_mode="otsu",
        speckle_size=20
    )
    assert raw_stats["noise_speckles_filtered"] >= 0

def test_vectorizer():
    raw_bytes = create_synthetic_noisy_test_image()
    cleaned_mask, skeleton_mask, _ = ImageCleaner.preprocess_image(
        image_bytes=raw_bytes,
        denoise_strength=10,
        threshold_mode="adaptive"
    )

    entities, stats = Vectorizer.vectorize(
        cleaned_mask=cleaned_mask,
        skeleton_mask=skeleton_mask,
        mode="centerline",
        approx_tolerance=1.5
    )

    assert len(entities) > 0
    assert stats["entity_count"] > 0
    assert stats["total_nodes"] > 0

    svg = Vectorizer.generate_svg_preview(entities, 300, 300)
    assert "<svg" in svg
    assert "</svg>" in svg
    assert "<path" in svg

def test_cad_exporter():
    raw_bytes = create_synthetic_noisy_test_image()
    cleaned_mask, skeleton_mask, _ = ImageCleaner.preprocess_image(
        image_bytes=raw_bytes,
        denoise_strength=10
    )
    entities, _ = Vectorizer.vectorize(cleaned_mask, skeleton_mask, mode="centerline")

    dxf_bytes = CadExporter.export_dxf_bytes(entities, 300, 300)
    assert len(dxf_bytes) > 0
    assert b"SECTION" in dxf_bytes
    assert b"HEADER" in dxf_bytes
    assert b"ENTITIES" in dxf_bytes
    assert b"EOF" in dxf_bytes

def test_process_endpoint():
    raw_bytes = create_synthetic_noisy_test_image()
    files = {"file": ("test_cad_drawing.png", io.BytesIO(raw_bytes), "image/png")}
    data = {
        "denoise_strength": "10",
        "threshold_mode": "adaptive",
        "speckle_size": "15",
        "approx_tolerance": "1.5",
        "vector_mode": "centerline"
    }
    response = client.post("/api/process", files=files, data=data)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["success"] is True
    assert "job_id" in res_data
    assert "svg_preview" in res_data
    assert "cleaned_preview_url" in res_data
    assert res_data["stats"]["entity_count"] > 0

    # Test downloading DXF
    job_id = res_data["job_id"]
    dl_response = client.get(f"/api/download/{job_id}/dxf")
    assert dl_response.status_code == 200
    assert dl_response.headers.get("content-type") == "application/dxf"
