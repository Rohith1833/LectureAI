# LECTUREAI CURRENT IMPLEMENTATION AUDIT & CONTEXT REPORT

**Generated:** 2026-09-28T19:01:00+05:30  
**Target Repository:** `LectureAI` (Root: `c:\Users\rohit\Downloads\ALL projects\LectureAI`)  
**Auditor:** Antigravity IDE Inspection Subagent  
**Scope:** Complete architectural inspection, execution verification, defect diagnosis, and handoff briefing.  
**Mode:** Inspection only. No application code, dependencies, or database structures were modified.

---

## 1. REPOSITORY STATE

### Git Inspection
* **Current Branch:** `main` (Up to date with `origin/main`)
* **HEAD Commit SHA:** `d52761dbc8330e4c65503f17e9bff7ae27dbf2e7`
* **Latest Commit Message:** `feat: complete phase 9 (artifact generation & orchestration)`
* **Preceding Commits:**
  - `4158bf0`: `feat: establish artifact generation architecture`
  - `2940e0a`: `fix: optimize academic review bulk approval`

### Working Tree Status (`git status`)
The local working tree contains subsequent, uncommitted changes made after commit `d52761d`:

```text
Changes not staged for commit:
  modified:   backend/app/main.py
  modified:   backend/tests/test_artifact_planner.py
  modified:   frontend/src/pages/ArtifactWorkspacePage.tsx

Untracked files:
  backend/tests/test_cors.py
  frontend/src/pages/__tests__/ArtifactWorkspacePage.test.tsx
  scratch/fix_tests.py
```

### Analysis of Uncommitted Changes vs. Commit `d52761d`
1. **Frontend `ArtifactWorkspacePage.tsx`**:
   - **ID Fix**: Changed `const { id: uploadId } = useParams()` to `const { id: documentId } = useParams()`. Now correctly calls `listFinalizedVersions(documentId)` and uses `version.upload_id` for `generateArtifact()` and `listJobs()`.
   - **Configuration Controls**: Added 5 user-facing controls:
     - `audienceLevel` (`general`, `undergraduate`, `graduate`, `expert`)
     - `depth` (`overview`, `standard`, `detailed`)
     - `numUnits` (`number` input)
     - `includeExamples` (`checkbox`)
     - `includeQuestions` (`checkbox`)
   - **Status & Lifecycle**: Download button strictly gated to `status === COMPLETED`. Displays `error_message` on `FAILED`. Polling interval active every 2000ms while `PENDING`, `PLANNING`, or `RENDERING`.
2. **Backend `main.py`**:
   - Reordered `CORSMiddleware` after the `@app.middleware("http")` logging middleware so Starlette evaluates CORS as the outermost middleware.
3. **Backend `test_artifact_planner.py`**:
   - Added `get_finalized_version` method to `MockKnowledgeRepo` to satisfy Phase 9C contract.
4. **Untracked Tests**:
   - `backend/tests/test_cors.py`: 5 tests covering preflight OPTIONS, regular GET, unknown origin rejection, and 404 error responses with TestClient.
   - `frontend/src/pages/__tests__/ArtifactWorkspacePage.test.tsx`: 19 Vitest tests validating configuration inputs, payload structure, polling lifecycle, and error boundaries.

---

## 2. STACK AND STARTUP

### Technologies & Manifest Versions
* **Python Runtime:** `3.13.0` [VERIFIED BY EXECUTION]
* **Backend Web Framework:** `FastAPI 0.115.12`, `Uvicorn 0.34.2` (`backend/requirements.txt:1-2`)
* **Data Validation:** `Pydantic 2.11.4`, `pydantic-settings 2.9.1` (`backend/requirements.txt:3-4`)
* **ORM & Database:** `SQLAlchemy 2.0.49` (`backend/requirements.txt:9`), SQLite 3
* **PDF Extraction & Layout:** `PyMuPDF (fitz) 1.25.x` (`backend/requirements.txt:8`)
* **OCR Engine:** `pytesseract` (`backend/requirements.txt:10`) backed by local binary `C:\Program Files\Tesseract-OCR\tesseract.exe` [VERIFIED BY EXECUTION]
* **Presentation Renderer:** `python-pptx 1.0.2` (`backend/requirements.txt:12`)
* **LLM Provider:** `groq 1.6.0` (`backend/requirements.txt:11`)
* **Frontend Runtime:** Node.js, `React 19.2.8`, `React-DOM 19.2.8` (`frontend/package.json:25-26`)
* **Frontend Routing:** `react-router-dom 7.11.0` (`frontend/package.json:27`)
* **Frontend Build Tool:** `Vite 8.2.0`, `TypeScript 6.0.2` (`frontend/package.json:42-43`)
* **Frontend Styling:** `TailwindCSS 4.3.3`, `@tailwindcss/vite 4.3.3` (`frontend/package.json:19, 29`)
* **Client Data Fetching:** `@tanstack/react-query 5.101.4`, `Axios 1.19.0` (`frontend/package.json:20-21`)
* **Test Runners:** `pytest 9.1.1` (backend), `vitest 4.1.11` (frontend)

