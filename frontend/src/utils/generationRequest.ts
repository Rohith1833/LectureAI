import type {
  GenerationMode,
  GenerationRequest,
  ComparisonOptions,
  StudyGuideOptions,
} from "@/types/generation";

export interface WorkspaceFormState {
  mode: GenerationMode;
  query: string;
  selectedVersionId: string | null;
  conversationId: string | null;
  temperature: number;
  topK: number;
  includeRelationships: boolean;
  includeEvidence: boolean;
  includePassages: boolean;
  comparisonSubjects: string[];
  comparisonDimensions: string;
  studyQuestionCount: number;
  studyDifficulty: "basic" | "intermediate" | "advanced";
}

export interface ValidationResult {
  isValid: boolean;
  errorMessage: string | null;
}

/**
 * Validates the form state for client-side submission readiness.
 */
export function validateGenerationForm(
  state: WorkspaceFormState,
  documentId?: string | null
): ValidationResult {
  if (!documentId) {
    return { isValid: false, errorMessage: "Document ID is required." };
  }

  const trimmedQuery = state.query.trim();

  // For Comparison mode, query may be auto-composed or user provided, but subjects are strictly required
  if (state.mode === "COMPARISON") {
    const validSubjects = state.comparisonSubjects
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    if (validSubjects.length < 2) {
      return {
        isValid: false,
        errorMessage: "At least 2 non-empty subjects are required for comparison.",
      };
    }
    if (validSubjects.length > 4) {
      return {
        isValid: false,
        errorMessage: "A maximum of 4 subjects can be compared at once.",
      };
    }
    // If query is empty, allow auto-composing from subjects during submission or require non-empty
    if (!trimmedQuery) {
      return {
        isValid: false,
        errorMessage: "Please enter a comparison prompt or query.",
      };
    }
  } else if (!trimmedQuery) {
    return {
      isValid: false,
      errorMessage: "Please enter a question or topic prompt.",
    };
  }

  // Study Guide validation
  if (state.mode === "STUDY_GUIDE") {
    if (
      !Number.isInteger(state.studyQuestionCount) ||
      state.studyQuestionCount < 1 ||
      state.studyQuestionCount > 10
    ) {
      return {
        isValid: false,
        errorMessage: "Question count must be an integer between 1 and 10.",
      };
    }
    if (!["basic", "intermediate", "advanced"].includes(state.studyDifficulty)) {
      return {
        isValid: false,
        errorMessage: "Difficulty must be 'basic', 'intermediate', or 'advanced'.",
      };
    }
  }

  // Temperature & Top-K validation
  if (state.temperature < 0.0 || state.temperature > 1.0) {
    return {
      isValid: false,
      errorMessage: "Temperature must be between 0.0 and 1.0.",
    };
  }
  if (state.topK < 5 || state.topK > 20) {
    return {
      isValid: false,
      errorMessage: "Top-K must be between 5 and 20.",
    };
  }

  return { isValid: true, errorMessage: null };
}

/**
 * Pure utility to build a GenerationRequest from workspace state.
 * Enforces strict mode isolation: comparison_options is only present for COMPARISON,
 * and study_options is only present for STUDY_GUIDE.
 */
export function buildGenerationRequest(
  state: WorkspaceFormState,
  documentId: string
): GenerationRequest {
  const request: GenerationRequest = {
    query: state.query.trim(),
    scope: {
      document_id: documentId,
      version_id: state.selectedVersionId || null,
      entity_types: null,
      relationship_types: null,
    },
    mode: state.mode,
    retrieval_options: {
      top_k: state.topK,
      include_relationships: state.includeRelationships,
      include_evidence: state.includeEvidence,
      include_passages: state.includePassages,
      relationship_depth: 1,
      strategy: "LEXICAL",
    },
    generation_options: {
      temperature: state.temperature,
      output_format: "JSON",
    },
    conversation_id: state.conversationId || null,
    comparison_options: null,
    study_options: null,
    conversation_context: null,
  };

  if (state.mode === "COMPARISON") {
    const validSubjects = state.comparisonSubjects
      .map((s) => s.trim())
      .filter((s) => s.length > 0);

    const parsedDimensions = state.comparisonDimensions
      ? state.comparisonDimensions
          .split(",")
          .map((d) => d.trim())
          .filter((d) => d.length > 0)
      : null;

    const compOpts: ComparisonOptions = {
      subjects: validSubjects,
      dimensions: parsedDimensions && parsedDimensions.length > 0 ? parsedDimensions : null,
    };
    request.comparison_options = compOpts;
  } else if (state.mode === "STUDY_GUIDE") {
    const studyOpts: StudyGuideOptions = {
      question_count: state.studyQuestionCount,
      difficulty: state.studyDifficulty,
    };
    request.study_options = studyOpts;
  }

  return request;
}
