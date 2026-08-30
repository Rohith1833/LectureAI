import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";

/**
 * Compatibility redirect:
 * Redirects legacy /documents/:id/qa routes to the unified Generation Workspace at
 * /documents/:id/generation?mode=QA
 */
export default function QnAPage() {
  const { id: documentId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  useEffect(() => {
    if (documentId) {
      navigate(`/documents/${documentId}/generation?mode=QA`, { replace: true });
    } else {
      navigate("/", { replace: true });
    }
  }, [documentId, navigate]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] gap-3">
      <div className="size-8 border-4 border-violet-600 border-t-transparent rounded-full animate-spin" />
      <p className="text-sm text-muted-foreground animate-pulse">
        Redirecting to Generation Workspace...
      </p>
    </div>
  );
}