### Startup & Verification Commands
* **Start Backend:**
  ```powershell
  cd backend
  python -m app.main
  # Serves at: http://127.0.0.1:8000
  ```
* **Start Frontend:**
  ```powershell
  cd frontend
  npm run dev
  # Serves at: http://localhost:5173
  ```
* **Run Backend Tests:**
  ```powershell
  cd backend
  python -m pytest -q
  ```
* **Run Frontend Tests:**
  ```powershell
  cd frontend
  npm test -- --run
  ```
* **Build Frontend:**
  ```powershell
  cd frontend
  npm run build
  ```

### Environment Variables Matrix
| Name | Required | Configured Locally | Purpose | Reference |
|---|---|---|---|---|
| `HOST` | No | Yes (`127.0.0.1`) | ASGI bind address | `backend/app/core/config.py:14` |
| `PORT` | No | Yes (`8000`) | ASGI bind port | `backend/app/core/config.py:15` |
| `DEBUG` | No | Yes (`True`) | Debug mode flag | `backend/app/core/config.py:16` |
| `PROJECT_NAME` | No | Yes (`LectureAI`) | Application name | `backend/app/core/config.py:17` |
| `API_VERSION` | No | Yes (`v1`) | Base API version | `backend/app/core/config.py:18` |
| `DATABASE_URL` | No | Yes (`sqlite:///./lectureai.db`) | SQLite connection URL | `backend/app/core/config.py:19` |
| `GROQ_API_KEY` | Optional | **Configured** (Secret redacted) | Live LLM generation calls | `backend/app/core/config.py:22` |
| `GROQ_MODEL` | No | Yes (`openai/gpt-oss-120b`) | Model identifier on Groq | `backend/app/core/config.py:23` |
| `VITE_API_URL` | Yes | Yes (`http://localhost:8000/api/v1`) | Axios base URL for frontend | `frontend/.env:1` |

---

## 3. REAL USER FLOW TRACE

The intended product workflow spans 9 stages. Here is the exact status of each step:

| Step | User Action | Route / Component | API Method & Endpoint | Backend Handler / Service | Models & IDs Exchanged | Connectivity State |
|---|---|---|---|---|---|---|
| 1. Upload | User selects and uploads PDF file | `/upload`<br>`UploadPage.tsx` | `POST /api/v1/upload` | `app/api/routes/upload.py:upload_file`<br>`UploadService.save_file` | Payload: `multipart/form-data`<br>Returns: `{ upload_id: UUID }` | **Connected** |
| 2. Job Queue | Frontend automatically enqueues extraction | `/upload`<br>`UploadPage.tsx` | `POST /api/v1/jobs` | `app/api/routes/jobs.py:create_job`<br>`job_service.create_job` | Sends: `{ upload_id }`<br>Returns: `{ job_id: UUID }` | **Connected** |
| 3. Extraction & OCR | Backend background task runs PyMuPDF + Tesseract | `/processing/:jobId`<br>`ProcessingPage.tsx` | `GET /api/v1/jobs/:jobId` (polling 2s) | `job_service.run_pdf_extraction_pipeline`<br>`run_document_agent` | Updates job JSON on disk; creates DB row: `Document(id, upload_id)` | **Connected** |
| 4. Unit Review & Navigation | User clicks "Continue" upon completion | `/processing/:jobId`<br>`ProcessingPage.tsx` | None | Client-side navigation: `navigate("/units")` | **BROKEN / DEAD-END**: Navigates to legacy mock demo `/units` instead of `/documents/:id` or `/academic/review/:uploadId`. | **Disconnected Workflow** |
| 5. Human Academic Review | User corrects classifications, reparents nodes, approves graph | `/academic/review/:uploadId`<br>`AcademicReviewPage.tsx` | `GET /api/v1/review/:uploadId/graph`<br>`POST /api/v1/review/:uploadId/actions`<br>`POST /api/v1/review/:uploadId/approve` | `app/api/routes/review.py`<br>`AcademicReviewService` | Takes: `upload_id`, `expected_revision`<br>Creates: `AcademicGraphSnapshot(id, upload_id, approval_version)` | **Connected** (Requires manual URL navigation) |
| 6. Knowledge Finalization | Auto-compiled upon approval | Background hook / API | `POST /api/v1/knowledge/compile/:snapshotId` | `KnowledgeBuilder.compile_snapshot` | Takes: `snapshot_id`<br>Creates: `KnowledgeVersion(id, upload_id, status="FINALIZED")` | **Connected** |
| 7. Unit Selection & Config | User sets audience, depth, num_units, examples, questions | `/documents/:id/artifact`<br>`ArtifactWorkspacePage.tsx` | `GET /api/v1/knowledge/document/:docId/versions` | `knowledge_repository.list_finalized_versions` | Fetches finalized versions for `Document.id`; displays controls | **Connected** (Fixed uncommitted) |
| 8. Artifact Generation Job | User clicks "Generate Presentation" | `/documents/:id/artifact`<br>`ArtifactWorkspacePage.tsx` | `POST /api/v1/artifacts/generate` | `app/api/routes/artifact.py:create_artifact_job`<br>`ArtifactService.create_artifact_job` | Sends: `{ upload_id, knowledge_version_id, artifact_type: "PPTX", config }` | **BLOCKED BY DATABASE DEFECT** (See Section 8) |
| 9. Download PPTX | User clicks download button | `/documents/:id/artifact`<br>`ArtifactWorkspacePage.tsx` | `GET /api/v1/artifacts/:jobId/download` | `app/api/routes/artifact.py:download_artifact` | Returns binary `.pptx` stream via `FileResponse` | **Implemented** (Unreachable due to Step 8) |

