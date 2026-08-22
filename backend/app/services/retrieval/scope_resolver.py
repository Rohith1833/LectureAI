from dataclasses import dataclass
from typing import Optional

from app.models.document import Document
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.retrieval import RetrievalScope


@dataclass
class ResolvedScope:
    document_id: str
    version_id: str


class ScopeResolver:
    """
    Validates and resolves a RetrievalScope to a finalized KnowledgeVersion
    belonging to the requested document.
    """

    def __init__(self, repo: KnowledgeRepository):
        self.repo = repo

    def resolve(self, scope: RetrievalScope) -> ResolvedScope:
        """
        Resolves the scope to a specific finalized KnowledgeVersion UUID.
        Raises ValueError if scope is invalid, document is not found, or version cannot be resolved.
        """
        # Case F: Document Not Found
        doc = self.repo.db.query(Document).filter(Document.id == scope.document_id).first()
        if not doc:
            raise ValueError(f"Document with ID '{scope.document_id}' not found.")

        if scope.version_id is not None:
            # Case A: Explicit Version
            from app.models.knowledge import KnowledgeVersion
            version = self.repo.db.query(KnowledgeVersion).filter(KnowledgeVersion.id == scope.version_id).first()
            if not version:
                raise ValueError(f"KnowledgeVersion '{scope.version_id}' not found.")

            # Case D: BUILDING Version Rejected
            if version.status != "FINALIZED":
                raise ValueError(f"KnowledgeVersion '{scope.version_id}' is not finalized.")


            # Case E: Version belonging to another document rejected
            if version.upload_id != doc.upload_id:
                raise ValueError(f"KnowledgeVersion '{scope.version_id}' does not belong to document '{scope.document_id}'.")

            resolved_version_id = version.id
        else:
            # Case B: No Explicit Version
            version = self.repo.get_latest_finalized_version(scope.document_id)
            if not version:
                # Case C: No Finalized Version
                raise ValueError(f"No finalized KnowledgeVersion found for document '{scope.document_id}'.")

            resolved_version_id = version.id

        return ResolvedScope(
            document_id=scope.document_id,
            version_id=resolved_version_id
        )
