# LECTUREAI PHASED REPAIR PLAN & ARCHITECTURAL BASELINE

**Document Version:** 1.3.0 (Phase 6A Complete)  
**Last Updated:** 2026-09-29  
**Scope:** Phase 6A Complete — Real-Browser Acceptance & Isolated Storage Integration Verification  
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
     - Implemented conservative token estimator (3.2 characters per token with 15% safety headroom and explicit token ceilings).
     - Headroom calculation:
       - Target context: 8,192 tokens
       - System instructions reserve: 1,000 tokens
       - Multi-slide JSON output reserve: 2,000 tokens
       - Usable context budget: `int((8192 - 3000) * 0.85) = 4,413` tokens (`MAX_CONTEXT_CHARS` ~ 14,120 characters)
     - Oversized content subdivision:
       - Long topics and units exceeding `MAX_SINGLE_ENTITY_CHARS` (1,200 tokens ~ 3,840 chars) are subdivided along supported source boundaries (`\n\n` paragraph breaks, then `. `, `? `, `! ` sentence boundaries) into bounded parts `(Part X of N)`.
       - All parts preserve exact source order, selected container membership, original evidence associations, and hierarchy context.
       - Each part is scheduled across bounded provider requests without silent omission or invented character offsets.
     - Total job workload ceiling:
       - Maximum 50 bounded requests per job (`MAX_TOTAL_CHUNKS = 50`). If a job exceeds this budget, it halts with an actionable error advising the user to narrow unit selection.
4. **Atomic Job Claiming & Lifecycle Recovery:**
   - In `backend/app/repositories/artifact_repository.py` & `artifact_service.py`:
     - Replaced read-then-update duplicate guard with an atomic conditional state transition (`UPDATE artifact_jobs SET status = 'PLANNING' WHERE id = :id AND status = 'PENDING'`).
     - Exactly one execution claims the job; concurrent or racing workers receive `None` and abort before invoking LLM providers or renderers.
     - Offline recovery tool: `backend/app/services/artifact/recover_jobs.py` (`python -m app.services.artifact.recover_jobs [--include-pending] [--dry-run]`).
     - Documented policy: must be executed offline when workers/servers are stopped. Safely transitions stranded `PLANNING`, `RENDERING` (and optionally `PENDING`) jobs to `FAILED` with an actionable message, cleans up partial files, and leaves `COMPLETED` jobs and artifacts untouched.
5. **Provider Bounds & Retry Policy:**
   - In `backend/app/services/generation/groq_provider.py`:
     - Per-attempt timeout: 30.0s (`AsyncGroq(timeout=30.0, max_retries=0)`).
     - Max attempts: 3 (attempt 0, 1, 2; `max_retries = 2`).
     - True exponential backoff: `1.0 * (2 ** attempt)` (1.0s, 2.0s).
     - Single retry wait budget: `max_retry_wait_budget = 15.0s`.
     - `Retry-After` enforcement: If `Retry-After` header exceeds 15.0s, execution halts immediately with `LLMProviderError` rather than retrying sooner than the provider requested.
     - Worst-case maximum total duration: `3 * 30.0s + 2 * 15.0s = 120.0s` (or 93.0s under standard backoff).
     - Strict provider separation: Live generation never silently produces fixture content; mock generation is quarantined to explicit test providers.
6. **Production-Route Acceptance & PPTX Verification:**
   - Verified via production application factory (`create_app()`) and real versioned prefix (`/api/v1/artifacts/...`):
     - `POST /api/v1/artifacts/generate`
     - `GET /api/v1/artifacts/{id}`
     - `GET /api/v1/artifacts/{id}/download`
   - Verified substantive selected content ("ATP", "mitochondrial matrix respiration", "Cellular respiration") in slide bodies (shapes with text frames), not only titles or speaker notes.
   - Verified unselected content ("Quantum Computing", "qubits", `EXCLUSIVELY_UNSELECTED_MARKER_DARK_MATTER`) is completely absent across all slides, titles, bodies, and speaker notes.
   - Retained labelled test artifact: `backend/data/test_artifacts/phase4_acceptance_artifact.pptx`.

