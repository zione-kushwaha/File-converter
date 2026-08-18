# VectorCAD Studio: Image to DWG/DXF Converter & Noise Removal Engine

VectorCAD Studio is an end-to-end web application that converts raster images, architectural floor plans, engineering sketches, and blueprints into standard AutoCAD-compatible CAD files (**DXF / DWG**) with integrated computer vision noise reduction.

![VectorCAD Studio Overview](https://img.shields.io/badge/CAD-AutoCAD%20DXF%20%2F%20DWG-0284c7?style=flat-square)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-059669?style=flat-square)
![OpenCV](https://img.shields.io/badge/Engine-OpenCV%20%26%20ezdxf-38bdf8?style=flat-square)
![Docker](https://img.shields.io/badge/Deployment-Docker%20Ready-f59e0b?style=flat-square)

---

## Key Features

### 1. Intelligent Noise Reduction & Image Preprocessing
- **Bilateral & Non-Local Means Denoising**: Smooths out paper grain, scan artifacts, and compression noise while maintaining sharp technical corners.
- **Adaptive Gaussian & Otsu Binarization**: Automatically isolates line drawings even on scans with uneven lighting or shadows.
- **Despeckle & Connected Component Filtering**: Eliminates isolated dust dots, salt-and-pepper scan noise, and hair-line fractures.
- **Inverted Drawing Support**: Seamlessly processes blueprints (white lines on blue/dark background) as well as traditional sketches on white paper.

### 2. CAD Vectorization Engine
- **Centerline / Skeleton Tracing**: Uses topological thinning to extract crisp, single-stroke CAD polylines for architectural and schematic diagrams.
- **Boundary Contour Tracing**: Extracts closed CAD polygons for solid boundaries, mechanical profiles, and wall thickness.
- **Ramer-Douglas-Peucker (RDP) Polyline Simplification**: Reduces CAD vertex counts for clean, lightweight drawings.
- **Organized CAD Layers**: Automatically generates standard layers (`CENTERLINES`, `CONTOURS`, `BOUNDARY`) with distinct AutoCAD color indexing (ACI).

### 3. Modern Interactive Web Application
- **Side-by-Side Comparison**: Live split-view between original noisy scan and the cleaned CAD vector model.
- **Lossless SVG Preview**: High-speed browser vector renderer with CAD grid background and zoom/pan tools.
- **Instant Downloads**: Export to AutoCAD DXF (native in AutoCAD, Revit, SolidWorks, Fusion 360, LibreCAD) or DWG.

---

## Project Structure

```
fileconverter/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI endpoints & static file server
│   │   ├── config.py            # App settings & defaults
│   │   └── services/
│   │       ├── image_cleaner.py # OpenCV denoising & binarization
│   │       ├── vectorizer.py    # Polyline & skeleton tracing
│   │       └── cad_exporter.py  # ezdxf CAD generation & DWG converter
│   ├── requirements.txt         # Python dependencies
│   └── tests/
│       └── test_conversion.py   # Test suite
├── frontend/
│   ├── index.html               # Web UI layout
│   ├── styles.css               # Modern slate/cyan design system
│   └── app.js                   # Interactive canvas, sliders, API client
├── Dockerfile                   # Multi-stage production container
├── docker-compose.yml           # Single-command container deployment
└── README.md                    # Documentation
```

---

## Getting Started Locally

### Prerequisites
- Python 3.10+
- (Optional) Docker & Docker Compose

### 1. Run with Python Directly
```bash
# 1. Clone or open workspace
cd fileconverter

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Start the application
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser and navigate to: **`http://localhost:8000`**  
Interactive API docs are available at: **`http://localhost:8000/docs`**

---

## Running with Docker (Recommended)

### Using Docker Compose
```bash
docker compose up -d --build
```
Access the application at `http://localhost:8000`.

### Using Docker CLI Directly
```bash
# Build image
docker build -t vectorcad-converter .

# Run container
docker run -d -p 8000:8000 --name vectorcad-converter vectorcad-converter
```

---

## Production Cloud Deployment Guide

### Option 1: Deploy to Render.com (Web Service)
1. Push your repository to GitHub / GitLab.
2. Log in to [Render](https://render.com) and click **New + > Web Service**.
3. Connect your repository.
4. Select **Docker** environment.
5. Set Health Check Path to `/api/health`.
6. Click **Deploy Web Service**.

### Option 2: Deploy to Railway.app
1. Go to [Railway](https://railway.app) and create a **New Project**.
2. Select **Deploy from GitHub repo**.
3. Railway automatically detects the `Dockerfile` and deploys your service.
4. Add a public networking domain under Settings.

### Option 3: Deploy to Fly.io
```bash
# Install flyctl
fly launch
fly deploy
```

### Option 4: Deploy to Ubuntu / Debian Cloud VPS (Nginx + Systemd)
1. Copy project to `/var/www/vectorcad`.
2. Create virtual environment and install requirements:
   ```bash
   python3 -m venv venv
   ./venv/bin/pip install -r backend/requirements.txt
   ```
3. Create a Systemd service (`/etc/systemd/system/vectorcad.service`):
   ```ini
   [Unit]
   Description=VectorCAD Converter Service
   After=network.target

   [Service]
   User=www-data
   WorkingDirectory=/var/www/vectorcad/backend
   ExecStart=/var/www/vectorcad/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
4. Proxy with Nginx (`/etc/nginx/sites-available/vectorcad`):
   ```nginx
   server {
       listen 80;
       server_name yourdomain.com;
       client_max_body_size 50M;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       }
   }
   ```

---

## API Reference

### `POST /api/process`
Vectorizes an image with real-time parameter tuning.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file` | File | Required | Uploaded image file (PNG, JPG, TIFF, etc.) |
| `denoise_strength` | int | `10` | Filter strength (0-30) for grain/scanner blur |
| `threshold_mode` | string | `adaptive` | `adaptive`, `otsu`, or `manual` |
| `manual_threshold`| int | `128` | Manual threshold value (1-254) |
| `invert` | bool | `false` | Invert line/background (ideal for blueprints) |
| `speckle_size` | int | `15` | Minimum pixel area for isolated noise blobs |
| `approx_tolerance`| float | `1.5` | Polyline RDP simplification tolerance |
| `vector_mode` | string | `centerline` | `centerline`, `contours`, or `both` |
| `scale` | float | `1.0` | Coordinate scale multiplier |

### `GET /api/download/{job_id}/{format}`
Downloads generated CAD file (`dxf` or `dwg`).

### `GET /api/health`
Service health check status.

---

## License
MIT License. Open for commercial and personal CAD vectorization projects.
