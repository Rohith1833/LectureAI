import re
import shutil
from PIL import Image, ImageOps, ImageEnhance, ImageFilter, ImageChops
import pytesseract
from loguru import logger


def _otsu_threshold(gray_img: Image.Image) -> int:
    """Compute optimal global binarization threshold using Otsu's method from PIL histogram."""
    hist = gray_img.histogram()
    total = sum(hist)
    if total == 0:
        return 128

    sum_total = sum(i * hist[i] for i in range(256))
    sum_b = 0
    w_b = 0
    var_max = 0.0
    threshold = 128

    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > var_max:
            var_max = var_between
            threshold = t

    return threshold


def _local_adaptive_binarize(gray_img: Image.Image, radius: int = 25, offset: int = 12) -> Image.Image:
    """Local adaptive thresholding via background estimation (handles shadows and uneven lighting)."""
    bg = gray_img.filter(ImageFilter.BoxBlur(radius=radius))
    # diff > 0 where background is brighter than foreground (dark text on lighter background)
    diff = ImageChops.subtract(bg, gray_img)
    return diff.point(lambda d: 0 if d > offset else 255)


def preprocess_image_for_ocr(
    image_path: str,
    output_path: str,
    tesseract_available: bool = True,
    mode: str = "standard",
) -> None:
    """Execute modular image preprocessing to optimize Tesseract accuracy on clean and degraded scans.

    Modes:
    - 'standard': autocontrast, OSD deskew, local adaptive thresholding.
    - 'aggressive': stronger contrast/sharpening + Otsu fallback for faint or noisy scans.
    """
    logger.info("Preprocessing page image for OCR (mode={}): {}", mode, image_path)

    try:
        img = Image.open(image_path)

        # 1. Grayscale conversion & autocontrast
        img = img.convert("L")
        img = ImageOps.autocontrast(img, cutoff=1 if mode == "standard" else 2)

        # 2. Upscale small/low-res images so Tesseract has >= 20px cap height
        w, h = img.size
        if max(w, h) < 1600:
            scale = 2
            img = img.resize((w * scale, h * scale), Image.Resampling.BICUBIC)
            w, h = img.size

        # 3. Orientation correction using Tesseract OSD on a fast downscaled copy
        if tesseract_available:
            try:
                osd_img = img
                if max(w, h) > 1200:
                    ratio = 1200.0 / max(w, h)
                    osd_img = img.resize((int(w * ratio), int(h * ratio)), Image.Resampling.BILINEAR)
                osd_data = pytesseract.image_to_osd(osd_img)
                rotate_match = re.search(r"Rotate:\s*(\d+)", osd_data)
                if rotate_match:
                    angle = int(rotate_match.group(1))
                    if angle != 0:
                        logger.info("Orientation correction: rotating page by {} degrees", angle)
                        img = img.rotate(-angle, expand=True)
                        w, h = img.size
            except Exception as osd_err:
                logger.debug("OSD orientation check skipped/failed: {}", str(osd_err))

        # 4. Gentle crop only on very thin scanner border noise (0.5%)
        crop_pixels = int(min(w, h) * 0.005)
        if crop_pixels > 2:
            img = img.crop((crop_pixels, crop_pixels, w - crop_pixels, h - crop_pixels))

        # 5. Enhancement & Binarization
        if mode == "aggressive":
            img = ImageEnhance.Contrast(img).enhance(2.0)
            img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=140, threshold=3))
            thresh = _otsu_threshold(img)
            img = img.point(lambda p: 255 if p > thresh else 0)
        else:
            img = ImageEnhance.Contrast(img).enhance(1.4)
            img = _local_adaptive_binarize(img, radius=25, offset=11)

        img.save(output_path)
        logger.info("OCR Image Preprocessing completed. Saved: {}", output_path)

    except Exception as e:
        logger.error("Image preprocessing failed: {}", str(e))
        shutil_copy(image_path, output_path)


def shutil_copy(src: str, dst: str) -> None:
    try:
        shutil.copy(src, dst)
    except Exception:
        pass
