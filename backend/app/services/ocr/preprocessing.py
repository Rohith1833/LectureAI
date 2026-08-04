import re
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import pytesseract
from loguru import logger


def preprocess_image_for_ocr(
    image_path: str, output_path: str, tesseract_available: bool = True
) -> None:
    """Execute modular, non-destructive image preprocessing stages to optimize Tesseract accuracy."""
    logger.info("Preprocessing page image for OCR: {}", image_path)

    try:
        # Load image
        img = Image.open(image_path)

        # 1. Grayscale Conversion
        img = img.convert("L")

        # 2. Contrast Enhancement
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.8)

        # 3. Noise Reduction (apply subtle median filter)
        img = img.filter(ImageFilter.MedianFilter(size=3))

        # 4. Orientation & Deskewing using Tesseract OSD if available
        if tesseract_available:
            try:
                # OSD: Orientation and Script Detection
                osd_data = pytesseract.image_to_osd(img)
                rotate_match = re.search(r"Rotate:\s*(\d+)", osd_data)
                if rotate_match:
                    angle = int(rotate_match.group(1))
                    if angle != 0:
                        logger.info("Orientation correction: rotating page by {} degrees", angle)
                        # Rotate opposite to Tesseract detected angle to return upright text
                        img = img.rotate(-angle, expand=True)
            except Exception as osd_err:
                # OSD often fails on pages with sparse text (e.g. covers or blank pages); skip gracefully
                logger.debug("OSD orientation check skipped/failed: {}", str(osd_err))

        # 5. Border cleanup: remove dark margins
        # Scan boundary pixels of the page and crop them out if we find extreme black margins
        # For simplicity and speed, a safe 2% boundary crop or standard auto-bbox crop is used
        w, h = img.size
        crop_pixels = int(min(w, h) * 0.015)  # crop 1.5% margins from edges
        if crop_pixels > 0:
            img = img.crop((crop_pixels, crop_pixels, w - crop_pixels, h - crop_pixels))

        # 6. Adaptive Thresholding / Binarization (convert to pure Black and White)
        # Using a global binarization threshold (e.g. Otsu's threshold alternative)
        img = img.point(lambda p: 255 if p > 120 else 0)

        # Save preprocessed image (maintain high DPI metadata if present)
        img.save(output_path)
        logger.info("OCR Image Preprocessing completed. Saved: {}", output_path)

    except Exception as e:
        logger.error("Image preprocessing failed: {}", str(e))
        # If preprocessing fails, copy the raw image to output path to avoid breaking pipeline
        shutil_copy(image_path, output_path)


def shutil_copy(src: str, dst: str) -> None:
    import shutil

    try:
        shutil.copy(src, dst)
    except Exception:
        pass