---

## 4. PDF AND UNIT HANDLING

### PDF Processing & Scanned Page Detection
* **Detection Mechanism (`PageDetector` in `backend/app/services/ocr/page_detector.py:20-43`):**
  - Strategies: `AUTO`, `FORCE`, `SKIP`.
  - In `AUTO` mode, calculates digital character volume per page: `total_chars < char_threshold (50)`.
  - If `< 50` characters, page is flagged for OCR.
* **OCR Execution (`OCRAgent` in `backend/app/agents/ocr_agent.py:195-230`):**
  - Renders page image via PyMuPDF at 300 DPI (`pix = page.get_pixmap(dpi=300)`).
  - Preprocesses image with contrast adjustment/binarization (`preprocess_image_for_ocr`).
  - Calls `TesseractEngine.perform_ocr()` returning word coordinates and confidences.
  - Rebuilds bounding box hierarchy using `OCRLayoutBuilder`.
  - Merges native digital blocks with OCR blocks using intersection-over-area (`merge_native_and_ocr_blocks`), deduplicating text.
* **OCR Fallback & Extraction Failures (`backend/app/agents/ocr_agent.py:196-202`):**
  - If Tesseract is unavailable or fails 3 retry attempts, the agent logs an error, falls back to native text blocks, records `failed_pages_count`, and continues processing without crashing.

### Unit Boundaries vs. Product Goal ("Select Specific Units")
* **Unit Detection in Document Extraction:**
  - `AcademicFeatureEngine` and `AcademicGraphBuilder` classify nodes into `AcademicNodeCategory` (e.g. `CHAPTER`, `SECTION`, `TOPIC`, `CONCEPT`).
  - Users can manually reclassify nodes to `UNIT` via `AcademicReviewPage.tsx` using `CHANGE_CATEGORY`.
* **THE UNIT COMPILATION CONFLICT (`KnowledgeBuilder`):**
  - In `backend/app/services/intelligence/knowledge_builder.py:18-22, 96-98`:
    ```python
    VALID_KNOWLEDGE_CATEGORIES = {
        "CHAPTER", "SECTION", "TOPIC", "CONCEPT", "DEFINITION", 
        "THEOREM", "PROOF", "FORMULA", "ALGORITHM", "EXAMPLE", 
        "EXERCISE", "SUMMARY"
    }
    ...
    if category not in VALID_KNOWLEDGE_CATEGORIES:
        continue
    ```
  - **`UNIT` is explicitly excluded from `VALID_KNOWLEDGE_CATEGORIES`!**
  - Any node categorized as `UNIT` in the approved snapshot is discarded during knowledge graph compilation.
  - As a result, a real compiled `KnowledgeVersion` has **zero** entities of type `UNIT`.
* **The Planner Dependency on Units (`ArtifactPlanner`):**
  - In `backend/app/services/artifact/artifact_planner.py:84-88`:
    ```python
    for entity in version.entities:
        if entity.entity_type == AcademicNodeCategory.UNIT:
            units.append(entity)
    if not units:
        raise ValueError("No academic units found in knowledge version.")
    ```
  - Because `KnowledgeBuilder` filters out `UNIT`, running `ArtifactPlanner` on a real finalized version will **always crash** with `ValueError: No academic units found in knowledge version`.
* **"Number of Units" vs. "Which Units":**
  - **No Unit Selection Mechanism Exists:** In `artifact_planner.py:103-106`:
    ```python
    num_units = job.config.get("num_units")
    if num_units and num_units < len(units):
        units = units[:num_units]
    ```
  - The system only accepts an integer `num_units`. It simply slices the top N units (`units[:num_units]`).
  - A user cannot select specific nonconsecutive units (e.g., "Unit 2 and Unit 4").
  - The UI in `ArtifactWorkspacePage.tsx` only exposes a single number input for `num_units`.

