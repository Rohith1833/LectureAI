# LECTUREAI PHASED REPAIR PLAN & ARCHITECTURAL BASELINE

**Document Version:** 1.2.0 (Phase 1 Complete)  
**Last Updated:** 2026-09-28  
**Scope:** Phase 1 Complete — Database Schema Repair & Application Boundary CORS Visibility  
**Authoritative Source of Truth:** Current local codebase, runtime logs, empirical database execution, and verified test suites.

---

## 1. PRODUCT ACCEPTANCE CRITERIA

The target product goal is:
> A user uploads a textbook PDF (digital, scanned, or mixed), reviews its detected academic structure, selects specific units (e.g., Unit 2 and Unit 4), and receives a downloadable educational PowerPoint presentation (`.pptx`) strictly grounded in the selected units.

### Specific Acceptance Criteria
1. **Upload & Layout Ingestion:**
   - Accepts PDF uploads up to 100MB.
   - Automatically detects scanned/image-only pages (< 50 digital characters) and applies 300 DPI Tesseract OCR with layout reconstruction and deduplicating merge.
   - Text extraction preserves reading order, page numbers, and bounding box coordinates.
2. **Review & Academic Structure Verification:**
   - User reviews extracted units, chapters, and topics on `/academic/review/:uploadId`.
   - Allows renaming, reparenting, and category reclassification with monotonic Optimistic Concurrency Control (OCC) revision tracking.
   - Approving the structure persists an **immutable** `AcademicGraphSnapshot`.
3. **Knowledge Graph Compilation:**
   - Compiles the snapshot into relational entities (`KnowledgeVersion`, `KnowledgeEntity`, `KnowledgeRelationship`, `KnowledgeEvidence`).
   - Retains all curricular structures (Units, Chapters, Topics) with deterministic source-order preservation.
   - Status transitions from `BUILDING` to `FINALIZED`.
4. **Exact Unit Selection & Scope Isolation:**
   - User can select specific, nonconsecutive units (e.g. Unit 2 and Unit 4).
   - If a textbook has no explicit Unit divisions, selection operates in a clearly labelled "Chapters" mode without implying syllabus-unit equivalence.
   - The selection contract strictly filters retrieval, chunking, planning, and validation.
   - Context, passages, and evidence from unselected units are completely excluded.
5. **Grounded Generation & Validation:**
   - `ArtifactPlanner` builds slide fragments citing only explicit `source_node_ids` and `evidence_ids` present in the retrieved chunk context.
   - `ArtifactValidator` enforces text density (<= 800 chars/slide, <= 7 bullets), configuration options (examples/questions), and strict academic coverage of the selected units.
6. **PPTX Slide Rendering & Download:**
   - `PPTXRenderer` produces a valid 16:9 `.pptx` file with slide titles, structured bullet frames, and speaker notes recording provenance evidence IDs.
   - The generated file opens without error in PowerPoint, Keynote, and Google Slides.
   - The browser can trigger and complete the download from `/documents/:id/artifact`.

---

## 2. VERIFIED ISSUE REGISTER

Every issue has a stable identifier, verified status, exact location, root cause, and proposed remediation.

