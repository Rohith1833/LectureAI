import os
import shutil
from typing import List, Dict, Any
import pytesseract
from PIL import Image

from app.services.ocr.base_engine import BaseOCREngine


class TesseractEngine(BaseOCREngine):
    """Production Tesseract OCR engine wrapper using pytesseract with multi-PSM fallback."""

    def __init__(self):
        self.tesseract_cmd = "tesseract"
        if not shutil.which(self.tesseract_cmd):
            win_paths = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            ]
            for path in win_paths:
                if os.path.exists(path):
                    self.tesseract_cmd = path
                    pytesseract.pytesseract.tesseract_cmd = path
                    break

    def get_name(self) -> str:
        return "tesseract"

    def get_version(self) -> str:
        if not self.is_available():
            return "unknown"
        try:
            ver = pytesseract.get_tesseract_version()
            return str(ver).split()[0] if ver else "5.0.0"
        except Exception:
            return "5.0.0"

    def is_available(self) -> bool:
        """Verify if Tesseract executable is found and runnable on the system."""
        if shutil.which("tesseract"):
            return True
        cmd = getattr(pytesseract.pytesseract, "tesseract_cmd", None)
        if cmd and os.path.exists(cmd):
            return True
        return False

    def _run_psm(self, img: Image.Image, psm: int) -> List[Dict[str, Any]]:
        config = f"--oem 3 --psm {psm}"
        data = pytesseract.image_to_data(img, config=config, output_type=pytesseract.Output.DICT)

        words: List[Dict[str, Any]] = []
        n_boxes = len(data.get("level", []))
        for i in range(n_boxes):
            if data["level"][i] == 5:
                text = str(data["text"][i]).strip()
                conf = float(data["conf"][i])
                if not text or conf < 0:
                    continue
                # Filter out single-char non-alphanumeric noise at very low confidence
                if conf < 25 and len(text) == 1 and not text.isalnum():
                    continue

                x0 = float(data["left"][i])
                y0 = float(data["top"][i])
                w = float(data["width"][i])
                h = float(data["height"][i])

                words.append(
                    {
                        "text": text,
                        "bbox": (x0, y0, x0 + w, y0 + h),
                        "confidence": round(conf / 100.0, 3),
                        "block_num": data["block_num"][i],
                        "par_num": data.get("par_num", [1] * n_boxes)[i],
                        "line_num": data["line_num"][i],
                    }
                )
        return words

    def perform_ocr(self, image_path: str) -> List[Dict[str, Any]]:
        """Extract layout words with coordinates, paragraph numbers, and confidence from Tesseract."""
        if not self.is_available():
            raise RuntimeError(
                "Tesseract OCR binary not found. Please install Tesseract-OCR on your system and add it to your PATH."
            )

        try:
            with Image.open(image_path) as img:
                words = self._run_psm(img, psm=3)
                # If automatic segmentation yields very few words, try uniform block (6) and sparse text (11)
                if len(words) < 5:
                    for fallback_psm in (6, 11):
                        alt_words = self._run_psm(img, psm=fallback_psm)
                        if len(alt_words) > len(words):
                            words = alt_words
                        if len(words) >= 15:
                            break
                return words
        except Exception as e:
            raise RuntimeError(f"Tesseract extraction failed on page image: {str(e)}")
