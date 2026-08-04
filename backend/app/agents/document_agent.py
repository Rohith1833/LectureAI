from loguru import logger

from app.db.session import SessionLocal
from app.repositories.document_repository import DocumentRepository
from app.services import pdf_extractor


def run_document_agent(upload_id: str, file_path: str) -> str:
    """Orchestrate PDF extraction to Canonical Pydantic schemas, and commit to Repository."""
    logger.info("DocumentAgent launched for upload ID: {}", upload_id)

    db = SessionLocal()
    try:
        # 1. Extract layout hierarchy (Agnostic Canonical Document Model)
        extraction_result = pdf_extractor.extract_pdf_document(upload_id, file_path)

        # 2. Save result using normalized persistence repository
        repo = DocumentRepository(db)
        db_doc = repo.save_extraction_result(extraction_result)

        logger.info(
            "DocumentAgent finished processing for upload {}. Document DB ID: {}, Status: {}",
            upload_id,
            db_doc.id,
            db_doc.status,
        )
        return db_doc.id
    except Exception as e:
        logger.error("DocumentAgent execution failed: {}", str(e))
        raise e
    finally:
        db.close()