| Issue ID | Status | File / Component | Empirical Evidence & Verified Root Cause | Proposed Remediation | Assigned Phase |
|---|:---:|---|---|---|:---:|
| **ISS-01** | **RESOLVED** | `backend/lectureai.db`<br>`artifact_jobs` table | `INSERT INTO artifact_jobs` raises SQLite `OperationalError: foreign key mismatch - "artifact_jobs" referencing "documents"`. The SQLite table was created with `FOREIGN KEY(upload_id) REFERENCES documents(upload_id)`, but `documents.upload_id` has no `UNIQUE` constraint. | Table rebuild migration: created `_artifact_jobs_new` with valid DDL (retaining `knowledge_version_id` FK), copied existing data with explicit column mappings, verified integrity, dropped old table, renamed replacement, recreated indexes, and verified foreign keys. Applied to `backend/lectureai.db`. | **Phase 1 (PASSED)** |
| **ISS-02** | **RESOLVED** | `backend/app/main.py`<br>`CORSAppProxy` & boundary middleware | 1) `allow_origins` only contained `["http://localhost:5173"]`, rejecting `http://127.0.0.1:5173`.<br>2) Starlette's `ServerErrorMiddleware` handles 500 errors outside user-added middlewares, returning 500 with **no CORS headers**, causing the browser to mask backend crashes as CORS policy violations. | 1) Allowed development origins `http://localhost:5173` and `http://127.0.0.1:5173`.<br>2) Implemented `CORSAppProxy` ASGI wrapper around the complete application so `ServerErrorMiddleware` and raw ASGI error responses receive `Access-Control-Allow-Origin` headers. | **Phase 1 (PASSED)** |
| **ISS-03** | **RESOLVED** | `backend/app/services/intelligence/knowledge_builder.py:18-22` | `VALID_KNOWLEDGE_CATEGORIES` explicitly excluded `"UNIT"`. Real compiled versions in the DB had zero `UNIT` entities. | Added `"UNIT"` to `VALID_KNOWLEDGE_CATEGORIES` in `knowledge_builder.py`. Verified in test suite (Tests A-K). | **Phase 2 (PASSED)** |
| **ISS-04** | **RESOLVED** | `backend/app/services/artifact/artifact_planner.py:84-88`<br>`backend/app/services/artifact/selection_resolver.py` | Halts with `ValueError("No academic units found")` if `UNIT` is absent. Textbooks organized by Chapter-only crashed during planning. | Implemented selectable container policy in `knowledge_ordering.py:get_selectable_containers` and consumed in `selection_resolver.py` / `artifact_planner.py`. Supports Chapters mode and Review Required mode. | **Phase 2 (Helper) / Phase 3 (PASSED)** |
| **ISS-05** | **RESOLVED** | `backend/app/services/artifact/artifact_service.py:125` vs `artifact_planner.py:105` | Unit ordering discrepancy: `artifact_service.py` sorted expected units by UUID string (`key=lambda x: x.id`), while `artifact_planner.py` used database order. Slicing `num_units` selected different units, causing validator `COVERAGE` failure. | Removed UUID string sorting and database order slicing. Both planner and validator consume `EffectiveSelection` sorted strictly by canonical source order. | **Phase 2 (Helper) / Phase 3 (PASSED)** |
| **ISS-06** | **RESOLVED (Backend Contract)** | `backend/app/schemas/artifact.py:39`<br>`backend/app/services/artifact/selection_resolver.py` | Contract gap: Accepted only `num_units: int` (sliced top N units). User could not pick specific nonconsecutive units (e.g. Unit 2 and Unit 4). | Added `selected_unit_ids: List[str]` to request config, validated selection, persisted with job, enforced scope in planner and validator. Frontend checkbox UI deferred to Phase 5. | **Phase 3 (Backend PASSED) / Phase 5 (Frontend)** |
| **ISS-07** | **RESOLVED** | `backend/app/services/artifact/artifact_planner.py:157` vs `backend/app/services/retrieval/scope_resolver.py:30` | Scope identifier mismatch: `ArtifactPlanner` passed `RetrievalScope(document_id=job.upload_id)`, but `ScopeResolver` queried `Document.id == scope.document_id`. Because `Document.id != upload_id`, resolver raised `ValueError("Document not found")`. | Implemented `resolve_document_id_for_version` in `selection_resolver.py`. `ArtifactPlanner` now passes the verified `Document.id` to `RetrievalScope`. Verified with distinct `doc.id != upload_id` tests. | **Phase 3 (PASSED)** |
| **ISS-08** | **CONFIRMED IN CODE** | `backend/app/services/generation/mock_provider.py:54-70` | Incompatible mock schema: `MockLLMProvider` returns `{"answer": ..., "claims": ...}` (Phase 8 Q&A schema). `ArtifactPlanner` requires `{"slides": [...]}`. Fallback to mock provider crashes planner with `GroundingValidationError`. | Update `MockLLMProvider` or provide a schema-aware mock supporting `SLIDE_FRAGMENT_SCHEMA` when requested. | **Phase 4** |
| **ISS-09** | **CONFIRMED IN CODE** | `backend/app/services/artifact/artifact_planner.py:137-142` | Oversized topic chunking: Topics with many concepts are added to `current_chunk` via `extend()` without sub-chunking, causing chunks to exceed `MAX_ENTITIES_PER_CHUNK = 10`. | Implement inner chunking for topics that exceed `MAX_ENTITIES_PER_CHUNK`. | **Phase 4** |
| **ISS-10** | **CONFIRMED IN CODE** | `backend/app/services/artifact/artifact_planner.py:181-190` | Evidence IDs hidden from model: `supplied_evidence_ids` are collected in Python, but `ev.id` is never formatted into `context_blocks`. The prompt forbids inventing IDs and validator requires them, but the model is never shown the evidence IDs. | Format `(evidence_id: {ev.id})` into the supporting evidence text presented in the prompt. | **Phase 4** |
| **ISS-11** | **CONFIRMED IN CODE** | `backend/app/services/artifact/artifact_planner.py:118` vs `backend/app/models/knowledge.py:108` | ORM string vs. Enum: `rel.relationship_type` is an SQLAlchemy `String`, but code accesses `rel.relationship_type.value == "CONTAINS"`. On real ORM objects, raises `AttributeError: 'str' object has no attribute 'value'`. | Check `rel.relationship_type == "CONTAINS"` (supporting both string and enum). | **Phase 4** |
| **ISS-12** | **CONFIRMED IN CODE** | `frontend/src/pages/ProcessingPage.tsx:62` | Navigation dead-end: Clicking "Continue" redirects to legacy mock `/units` instead of real document review. | Redirect `ProcessingPage.tsx` to `/academic/review/${job.upload_id}` (or `/documents/${job.document_id}`). | **Phase 5** |
| **ISS-13** | **CONFIRMED IN CODE** | `frontend/src/types/artifact.ts:33`<br>`backend/app/schemas/artifact.py:50` | Timestamp mismatch: Backend returns ISO datetime string, frontend type declared `number`. Multiplying by 1000 produced `NaN` ("Invalid Date"). | Update frontend type to `string` and parse with `new Date(job.created_at)`. | **Phase 5** |

---

## 3. ARCHITECTURAL DECISIONS

### Decision A: Selectable Unit Identification
* **Identity:** A selectable unit is identified by its `KnowledgeEntity.id` (UUID) within a specific finalized `KnowledgeVersion`.
* **Selection Scope:**
  1. If entities with `entity_type == "UNIT"` exist, all such entities are selectable units.
  2. If no `UNIT` entities exist, all top-level `CHAPTER` entities serve as the selectable units under "Chapters Mode".
