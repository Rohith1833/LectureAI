"""
Phase 8F-4 — Golden Benchmark Dataset Fixtures

Curated collection of deterministic evaluation test cases covering all 5 generation modes:
- QA
- EXPLANATION
- SUMMARY
- COMPARISON
- STUDY_GUIDE

Includes grounded, partially grounded, invalid citation, abstention, and malformed scenarios.
"""

from typing import List
from app.schemas.generation import (
    GenerationMode,
    GenerationRequest,
    GenerationResult,
    GenerationClaim,
    GroundingStatus,
    ContextSource,
    ComparisonOptions,
    StudyGuideOptions,
)
from app.schemas.retrieval import RetrievalScope
from app.schemas.evaluation import EvaluationVerdict
from app.services.evaluation.benchmark import EvaluationCase


def make_source(citation_id: str, title: str, content: str) -> ContextSource:
    return ContextSource(
        citation_id=citation_id,
        entity_id=f"ent_{citation_id}",
        title=title,
        entity_type="CONCEPT",
        content=content,
        passage=None,
        provenance="Page 1",
    )


def get_golden_dataset() -> List[EvaluationCase]:
    """Returns the standardized suite of 12 deterministic benchmark evaluation cases."""
    scope = RetrievalScope(document_id="doc_golden", version_id="v_1")

    # 1. Grounded QA
    src_bs = make_source("S1", "Binary Search", "Binary search runs in O(log n) time complexity on sorted arrays.")
    case_1 = EvaluationCase(
        id="case_01_qa_grounded",
        description="Grounded QA response with valid citation and full token support.",
        generation_request=GenerationRequest(query="What is the complexity of binary search?", scope=scope, mode=GenerationMode.QA),
        generation_result=GenerationResult(
            mode=GenerationMode.QA,
            answer="Binary search runs in O(log n) time complexity on sorted arrays [S1].",
            claims=[
                GenerationClaim(claim_id="c1", text="Binary search runs in O(log n) time complexity on sorted arrays.", citation_ids=["S1"], grounding_status=GroundingStatus.SUPPORTED)
            ],
            citations={"S1": src_bs},
            overall_grounding_status=GroundingStatus.SUPPORTED,
            model_metadata={"model": "mock-llm"},
        ),
        context_sources={"S1": src_bs},
        expected_verdict=EvaluationVerdict.PASS,
        tags=["grounded", "qa"],
    )

    # 2. Unsupported QA (Hallucination)
    src_plants = make_source("S1", "Botany", "Photosynthesis converts sunlight into glucose.")
    case_2 = EvaluationCase(
        id="case_02_qa_unsupported",
        description="QA response making an unsupported algorithm claim against botany context.",
        generation_request=GenerationRequest(query="Explain binary search", scope=scope, mode=GenerationMode.QA),
        generation_result=GenerationResult(
            mode=GenerationMode.QA,
            answer="Binary search runs in O(log n) time [S1].",
            claims=[
                GenerationClaim(claim_id="c1", text="Binary search runs in O(log n) time.", citation_ids=["S1"], grounding_status=GroundingStatus.SUPPORTED)
            ],
            citations={"S1": src_plants},
            overall_grounding_status=GroundingStatus.SUPPORTED,
            model_metadata=None,
        ),
        context_sources={"S1": src_plants},
        expected_verdict=EvaluationVerdict.FAIL,
        tags=["unsupported", "qa"],
    )

    # 3. Invalid Citation ID
    case_3 = EvaluationCase(
        id="case_03_qa_invalid_citation",
        description="QA response citing a hallucinated S99 source not in context.",
        generation_request=GenerationRequest(query="What is quicksort?", scope=scope, mode=GenerationMode.QA),
        generation_result=GenerationResult(
            mode=GenerationMode.QA,
            answer="Quicksort is divide and conquer [S99].",
            claims=[
                GenerationClaim(claim_id="c1", text="Quicksort is divide and conquer.", citation_ids=["S99"], grounding_status=GroundingStatus.UNSUPPORTED)
            ],
            citations={"S99": make_source("S99", "Fake", "Fake content")},
            overall_grounding_status=GroundingStatus.PARTIALLY_SUPPORTED,
            model_metadata=None,
        ),
        context_sources={"S1": src_bs},
        expected_verdict=EvaluationVerdict.FAIL,
        tags=["invalid_citation", "qa"],
    )

    # 4. Grounded Explanation
    src_rec = make_source("S1", "Recursion", "Recursion is a method of solving problems where a function calls itself.")
    case_4 = EvaluationCase(
        id="case_04_explanation_grounded",
        description="Grounded explanation of recursion with valid claims and citations.",
        generation_request=GenerationRequest(query="Explain recursion", scope=scope, mode=GenerationMode.EXPLANATION),
        generation_result=GenerationResult(
            mode=GenerationMode.EXPLANATION,
            answer="Recursion is a programming method where a function calls itself to solve smaller subproblems [S1].",
            claims=[
                GenerationClaim(claim_id="c1", text="Recursion is a method where a function calls itself.", citation_ids=["S1"], grounding_status=GroundingStatus.SUPPORTED)
            ],
            citations={"S1": src_rec},
            overall_grounding_status=GroundingStatus.SUPPORTED,
            model_metadata=None,
        ),
        context_sources={"S1": src_rec},
        expected_verdict=EvaluationVerdict.PASS,
        tags=["grounded", "explanation"],
    )

    # 5. Grounded Summary
    src_sorts = make_source("S1", "Sorting Algorithms", "Sorting algorithms arrange elements in a list in a specific order.")
    case_5 = EvaluationCase(
        id="case_05_summary_grounded",
        description="Grounded summary of sorting algorithms.",
        generation_request=GenerationRequest(query="Summarize sorting algorithms", scope=scope, mode=GenerationMode.SUMMARY),
        generation_result=GenerationResult(
            mode=GenerationMode.SUMMARY,
            answer="Sorting algorithms arrange elements in lists into specified orders [S1].",
            claims=[
                GenerationClaim(claim_id="c1", text="Sorting algorithms arrange elements in lists in specified order.", citation_ids=["S1"], grounding_status=GroundingStatus.SUPPORTED)
            ],
            citations={"S1": src_sorts},
            overall_grounding_status=GroundingStatus.SUPPORTED,
            model_metadata=None,
        ),
        context_sources={"S1": src_sorts},
        expected_verdict=EvaluationVerdict.PASS,
        tags=["grounded", "summary"],
    )

    # 6. Valid Abstention on Empty Context
    case_6 = EvaluationCase(
        id="case_06_abstention_valid",
        description="Accurate model abstention when context is completely empty.",
        generation_request=GenerationRequest(query="What is quantum entanglement?", scope=scope, mode=GenerationMode.QA),
        generation_result=GenerationResult(
            mode=GenerationMode.QA,
            answer="INSUFFICIENT_CONTEXT",
            claims=[],
            citations={},
            overall_grounding_status=GroundingStatus.INSUFFICIENT_CONTEXT,
            model_metadata=None,
        ),
        context_sources={},
        expected_verdict=EvaluationVerdict.PASS,
        tags=["abstention", "qa"],
    )

    # 7. Failed Abstention on Empty Context (Fabrication)
    case_7 = EvaluationCase(
        id="case_07_abstention_failed",
        description="Model hallucinates a substantive answer despite having empty context.",
        generation_request=GenerationRequest(query="What is quantum entanglement?", scope=scope, mode=GenerationMode.QA),
        generation_result=GenerationResult(
            mode=GenerationMode.QA,
            answer="Quantum entanglement is a physical phenomenon where particles remain connected regardless of distance.",
            claims=[
                GenerationClaim(claim_id="c1", text="Particles remain connected regardless of distance.", citation_ids=[], grounding_status=GroundingStatus.UNSUPPORTED)
            ],
            citations={},
            overall_grounding_status=GroundingStatus.UNSUPPORTED,
            model_metadata=None,
        ),
        context_sources={},
        expected_verdict=EvaluationVerdict.FAIL,
        tags=["abstention", "hallucination"],
    )

    # 8. Grounded Comparison
    src_comp = make_source("S1", "Sort Comparison", "Merge sort is guaranteed O(n log n). Quick sort is O(n log n) average but O(n^2) worst case.")
    comparison_dict = {
        "title": "Merge Sort vs Quick Sort Comparison",
        "subjects": ["Merge Sort", "Quick Sort"],
        "comparison_table": [
            {
                "dimension": "Time Complexity",
                "values": [
                    {"subject": "Merge Sort", "value": "O(n log n) [S1]", "citation_ids": ["S1"]},
                    {"subject": "Quick Sort", "value": "O(n log n) average [S1]", "citation_ids": ["S1"]},
                ],
                "explanation": "Merge sort guarantees logarithmic time.",
            }
        ],
        "similarities": [{"text": "Both are divide and conquer [S1].", "citation_ids": ["S1"]}],
        "differences": [{"text": "Merge sort requires additional memory [S1].", "citation_ids": ["S1"]}],
    }
    case_8 = EvaluationCase(
        id="case_08_comparison_grounded",
        description="Complete and grounded Comparison output.",
        generation_request=GenerationRequest(
            query="Compare Merge Sort and Quick Sort",
            scope=scope,
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(subjects=["Merge Sort", "Quick Sort"], dimensions=["Time Complexity"]),
        ),
        generation_result=GenerationResult(
            mode=GenerationMode.COMPARISON,
            answer="Comparison Overview",
            claims=[],
            citations={"S1": src_comp},
            overall_grounding_status=GroundingStatus.SUPPORTED,
            model_metadata=None,
            structured_output=comparison_dict,
        ),
        context_sources={"S1": src_comp},
        expected_verdict=EvaluationVerdict.PASS,
        tags=["grounded", "comparison"],
    )

    # 9. Comparison Missing Subject
    comp_missing = {
        "title": "Comparison",
        "subjects": ["Merge Sort"],  # Missing Quick Sort
        "comparison_table": [
            {
                "dimension": "Time Complexity",
                "values": [{"subject": "Merge Sort", "value": "O(n log n)", "citation_ids": []}],
            }
        ],
        "similarities": [],
        "differences": [],
    }
    case_9 = EvaluationCase(
        id="case_09_comparison_missing_subject",
        description="Comparison missing one of the explicitly requested subjects.",
        generation_request=GenerationRequest(
            query="Compare sorts",
            scope=scope,
            mode=GenerationMode.COMPARISON,
            comparison_options=ComparisonOptions(subjects=["Merge Sort", "Quick Sort"]),
        ),
        generation_result=GenerationResult(
            mode=GenerationMode.COMPARISON,
            answer="Comparison",
            claims=[],
            citations={},
            overall_grounding_status=GroundingStatus.UNSUPPORTED,
            model_metadata=None,
            structured_output=comp_missing,
        ),
        context_sources={"S1": src_comp},
        expected_verdict=EvaluationVerdict.FAIL,
        tags=["comparison", "coverage_failure"],
    )

    # 10. Grounded Study Guide
    src_study = make_source("S1", "Trees", "A binary search tree is a rooted binary tree with ordered keys.")
    study_dict = {
        "title": "Binary Search Trees Study Guide",
        "answer": "Overview of Binary Search Trees data structure [S1].",
        "key_concepts": [{"concept": "Binary Search Tree", "definition": "Rooted binary tree with ordered keys [S1].", "citation_ids": ["S1"]}],
        "learning_objectives": ["Understand tree ordering property [S1]."],
        "review_questions": [
            {"question": f"Question {i+1} about BST?", "answer": f"Answer {i+1}", "explanation": "Explanation", "citation_ids": ["S1"]}
            for i in range(3)
        ],
    }
    case_10 = EvaluationCase(
        id="case_10_study_guide_grounded",
        description="Complete and grounded Study Guide with 3 review questions.",
        generation_request=GenerationRequest(
            query="Create study guide for binary search trees",
            scope=scope,
            mode=GenerationMode.STUDY_GUIDE,
            study_options=StudyGuideOptions(question_count=3, difficulty="basic"),
        ),
        generation_result=GenerationResult(
            mode=GenerationMode.STUDY_GUIDE,
            answer="Overview",
            claims=[],
            citations={"S1": src_study},
            overall_grounding_status=GroundingStatus.SUPPORTED,
            model_metadata=None,
            structured_output=study_dict,
        ),
        context_sources={"S1": src_study},
        expected_verdict=EvaluationVerdict.PASS,
        tags=["grounded", "study_guide"],
    )

    # 11. Study Guide Missing Questions
    study_missing = {
        "title": "Incomplete Guide",
        "answer": "Overview text",
        "key_concepts": [],
        "learning_objectives": [],
        "review_questions": [],  # Empty
    }
    case_11 = EvaluationCase(
        id="case_11_study_guide_missing_questions",
        description="Study guide output containing zero review questions when 5 were requested.",
        generation_request=GenerationRequest(
            query="Study guide",
            scope=scope,
            mode=GenerationMode.STUDY_GUIDE,
            study_options=StudyGuideOptions(question_count=5, difficulty="intermediate"),
        ),
        generation_result=GenerationResult(
            mode=GenerationMode.STUDY_GUIDE,
            answer="Overview",
            claims=[],
            citations={},
            overall_grounding_status=GroundingStatus.UNSUPPORTED,
            model_metadata=None,
            structured_output=study_missing,
        ),
        context_sources={"S1": src_study},
        expected_verdict=EvaluationVerdict.FAIL,
        tags=["study_guide", "missing_questions"],
    )

    # 12. Structural Malformed (Empty Answer)
    case_12 = EvaluationCase(
        id="case_12_structural_malformed",
        description="QA generation with blank answer string violating structural contract.",
        generation_request=GenerationRequest(query="What is hashing?", scope=scope, mode=GenerationMode.QA),
        generation_result=GenerationResult(
            mode=GenerationMode.QA,
            answer="   ",  # Blank
            claims=[],
            citations={},
            overall_grounding_status=GroundingStatus.UNSUPPORTED,
            model_metadata=None,
        ),
        context_sources={},
        expected_verdict=EvaluationVerdict.FAIL,
        tags=["malformed", "structural"],
    )

    return [
        case_1, case_2, case_3, case_4, case_5, case_6,
        case_7, case_8, case_9, case_10, case_11, case_12,
    ]
