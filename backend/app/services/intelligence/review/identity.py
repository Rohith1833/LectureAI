import re
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from app.schemas.document import BlockSchema
from app.schemas.academic import AcademicNode, AcademicNodeCategory
from app.services.intelligence.graph import DocumentGraph


class AnchorCollisionError(Exception):
    """Raised when a collision is detected between generated contextual anchor keys."""
    def __init__(self, message: str, conflicts: Dict[str, List[Dict[str, Any]]]):
        super().__init__(message)
        self.conflicts = conflicts


def normalize_title(title: Optional[str]) -> str:
    """Standardizes section/chapter title text for stable path identifiers."""
    if not title:
        return "root"
    # Lowercase, replace non-alphanumeric (except spaces/dashes) with empty, and spaces with dashes
    normalized = title.lower().strip()
    normalized = re.sub(r"[^a-z0-9\s\-]", "", normalized)
    normalized = re.sub(r"[\s\-]+", "-", normalized)
    return normalized.strip("-")


def get_normalized_section_path(doc_graph: DocumentGraph, block_id: str) -> str:
    """Computes a slashed path of enclosing section/chapter titles up to the document root."""
    ancestors = doc_graph.get_ancestors(block_id)
    # Filter headings only
    headings = [a for a in ancestors if a.block_type == "HEADING"]
    # Sort from root to leaf (get_ancestors returns bottom-up, so we reverse it)
    headings.reverse()
    
    if not headings:
        # Check if the block itself is a heading, if so, its path is its parent section
        # but since it's the heading itself, parent section is empty
        return "root"
        
    path_components = [normalize_title(h.text) for h in headings]
    return "/".join(path_components)


def compute_text_hash(text: Optional[str]) -> str:
    """Generates a stable SHA-256 hash of text normalized by removing casing and formatting."""
    if not text:
        return ""
    # Strip all spacing and punctuation
    normalized = re.sub(r"\s+", "", text.lower())
    normalized = re.sub(r"[^\w]", "", normalized)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def generate_anchor_key(
    upload_id: str,
    section_path: str,
    academic_type: str,
    text_hash: str,
    ordinal_index: int
) -> str:
    """Generates a collision-resistant SHA-256 hash representation of an academic node."""
    raw_payload = f"{upload_id}:{section_path}:{academic_type}:{text_hash}:{ordinal_index}"
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()


def resolve_anchor_keys_for_nodes(
    upload_id: str,
    nodes_data: List[Tuple[str, str, AcademicNodeCategory]],  # List of (block_id, block_text, category)
    doc_graph: DocumentGraph
) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """
    Computes anchor keys for generated nodes and returns:
    1. A dictionary mapping block_id to computed anchor_key.
    2. A list of diagnostic collision details if conflicts occurred.
    """
    anchor_map: Dict[str, str] = {}
    path_type_counts: Dict[Tuple[str, str], int] = {}
    temp_records: List[Dict[str, Any]] = []

    # Count sibling ordinals by processing nodes in reading order
    # To assure order stability, we sort nodes_data by block_id or their positions if available.
    # Since nodes_data is typically sorted in reading order, we preserve it.
    for block_id, text, category in nodes_data:
        path = get_normalized_section_path(doc_graph, block_id)
        type_str = category.value
        
        # Sibling ordinal tracker: count of identical types under identical path
        key = (path, type_str)
        ordinal = path_type_counts.get(key, 0)
        path_type_counts[key] = ordinal + 1

        text_hash = compute_text_hash(text)
        anchor = generate_anchor_key(upload_id, path, type_str, text_hash, ordinal)
        
        temp_records.append({
            "block_id": block_id,
            "anchor_key": anchor,
            "category": category,
            "path": path,
            "text": text,
            "ordinal": ordinal
        })

    # Collision detection
    anchor_groups: Dict[str, List[Dict[str, Any]]] = {}
    for rec in temp_records:
        anchor_groups.setdefault(rec["anchor_key"], []).append(rec)

    collisions: Dict[str, List[Dict[str, Any]]] = {}
    for anchor, items in anchor_groups.items():
        if len(items) > 1:
            collisions[anchor] = items
        # Set target anchor key mapping
        for item in items:
            anchor_map[item["block_id"]] = anchor

    diagnostics = []
    if collisions:
        for anchor, items in collisions.items():
            diagnostics.append({
                "anchor_key": anchor,
                "conflicts": [
                    {
                        "block_id": it["block_id"],
                        "category": it["category"].value,
                        "path": it["path"],
                        "ordinal": it["ordinal"]
                    } for it in items
                ]
            })

    return anchor_map, diagnostics