* **Metadata Exchanged:** Each selectable unit exposes `id`, `title`, `entity_type`, `source_page_start`, `source_page_end`, and `topic_count`.

### Decision B: Deterministic Source Ordering
* **Investigation of Persisted Fields:**
  - `KnowledgeEvidence` contains `page_number: Optional[int]`, `x0, y0, x1, y1: Optional[float]`. It does **not** have a `reading_order` column.
  - `DocumentBlock` contains `page_number: int` and `reading_order: int`.
  - `AcademicGraphSnapshot.nodes` is an ordered list where each node contains `target_block_id`.
* **Ordering Definition:**
  - Units must be ordered by the earliest actual source position tuple:
    $$\text{sort\_key} = (\min(\text{page\_number}), \min(\text{y0 or reading\_order}))$$
  - The minimum must be evaluated over the actual source tuples rather than taking minimum page and minimum order independently from different blocks.
  - **Proposed Work (Phase 2):** During `KnowledgeBuilder.compile_snapshot()`, persist the resolved earliest source position into `KnowledgeEntity.metadata_json["source_position"] = {"page": p, "reading_order": r, "snapshot_index": idx}`.
  - **Tie-Breaking:** If two entities share the same page/position or have missing evidence, break ties deterministically by `snapshot_index`, followed by lexicographical `stable_id`.

### Decision C: Handling CHAPTER / SECTION Structures & Selectable Content Policy
* **Mode A: Explicit Units (Default when `count(UNIT) > 0`):**
  - Selectable items are `KnowledgeEntity` rows where `entity_type == "UNIT"`.
  - UI displays "Select Units to Generate".
* **Mode B: Chapters Mode (When `count(UNIT) == 0` and `count(CHAPTER) > 0`):**
  - Selectable items are `KnowledgeEntity` rows where `entity_type == "CHAPTER"`.
  - UI displays "Select Chapters to Generate" with an explicit advisory: *"This textbook has no explicit Unit divisions. Generating by individual Chapters."*
  - Preserves original chapter names and numbers. Does NOT label chapters as "Units" and does NOT imply syllabus-unit equivalence.
* **Documents with Neither Units Nor Chapters:**
  - If a document has neither `UNIT` nor `CHAPTER` entities (e.g. unstructured sections only), generation halts with an explanatory message:
    *"No top-level curricular containers (Units or Chapters) were detected. Please review the document structure in Academic Review and designate containers before generating presentation slides."*
  - Arbitrary sections are **never** silently converted into units.
* **Partial Coverage & Overlapping Containers:**
  - If units cover only part of a document, content outside selected units is excluded from generation.
  - If a concept has multiple parents across different units, it is planned once under its earliest-occurring parent in source order, with cross-references recorded in speaker notes.

### Decision D: Corrected Knowledge Version Creation & Immutability
* **Immutability Protection:** Finalized knowledge versions and approved snapshots are protected by SQLite triggers; they cannot be updated or deleted in place.
* **Next Approval Version Allocation:**
  - `AcademicReviewService.approve_resolved_graph()` calls `self.review_repo.get_next_approval_version(upload_id)`.
  - This dynamically queries `MAX(approval_version) + 1` (not hardcoded v2).
* **Compiler Idempotency:**
  - `KnowledgeBuilder.compile_snapshot(snapshot_id)` checks `snapshot_id == snapshot_id`. Because each new approval creates a new snapshot record with a distinct `snapshot_id`, a new `KnowledgeVersion` row is created in `FINALIZED` status.
  - Historical snapshots and earlier finalized versions remain completely unchanged.
  - `KnowledgeRepository.list_finalized_versions(document_id)` orders by `approval_version.desc()`, so the latest approved version is automatically selected.
* **UI Availability Note:**
  - The UI supports `CHANGE_CATEGORY` (promoting chapters to units), `RENAME_TITLE`, `REPARENT_NODE`, `ACCEPT_NODE`, and `DELETE_NODE`.
  - The UI does **not** currently expose a modal for `CREATE_NODE`. Creating new synthetic units from scratch requires extending the review UI (addressed in Phase 5).

### Decision E: Navigation After Extraction
* **Route Target:** `/processing/:jobId` must navigate to:
  $$\mathbf{/academic/review/:uploadId}$$
* **Rationale:** Aligns with the core product goal (*"reviews its detected academic structure"*). The user verifies detected units and boundaries, approves the structure, and is then seamlessly directed to `/documents/:documentId/artifact` to select units and generate presentations.

### Decision F: Provider Concurrency & Rate Limiting
* **Policy:** Keep LLM chunk generation sequential initially.
* **Resilience:**
  - Enforce a 60-second bounded timeout per chunk.
  - Implement exponential backoff for HTTP 429 rate limit responses from the Groq API (e.g. 3 retries with jitter).
  - Defer concurrent requests (`asyncio.gather` / `asyncio.Semaphore`) until real production measurements demonstrate a performance need.

---

## 4. PHASED REPAIR PROGRAMME & DEPENDENCIES

