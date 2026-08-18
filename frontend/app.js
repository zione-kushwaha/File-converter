/**
 * VectorCAD Studio - Frontend Application Logic
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('file-input');
  const fileDetails = document.getElementById('file-details');
  const filenameDisplay = document.getElementById('filename-display');
  const removeFileBtn = document.getElementById('remove-file-btn');
  const sampleBtn = document.getElementById('sample-btn');
  const sampleHeroBtn = document.getElementById('load-sample-hero');
  const processBtn = document.getElementById('process-btn');

  // Sliders & Controls
  const denoiseSlider = document.getElementById('denoise-slider');
  const denoiseVal = document.getElementById('denoise-val');
  const thresholdMode = document.getElementById('threshold-mode');
  const manualThreshGroup = document.getElementById('manual-thresh-group');
  const manualThreshSlider = document.getElementById('manual-thresh-slider');
  const manualThreshVal = document.getElementById('manual-thresh-val');
  const speckleSlider = document.getElementById('speckle-slider');
  const speckleVal = document.getElementById('speckle-val');
  const invertToggle = document.getElementById('invert-toggle');
  
  // CAD Geometry Controls
  const vectorMode = document.getElementById('vector-mode');
  const orthoToggle = document.getElementById('ortho-toggle');
  const minLenSlider = document.getElementById('min-len-slider');
  const minLenVal = document.getElementById('min-len-val');
  const cornerSnapSlider = document.getElementById('corner-snap-slider');
  const cornerSnapVal = document.getElementById('corner-snap-val');
  const toleranceSlider = document.getElementById('tolerance-slider');
  const toleranceVal = document.getElementById('tolerance-val');
  const scaleSelect = document.getElementById('scale-select');

  // Viewports & Canvas
  const tabBtns = document.querySelectorAll('.tab-btn');
  const viewContents = document.querySelectorAll('.view-content');
  const emptyState = document.getElementById('empty-state');
  const loadingOverlay = document.getElementById('loading-overlay');
  const svgRenderTarget = document.getElementById('svg-render-target');
  const cleanedImgTarget = document.getElementById('cleaned-img-target');
  const originalImgTarget = document.getElementById('original-img-target');
  const splitOriginalImg = document.getElementById('split-original-img');
  const splitSvgTarget = document.getElementById('split-svg-target');

  // Zoom
  const zoomInBtn = document.getElementById('zoom-in-btn');
  const zoomOutBtn = document.getElementById('zoom-out-btn');
  const zoomResetBtn = document.getElementById('zoom-reset-btn');

  // Stats & Exports
  const statStatus = document.getElementById('stat-status');
  const statSpeckles = document.getElementById('stat-speckles');
  const statEntities = document.getElementById('stat-entities');
  const statNodes = document.getElementById('stat-nodes');
  const statTime = document.getElementById('stat-time');
  const downloadDxfBtn = document.getElementById('download-dxf-btn');
  const downloadDwgBtn = document.getElementById('download-dwg-btn');

  // State
  let currentFile = null;
  let currentJobId = null;
  let currentZoom = 1.0;
  let debounceTimeout = null;

  // Slider value synchronization
  denoiseSlider.addEventListener('input', (e) => {
    denoiseVal.textContent = e.target.value;
    triggerAutoProcess();
  });

  thresholdMode.addEventListener('change', (e) => {
    if (e.target.value === 'manual') {
      manualThreshGroup.classList.remove('hidden');
    } else {
      manualThreshGroup.classList.add('hidden');
    }
    triggerAutoProcess();
  });

  manualThreshSlider.addEventListener('input', (e) => {
    manualThreshVal.textContent = e.target.value;
    triggerAutoProcess();
  });

  speckleSlider.addEventListener('input', (e) => {
    speckleVal.textContent = `${e.target.value} px`;
    triggerAutoProcess();
  });

  if (minLenSlider) {
    minLenSlider.addEventListener('input', (e) => {
      minLenVal.textContent = `${e.target.value} px`;
      triggerAutoProcess();
    });
  }

  if (cornerSnapSlider) {
    cornerSnapSlider.addEventListener('input', (e) => {
      cornerSnapVal.textContent = `${e.target.value} px`;
      triggerAutoProcess();
    });
  }

  toleranceSlider.addEventListener('input', (e) => {
    toleranceVal.textContent = e.target.value;
    triggerAutoProcess();
  });

  invertToggle.addEventListener('change', triggerAutoProcess);
  if (orthoToggle) orthoToggle.addEventListener('change', triggerAutoProcess);
  vectorMode.addEventListener('change', triggerAutoProcess);
  scaleSelect.addEventListener('change', triggerAutoProcess);

  // File Upload Handlers
  dropzone.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
  });

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  });

  removeFileBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    resetFileState();
  });

  // Sample blueprint loader
  sampleBtn.addEventListener('click', loadSampleDrawing);
  sampleHeroBtn.addEventListener('click', loadSampleDrawing);

  function resetFileState() {
    currentFile = null;
    currentJobId = null;
    fileInput.value = '';
    fileDetails.classList.add('hidden');
    dropzone.classList.remove('hidden');
    emptyState.classList.remove('hidden');
    svgRenderTarget.innerHTML = '';
    cleanedImgTarget.src = '';
    originalImgTarget.src = '';
    splitOriginalImg.src = '';
    splitSvgTarget.innerHTML = '';
    downloadDxfBtn.disabled = true;
    downloadDwgBtn.disabled = true;
    updateStats({ status: 'Ready' });
  }

  function handleFile(file) {
    currentFile = file;
    filenameDisplay.textContent = file.name;
    fileDetails.classList.remove('hidden');
    dropzone.classList.add('hidden');

    const reader = new FileReader();
    reader.onload = (e) => {
      originalImgTarget.src = e.target.result;
      splitOriginalImg.src = e.target.result;
    };
    reader.readAsDataURL(file);

    processImage();
  }

  // Load sample architectural blueprint with noise
  function loadSampleDrawing() {
    const canvas = document.createElement('canvas');
    canvas.width = 800;
    canvas.height = 600;
    const ctx = canvas.getContext('2d');

    // Paper background
    ctx.fillStyle = '#f8fafc';
    ctx.fillRect(0, 0, 800, 600);

    // Draw architectural floor plan elements
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 3;
    ctx.lineCap = 'square';

    // Outer walls
    ctx.strokeRect(80, 80, 640, 440);

    // Inner rooms
    ctx.beginPath();
    ctx.moveTo(340, 80);
    ctx.lineTo(340, 520);
    ctx.moveTo(80, 300);
    ctx.lineTo(340, 300);
    ctx.moveTo(340, 260);
    ctx.lineTo(720, 260);
    ctx.stroke();

    // Fixtures
    ctx.lineWidth = 1.5;
    ctx.strokeRect(120, 120, 80, 100);
    ctx.strokeRect(500, 360, 140, 90);

    // Add noise speckles
    const imgData = ctx.getImageData(0, 0, 800, 600);
    const data = imgData.data;
    for (let i = 0; i < 3000; i++) {
      const rx = Math.floor(Math.random() * 800);
      const ry = Math.floor(Math.random() * 600);
      const idx = (ry * 800 + rx) * 4;
      const noise = Math.random() > 0.5 ? 30 : 230;
      data[idx] = noise;
      data[idx + 1] = noise;
      data[idx + 2] = noise;
    }
    ctx.putImageData(imgData, 0, 0);

    canvas.toBlob((blob) => {
      const sampleFile = new File([blob], 'architectural_sample.png', { type: 'image/png' });
      handleFile(sampleFile);
      showToast('Sample architectural blueprint loaded!', 'success');
    }, 'image/png');
  }

  // Processing API call
  async function processImage() {
    if (!currentFile) return;

    loadingOverlay.classList.remove('hidden');
    emptyState.classList.add('hidden');
    statStatus.textContent = 'Processing...';

    const formData = new FormData();
    formData.append('file', currentFile);
    formData.append('denoise_strength', denoiseSlider.value);
    formData.append('threshold_mode', thresholdMode.value);
    formData.append('manual_threshold', manualThreshSlider.value);
    formData.append('invert', invertToggle.checked);
    formData.append('speckle_size', speckleSlider.value);
    formData.append('approx_tolerance', toleranceSlider.value);
    formData.append('vector_mode', vectorMode.value);
    formData.append('ortho_snap', orthoToggle ? orthoToggle.checked : true);
    formData.append('min_line_len', minLenSlider ? minLenSlider.value : 12.0);
    formData.append('corner_snap_radius', cornerSnapSlider ? cornerSnapSlider.value : 8.0);
    formData.append('scale', scaleSelect.value);

    try {
      const response = await fetch('/api/process', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Conversion failed');
      }

      const data = await response.json();
      currentJobId = data.job_id;

      // Update Views
      svgRenderTarget.innerHTML = data.svg_preview;
      splitSvgTarget.innerHTML = data.svg_preview;
      cleanedImgTarget.src = data.cleaned_preview_url;

      // Enable downloads
      downloadDxfBtn.disabled = false;
      downloadDwgBtn.disabled = false;

      // Update statistics
      updateStats({
        status: 'Clean CAD Generated',
        speckles: data.stats.noise_speckles_filtered,
        entities: data.stats.entity_count,
        nodes: data.stats.total_nodes,
        time: `${data.stats.processing_time_ms} ms`
      });

      showToast('Successfully generated clean editable CAD geometry!', 'success');
    } catch (err) {
      console.error(err);
      showToast(`Error: ${err.message}`, 'error');
      statStatus.textContent = 'Error';
    } finally {
      loadingOverlay.classList.add('hidden');
    }
  }

  function triggerAutoProcess() {
    if (!currentFile) return;
    clearTimeout(debounceTimeout);
    debounceTimeout = setTimeout(() => {
      processImage();
    }, 300);
  }

  processBtn.addEventListener('click', processImage);

  // Tab switching
  tabBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      tabBtns.forEach((b) => b.classList.remove('active'));
      viewContents.forEach((c) => c.classList.add('hidden'));

      btn.classList.add('active');
      const targetView = document.getElementById(`view-${btn.dataset.tab}`);
      if (targetView) targetView.classList.remove('hidden');
    });
  });

  // Zoom controls
  zoomInBtn.addEventListener('click', () => setZoom(currentZoom + 0.2));
  zoomOutBtn.addEventListener('click', () => setZoom(Math.max(0.2, currentZoom - 0.2)));
  zoomResetBtn.addEventListener('click', () => setZoom(1.0));

  function setZoom(val) {
    currentZoom = val;
    zoomResetBtn.textContent = `${Math.round(currentZoom * 100)}%`;
    const targets = document.querySelectorAll('.zoom-target');
    targets.forEach((t) => {
      t.style.transform = `scale(${currentZoom})`;
    });
  }

  // CAD Downloads
  downloadDxfBtn.addEventListener('click', () => {
    if (!currentJobId) return;
    window.location.href = `/api/download/${currentJobId}/dxf`;
    showToast('Downloading AutoCAD DXF...', 'success');
  });

  downloadDwgBtn.addEventListener('click', () => {
    if (!currentJobId) return;
    window.location.href = `/api/download/${currentJobId}/dwg`;
    showToast('Downloading DWG...', 'success');
  });

  function updateStats(stats) {
    if (stats.status) statStatus.textContent = stats.status;
    if (stats.speckles !== undefined) statSpeckles.textContent = stats.speckles;
    if (stats.entities !== undefined) statEntities.textContent = stats.entities;
    if (stats.nodes !== undefined) statNodes.textContent = stats.nodes;
    if (stats.time !== undefined) statTime.textContent = stats.time;
  }

  function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.remove();
    }, 4000);
  }
});