---

## 5. ID AND API CONTRACTS

### Identifier Taxonomy & Relationships
1. **`Document.id` (UUID):** Primary key of the document row in SQLite (`backend/app/models/document.py:11`). Used in frontend routing (`/documents/:id`, `/documents/:id/artifact`).
2. **`Document.upload_id` (UUID):** Upload batch identifier (`backend/app/models/document.py:12`). Indexed, **NOT unique**.
3. **`KnowledgeVersion.id` (UUID):** Primary key of the compiled knowledge graph version (`backend/app/models/knowledge.py:24`).
4. **`KnowledgeVersion.upload_id` (UUID):** Foreign key reference matching `Document.upload_id` (`backend/app/models/knowledge.py:25`).

### Endpoint Contract Verification

#### 1. Create Artifact Job
* **Request (`POST /api/v1/artifacts/generate`):**
  ```json
  {
    "upload_id": "153a94af-05df-4932-b527-610cc441f32f",
    "knowledge_version_id": "f33de2bf-33f8-438c-b299-b612072ebc12",
    "artifact_type": "PPTX",
    "config": {
      "audience_level": "undergraduate",
      "depth": "standard",
      "num_units": 2,
      "include_examples": true,
      "include_questions": true
    }
  }
  ```
* **Validation Guards (`backend/app/services/artifact/artifact_service.py:44-61`):**
  - `KnowledgeVersion` must exist (or 404).
  - `kv.upload_id == request.upload_id` (or 400: `"Knowledge version does not belong to the requested upload_id."`).
  - `kv.status == "FINALIZED"` (or 400: `"Cannot generate artifact from unfinalized knowledge version."`).
* **Expected Response (Status 200):**
  ```json
  {
    "id": "e4f8b912-4c21-4f09-8d76-123456789abc",
    "upload_id": "153a94af-05df-4932-b527-610cc441f32f",
    "knowledge_version_id": "f33de2bf-33f8-438c-b299-b612072ebc12",
    "artifact_type": "PPTX",
    "status": "PENDING",
    "config": { "num_units": 2 },
    "artifact_uri": null,
    "error_message": null,
    "created_at": "2026-09-28T13:45:00",
    "updated_at": "2026-09-28T13:45:00",
    "completed_at": null
  }
  ```
* **Timestamp Format Mismatch Note:**
  - Backend schema `ArtifactJobRead` returns ISO-8601 strings (`created_at: datetime`).
  - Frontend type `ArtifactJobRead` (`frontend/src/types/artifact.ts:33`) declares `created_at: number`.
  - When the frontend previously ran `new Date(job.created_at * 1000)`, multiplying an ISO string by 1000 produced `NaN` ("Invalid Date").

#### 2. Poll Status
* **Endpoint:** `GET /api/v1/artifacts/{job_id}`
* **Returns:** Same `ArtifactJobRead` structure with `status`: `"PENDING" | "PLANNING" | "RENDERING" | "COMPLETED" | "FAILED"`.

#### 3. Download
* **Endpoint:** `GET /api/v1/artifacts/{job_id}/download`
* **Guards:** Returns 400 if `status != COMPLETED`; returns 404 if file does not exist on disk. Returns `FileResponse` with MIME type `application/vnd.openxmlformats-officedocument.presentationml.presentation`.

---

## 6. GENERATION AND PPTX ENGINE

### Pipeline Call Chain (`ArtifactService.run_generation_pipeline`)
```
ArtifactJob (PENDING)
   │
   ▼
ArtifactService transitions status -> PLANNING
   │
   ▼
ArtifactPlanner.plan(job)
   ├─ Queries KnowledgeRepository.get_finalized_version()
   ├─ Slices units[:num_units]
   ├─ Chunks topics (MAX 10 entities per chunk)
   ├─ Calls RetrievalService.retrieve(RetrievalRequest(strategy="LEXICAL"))
   ├─ Builds prompt with explicit node_ids and evidence_ids
   ├─ Calls LLMProvider.generate(SLIDE_FRAGMENT_SCHEMA)
   └─ Validates output against fabrication (source_node_ids, evidence_ids)
   │
   ▼
ArtifactValidator.validate(plan, context)
   ├─ Validates structure (non-empty slides, titles, content)
   ├─ Validates text density (<= 800 chars/slide, <= 7 bullets, <= 250 chars/bullet)
   ├─ Validates config compliance (no EXAMPLE/QUESTION slides if toggled off)
   ├─ Validates academic coverage (all expected units covered)
   └─ Validates evidence grounding (all factual slides cite valid source/evidence)
   │
   ▼
ArtifactService transitions status -> RENDERING
   │
   ▼
PPTXRenderer.render(plan, output_path)
   ├─ Generates 16:9 slides using python-pptx
   ├─ Types: TITLE, CONTENT, CONCEPT, EXAMPLE, QUESTION
   ├─ Formats bullets and text frames with margin constraints
   └─ Writes source_node_ids and evidence_ids into speaker notes for audit provenance
   │
   ▼
ArtifactService transitions status -> COMPLETED (sets artifact_uri and completed_at)
```