```
Phase 0: Baseline & Plan (COMPLETED)
   │
   ▼
Phase 1: Database & Error Visibility
   │
   ▼
Phase 2: Academic Structure & Knowledge Compilation
   │
   ▼
Phase 3: Exact Unit Selection & Retrieval
   │
   ▼
Phase 4: Generation, Validation & Job Lifecycle
   │
   ▼
Phase 5: Connect Real User Workflow
   │
   ▼
Phase 6: Real End-to-End Acceptance
   │
   ▼
Phase 7: Presentation Quality & Release Readiness
```

---

## 5. DETAILED PHASE 1 SPECIFICATION: DATABASE & ERROR VISIBILITY

### Objective
`POST /api/v1/artifacts/generate` succeeds against the development SQLite database, and allowed-origin browser clients receive proper CORS headers on successful responses, handled 4xx errors, and unhandled 500 server crashes.

### Verified Database Identity
* `settings.DATABASE_URL`: `sqlite:///./lectureai.db`
* Resolved active database path obtained from live engine connection (`PRAGMA database_list`):
  `C:\Users\rohit\Downloads\ALL projects\LectureAI\backend\lectureai.db`
* File size: ~245 MB.

### Work Items for Phase 1
1. **Repeatable Data-Preserving Table Migration (IMPLEMENTED & APPLIED):**
   - Migration script: `backend/app/db/migrate_artifact_jobs.py` (CLI: `python -m app.db.migrate_artifact_jobs --db lectureai.db [--dry-run]`).
   - Backup created before write operations using consistent SQLite online backup API: `backend/lectureai.db.bak.20260928_193335`.
   - Inspection mode: inspects foreign key list, indexes, and existing columns.
   - Migration strategy:
     1. Creates replacement table `_artifact_jobs_new` with valid schema (retaining `FOREIGN KEY (knowledge_version_id) REFERENCES knowledge_versions (id)` and removing invalid `upload_id` FK).
     2. Copies all existing rows using explicit column mapping (mapping legacy missing optional columns to NULL).
     3. Drops legacy `artifact_jobs` table.
     4. Renames `_artifact_jobs_new` to `artifact_jobs`.
     5. Recreates indexes: `ix_artifact_jobs_upload_id` and `ix_artifact_jobs_knowledge_version_id`.
     6. Verifies `PRAGMA foreign_key_check` and `PRAGMA integrity_check`.
   - **Development Database Migration Applied:** YES. Applied to `backend/lectureai.db` on 2026-09-28. Pre/post counts verified (0 rows preserved, schema fully compliant).
   - **Repeat Execution Verification:** Verified by invoking a second actual migration (`run_migration_on_file(disposable_db, dry_run=False)`) against a disposable copy of the migrated database. Safely returned `{"status": "NOOP", "reason": "Schema already compliant (no invalid foreign keys)"}` without mutating schemas or data.
   - **Disaster Recovery Procedure (Offline Recovery Documentation Only - Not Executed):**
     1. Stop all application writers and processes and ensure database connections are closed.
     2. Preserve the active database and its specific associated journal/WAL files as an isolated recovery set using explicit paths (do NOT use wildcards like `lectureai.db*` which would accidentally move the `.bak` backup file):
        ```powershell
        New-Item -ItemType Directory -Path "backend/quarantine_recovery_set" -Force
        foreach ($file in @("lectureai.db", "lectureai.db-wal", "lectureai.db-shm", "lectureai.db-journal")) {
            if (Test-Path "backend/$file") { Move-Item "backend/$file" "backend/quarantine_recovery_set/" }
        }
        ```
     3. Keep the verified backup file (`backend/lectureai.db.bak.20260928_193335`) separately accessible and copy it into the clean destination path:
        ```powershell
        Copy-Item "backend/lectureai.db.bak.20260928_193335" "backend/lectureai.db"
        ```
     4. Note on Schema State: Restoring this pre-migration backup restores the database to its exact pre-migration state, including the original legacy schema defect (the invalid `upload_id` foreign key). Disaster recovery and schema repair are distinct operational steps; restoring a pre-migration backup will NOT pass repaired-schema foreign-key validation without re-applying the migration command.
     5. Run SQLite integrity validation on the restored file before reopening application traffic:
        ```powershell
        python -c "import sqlite3; conn = sqlite3.connect('backend/lectureai.db'); print(conn.execute('PRAGMA integrity_check;').fetchall()); conn.close()"
        ```
2. **CORS Visibility at Application Boundary (IMPLEMENTED & VERIFIED):**
   - In `backend/app/main.py`:
     - Configured `ALLOWED_DEVELOPMENT_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]`.
     - Implemented `CORSAppProxy` ASGI wrapper around the entire application boundary wrapping `ServerErrorMiddleware`.
     - Responses produced by `ServerErrorMiddleware` (unhandled 500 exceptions) receive standard single-origin CORS headers.
     - Transparent attribute delegation preserves `routes`, `openapi`, `lifespan`, `dependency_overrides`, and `state`.
     - Server errors remain HTTP 500 (never masked as 200).
   - **Verification Scope:** Verified via `TestClient` integration test suite (`tests/test_cors.py`). Full browser generation is explicitly deferred to later end-to-end phases.

