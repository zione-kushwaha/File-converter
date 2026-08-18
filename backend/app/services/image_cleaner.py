import cv2
import numpy as np
from typing import Tuple, Dict, Any
from skimage.morphology import skeletonize

class ImageCleaner:
    """
    Advanced noise removal and image preprocessing service tailored
    for technical drawings, blueprints, sketches, and engineering diagrams.
    """

    @staticmethod
    def preprocess_image(
        image_bytes: bytes,
        denoise_strength: int = 10,
        threshold_mode: str = "adaptive",
        manual_threshold: int = 128,
        invert: bool = False,
        speckle_size: int = 15,
        morph_close_size: int = 1,
        morph_open_size: int = 1
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
        """
        Processes a raw input image:
        1. Decodes to grayscale
        2. Denoises (Non-Local Means / Bilateral)
        3. Applies adaptive or Otsu thresholding to separate foreground lines
        4. Removes isolated speckles and scanner noise via connected component filtering
        5. Performs morphological operations (close gaps, open dust)
        
        Returns:
            binary_cleaned: Binary mask (255 for drawing lines/foreground, 0 for background)
            skeleton: 1-pixel wide skeletonized centerlines
            stats: Metadata regarding image dimensions and noise reduction
        """
        # 1. Decode raw bytes to OpenCV image
        nparr = np.frombuffer(image_bytes, np.uint8)
        img_color = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img_color is None:
            raise ValueError("Invalid or corrupted image format")

        h, w = img_color.shape[:2]
        gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)

        # 2. Denoising
        if denoise_strength > 0:
            # Fast bilateral filter preserves sharp technical lines while blurring scanner grain
            d = 5 + min(denoise_strength, 10)
            sigma_color = denoise_strength * 7
            sigma_space = denoise_strength * 7
            denoised = cv2.bilateralFilter(gray, d, sigma_color, sigma_space)
            
            # Non-local means denoising for higher noise levels
            if denoise_strength >= 15:
                denoised = cv2.fastNlMeansDenoising(denoised, None, h=denoise_strength, templateWindowSize=7, searchWindowSize=21)
        else:
            denoised = gray.copy()

        # 3. Binarization / Thresholding
        if threshold_mode == "adaptive":
            # Adaptive Gaussian Thresholding - handles uneven scanner lighting & paper shadows
            block_size = 21
            if block_size >= min(h, w):
                block_size = max(3, (min(h, w) // 2) * 2 + 1)
            binary = cv2.adaptiveThreshold(
                denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, block_size, 5
            )
        elif threshold_mode == "otsu":
            # Otsu's automatic global thresholding
            _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        else:
            # Manual thresholding
            _, binary = cv2.threshold(denoised, manual_threshold, 255, cv2.THRESH_BINARY_INV)

        # Invert handling if requested
        # By default, binary mask has 255 for lines and 0 for background.
        if invert:
            binary = cv2.bitwise_not(binary)

        # 4. Morphological Operations
        # Morphological Closing: bridges tiny micro-breaks in lines caused by scanner artifacts
        if morph_close_size > 0:
            kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (morph_close_size + 1, morph_close_size + 1))
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_close)

        # Morphological Opening: removes tiny salt-and-pepper noise
        if morph_open_size > 0:
            kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (morph_open_size + 1, morph_open_size + 1))
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open)

        # 5. Connected Component Speckle Removal
        # Removes isolated noise blobs smaller than speckle_size area (pixels)
        num_labels, labels, stats_cc, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        cleaned_mask = np.zeros_like(binary)
        
        noise_components_removed = 0
        for i in range(1, num_labels):
            area = stats_cc[i, cv2.CC_STAT_AREA]
            if area >= speckle_size:
                cleaned_mask[labels == i] = 255
            else:
                noise_components_removed += 1

        # 6. Skeletonization (Zhang-Suen / Lee algorithm via scikit-image)
        # Produces exact 1-pixel centerline strokes ideal for CAD Line / Polyline generation
        bool_img = cleaned_mask > 0
        skeleton_bool = skeletonize(bool_img)
        skeleton_mask = (skeleton_bool * 255).astype(np.uint8)

        stats = {
            "original_width": int(w),
            "original_height": int(h),
            "noise_speckles_filtered": int(noise_components_removed),
            "active_line_pixels": int(np.count_nonzero(cleaned_mask)),
            "skeleton_pixels": int(np.count_nonzero(skeleton_mask))
        }

        return cleaned_mask, skeleton_mask, stats

    @staticmethod
    def encode_image_png(img_array: np.ndarray) -> bytes:
        """Encodes an OpenCV image array to PNG bytes"""
        _, buffer = cv2.imencode('.png', img_array)
        return buffer.tobytes()