### Critical Findings & Implemented vs. Intended Discrepancies
1. **Live Provider vs. Mock:**
   - `_get_provider()` in `backend/app/services/generation/generation_service.py` checks `settings.GROQ_API_KEY`. If set, it returns `GroqProvider`; otherwise, it falls back to `MockProvider`.
   - `GROQ_API_KEY` is configured locally. However, `ArtifactPlanner` has never been executed against Groq in real end-to-end testing.
2. **Planner vs. Validator Unit Mismatch:**
   - In `artifact_planner.py:105`: Units are selected by database collection order: `units = units[:num_units]`.
   - In `artifact_service.py:125`: Expected units are selected by sorting UUIDs alphabetically:
     `sorted_units = sorted(..., key=lambda x: x.id); expected_units = set(u.id for u in sorted_units[:num_units])`.
   - If `num_units < total_units`, the planner plans one subset of units, while the validator expects a **different subset**, causing the validator to reject the plan with `COVERAGE: Missing required unit '...' in the plan`.
3. **Token Limits & Oversized Topics:**
   - Chunks are bounded to 10 entities (`MAX_ENTITIES_PER_CHUNK = 10`), but if a single topic contains more than 10 concepts, the entire chunk can exceed token thresholds without sub-chunking.
4. **Renderer Content Boundaries:**
   - `PPTXRenderer` renders titles, bullets, and speaker notes. It does **not** render tables, diagrams, images, or mathematical equations. Tables and images extracted in Phase 3 are not yet wired into the slide renderer.

---

## 7. MOCKS AND PARALLEL WORKFLOWS

| Route | Page Component | Backed by Real DB / API? | Data Source | Notes |
|---|---|---|---|---|
| `/upload` | `UploadPage.tsx` | **YES** | `POST /api/v1/upload`, `POST /api/v1/jobs` | Real file upload and job creation. |
| `/processing/:jobId` | `ProcessingPage.tsx` | **YES** | `GET /api/v1/jobs/:jobId` | Real polling of background extraction. |
| `/units` | `UnitsPage.tsx` | **NO (100% Mock)** | `mockUnits` hardcoded array (`UnitsPage.tsx:19-74`) | Legacy static mockup for "Computer Networking". Unconnected to uploaded PDF. |
| `/outline` | `OutlinePage.tsx` | **NO (100% Mock)** | `mockOutlines` hardcoded array (`OutlinePage.tsx:16-50`) | Legacy static mockup. |
| `/preview` | `PreviewPage.tsx` | **NO (100% Mock)** | `mockSlides` hardcoded array (`PreviewPage.tsx:17-60`) | Legacy static slide mockup with Unsplash image URLs. |
| `/documents/:id` | `DocumentPreviewPage.tsx` | **YES** | `GET /api/v1/documents/:id/*` | Real database inspector for extracted pages, blocks, tables, images, and stats. |
| `/academic/review/:uploadId` | `AcademicReviewPage.tsx` | **YES** | `GET/POST /api/v1/review/:uploadId/*` | Real human review workspace with OCC revision control and immutable snapshots. |
| `/documents/:id/knowledge` | `KnowledgeExplorerPage.tsx` | **YES** | `GET /api/v1/knowledge/*` | Real relational knowledge graph explorer. |
| `/documents/:id/retrieval` | `RetrievalInspectorPage.tsx` | **YES** | `POST /api/v1/retrieval/query` | Real Phase 7 RAG test bench. |
| `/documents/:id/generation` | `GenerationWorkspacePage.tsx` | **YES** | `POST /api/v1/generation/*` | Real Phase 8 LLM reasoning workbench. |
| `/documents/:id/artifact` | `ArtifactWorkspacePage.tsx` | **YES** | `GET/POST /api/v1/artifacts/*` | Phase 9 slide generation workspace. |

---

## 8. CURRENT FAILURES & ROOT CAUSE ANALYSIS

### Defect 1 (CRITICAL ROOT CAUSE): Foreign Key Mismatch in SQLite `artifact_jobs` Table
* **Steps to Reproduce:**
  1. Have backend running with `./lectureai.db` in `backend/`.
  2. Send `POST /api/v1/artifacts/generate` with valid `upload_id` and `knowledge_version_id`.