### Phase 1 Completion Gate — STATUS: PASSED
- [x] Populated legacy-schema migration preserves existing data and indexes (`tests/test_migration_artifact_jobs.py`).
- [x] Running migration a second time is a safe no-op (verified via second actual invocation on disposable migrated DB).
- [x] Valid job creation via `POST /api/v1/artifacts/generate` succeeds (returns HTTP 200 with job in `PENDING` state in TestClient suite).
- [x] Invalid upload/version ownership is rejected with HTTP 400 and valid CORS headers.
- [x] OPTIONS preflight and actual POST requests tested from both `http://localhost:5173` and `http://127.0.0.1:5173`.
- [x] Isolated unhandled 500 error carries the `Access-Control-Allow-Origin` header without exception re-raising.
- [x] Disallowed origin (e.g. `http://malicious-site.example.com`) receives no allow-origin grant.
- [x] No live LLM calls executed during Phase 1 (background tasks suppressed via test monkeypatching).
- [x] Complete backend test suite against final working tree: **526 passed, 1 skipped, 0 failed in 30.48s** with development DB SHA256 verified untouched.
- [x] Real-browser verification: **NOT PERFORMED** (explicitly deferred).

---

## 6. DETAILED PHASE 2 SPECIFICATION: ACADEMIC STRUCTURE & KNOWLEDGE COMPILATION

### Objective
A real approved snapshot containing units, chapters, topics, concepts, and evidence compiles through the actual `KnowledgeBuilder` and repository into a finalized knowledge version that preserves its usable hierarchy, provenance, and deterministic source ordering without mutating history.

### Work Items for Phase 2
1. **Academic Category & Structure Preservation:**
   - Updated `backend/app/services/intelligence/knowledge_builder.py`: Added `"UNIT"` to `VALID_KNOWLEDGE_CATEGORIES`.
   - Retained support for hierarchies: `UNIT -> CHAPTER -> SECTION -> TOPIC -> CONCEPT` and shorter variants.
   - Manual containers without direct source blocks do not have fictitious evidence rows invented.
2. **Deterministic Source Ordering (`backend/app/services/intelligence/knowledge_ordering.py`):**
   - Lexicographical earliest actual source position tuple: `min((page_number, reading_order))` evaluated as a paired tuple.
   - Valid 0 values preserved (`is not None`).
   - BFS descendant-derived positions for manual containers labeled `DESCENDANT_DERIVED`. Missing/isolated containers labeled `FALLBACK`.
   - Persisted ordering metadata in entity `metadata_json`: `canonical_source_position`, `source_position_origin`, `snapshot_index`, `source_position_descendant_id`.
   - Reusable ordering function: `sort_entities_by_source_order`.
3. **Selectable Containers Helper (`backend/app/services/intelligence/knowledge_ordering.py`):**
   - `get_selectable_containers(entities, relationships)` returns `ContainerSelectionResult`:
     - Explicit units mode (`mode="UNITS"`) when `UNIT` entities exist.
     - Top-level chapters mode (`mode="CHAPTERS"`) when no `UNIT` exists, excluding nested sub-chapters via containment graph traversal.
     - `mode="REVIEW_REQUIRED"` when neither exists.
4. **Idempotency & Re-approval Lifecycle:**
   - Re-approval allocates `approval_version = MAX(approval_version) + 1`, generates distinct snapshot, and compiles to distinct `KnowledgeVersion`.
   - Compiling the same snapshot twice is strictly idempotent (returns existing version).
   - SQLite immutability triggers on snapshots and finalized versions remain intact.

### Phase 2 Completion Gate — STATUS: PASSED
- [x] Test A: `UNIT` category survives compilation alongside existing academic categories.
- [x] Test B: `UNIT -> CHAPTER -> SECTION -> TOPIC -> CONCEPT` retains valid containment structure.
- [x] Test C: Chapter-only input remains chapters and is identified as `CHAPTERS` mode.
- [x] Test D: Input without usable containers yields `REVIEW_REQUIRED` behavior.
- [x] Test E: Out-of-order UUIDs and shuffled entity insertion do not change source ordering.
- [x] Test F: Multiple source positions use the earliest actual tuple `(page, reading_order)`.
- [x] Test G: Missing positions / manual containers follow documented descendant / fallback rules.
- [x] Test H: Evidence preserves correct document IDs, source pages, and provenance.
- [x] Test I: Compiling the same snapshot twice remains idempotent.
- [x] Test J: Re-approval creates new snapshot/version identities while prior finalized content remains unchanged.
- [x] Test K: Existing immutability protections still reject prohibited changes.
- [x] Full regression suite passes: **537 passed, 1 skipped, 0 failed in 32.07s**.
- [x] Development database (`lectureai.db`) SHA256 verified untouched before and after test execution.

---

## 7. DETAILED PHASE 3 SPECIFICATION: EXACT CONTAINER SELECTION & SCOPE RESOLUTION

### Objective
For a finalized textbook knowledge version containing multiple units or chapters, selecting specific containers (e.g. Unit 2 and Unit 4) persists that exact selection with the artifact job, preserves textbook order, scopes retrieval and planning context to permitted descendants and evidence while excluding unselected containers, uses the correct `Document.id`, and aligns planning and validation under the exact same effective selection.

