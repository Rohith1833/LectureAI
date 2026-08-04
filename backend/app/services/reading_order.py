from typing import List, Dict, Any, Optional
import uuid
from app.schemas.document import BlockSchema, BlockType, BoundingBox

# Standard header/footer threshold margin in points (e.g. 50pt from edges)
HEADER_MARGIN = 60.0


def sort_and_link_blocks(
    raw_blocks: List[Dict[str, Any]], page_number: int, page_width: float, page_height: float
) -> List[BlockSchema]:
    """Sort blocks intelligently according to single/two-column layouts and establish reading links."""
    if not raw_blocks:
        return []

    # 1. Classify blocks into layout structures (Headers, Footers, and Body)
    headers = []
    footers = []
    body_blocks = []

    for rb in raw_blocks:
        # rb is a dictionary containing block info (bbox, type, spans, etc.)
        bbox = rb.get("bbox", (0, 0, 0, 0))
        y0, y1 = bbox[1], bbox[3]

        if y1 <= HEADER_MARGIN:
            headers.append(rb)
        elif y0 >= page_height - HEADER_MARGIN:
            footers.append(rb)
        else:
            body_blocks.append(rb)

    # Sort headers and footers vertically
    headers.sort(key=lambda b: b["bbox"][1])
    footers.sort(key=lambda b: b["bbox"][1])

    # 2. Sort body blocks based on column structures
    # Let's detect if we have a prominent two-column layout in the body blocks
    # If we have blocks on the left half and right half that overlap in Y-coordinates,
    # it indicates a multi-column structure.
    sorted_body = []

    # Determine if two columns are present by looking at overlap metrics
    left_side = []
    right_side = []
    spanning = []

    mid_x = page_width / 2.0

    for b in body_blocks:
        bbox = b["bbox"]
        x0, x1 = bbox[0], bbox[2]
        centroid_x = (x0 + x1) / 2.0

        # Spanning is defined as blocks starting in the left third and ending in the right third
        is_spanning = x0 < (page_width / 3.0) and x1 > (2.0 * page_width / 3.0)

        if is_spanning:
            spanning.append(b)
        elif centroid_x < mid_x:
            left_side.append(b)
        else:
            right_side.append(b)

    # If both columns contain blocks, sort them into Left -> Right sequences between spanning blocks
    if left_side and right_side:
        # Group spanning blocks and column blocks by Y-coordinate segments
        # Let's sort all elements vertically. For elements in left/right,
        # we can sort them by y0.
        # An elegant heuristic:
        # We sort spanning elements by y0.
        # We then group left/right elements that fall between spanning elements,
        # sorting left column and then right column vertically for each segment.
        spanning.sort(key=lambda b: b["bbox"][1])

        left_side.sort(key=lambda b: b["bbox"][1])
        right_side.sort(key=lambda b: b["bbox"][1])

        current_y = 0.0
        left_idx = 0
        right_idx = 0

        for span in spanning:
            span_y = span["bbox"][1]

            # Add left and right column elements that lie above this spanning element
            temp_left = []
            while left_idx < len(left_side) and left_side[left_idx]["bbox"][1] < span_y:
                temp_left.append(left_side[left_idx])
                left_idx += 1

            temp_right = []
            while right_idx < len(right_side) and right_side[right_idx]["bbox"][1] < span_y:
                temp_right.append(right_side[right_idx])
                right_idx += 1

            sorted_body.extend(temp_left)
            sorted_body.extend(temp_right)
            sorted_body.append(span)

        # Append any remaining left and right column blocks
        sorted_body.extend(left_side[left_idx:])
        sorted_body.extend(right_side[right_idx:])
    else:
        # Default single-column vertical sorting
        body_blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
        sorted_body = body_blocks

    # Combine all sorted components
    all_sorted = headers + sorted_body + footers

    # 3. Construct Pydantic BlockSchema nodes and generate relationship chains
    schemas: List[BlockSchema] = []
    active_headings: Dict[int, str] = {}  # Mappings of level -> block_id

    for idx, rb in enumerate(all_sorted):
        bbox_coords = rb.get("bbox", (0, 0, 0, 0))
        bbox = BoundingBox(
            x0=bbox_coords[0], y0=bbox_coords[1], x1=bbox_coords[2], y1=bbox_coords[3]
        )

        block_id = rb.get("block_id", str(uuid.uuid4()))
        b_type = rb.get("block_type", BlockType.UNKNOWN)
        heading_lvl = rb.get("heading_level", None)

        # Style resolution
        font_size = rb.get("font_size", None)
        font_family = rb.get("font_family", None)
        bold = rb.get("bold", False)
        italic = rb.get("italic", False)

        # Determine Parent Block ID (Hierarchical Headings)
        parent_id = None
        if b_type == BlockType.HEADING and heading_lvl is not None:
            # Register this heading
            active_headings[heading_lvl] = block_id
            # Remove any deeper headings
            for lvl in list(active_headings.keys()):
                if lvl > heading_lvl:
                    active_headings.pop(lvl)
            # Parent is the next higher level heading active
            higher_levels = [lvl for lvl in active_headings.keys() if lvl < heading_lvl]
            if higher_levels:
                parent_id = active_headings[max(higher_levels)]
        else:
            # For non-headings, parent is the deepest active heading level
            if active_headings:
                parent_id = active_headings[max(active_headings.keys())]

        block = BlockSchema(
            block_id=block_id,
            page_number=page_number,
            reading_order=idx,
            block_type=b_type,
            bounding_box=bbox,
            text=rb.get("text", "").strip(),
            font_size=font_size,
            font_family=font_family,
            bold=bold,
            italic=italic,
            confidence=rb.get("confidence", 1.0),
            parent_block_id=parent_id,
            previous_block_id=None,  # will link below
            next_block_id=None,  # will link below
            heading_level=heading_lvl,
            extra_metadata=rb.get("extra_metadata"),
        )
        schemas.append(block)

    # 4. Link previous and next block IDs
    for idx in range(len(schemas)):
        if idx > 0:
            schemas[idx].previous_block_id = schemas[idx - 1].block_id
        if idx < len(schemas) - 1:
            schemas[idx].next_block_id = schemas[idx + 1].block_id

    return schemas