* **Expected Result:**
  Row inserted into `artifact_jobs`, returns HTTP 200 with job record in `PENDING` state.
* **Actual Result:**
  FastAPI server crashes with HTTP 500:
  ```text
  sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) foreign key mismatch - "artifact_jobs" referencing "documents"
  [SQL: INSERT INTO artifact_jobs (id, upload_id, knowledge_version_id, artifact_type, status, config, artifact_uri, error_message, created_at, updated_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)]
  ```
* **Root Cause Diagnosis:**
  - The SQLite database table was created from an older schema where `artifact_jobs.upload_id` was declared with `FOREIGN KEY(upload_id) REFERENCES documents(upload_id)`.
  - In SQLite, foreign keys can **only** reference columns that have a `UNIQUE` constraint or are the `PRIMARY KEY`.
  - In `documents`, `id` is the primary key; `upload_id` is merely indexed (`index=True`), not unique.
  - Whenever `INSERT INTO artifact_jobs` executes with SQLite foreign keys enabled, SQLite halts with `foreign key mismatch`.
  - In the Python model (`backend/app/models/artifact.py:15`), the `ForeignKey` was removed from `upload_id`. However, because SQLAlchemy's `create_all()` never alters or drops existing tables, the bad DDL constraint persisted inside `backend/lectureai.db`.

### Defect 2: Real Browser CORS Masking 500 Internal Server Errors
* **Steps to Reproduce:**
  1. Trigger Defect 1 from the browser frontend at `http://localhost:5173`.
* **Observed Browser Error:**
  ```text
  Access to XMLHttpRequest at 'http://localhost:8000/api/v1/artifacts/generate' from origin 'http://localhost:5173' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource.
  ```
* **Root Cause Diagnosis:**
  - In Starlette / FastAPI, when an unhandled server error occurs (such as the SQLite `OperationalError` above), Starlette's `ServerErrorMiddleware` catches the exception and returns a generic 500 plain text response.
  - `ServerErrorMiddleware` is located outside `CORSMiddleware`.
  - Consequently, the 500 response is sent back **without any `Access-Control-Allow-Origin` header**.
  - When the browser sees a 500 response without CORS headers on a cross-origin request, the browser's security layer intercepts it and reports a CORS blockage, completely masking the real 500 database error from the developer console.

### Defect 3: Localhost Origin Mismatch (`localhost` vs `127.0.0.1`)
* **Verification in Code & Execution:**
  - `backend/app/main.py:108` explicitly hardcodes: `allow_origins=["http://localhost:5173"]`.
  - Verified by execution:
    - `OPTIONS /api/v1/artifacts/generate` with `Origin: http://localhost:5173` -> Status 200, returns CORS headers.
    - `OPTIONS /api/v1/artifacts/generate` with `Origin: http://127.0.0.1:5173` -> Status 400, **NO CORS headers**.
  - If the user accesses the Vite app via `http://127.0.0.1:5173`, every API request is rejected by `CORSMiddleware`.

### Defect 4: `startTime` Error Investigation
* **Search Results:** A comprehensive grep across the entire repository for `startTime` returned **zero matches**.
* **Finding:** No variable, function, or property named `startTime` exists in the codebase.
* **Likely Cause:** The error was either an internal browser/devtools performance timing trace, or related to `created_at` timestamp multiplication producing `NaN` in `ArtifactWorkspacePage.tsx`.

---

## 9. VERIFICATION LOGS

### 1. Backend Test Suite (`pytest`)
* **Command:** `python -m pytest tests/test_artifact_api.py tests/test_artifact_orchestration.py tests/test_artifact_planner.py tests/test_artifact_validator.py tests/test_pptx_renderer.py tests/test_cors.py -v`
* **Exit Code:** `0`
* **Result:** **31 passed**, 0 failed, 18 deprecation warnings (Python 3.12+ `datetime.utcnow()` deprecation).
* **Limitations Disclosed:**
  - `test_artifact_orchestration.py` mocks `ArtifactPlanner.plan`.
  - `test_artifact_planner.py` mocks `KnowledgeRepository`, `RetrievalService`, and `LLMProvider`.
  - All artifact tests inject synthetic in-memory databases and synthetic `UNIT` entities, bypassing real `KnowledgeBuilder` and real SQLite schema constraints.

### 2. Frontend Test Suite (`vitest`)
* **Command:** `npm test -- --run`
* **Exit Code:** `0`
* **Result:** **32 passed**, 0 failed (across 5 test files).
* **Files Verified:**
  - `src/pages/__tests__/ArtifactWorkspacePage.test.tsx` (19 passed)
  - `src/pages/__tests__/GenerationWorkspacePage.test.tsx` (4 passed)
  - `src/components/generation/__tests__/ConversationSelector.test.tsx` (4 passed)
  - `src/components/generation/__tests__/ConversationHistoryView.test.tsx` (3 passed)
  - `src/pages/__tests__/AcademicReviewPage.test.tsx` (2 passed)