### Work Items for Phase 3
1. **Shared Selection Resolver (`backend/app/services/artifact/selection_resolver.py`):**
   - Implemented `EffectiveSelection` dataclass encapsulating `knowledge_version_id`, `document_id`, `upload_id`, `container_mode`, `container_type`, `selected_container_ids` (textbook-ordered), `permitted_entity_ids`, `permitted_evidence_ids`, and `container_to_descendants`.
   - **Document ID Resolution & Fallback Removal:**
     - Evidence references are checked for distinct `document_id` values. If evidence exists, verifies the referenced `Document` exists in DB and its `upload_id` matches `version.upload_id`. Conflicting or ambiguous associations are rejected explicitly.
     - When no evidence records exist, resolves via `Document.upload_id == version.upload_id`. If 0 rows exist, raises an explicit domain `ValueError`. The synthetic test fallback returning `version.upload_id` was **completely removed**.
     - Persisted and client-supplied `document_id` is never trusted; server-resolved identity is always authoritative.
   - **Typed Request Contract & Selection Validation (`backend/app/schemas/artifact.py`):**
     - Introduced `ArtifactGenerationConfig` Pydantic model with strict field validators.
     - Rejects non-list `selected_unit_ids`, null or empty string elements, and empty lists.
     - Rejects boolean, fractional, zero, or negative `num_units`.
     - Rejects mutual provision of both `selected_unit_ids` and `num_units`.
     - Domain validation rejects unknown container IDs, foreign-version IDs, and non-container entities (e.g. selecting a TOPIC as top-level container).
     - Preserves unrelated presentation settings (`audience_level`, `custom_theme`, etc.).
     - Canonical effective selection, mode, and server-resolved document identity are persisted in `job.config`, while `num_units` is cleared upon persistence to prevent downstream conflicts.
2. **Retrieval Scope Filtering & Passage-Level Isolation:**
   - Updated `RetrievalScope` in `backend/app/schemas/retrieval.py` to add `allowed_entity_ids: Optional[List[str]]`.
   - Updated `backend/app/services/retrieval/lexical_retriever.py` to filter candidates to `allowed_entity_ids` before ranking or top-k.
   - Updated `backend/app/services/retrieval/graph_expander.py` to prevent BFS traversal to neighbors outside `allowed_entity_ids`.
   - **Passage-Level Isolation & Provenance Resolution (`backend/app/services/retrieval/passage_retriever.py`):**
     - **Defect Repaired:** Previously, a physical block containing both selected and exclusively unselected content was admitted verbatim, leaking unselected material into the LLM prompt.
     - **Reproduced Failure:** Created regression fixture `test_reproduce_mixed_block_leak` demonstrating that `MARKER_UNIT1_EXCLUSIVE_LEAK` in a shared physical block entered the planning prompt when generating for Unit 2.
     - **Verified Provenance on Mixed Blocks:** When a block contains content from both selected and unselected containers, the selected portion is isolated using the persisted source span (`ev.text_reference`). If no verified boundary isolates the selected from unselected text, the ambiguous block is excluded with diagnostic `MIXED_BLOCK_EXCLUDED`. No LLMs, guessed splits, or invented offsets are used.
     - **Cross-Scope Overlap Disambiguation:** Geometric intersection is treated as candidate matching only. Overlapping cross-scope blocks are disambiguated by validated provenance (`text_reference in block.text`), not solely by largest intersection area. Unresolvable ambiguities are excluded with diagnostic `CROSS_SCOPE_AMBIGUITY`.
     - **Missing Coordinates Handling:** Missing bounding boxes do not trigger rejection if a trustworthy source reference establishes the exact allowed text (`EXACT_SPAN_RESOLVED`). If coordinates are missing without a trustworthy reference, whole-page fallback is suppressed (`MISSING_BOUNDING_BOX`).
     - **Surrounding Context Isolation:** Neighboring blocks are inspected for unselected evidence; `previous_text` and `next_text` are suppressed (`None`) on mixed blocks and when adjacent blocks contain unselected content.
     - **Bypass Prevention:** Excluded evidence IDs (`PassageRetriever.excluded_evidence_ids`) are omitted from `RetrievalResult.entities[i].evidence` so unverified text cannot bypass passage filtering into the prompt.
     - **Actionable Halting on Zero Substantive Evidence:** If exclusion leaves a selected container without usable substantive evidence, `ArtifactPlanner.plan` halts BEFORE provider invocation (`GroundingValidationError`), providing an actionable message identifying the affected container, source page/block, and diagnostic details. Headings-only presentations are prevented.
     - **Diagnostic Propagation:** All layout and resolution diagnostics are collected in `RetrievalResult.diagnostics` and propagated to `final_plan.metadata["retrieval_diagnostics"]`.
     - **Ordinary Unscoped Retrieval Preserved:** When `allowed_entity_ids` is None, full block text and ordinary coordinate matching remain active without restriction.
3. **Artifact Service & Job Persistence:**
   - In `backend/app/services/artifact/artifact_service.py`:
     - `create_artifact_job` validates selection upfront and persists `selected_unit_ids`, `container_mode`, `container_type`, and `document_id` in `job.config`.
     - `run_generation_pipeline` resolves `EffectiveSelection` and passes consistent permitted node IDs, evidence IDs, and expected container IDs to `ArtifactValidationContext`.
4. **Artifact Planner & Validator Alignment:**
   - In `backend/app/services/artifact/artifact_planner.py`:
     - Resolves `EffectiveSelection`. Plans chunks per selected container in textbook order.
     - Handles arbitrary hierarchies (UNIT -> CHAPTER -> SECTION -> TOPIC -> CONCEPT or CHAPTER -> TOPIC -> CONCEPT).
     - Deduplicates shared descendants across selected containers.
     - Supplies correct `Document.id` and `allowed_entity_ids` to `RetrievalScope`.
     - Formats substantive textbook explanations and evidence IDs into planning context.
   - In `backend/app/services/artifact/artifact_validator.py`:
     - `ArtifactValidationContext` supports `container_type` and `container_to_descendants`.
     - Grounding validation checks that cited nodes and evidence belong to `permitted_entity_ids` and `permitted_evidence_ids`.
     - Coverage validation attributes coverage either directly or via container descendants.

