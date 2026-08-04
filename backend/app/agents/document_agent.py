from loguru import logger

from app.db.session import SessionLocal
from app.repositories.document_repository import DocumentRepository
from app.services import pdf_extractor
from app.agents.ocr_agent import OCRAgent
from app.services.ocr.page_detector import OCRStrategy


def run_document_agent(
    upload_id: str, file_path: str, ocr_strategy: OCRStrategy = OCRStrategy.AUTO
) -> str:
    """Orchestrate PDF layout parsing, execute OCR processing on scanned layers, and persist results."""
    logger.info(
        "DocumentAgent launched for upload ID: {} with strategy {}", upload_id, ocr_strategy.value
    )

    db = SessionLocal()
    try:
        # 1. Extract layout hierarchy (Agnostic Canonical Document Model)
        extraction_result = pdf_extractor.extract_pdf_document(upload_id, file_path)

        # 2. Run OCR agent over pages that need it
        ocr_agent = OCRAgent()
        extraction_result = ocr_agent.process_document(
            extraction_result, file_path, strategy=ocr_strategy
        )

        # 3. Save result using normalized persistence repository
        repo = DocumentRepository(db)
        db_doc = repo.save_extraction_result(extraction_result)

        logger.info(
            "DocumentAgent finished processing for upload {}. Document DB ID: {}, Status: {}, OCR Status: {}",
            upload_id,
            db_doc.id,
            db_doc.status,
            db_doc.ocr_status,
        )
        return db_doc.id
    except Exception as e:
        logger.error("DocumentAgent execution failed: {}", str(e))
        raise e
    finally:
        db.close()
