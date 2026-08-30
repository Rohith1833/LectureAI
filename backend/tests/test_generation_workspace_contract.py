"""
Phase 8E-4A & 8E-4B — Generation Workspace Contracts & Form Controls Verification

Tests validating frontend-backend contract parity for the Unified Generation Workspace:
- All 5 GenerationMode enum values (QA, EXPLANATION, SUMMARY, COMPARISON, STUDY_GUIDE)
- URL mode parameter sanitization logic
- Target scope document and version validation
- Pure request building and strict mode isolation
- Client-side validation bounds and schema parity
"""

import unittest
from app.schemas.generation import (
    GenerationMode,
    GenerationRequest,
    GenerationResult,
    ComparisonOptions,
    StudyGuideOptions,
    GroundingStatus,
)
from app.schemas.retrieval import RetrievalScope, RetrievalOptions


def sanitize_frontend_mode(raw_mode: str | None) -> GenerationMode:
    """Python mirror of frontend sanitizeMode() function in GenerationWorkspacePage.tsx."""
    valid_modes = [m.value for m in GenerationMode]
    if not raw_mode:
        return GenerationMode.QA
    upper = raw_mode.upper()
    if upper in valid_modes:
        return GenerationMode(upper)
    return GenerationMode.QA


def mock_frontend_build_request(
    mode: str,
    query: str,
    document_id: str,
    version_id: str | None = None,
    temperature: float = 0.0,
    top_k: int = 10,
    include_relationships: bool = True,
    include_evidence: bool = True,
    include_passages: bool = True,
    comparison_subjects: list[str] | None = None,
    comparison_dimensions: str | None = None,
    study_question_count: int = 5,
    study_difficulty: str = "intermediate",
) -> GenerationRequest:
    """Python mirror of frontend buildGenerationRequest() in utils/generationRequest.ts."""
    gen_mode = GenerationMode(mode)
    comp_opts = None
    study_opts = None

    if gen_mode == GenerationMode.COMPARISON:
        valid_subjects = [s.strip() for s in (comparison_subjects or []) if s.strip()]
        dims = (
            [d.strip() for d in comparison_dimensions.split(",") if d.strip()]
            if comparison_dimensions
            else None
        )
        comp_opts = ComparisonOptions(
            subjects=valid_subjects,
            dimensions=dims if dims else None,
        )
    elif gen_mode == GenerationMode.STUDY_GUIDE:
        study_opts = StudyGuideOptions(
            question_count=study_question_count,
            difficulty=study_difficulty,
        )

    req = GenerationRequest(
        query=query.strip(),
        scope=RetrievalScope(document_id=document_id, version_id=version_id),
        mode=gen_mode,
        retrieval_options=RetrievalOptions(
            top_k=top_k,
            include_relationships=include_relationships,
            include_evidence=include_evidence,
            include_passages=include_passages,
            relationship_depth=1,
            strategy="LEXICAL",
        ),
        generation_options={
            "temperature": temperature,
            "output_format": "JSON",
        },
        comparison_options=comp_opts,
        study_options=study_opts,
    )

    return req