### Phase 3 Completion Gate — STATUS: PASSED
- [x] Passage isolation leak reproduced and demonstrated in capturing fixture prior to fix.
- [x] Input selection in reverse order `[Unit 4, Unit 2]` resolves and persists as `[Unit 2, Unit 4]` in textbook order.
- [x] Production document-ID fallback completely removed; missing/mismatched document associations raise explicit domain errors.
- [x] Lightweight fixtures updated with distinct `Document.id` and `upload_id`.
- [x] Malformed selections rejected at schema and API boundaries (string instead of list, null elements, empty list, mutual exclusion, bool/fractional/zero/negative num_units, foreign/unknown IDs).
- [x] Arbitrary unit selection verified with parameterized dynamic container IDs (each unit individually, subsets, all units, reverse order).
- [x] Alternate 5-unit textbook fixture verified without hardcoded unit labels or numbers.
- [x] Mixed physical blocks: verified source span extraction isolated; ambiguous mixed blocks excluded with `MIXED_BLOCK_EXCLUDED`.
- [x] Overlapping cross-scope candidates: disambiguated by validated provenance, rejecting largest-area heuristics.
- [x] Missing coordinates with valid text reference resolved via `EXACT_SPAN_RESOLVED`; missing coordinates without reference excluded via `MISSING_BOUNDING_BOX`.
- [x] Legitimate shared descendants preserved and permitted in effective selection.
- [x] Selected container left without usable substantive evidence halts before provider invocation with actionable diagnostic.
- [x] No excluded marker reaches any provider-context field (entity content, evidence, passages, previous/next context).
- [x] Diagnostics propagated to `RetrievalResult.diagnostics` and `final_plan.metadata["retrieval_diagnostics"]`.
- [x] Real `ScopeResolver` receives canonical `Document.id` (strictly a Document.id contract).
- [x] Validator expects exactly the selected containers (`{Unit 2, Unit 4}`) and does not expect unselected containers.
- [x] Out-of-scope nodes and evidence citations are rejected with `GROUNDING` errors.
- [x] Ordinary unscoped retrieval verified 100% functional.
- [x] Full regression suite passes: **573 passed, 1 skipped, 0 failed in 28.89s**.
- [x] Development database (`lectureai.db`) SHA256 verified untouched: `08802202e39df7d3f822b750ac4b1a4240dd326a51b0d8ac1f391316a752257c`.

---

---

## 8. DETAILED PHASE 4 SPECIFICATION: GENERATION, VALIDATION, RENDERING & JOB LIFECYCLE

### Objective
Demonstrate the real internal generation pipeline from approved snapshot to compiled knowledge, persisted selection, scoped retrieval, chunked planning, strict validation, PPTX rendering, completed job, and presentation download. Use a deterministic, schema-valid provider fixture without mocking the compiler, selection resolver, retrieval service, planner, validator, or renderer in the acceptance integration test.

### Work Items for Phase 4
1. **Generation Prerequisites Closed:**
   - **Ambiguous Provenance Excluded Without Area Bias (`backend/app/services/retrieval/passage_retriever.py`):**
     - When multiple candidate blocks match an identical text reference and no exact block reference (`block_id` in metadata or `source_anchor_key`) is present, candidates are excluded with `CROSS_SCOPE_AMBIGUITY`. Geometry/area is never used to claim ownership.
     - Added `check_text_references_overlap` to verify partial overlapping references (prefix/suffix overlap and block span overlap) between selected and unselected references.
     - Ambiguous mixed blocks and overlapping text references are excluded. Persisted source spans are only claimed when true character offsets exist.
   - **Evidence Sufficiency Guard Unconditioned on Diagnostics (`backend/app/services/artifact/artifact_planner.py`):**
     - Removed `has_exclusion` gating. If retrieval returns empty results or if available content consists solely of headings/citation IDs, `ArtifactPlanner.plan` halts immediately with `GroundingValidationError` identifying the affected container and location.
     - Added `_is_trivial_or_heading` check avoiding regex backtracking to evaluate content substantiveness in linear time.
2. **Provider Configuration & Structured Output (`backend/app/services/generation/`):**
   - In `backend/app/services/generation/groq_provider.py`:
     - Initialized `AsyncGroq(..., max_retries=0)` to avoid nested multiplications with the bounded application retry loop.
     - Bounded retries: 2 retries (3 attempts total) with exponential backoff and extraction of `Retry-After` header capped at 10.0s.
     - Immediate failure on non-retryable errors (`AuthenticationError`, `BadRequestError`) with sanitized messages that do not expose API keys or private textbook text.
   - In `backend/app/services/generation/mock_provider.py`:
     - Enhanced `MockLLMProvider` to dynamically parse slide fragment schemas from prompt entities (`- [CATEGORY] (id) title:`), supporting custom test modes: `invalid_citation`, `malformed_output`, `malformed_slides_schema`, and `success`.
     - Preserves backwards compatibility for Q&A generations.
   - In `backend/app/services/artifact/artifact_service.py`:
     - Missing live provider credentials (`GROQ_API_KEY`) produces an explicit configuration failure; silent fallback to mock is strictly prevented. Mock provider is only available via explicit test/demo configuration (`provider="mock"` in job config or `LLM_PROVIDER=mock`).
