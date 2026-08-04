# Walkthrough — Production OCR & Document Intelligence Engine

We have successfully implemented the production OCR subsystem and integrated it seamlessly into the Document Agent pipeline. Downstream modules now consume the exact same canonical blocks whether they originated from native text or OCR recognition layers.

---

## 1. Pluggable OCR Architecture & Engine Interface

- **Engine Abstraction**: Created `BaseOCREngine` abstract base class defining standard interface contracts for dynamic library and CLI integrations.
- **Tesseract OCR Wrapper**: Built `TesseractEngine` leveraging `pytesseract` to parse image text blocks. Added system path checks and auto-detection capabilities for Windows/Linux environments.
- **Modular Image Preprocessing**: Developed an image enhancement pipeline (`preprocessing.py`) to convert pages to upright 300 DPI images, execute contrast correction, apply median noise filters, run orientation alignment (Tesseract OSD), crop dark border margins, and perform adaptive binarization.
- **Intelligent Page Detection**: Page scanner `page_detector.py` checks native text volume to screen scanned pages. Supports:
  - `AUTO`: Runs OCR only when extractable character counts are low (< 50 characters).
  - `FORCE`: Runs OCR for all pages.
  - `SKIP`: Skips OCR entirely.
- **OCR Merging Engine**: Bounding-box matching checks overlap ratios between OCR and native text blocks. Duplicate blocks are resolved by keeping the higher confidence block and assigning `provenance = "MERGED"`.
- **OCR Page-Level Caching**: Unique page fingerprints are calculated from the PDF content stream. OCR block results are cached inside `storage/cache/ocr/<page_hash>.json`. Cache hits skip preprocessing and OCR entirely.
- **Resource safety & Page Retries**: Re-runs OCR up to 3 times on page failures and continues to subsequent pages without crashing the background worker. Wrapped PDF handles in strict `try...finally` scopes to release file locks on Windows systems.

---

## 2. Database Schema Self-Migrations

At startup, the application runs dynamic database self-migrations to alter existing SQL tables. This guarantees backward compatibility with existing dev database configurations:
- **`documents` table**: Added `ocr_status`, `ocr_engine`, `ocr_version`, `ocr_confidence`, `ocr_language`, and `ocr_processing_time`.
- **`document_blocks` table**: Added `provenance` (`NATIVE`, `OCR`, or `MERGED`).

---

## 3. Developer Preview Frontend Enhancements

- **OCR Audit Banner**: Renders OCR status, engine name, version, page-level confidence, language, and processing duration inside the document details panel.
- **Provenance Badges**: Added visual colored labels to layout blocks identifying their origin (`NATIVE`, `OCR`, or `MERGED`).
- **Layer Toggle Filter**: Users can filter layout blocks by "All Layers", "Native Layer", or "OCR Layer".

---

## 4. Verification & Testing

### Automated Test Suite
Created `backend/tests/test_ocr.py` covering:
- AUTO, FORCE, and SKIP strategy evaluation.
- Overlapping duplicate resolution and provenance tagging.
- Coordinate scaling from image pixel bounds back to PDF point bounds.
- Unique page hash fingerprint caching.
- Custom injected `MockOCREngine` (preventing Tesseract dependencies during testing).

Result: **OK (4 tests passed)**
```text
Ran 4 tests in 0.642s
OK
```

Total Backend Suite: **OK (9 tests passed)**
```text
Ran 9 tests in 0.657s
OK
```

### E2E Pipeline Run Logs
- **Job Status Transition**: `queued` -> `Preparing (5%)` -> `Reading Document (20%)` -> `OCR (50%)` -> `Completed (100%)`.
- **Auditing metrics**: Document status recorded as `processed` with `ocr_status` logged as `skipped` (due to rich native text layer detected on Page 1).
