import os
import shutil
from typing import List, Dict, Any
import pytesseract
from PIL import Image

from app.services.ocr.base_engine import BaseOCREngine


class TesseractEngine(BaseOCREngine):
    """Production Tesseract OCR engine wrapper that uses pytesseract."""

    def __init__(self):
        self.tesseract_cmd = "tesseract"
        # Auto-detect Tesseract binary path on Windows / Linux systems
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
            # Parse version string cleanly
            ver = pytesseract.get_tesseract_version()
            return str(ver).split()[0] if ver else "5.0.0"
        except Exception:
            return "5.0.0"

    def is_available(self) -> bool:
        """Verify if Tesseract executable is found and runnable on the system."""
        # 1. Check system path
        if shutil.which("tesseract"):
            return True
        # 2. Check explicitly configured pytesseract path
        cmd = getattr(pytesseract.pytesseract, "tesseract_cmd", None)
        if cmd and os.path.exists(cmd):
            return True
        return False

    def perform_ocr(self, image_path: str) -> List[Dict[str, Any]]:
        """Extract layout words with coordinates and confidence from Tesseract TSV output."""
        if not self.is_available():
            raise RuntimeError(
                "Tesseract OCR binary not found. Please install Tesseract-OCR on your system and add it to your PATH."
            )

        try:
            img = Image.open(image_path)
            # Retrieve structured dictionary containing coordinates and word confidences
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

            words = []
            n_boxes = len(data.get("level", []))
            for i in range(n_boxes):
                # level 5 indicates word elements in Tesseract hierarchy
                if data["level"][i] == 5:
                    text = str(data["text"][i]).strip()
                    conf = float(data["conf"][i])
                    # conf = -1 means Tesseract did not evaluate confidence for this block
                    if not text or conf < 0:
                        continue

                    x0 = float(data["left"][i])
                    y0 = float(data["top"][i])
                    w = float(data["width"][i])
                    h = float(data["height"][i])

                    words.append(
                        {
                            "text": text,
                            "bbox": (x0, y0, x0 + w, y0 + h),
                            "confidence": round(conf / 100.0, 3),  # normalize confidence to [0, 1]
                            "block_num": data["block_num"][i],
                            "line_num": data["line_num"][i],
                        }
                    )
            return words
        except Exception as e:
            raise RuntimeError(f"Tesseract extraction failed on page image: {str(e)}")