3. **Bounded Hierarchical Chunking & Token Budgeting:**
   - In `backend/app/services/artifact/artifact_planner.py`:
     - Defined conservative token estimator `estimate_tokens(text)` (~4 chars per token) and strict limits:
       - `MAX_ENTITIES_PER_CHUNK = 10`
       - `MAX_CONTEXT_TOKENS = 6000` (reserving headroom for instructions and model output)
       - `MAX_TOTAL_CHUNKS = 50`
     - Oversized topics/contexts raise an actionable `GroundingValidationError` instead of truncating citations or silently omitting selected material.
     - Enclosed source material in `<source_data>` tags with explicit instructions that textbook passages are passive reference data that cannot override formatting or schema rules.
     - Validated generated slide citations strictly against the exact node and evidence IDs supplied in that specific chunk call.
4. **Job Lifecycle & Persistence:**
   - In `backend/app/services/artifact/artifact_service.py`:
     - Lifecycle transitions: `PENDING -> PLANNING -> RENDERING -> COMPLETED` (or `FAILED`).
     - Validation occurs before rendering.
     - Validated plan is saved to `job.plan` and committed to the database before transitioning to `RENDERING`.
     - Final presentation artifact is reopened and verified using `python-pptx` before marking the job `COMPLETED`.
     - Partial artifacts are cleaned up on failure so no downloadable partial file remains.
     - Duplicate execution of active or completed jobs is rejected with `ValueError`.
     - Added `recover_interrupted_jobs()` to safely transition orphaned jobs stuck in `PLANNING` or `RENDERING` across process restarts to `FAILED` with actionable guidance, preventing silent partial downloads or double-billing.
5. **PPTX Rendering & Download Verification:**
   - In `backend/app/services/artifact/pptx_renderer.py`:
     - Configured explicit 16:9 widescreen dimensions (`slide_width = 13.333 inches`, `slide_height = 7.5 inches`).
     - Atomic final-file replacement using `os.replace` directly without premature deletion of existing target files.
     - Temporary files generated during rendering are cleaned up safely in `finally` blocks.
     - Download endpoint `/api/artifacts/{job_id}/download` returns completed presentation with correct MIME type `application/vnd.openxmlformats-officedocument.presentationml.presentation` and `Content-Disposition` header.

### Phase 4 Completion Gate — STATUS: PASSED
- [x] Full internal pipeline executed from compiled knowledge, persisted selection, scoped retrieval, chunked planning, validation, PPTX rendering, to download endpoint without mocking core components.
- [x] Downloaded PPTX verified via `python-pptx`: valid widescreen 16:9 structure, slide titles, body placeholders, speaker notes, and selected unit content.
- [x] Exclusively unselected content markers (`EXCLUSIVELY_UNSELECTED_MARKER_DARK_MATTER`, `qubits`) verified absent from all slides and speaker notes.
- [x] Cross-scope identical-text ambiguity excluded with `CROSS_SCOPE_AMBIGUITY` diagnostic when block provenance is missing; largest-area heuristic rejected.
- [x] Exact block ID provenance successfully disambiguates multiple matching blocks.
- [x] Empty retrieval or non-substantive text without diagnostics halts with actionable `GroundingValidationError` identifying container.
- [x] Missing live provider configuration fails explicitly; failed live calls never fall back to mock.
- [x] Malformed JSON, schema violations, and fabricated citations rejected cleanly.
- [x] Provider timeouts and rate limits handled with bounded retries and backoff.
- [x] Oversized context exceeding limits returns explicit `GroundingValidationError` without truncation.
- [x] Renderer failures clean up partial files and transition job to `FAILED`.
- [x] Duplicate execution of running or completed jobs rejected.
- [x] Interrupted jobs recovered to `FAILED` status without leaving corrupt downloadable files.
- [x] Full regression suite passes: **587 passed, 1 skipped, 0 failed in 43.12s**.
- [x] Development database (`lectureai.db`) verified untouched.

---

## 9. DEFERRED ARCHITECTURAL CLARIFICATIONS (FOR PHASES 5–7)

1. **Frontend Unit Selection Checkboxes (Phase 5):**
   - `selected_unit_ids` API contract is fully functional on backend. UI checkboxes on `/documents/:id/artifact` and approval review routing deferred to Phase 5.
2. **End-to-End Real Textbook Validation (Phase 6):**
   - Human comparison of real textbook pages against generated slide content deferred to Phase 6.
3. **Advanced Presentation Layout & Styling (Phase 7):**
   - Advanced themes, custom typography, table/formula rendering, and visual polish deferred to Phase 7.

---

## 10. REMAINING FACTUAL UNKNOWNS

1. **OCR Performance on Large Textbooks:**
   - Local Tesseract binary is verified available. However, processing a 300+ page textbook at 300 DPI will take substantial time. Does the current job timeout threshold accommodate 30+ minutes of extraction?
2. **Groq Token Limits for Rich Units:**
   - Groq model `openai/gpt-oss-120b` has vendor TPM limits. Real token consumption per chunk must be monitored during live generation in Phase 6.