### 3. Frontend Production Build
* **Command:** `npm run build` (`tsc -b && vite build`)
* **Exit Code:** `0`
* **Result:** Successfully compiled in 383ms. Output bundles generated in `dist/assets/`. Zero TypeScript errors.

### 4. Real Workflow Execution Audit
* **Question:** Has a real `PDF -> Extraction -> Review -> Knowledge Compile -> Real LLM -> Downloaded PPTX` ever run to completion?
* **Answer: NO.**
  - Verified by querying `lectureai.db`: `SELECT COUNT(*) FROM artifact_jobs` returns `0`.
  - The SQLite schema defect and the `KnowledgeBuilder` `UNIT` exclusion filter have prevented any live artifact generation from ever succeeding.

---

## 10. PRIORITISED HANDOFF

### Feature Status Summary
| Component / Feature | Implemented | Partial | Broken | Mock | Unknown | Notes |
|---|:---:|:---:|:---:|:---:|:---:|---|
| PDF Extraction & Layout Parser | ✅ | | | | | PyMuPDF extracts blocks, tables, images, metadata. |
| Scanned PDF OCR Detection | ✅ | | | | | Tesseract auto-detection at 300 DPI with layout merging. |
| Text Normalization Pipeline | ✅ | | | | | 7-stage deterministic normalizer (NFKD, whitespace, hyphen). |
| DocumentGraph & AcademicGraph | ✅ | | | | | Dual-graph representation of layout and pedagogical elements. |
| Human Review & Approval (Phase 5) | ✅ | | | | | OCC revisions, overrides, append-only triggers, snapshots. |
| Knowledge Engine (Phase 6) | | ⚠️ | | | | Relational tables intact, but filters out `UNIT` category. |
| RAG Retrieval Engine (Phase 7) | ✅ | | | | | Lexical search, graph expansion, provenance ranking. |
| AI Reasoning Layer (Phase 8) | ✅ | | | | | Grounding validation, explanation & Q&A modes. |
| Legacy UI Workflow (`/units`, `/outline`, `/preview`) | | | | 🎭 | | Unconnected mock flow from Phase 1 demo. |
| Post-Processing Navigation | | | ❌ | | | `/processing/:id` routes to mock `/units` instead of real review. |
| Artifact Generation UI (Phase 9E) | ✅ | | | | | Controls, polling, and `upload_id` parameter fixed uncommitted. |
| Artifact Backend Schema | | | ❌ | | | `artifact_jobs` table in `backend/lectureai.db` has invalid FK. |
| Unit-Specific Selection (Goal) | | | ❌ | | | System only takes `num_units: int` (slices top N); cannot pick specific nonconsecutive units. |
| PPTX Presentation Renderer | ✅ | | | | | Native 16:9 slides with speaker note provenance citations. |

### Confirmed Defects Ordered by Severity

#### Severity 1 (CRITICAL BLOCKER): SQLite Foreign Key Mismatch on `artifact_jobs`
* **Defect:** `artifact_jobs` table in `backend/lectureai.db` contains `FOREIGN KEY(upload_id) REFERENCES documents(upload_id)`.
* **Impact:** Every `POST /api/v1/artifacts/generate` crashes with 500 `OperationalError`, which Starlette returns without CORS headers, causing the browser to block the request.
* **Repair:** Recreate the `artifact_jobs` table without the invalid `upload_id` foreign key constraint, matching the current Python model.

#### Severity 2 (CRITICAL ARCHITECTURAL CONFLICT): `UNIT` Category Filter in `KnowledgeBuilder`
* **Defect:** `backend/app/services/intelligence/knowledge_builder.py:18-22` excludes `UNIT` from `VALID_KNOWLEDGE_CATEGORIES`.
* **Impact:** Any document approved and compiled produces 0 `UNIT` entities. `ArtifactPlanner.plan()` immediately raises `ValueError: No academic units found in knowledge version`.
* **Repair:** Add `"UNIT"` to `VALID_KNOWLEDGE_CATEGORIES` in `knowledge_builder.py`, or update `ArtifactPlanner` to handle `CHAPTER` / `SECTION` as fallback units.

#### Severity 3 (MAJOR BUG): Planner vs. Validator Expected Unit Discrepancy
* **Defect:** `ArtifactPlanner` selects units by document order (`units[:num_units]`), whereas `ArtifactService` selects expected units for validation by sorting UUID strings (`sorted(..., key=lambda x: x.id)`).
* **Impact:** When `num_units < total_units`, the validator fails with a `COVERAGE` error because the two sets of units do not match.
* **Repair:** Align both to use the same ordering (document reading order).