### Phase 4 Completion Gate — STATUS: PASSED
- [x] Oversized topics subdivided into bounded requests along supported boundaries without rejection.
- [x] Source order, container membership, evidence associations, and hierarchy preserved across chunk parts.
- [x] Conservative token estimator (3.2 chars/token) and explicit token ceilings documented and enforced.
- [x] Atomic conditional job claiming (`UPDATE ... WHERE status = 'PENDING'`) verified with concurrent sessions; losing execution aborts before provider/renderer calls.
- [x] Offline job recovery tool (`recover_jobs.py`) implemented and tested for `PENDING`, `PLANNING`, `RENDERING`; completed artifacts untouched.
- [x] Provider timeout (30.0s), max attempts (3), true exponential backoff (`1.0 * 2^attempt`), and `Retry-After` wait budget (15.0s) enforced.
- [x] Full real-pipeline acceptance test verified through production factory `create_app()` and `/api/v1` prefix.
- [x] Substantive content confirmed in slide bodies; unselected content verified absent.
- [x] Labelled test artifact saved to `backend/data/test_artifacts/phase4_acceptance_artifact.pptx`.
- [x] Full backend test suite passing: **589 passed, 1 skipped (real-API smoke test), 0 failed in 58.83s**.
- [x] Development database (`lectureai.db`) verified untouched (identical SHA256 and row counts before and after full test run).

---

## 9. DETAILED PHASE 5 SPECIFICATION: FRONTEND WORKFLOW INTEGRATION & SELECTABLE CONTAINERS

### Objective
Connect LectureAI’s real frontend workflow to the repaired backend across the full user journey:
Upload textbook PDF → processing/OCR → review academic structure → approve and compile → choose any available units → generate → see actual job status → download PPTX.
Enable dynamic selection of any single unit, any combination of units, or all available units sourced dynamically from the textbook’s finalized knowledge version without hardcoded counts or artificial unit limits.

### Work Items for Phase 5
1. **Journey Trace & Navigation Wiring:**
   - In `frontend/src/pages/ProcessingPage.tsx`:
     - On extraction completion, `handleContinue` navigates to `/academic/review/${job.upload_id}`.
     - Mock routes `/units`, `/outline`, `/preview` are completely eliminated from the real user journey.
     - Extraction failures remain visible with actionable diagnostics, providing "Back to Upload" and "Inspect Partial Structure" options.
   - In `frontend/src/pages/AcademicReviewPage.tsx`:
     - Synchronous graph approval & compilation returns `approval_version`, `approved_revision`, `resolved_graph_fingerprint`, `document_id`, `knowledge_version_id`.
     - Approval success modal provides primary action "Proceed to Slide Generation" navigating to `/documents/${docId}/artifact`.
     - When document is already `APPROVED`, header renders a direct "Generate Slides" button.
2. **Backend Read-Only Selectable Containers Endpoint:**
   - In `backend/app/api/routes/knowledge.py`:
     - `GET /api/v1/knowledge/versions/{version_id}/selectable-containers`
     - `GET /api/v1/knowledge/document/{document_id}/selectable-containers`
     - Evaluates `get_selectable_containers(db, version.id)` returning `container_mode` (`UNITS`, `CHAPTERS`, `REVIEW_REQUIRED`), `container_type`, `containers` in canonical source order, and `diagnostics`.
     - For each container, resolves `source_page_start`, `source_page_end`, and `topic_count`.
     - Ordering sentinels (e.g. `999999999`) are strictly mapped to `null` to ensure the frontend never displays synthetic sentinel numbers as real pages.
3. **Dynamic Unit Selection & Mutual Exclusion UI (`frontend/src/pages/ArtifactWorkspacePage.tsx`):**
   - Checkbox for every available container with exact textbook title, page range badge (when valid), and topic count badge.
   - Intentional initial state: empty selection (`0 of N selected`).
   - "Generate Presentation" disabled until at least one container is selected.
   - "Select All" and "Clear Selection" buttons, plus search filter for longer container lists.
   - For `CHAPTERS` mode: displays informational banner clarifying that choices are chapters rather than syllabus units.
   - For `REVIEW_REQUIRED` mode: explains missing container structure, links to `/academic/review/${upload_id}`, and disables generation.
   - Sends exact `config.selected_unit_ids` array containing real entity UUIDs; does not send `num_units` or client-authored document IDs.