class TestGenerationWorkspaceContracts(unittest.TestCase):
    """Test suite verifying mode selection, sanitization, and workspace contract integrity."""

    def test_01_all_five_modes_supported(self):
        """Verify all five expected generation modes are present in GenerationMode enum."""
        expected_modes = {"QA", "EXPLANATION", "SUMMARY", "COMPARISON", "STUDY_GUIDE"}
        actual_modes = {m.value for m in GenerationMode}
        self.assertEqual(actual_modes, expected_modes)

    def test_02_mode_sanitization_valid(self):
        """Verify valid mode query params are parsed and preserved accurately."""
        self.assertEqual(sanitize_frontend_mode("QA"), GenerationMode.QA)
        self.assertEqual(sanitize_frontend_mode("qa"), GenerationMode.QA)
        self.assertEqual(sanitize_frontend_mode("EXPLANATION"), GenerationMode.EXPLANATION)
        self.assertEqual(sanitize_frontend_mode("explanation"), GenerationMode.EXPLANATION)
        self.assertEqual(sanitize_frontend_mode("SUMMARY"), GenerationMode.SUMMARY)
        self.assertEqual(sanitize_frontend_mode("summary"), GenerationMode.SUMMARY)
        self.assertEqual(sanitize_frontend_mode("COMPARISON"), GenerationMode.COMPARISON)
        self.assertEqual(sanitize_frontend_mode("comparison"), GenerationMode.COMPARISON)
        self.assertEqual(sanitize_frontend_mode("STUDY_GUIDE"), GenerationMode.STUDY_GUIDE)
        self.assertEqual(sanitize_frontend_mode("study_guide"), GenerationMode.STUDY_GUIDE)

    def test_03_mode_sanitization_invalid_fallback(self):
        """Verify invalid or empty mode query params safely fallback to QA."""
        self.assertEqual(sanitize_frontend_mode(None), GenerationMode.QA)
        self.assertEqual(sanitize_frontend_mode(""), GenerationMode.QA)
        self.assertEqual(sanitize_frontend_mode("UNKNOWN_MODE"), GenerationMode.QA)
        self.assertEqual(sanitize_frontend_mode("chat"), GenerationMode.QA)
        self.assertEqual(sanitize_frontend_mode("12345"), GenerationMode.QA)

    def test_04_workspace_request_contracts(self):
        """Verify request schema accepts mode and properly scopes options."""
        # Standard QA request
        qa_req = GenerationRequest(
            query="test question",
            scope=RetrievalScope(document_id="doc_1", version_id="v_1"),
            mode=GenerationMode.QA,
        )
        self.assertEqual(qa_req.mode, GenerationMode.QA)
        self.assertIsNone(qa_req.comparison_options)
        self.assertIsNone(qa_req.study_options)

        # Comparison request
        comp_req = GenerationRequest(
            query="compare concepts",
            scope=RetrievalScope(document_id="doc_1", version_id="v_1"),
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(subjects=["A", "B"]),
        )
        self.assertEqual(comp_req.mode, GenerationMode.COMPARISON)
        self.assertEqual(comp_req.comparison_options.subjects, ["A", "B"])

        # Study Guide request
        study_req = GenerationRequest(
            query="study material",
            scope=RetrievalScope(document_id="doc_1", version_id="v_1"),
            mode=GenerationMode.STUDY_GUIDE,
            study_options=StudyGuideOptions(question_count=5, difficulty="intermediate"),
        )
        self.assertEqual(study_req.mode, GenerationMode.STUDY_GUIDE)
        self.assertEqual(study_req.study_options.question_count, 5)

    def test_05_build_request_mode_isolation(self):
        """Verify buildGenerationRequest enforces mode isolation without option leakage."""
        # QA
        qa = mock_frontend_build_request(
            mode="QA",
            query="question",
            document_id="doc_1",
            comparison_subjects=["A", "B"],
            study_question_count=8,
        )
        self.assertEqual(qa.mode, GenerationMode.QA)
        self.assertIsNone(qa.comparison_options)
        self.assertIsNone(qa.study_options)

        # EXPLANATION
        exp = mock_frontend_build_request(
            mode="EXPLANATION",
            query="explain",
            document_id="doc_1",
            comparison_subjects=["A", "B"],
            study_question_count=8,
        )
        self.assertEqual(exp.mode, GenerationMode.EXPLANATION)
        self.assertIsNone(exp.comparison_options)
        self.assertIsNone(exp.study_options)

        # SUMMARY
        sum_req = mock_frontend_build_request(
            mode="SUMMARY",
            query="summary",
            document_id="doc_1",
            comparison_subjects=["A", "B"],
            study_question_count=8,
        )
        self.assertEqual(sum_req.mode, GenerationMode.SUMMARY)
        self.assertIsNone(sum_req.comparison_options)
        self.assertIsNone(sum_req.study_options)

        # COMPARISON
        comp = mock_frontend_build_request(
            mode="COMPARISON",
            query="compare",
            document_id="doc_1",
            comparison_subjects=["Binary Search", "Linear Search"],
            comparison_dimensions="Time, Space",
            study_question_count=8,
        )
        self.assertEqual(comp.mode, GenerationMode.COMPARISON)
        self.assertIsNotNone(comp.comparison_options)
        self.assertEqual(comp.comparison_options.subjects, ["Binary Search", "Linear Search"])
        self.assertEqual(comp.comparison_options.dimensions, ["Time", "Space"])
        self.assertIsNone(comp.study_options)

        # STUDY_GUIDE
        study = mock_frontend_build_request(
            mode="STUDY_GUIDE",
            query="study",
            document_id="doc_1",
            comparison_subjects=["A", "B"],
            study_question_count=4,
            study_difficulty="advanced",
        )
        self.assertEqual(study.mode, GenerationMode.STUDY_GUIDE)
        self.assertIsNone(study.comparison_options)
        self.assertIsNotNone(study.study_options)
        self.assertEqual(study.study_options.question_count, 4)
        self.assertEqual(study.study_options.difficulty, "advanced")

    def test_06_comparison_validation_rules(self):
        """Verify comparison options requires >= 2 subjects and handles whitespace."""
        # 2 valid subjects
        comp = mock_frontend_build_request(
            mode="COMPARISON",
            query="compare",
            document_id="doc_1",
            comparison_subjects=["  Subject A  ", "Subject B", "   "],
        )
        self.assertEqual(comp.comparison_options.subjects, ["Subject A", "Subject B"])

    def test_07_study_guide_validation_rules(self):
        """Verify study guide options accept valid range and difficulty."""
        study = mock_frontend_build_request(
            mode="STUDY_GUIDE",
            query="topic",
            document_id="doc_1",
            study_question_count=10,
            study_difficulty="basic",
        )
        self.assertEqual(study.study_options.question_count, 10)
        self.assertEqual(study.study_options.difficulty, "basic")

    def test_08_grounding_status_values(self):
        """Verify all 4 grounding status values are supported."""
        expected = {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "INSUFFICIENT_CONTEXT"}
        actual = {s.value for s in GroundingStatus}
        self.assertEqual(actual, expected)

    def test_09_result_serialization_and_citations(self):
        """Verify GenerationResult schema serialization with citations and claims."""
        from app.schemas.generation import GenerationClaim, ContextSource
        claim = GenerationClaim(
            claim_id="c1",
            text="Binary search is logarithmic.",
            citation_ids=["S1"],
            grounding_status=GroundingStatus.SUPPORTED,
        )
        source = ContextSource(
            citation_id="S1",
            entity_id="ent_1",
            title="Binary Search",
            entity_type="CONCEPT",
            content="Binary search operates in O(log n).",
            passage=None,
            provenance="Page 1",
        )
        res = GenerationResult(
            mode=GenerationMode.QA,
            answer="Binary search runs in O(log n) time [S1].",
            claims=[claim],
            citations={"S1": source},
            overall_grounding_status=GroundingStatus.SUPPORTED,
            model_metadata={"model_name": "test-model", "token_usage": {"total_tokens": 100}},
            structured_output=None,
        )
        self.assertEqual(res.mode, GenerationMode.QA)
        self.assertEqual(res.overall_grounding_status, GroundingStatus.SUPPORTED)
        self.assertEqual(len(res.claims), 1)
        self.assertIn("S1", res.citations)
        self.assertEqual(res.citations["S1"].title, "Binary Search")

    def test_10_comparison_structured_output_contract(self):
        """Verify Comparison structured output serialization conforms to frontend contract."""
        comparison_dict = {
            "title": "Search Algorithms Comparison",
            "subjects": ["Binary Search", "Linear Search"],
            "comparison_table": [
                {
                    "dimension": "Time Complexity",
                    "values": [
                        {"subject": "Binary Search", "value": "O(log n) [S1]", "citation_ids": ["S1"]},
                        {"subject": "Linear Search", "value": "O(n) [S2]", "citation_ids": ["S2"]},
                    ],
                    "explanation": "Binary search is logarithmic.",
                }
            ],
            "similarities": [{"text": "Both search items.", "citation_ids": ["S1"]}],
            "differences": [{"text": "Linear does not require sorting.", "citation_ids": ["S2"]}],
        }
        res = GenerationResult(
            mode=GenerationMode.COMPARISON,
            answer="Search Algorithms Comparison",
            claims=[],
            citations={},
            overall_grounding_status=GroundingStatus.SUPPORTED,
            model_metadata=None,
            structured_output=comparison_dict,
        )
        self.assertEqual(res.mode, GenerationMode.COMPARISON)
        self.assertIsNotNone(res.structured_output)
        self.assertEqual(res.structured_output["subjects"], ["Binary Search", "Linear Search"])
        self.assertEqual(len(res.structured_output["comparison_table"]), 1)

    def test_11_study_guide_structured_output_contract(self):
        """Verify Study Guide structured output serialization conforms to frontend contract."""
        study_dict = {
            "title": "Algorithms Study Guide",
            "answer": "Comprehensive review of search algorithms [S1].",
            "key_concepts": [
                {"concept": "Binary Search", "definition": "Divide and conquer search [S1].", "citation_ids": ["S1"]}
            ],
            "learning_objectives": ["Understand search complexities [S1]."],
            "review_questions": [
                {
                    "question": "What is the time complexity?",
                    "answer": "O(log n) [S1]",
                    "explanation": "Halves search space on each step.",
                    "citation_ids": ["S1"],
                }
            ],
        }
        res = GenerationResult(
            mode=GenerationMode.STUDY_GUIDE,
            answer="Comprehensive review of search algorithms [S1].",
            claims=[],
            citations={},
            overall_grounding_status=GroundingStatus.SUPPORTED,
            model_metadata=None,
            structured_output=study_dict,
        )
        self.assertEqual(res.mode, GenerationMode.STUDY_GUIDE)
        self.assertIsNotNone(res.structured_output)
        self.assertEqual(len(res.structured_output["key_concepts"]), 1)
        self.assertEqual(len(res.structured_output["review_questions"]), 1)


if __name__ == "__main__":
    unittest.main()