#### Severity 4 (HIGH DEFECT): Origin Whitelist Rejects `127.0.0.1:5173`
* **Defect:** `backend/app/main.py:108` only allows `http://localhost:5173`.
* **Impact:** If the user opens the frontend at `http://127.0.0.1:5173`, preflight and actual requests fail CORS.
* **Repair:** Add `"http://127.0.0.1:5173"` to `allow_origins`.

#### Severity 5 (PRODUCT GAP): Inability to Select Specific, Nonconsecutive Units
* **Defect:** `ArtifactJobCreate.config` and `ArtifactPlanner` only support `num_units: int`.
* **Impact:** Does not satisfy the user goal: *"chooses specific units—for example Unit 2 and Unit 4."*
* **Repair:** Add `selected_unit_ids: List[str]` to the API contract, update `ArtifactWorkspacePage.tsx` to display unit checkboxes, and update `ArtifactPlanner` to filter `units = [u for u in all_units if u.id in selected_unit_ids]`.

#### Severity 6 (UI WORKFLOW DISCONNECT): Disconnected Pipeline Navigation
* **Defect:** `frontend/src/pages/ProcessingPage.tsx:62` navigates to `/units` when processing completes.
* **Impact:** Diverts users away from the real document into the static mock presentation demo.
* **Repair:** Change `handleContinue` in `ProcessingPage.tsx` to navigate to `/documents/${job.document_id}` or `/academic/review/${job.upload_id}`.

---

### Minimal Recommended Repair Sequence for Subsequent Agent

```
Step 1: Fix Database Schema
  └─ Execute SQLite migration on backend/lectureai.db:
     DROP TABLE IF EXISTS artifact_jobs;
     Create artifact_jobs using Base.metadata.tables["artifact_jobs"].create(bind=engine)
     (Fixes the immediate 500 error and unmasks real backend responses)

Step 2: Fix CORS Whitelist in backend/app/main.py
  └─ Add "http://127.0.0.1:5173" to allow_origins.

Step 3: Enable UNIT in backend/app/services/intelligence/knowledge_builder.py
  └─ Add "UNIT" to VALID_KNOWLEDGE_CATEGORIES.

Step 4: Align Unit Ordering between Planner and Validator
  └─ In backend/app/services/artifact/artifact_service.py:125, remove `key=lambda x: x.id`
     so expected_units matches the planner's document ordering.

Step 5: Implement Specific Unit Selection
  └─ In backend/app/services/artifact/artifact_planner.py:
     Check `selected_unit_ids = job.config.get("selected_unit_ids")`
     Filter units accordingly before planning chunks.
  └─ In frontend/src/pages/ArtifactWorkspacePage.tsx:
     Fetch units from knowledge version, render multi-select checkboxes, and send selected_unit_ids.

Step 6: Reconnect Navigation
  └─ In frontend/src/pages/ProcessingPage.tsx:62:
     navigate(`/documents/${job.document_id}`);
```

---

### Code Excerpts for Immediate Defect Resolution

#### Excerpt A: The Bad DDL in `backend/lectureai.db` (Defect 1)
```sql
-- Existing bad DDL in backend/lectureai.db:
CREATE TABLE artifact_jobs (
    ...
    PRIMARY KEY (id), 
    FOREIGN KEY(upload_id) REFERENCES documents (upload_id), -- <-- FAILS IN SQLITE (upload_id is not unique!)
    FOREIGN KEY(knowledge_version_id) REFERENCES knowledge_versions (id)
);
```

#### Excerpt B: The Category Exclusion in `backend/app/services/intelligence/knowledge_builder.py` (Defect 2)
```python
# Lines 18-22:
VALID_KNOWLEDGE_CATEGORIES = {
    "CHAPTER", "SECTION", "TOPIC", "CONCEPT", "DEFINITION", 
    "THEOREM", "PROOF", "FORMULA", "ALGORITHM", "EXAMPLE", 
    "EXERCISE", "SUMMARY"
    # MISSING: "UNIT"
}
```

#### Excerpt C: Unit Ordering Mismatch in `backend/app/services/artifact/artifact_service.py` (Defect 3)
```python
# Lines 122-126:
num_units = job.config.get("num_units")
if num_units and num_units < len(expected_units):
    # SORTS BY UUID STRING INSTEAD OF DOCUMENT ORDER:
    sorted_units = sorted([e for e in kv.entities if e.entity_type == AcademicNodeCategory.UNIT], key=lambda x: x.id)
    expected_units = set(u.id for u in sorted_units[:num_units])
```
vs `backend/app/services/artifact/artifact_planner.py`:
```python
# Lines 103-105:
num_units = job.config.get("num_units")
if num_units and num_units < len(units):
    # TAKES FIRST N IN NATURAL DATABASE ORDER:
    units = units[:num_units]
```