4. **Version Changes & Old Knowledge Handling:**
   - Changing `documentId` or version clears previous selections, errors, and in-flight polling.
   - Stale requests are ignored via unmount/active token guards.
   - Job history retains its original version and selection scope without cross-version confusion.
5. **Generation, Polling & Error Resilience:**
   - Immediate duplicate submission prevention: `isSubmitting` disables the generate button while the create POST is in-flight.
   - Tracks actual persisted stages (`PENDING`, `PLANNING`, `RENDERING`, `COMPLETED`, `FAILED`) without fabricated percentages.
   - Resumes status polling after page refresh using active job from job history.
   - Stops polling immediately on terminal states (`COMPLETED`, `FAILED`).
   - Handles transient network errors during polling without prematurely marking jobs failed or stopping polling.
   - Robust backend error parsing (`formatBackendError`) handles Pydantic validation arrays, workload limit errors, and domain errors cleanly.
6. **Download & Contract Alignment:**
   - PPTX download button enabled ONLY for `COMPLETED` jobs.
   - Download URL constructed cleanly from `apiClient.defaults.baseURL` / `VITE_API_URL` without trailing slash bugs.

### Phase 5 Completion Gate — STATUS: PASSED
- [x] Processing → review navigation uses real `upload_id` and eliminates mock `/units`, `/outline`, `/preview` routes.
- [x] Approval success modal provides "Proceed to Slide Generation" navigating to `/documents/${docId}/artifact`.
- [x] Backend endpoint `GET /api/v1/knowledge/versions/{version_id}/selectable-containers` returns canonically ordered containers and masks sentinels to `null`.
- [x] Chapters mode and Review-Required mode handled with dedicated banners, diagnostics, and links.
- [x] Single, multiple, and all container selections verified with exact `selected_unit_ids` payload; `num_units` is omitted.
- [x] Immediate duplicate-submit prevention verified while create request is in-flight.
- [x] Terminal status polling stop and transient error resilience verified.
- [x] Page refresh polling resumption verified from job history.
- [x] PPTX download enabled only for `COMPLETED` jobs with verified download URL construction.
- [x] Full frontend test suite passing: **34 passed across 6 test files in 5.24s**.
- [x] Frontend production build (`tsc -b && vite build`) passing with zero errors.
- [x] Backend test suite passing: **51 passed in 5.91s**.
- [x] Development database (`lectureai.db`) verified untouched.

---

## 10. PHASE 6A: REAL-BROWSER ACCEPTANCE & ISOLATED INTEGRATION VERIFICATION

### Status: PASSED

### 1. Isolated Environment Architecture
- **Isolated Database:** `sqlite:///C:/Users/rohit/.gemini/antigravity-ide/brain/8d485f93-7a2a-49ba-b72d-3fa779158f26/scratch/storage_phase6a/isolated_lectureai.db`
- **Isolated Storage Root:** `C:\Users\rohit\.gemini\antigravity-ide\brain\8d485f93-7a2a-49ba-b72d-3fa779158f26\scratch\storage_phase6a`
- **Isolated Artifacts Directory:** `C:\Users\rohit\.gemini\antigravity-ide\brain\8d485f93-7a2a-49ba-b72d-3fa779158f26\scratch\storage_phase6a\artifacts`
- **Isolated Backend Server:** Port `8001` via `start_isolated_backend.py` with `LLM_PROVIDER=mock` (ordinary client requests do not include `provider="mock"`).
- **Isolated Frontend Dev Server:** Port `5174` via `vite --port 5174 --strictPort --mode isolated` pointing to `VITE_API_URL=http://localhost:8001/api/v1`.
- **CORS Allowed Origins:** Updated `ALLOWED_DEVELOPMENT_ORIGINS` to support `http://localhost:5174` and `http://127.0.0.1:5174`.

### 2. Functional PDF Test Fixtures Created
1. `sample_digital_textbook.pdf`:
   - 4 pages, digital selectable text layer (752, 597, 1045, 1000 chars per page).
   - Contains 3 Units (Unit 1 across pages 1-2, Unit 2 on page 3, Unit 3 on page 4).
   - Distinct source statement markers: `DISTINCT_MARKER_U1_ARCH`, `DISTINCT_MARKER_U1_FAIL`, `DISTINCT_MARKER_U2_RAFT`, `DISTINCT_MARKER_U2_CLOCK`, `DISTINCT_MARKER_U3_STREAM`, `DISTINCT_MARKER_U3_GRAPH`.
2. `sample_scanned_textbook.pdf`:
   - 2 pages, pure raster bitmap images (0 digital font characters, forcing OCR detection).
   - Verified Tesseract OCR 5.5 invocation (processing time 1.45s, `ocr_status="completed"`, recognized text extracted with provenance `"OCR"`).

### 3. Real-Browser Acceptance Journey Verified
- **Upload & Ingestion:** Uploaded `sample_digital_textbook.pdf`, processed through canonical document extraction, reading order, and normalization.
- **Processing Observation:** Observed real progress transitions to `completed` on `/processing/:jobId`.
- **Academic Review:** Navigated via "Review Academic Structure", inspected hierarchical nodes, verified source text and distinct markers, executed node reviews, and approved graph snapshot.
- **Approval Payload & State Transfer:** Confirmed `document_id` and `knowledge_version_id` survive response serialization to browser; approved snapshot frozen and committed.
- **Artifact Selection:** Navigated via "Proceed to Slide Generation" to `/documents/:id/artifact`. Verified:
  - Generate Presentation button is disabled when 0 containers are selected.
  - "Select All" selects all 3 units (counter updates to 3).
  - "Clear Selection" clears all units (counter resets to 0, button disabled).
  - Search filter isolates matching units dynamically.
  - Flexible selection verified: Unit 1 and Unit 3 selected together.
- **Generation & Polling:** Clicked "Generate Presentation (.pptx)", observed real backend status progression (`PENDING` -> `PLANNING` -> `RENDERING` -> `COMPLETED`).
- **Download & Inspection:** Downloaded `.pptx` presentations, verified with `python-pptx`:
  - Valid 16:9 PowerPoint structure containing 10 slides.
  - Contains substantive selected content, speaker notes, and provenance source notes (`[Provenance] Sources: ...`).
  - Correct MIME type `application/vnd.openxmlformats-officedocument.presentationml.presentation` and `Content-Disposition`.
- **Controlled Failure & Error Resilience:** Verified 404 response on missing or invalid download job without crashes.

### 4. Issues Identified & Resolved in Phase 6A
- **ISS-14 (RESOLVED):** `OCRAgent` OCR cache block ID duplication (`UNIQUE constraint failed: document_blocks.id`). Replaced cached block ID reuse with fresh `uuid.uuid4()` generation, and added primary-key uniqueness safeguard in `DocumentRepository.save_extraction_result`.
- **ISS-15 (RESOLVED):** Oversized single-sentence chunking without delimiters in `ArtifactPlanner.split_content_into_bounded_segments`. Subdivided oversized single sentences on whitespace and character slices without silent truncation; added unit test `test_phase6a_oversized_sentence.py` (2/2 passing).
- **ISS-16 (RESOLVED):** Environment variable isolation for storage root, artifacts directory, and CORS allowed origins (`LECTUREAI_STORAGE_ROOT`, `LECTUREAI_ARTIFACTS_DIR`, `ALLOWED_ORIGINS`).

---

## 11. DEFERRED ARCHITECTURAL CLARIFICATIONS (FOR PHASE 7)

1. **Visual Polish & Premium UI (Phase 7):**
   - Fine-grained typography, glassmorphism, slide transition animations, and dark-mode styling refinements deferred to Phase 7.
2. **Live LLM Model Output Validation:**
   - Production validation with live Groq API keys and domain-expert pedagogical evaluation.



