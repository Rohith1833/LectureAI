import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getReviewSummary,
  getAcademicGraph,
  getAcademicNode,
  applyReviewAction,
  getReconciliation,
  getAuditHistory,
  getApprovalReadiness,
  approveGraph
} from "../services/reviewService";
import type {
  NodeReviewState,
  AcademicNode,
  ApprovedSnapshotInfo
} from "../types/review";
import {
  ArrowLeft,
  Check,
  Plus,
  Search,
  AlertTriangle,
  History,
  Folder,
  FileText,
  RefreshCw,
  GitBranch,
  Settings,
  ChevronRight,
  ChevronDown,
  Shield,
  Award,
  User,
  Calendar
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { InfoCard } from "@/components/ui/card";

// Valid categories list matching backend
const VALID_CATEGORIES = [
  "UNIT",
  "CHAPTER",
  "SECTION",
  "TOPIC",
  "DEFINITION",
  "THEOREM",
  "PROOF",
  "FORMULA",
  "ALGORITHM",
  "EXAMPLE",
  "EXERCISE",
  "SUMMARY"
];

export default function AcademicReviewPage() {
  const { uploadId } = useParams<{ uploadId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Selected Node State
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Filters State
  const [searchTerm, setSearchTerm] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [reviewStateFilter, setReviewStateFilter] = useState<string>("");
  const [lowConfidenceFilter, setLowConfidenceFilter] = useState<boolean | null>(null);
  const [orphanFilter, setOrphanFilter] = useState<boolean | null>(null);

  // Tab State for bottom pane
  const [activeBottomTab, setActiveBottomTab] = useState<"audit" | "reconciliation" | "history">("audit");

  // Local Edits State for the Node Detail form (preserves edits on OCC conflict)
  const [localTitle, setLocalTitle] = useState("");
  const [localCategory, setLocalCategory] = useState("");
  const [localParentId, setLocalParentId] = useState("");
  const [mutationComment, setMutationComment] = useState("");

  // Create Node Modal State
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newCategory, setNewCategory] = useState("TOPIC");
  const [newParentId, setNewParentId] = useState("");

  // OCC Conflict State
  const [occError, setOccError] = useState<string | null>(null);

  // Approval Modal States
  const [showApprovalConfirm, setShowApprovalConfirm] = useState(false);
  const [approvalSuccess, setApprovalSuccess] = useState<ApprovedSnapshotInfo | null>(null);

  // 1. Fetch Review Summary
  const summaryQuery = useQuery({
    queryKey: ["reviewSummary", uploadId],
    queryFn: () => getReviewSummary(uploadId!),
    enabled: !!uploadId
  });

  const currentRevision = summaryQuery.data?.resolved_graph_version ?? 0;

  // 2. Fetch Resolved Academic Graph (Tree representation)
  const graphQuery = useQuery({
    queryKey: [
      "academicGraph",
      uploadId,
      categoryFilter,
      reviewStateFilter,
      lowConfidenceFilter,
      orphanFilter
    ],
    queryFn: () =>
      getAcademicGraph(uploadId!, {
        category: categoryFilter || undefined,
        reviewState: reviewStateFilter || undefined,
        lowConfidence: lowConfidenceFilter ?? undefined,
        orphan: orphanFilter ?? undefined,
        limit: 500
      }),
    enabled: !!uploadId
  });

  // 3. Fetch Selected Node Details
  const nodeDetailsQuery = useQuery({
    queryKey: ["nodeDetails", uploadId, selectedNodeId],
    queryFn: () => getAcademicNode(uploadId!, selectedNodeId!),
    enabled: !!uploadId && !!selectedNodeId
  });

  // 4. Fetch Reconciliation details
  const reconQuery = useQuery({
    queryKey: ["reconciliation", uploadId],
    queryFn: () => getReconciliation(uploadId!),
    enabled: !!uploadId
  });

  // 5. Fetch Full Audit history
  const auditQuery = useQuery({
    queryKey: ["auditHistory", uploadId],
    queryFn: () => getAuditHistory(uploadId!),
    enabled: !!uploadId
  });

  // 6. Fetch Approval Readiness Evaluation Checklist
  const readinessQuery = useQuery({
    queryKey: ["approvalReadiness", uploadId],
    queryFn: () => getApprovalReadiness(uploadId!),
    enabled: !!uploadId
  });

  // Keep local edits in sync when selected node changes
  useEffect(() => {
    if (nodeDetailsQuery.data) {
      setLocalTitle(nodeDetailsQuery.data.title);
      setLocalCategory(nodeDetailsQuery.data.category);
      setLocalParentId(nodeDetailsQuery.data.parent_id || "");
      setMutationComment("");
      setOccError(null);
    }
  }, [nodeDetailsQuery.data]);

  // Mutation: Apply review actions (OCC revision verification handled in service)
  const applyActionMutation = useMutation({
    mutationFn: (params: { action_type: string; payload: Record<string, any> }) =>
      applyReviewAction(uploadId!, {
        action_type: params.action_type,
        payload: params.payload,
        expected_version: currentRevision,
        comment: mutationComment || undefined
      }),
    onSuccess: () => {
      // Invalidate and refetch all data queries
      queryClient.invalidateQueries({ queryKey: ["reviewSummary", uploadId] });
      queryClient.invalidateQueries({ queryKey: ["academicGraph", uploadId] });
      queryClient.invalidateQueries({ queryKey: ["reconciliation", uploadId] });
      queryClient.invalidateQueries({ queryKey: ["auditHistory", uploadId] });
      if (selectedNodeId) {
        queryClient.invalidateQueries({ queryKey: ["nodeDetails", uploadId, selectedNodeId] });
      }
      setMutationComment("");
      setOccError(null);
    },
    onError: (error: any) => {
      // Check for OCC Conflict (HTTP 409)
      if (error?.response?.status === 409) {
        setOccError(
          error.response.data?.message ||
            "Optimistic Concurrency Control conflict. The document was modified by another session. Please review differences below."
        );
        // Invalidate summary to pull latest revision number
        queryClient.invalidateQueries({ queryKey: ["reviewSummary", uploadId] });
      } else {
        alert(error?.response?.data?.message || "Action mutation failed. Please verify graph constraints.");
      }
    }
  });

  // Mutation: Approve resolved AcademicGraph snapshots
  const approveGraphMutation = useMutation({
    mutationFn: () => approveGraph(uploadId!, currentRevision),
    onSuccess: (data: any) => {
      // Invalidate queries
      queryClient.invalidateQueries({ queryKey: ["reviewSummary", uploadId] });
      queryClient.invalidateQueries({ queryKey: ["academicGraph", uploadId] });
      queryClient.invalidateQueries({ queryKey: ["auditHistory", uploadId] });
      queryClient.invalidateQueries({ queryKey: ["approvalReadiness", uploadId] });

      setApprovalSuccess({
        approval_version: data.approval_version,
        approved_revision: data.approved_revision,
        pipeline_run_id: summaryQuery.data?.pipeline_run_id || "",
        approval_timestamp: Date.now() / 1000,
        reviewer_id: "trusted_reviewer_user",
        resolved_graph_fingerprint: data.resolved_graph_fingerprint
      });
      setShowApprovalConfirm(false);
      setOccError(null);
    },
    onError: (error: any) => {
      if (error?.response?.status === 409) {
        setOccError(
          error.response.data?.message ||
            "Optimistic Concurrency Control conflict. The document was modified by another session. Please review latest changes before approving."
        );
        queryClient.invalidateQueries({ queryKey: ["reviewSummary", uploadId] });
      } else {
        alert(error?.response?.data?.detail || error?.response?.data?.message || "Approval failed.");
      }
      setShowApprovalConfirm(false);
    }
  });

  const isLoading = summaryQuery.isLoading || graphQuery.isLoading;

  if (isLoading) {
    return (
      <div className="flex h-96 flex-col items-center justify-center space-y-4">
        <RefreshCw className="size-10 animate-spin text-violet-600" />
        <span className="text-sm font-medium text-muted-foreground">Extracting Academic Graph Structure...</span>
      </div>
    );
  }

  if (summaryQuery.isError) {
    const error: any = summaryQuery.error;
    const statusCode = error?.response?.status;
    const backendMessage = error?.response?.data?.message || error?.message;

    let errorType = "Unknown Error";
    let detailMessage = "An unexpected error occurred while loading the academic review.";

    if (!statusCode) {
      errorType = "Network Failure / Timeout";
      detailMessage = "Unable to connect to the backend server. Please verify the backend API server is running and check your network.";
    } else if (statusCode === 404) {
      errorType = "Document Not Found (404)";
      detailMessage = "The requested document upload ID does not exist or has not been processed yet.";
    } else if (statusCode === 409) {
      errorType = "Concurrency Conflict (409)";
      detailMessage = "Optimistic Concurrency Control conflict. The document was modified by another reviewer.";
    } else if (statusCode === 422) {
      errorType = "Validation Error (422)";
      detailMessage = "The request payload failed backend schema validations.";
    } else if (statusCode >= 500) {
      errorType = "Server Error (500)";
      detailMessage = `The server encountered an internal error: ${backendMessage}`;
    }

    return (
      <div className="max-w-2xl mx-auto my-12 p-6 border border-red-250 bg-red-50/10 dark:border-red-950 dark:bg-red-950/10 rounded-xl space-y-4">
        <div className="flex items-center gap-3 text-rose-600">
          <AlertTriangle className="size-6" />
          <h2 className="font-semibold text-lg">Unable to load academic review</h2>
        </div>
        <div className="space-y-1.5 bg-muted/40 p-3 rounded-lg border text-xs">
          <p className="font-bold text-foreground">Error Type: <span className="text-rose-600 font-semibold">{errorType}</span></p>
          <p className="text-muted-foreground">{detailMessage}</p>
          {backendMessage && (
            <p className="text-muted-foreground font-mono mt-1 text-[10px] bg-background/50 p-1 rounded border">
              Raw Message: {backendMessage}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <Button onClick={() => summaryQuery.refetch()} className="cursor-pointer">Retry Loading</Button>
          <Button onClick={() => navigate("/upload")} variant="outline" className="cursor-pointer">Back to Uploads</Button>
        </div>
      </div>
    );
  }

  if (!summaryQuery.data) {
    return (
      <div className="max-w-2xl mx-auto my-12 p-6 border border-red-200 bg-red-50/20 dark:border-red-950 dark:bg-red-950/10 rounded-xl space-y-4">
        <div className="flex items-center gap-3 text-red-600">
          <AlertTriangle className="size-6" />
          <h2 className="font-semibold text-lg">Unable to load academic review</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          No academic review summary was returned by the backend.
        </p>
        <Button onClick={() => navigate("/upload")} className="cursor-pointer">Back to Uploads</Button>
      </div>
    );
  }

  const summary = summaryQuery.data;
  const nodes = graphQuery.data?.nodes || [];
  const edges = graphQuery.data?.edges || [];

  // Filter nodes matching search term locally
  const searchedNodes = nodes.filter((n) =>
    n.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
    n.category.toLowerCase().includes(searchTerm.toLowerCase())
  );

  // Group nodes hierarchically where parent contains children
  const rootNodes = searchedNodes.filter((n) => {
    // If filtering is active, flat list is more helpful, else show root nodes
    if (categoryFilter || reviewStateFilter || lowConfidenceFilter !== null || orphanFilter !== null || searchTerm) {
      return true;
    }
    const hasParent = edges.some((e) => e.edge_type === "CONTAINS" && e.target_node_id === n.node_id);
    return !hasParent;
  });

  const getChildren = (nodeId: string) => {
    const childIds = edges
      .filter((e) => e.edge_type === "CONTAINS" && e.source_node_id === nodeId)
      .map((e) => e.target_node_id);
    return searchedNodes.filter((n) => childIds.includes(n.node_id));
  };

  const getReviewBadgeColor = (state: NodeReviewState) => {
    switch (state) {
      case "ACCEPTED":
        return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-400";
      case "MODIFIED":
        return "bg-amber-100 text-amber-800 dark:bg-amber-950/30 dark:text-amber-400";
      case "REJECTED":
        return "bg-rose-100 text-rose-800 dark:bg-rose-950/30 dark:text-rose-400";
      default:
        return "bg-violet-100 text-violet-800 dark:bg-violet-950/30 dark:text-violet-400";
    }
  };

  // Node Component for rendering the hierarchical Tree
  const TreeNode = ({ node }: { node: AcademicNode }) => {
    const children = getChildren(node.node_id);
    const hasChildren = children.length > 0;
    const isSelected = selectedNodeId === node.node_id;

    return (
      <div className="space-y-1">
        <div
          onClick={() => setSelectedNodeId(node.node_id)}
          className={`group flex items-center justify-between p-2 rounded-lg text-xs font-medium cursor-pointer transition-all border ${
            isSelected
              ? "bg-violet-50 border-violet-200 dark:bg-violet-950/20 dark:border-violet-850"
              : "border-transparent hover:bg-muted/40"
          }`}
        >
          <div className="flex items-center gap-2 truncate">
            {hasChildren ? <ChevronDown className="size-3 text-muted-foreground" /> : <ChevronRight className="size-3 text-muted-foreground/30" />}
            {node.category === "UNIT" || node.category === "CHAPTER" || node.category === "SECTION" ? (
              <Folder className={`size-3.5 ${isSelected ? "text-violet-600" : "text-amber-500"}`} />
            ) : (
              <FileText className={`size-3.5 ${isSelected ? "text-violet-600" : "text-muted-foreground"}`} />
            )}
            <span className={`font-semibold uppercase tracking-wider text-[10px] ${isSelected ? "text-violet-700" : "text-muted-foreground"}`}>
              [{node.category}]
            </span>
            <span className="truncate text-foreground max-w-xs">{node.title}</span>
          </div>

          <div className="flex items-center gap-1.5 opacity-90">
            {node.metadata.provenance === "HUMAN_OVERRIDE" && (
              <span className="bg-blue-100 text-blue-800 dark:bg-blue-950/30 dark:text-blue-400 text-[9px] px-1 rounded">
                Manual
              </span>
            )}
            <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-semibold ${getReviewBadgeColor(node.review_state)}`}>
              {node.review_state}
            </span>
          </div>
        </div>

        {/* Child recursion */}
        {hasChildren && (
          <div className="pl-4 border-l border-muted/50 ml-3.5 space-y-1">
            {children.map((child) => (
              <TreeNode key={child.node_id} node={child} />
            ))}
          </div>
        )}
      </div>
    );
  };

  const handleCreateNode = () => {
    if (!newTitle.trim()) {
      alert("Node title cannot be empty");
      return;
    }
    applyActionMutation.mutate({
      action_type: "CREATE_NODE",
      payload: {
        category: newCategory,
        title: newTitle.trim(),
        new_parent_id: newParentId || undefined
      }
    });
    setNewTitle("");
    setNewParentId("");
    setShowCreateModal(false);
  };

  const handleApplyNodeEdits = (action: string) => {
    if (!selectedNodeId || !nodeDetailsQuery.data) return;
    const detail = nodeDetailsQuery.data;

    let payload: Record<string, any> = { target_anchor_key: detail.anchor_key };

    if (action === "CHANGE_CATEGORY") {
      payload.new_category = localCategory;
    } else if (action === "RENAME_TITLE") {
      if (!localTitle.trim()) {
        alert("Title cannot be empty");
        return;
      }
      payload.new_title = localTitle.trim();
    } else if (action === "REPARENT_NODE") {
      payload.new_parent_id = localParentId;
    }

    applyActionMutation.mutate({
      action_type: action,
      payload
    });
  };

  const handleQuickAction = (action: "ACCEPT_NODE" | "DELETE_NODE") => {
    if (!selectedNodeId || !nodeDetailsQuery.data) return;
    applyActionMutation.mutate({
      action_type: action,
      payload: { target_anchor_key: nodeDetailsQuery.data.anchor_key }
    });
  };

  return (
    <div className="space-y-6 py-6 max-w-6xl mx-auto px-4">
      {/* 1. Header Section */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b pb-4">
        <div className="space-y-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(`/documents/${summary?.document_id || summary?.upload_id}`)}
            className="pl-0 gap-1.5 text-muted-foreground hover:text-foreground cursor-pointer"
          >
            <ArrowLeft className="size-4" /> Back to Document Details
          </Button>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold tracking-tight">Academic Graph Review</h1>
            <span
              className={`text-xs px-2.5 py-0.5 rounded-full font-bold uppercase ${
                summary.document_review_state === "APPROVED"
                  ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-400"
                  : "bg-amber-100 text-amber-800 dark:bg-amber-950/30 dark:text-amber-400"
              }`}
            >
              {summary.document_review_state}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Current Concurrency Revision: <span className="font-mono font-bold text-violet-600">{currentRevision}</span>
          </p>
        </div>

        <div className="flex items-center gap-2">
          {summary.document_review_state === "APPROVED" ? (
            <span className="text-xs font-semibold text-emerald-600 bg-emerald-50 dark:bg-emerald-950/20 px-3 py-1.5 rounded-lg border border-emerald-250 flex items-center gap-1.5">
              <Check className="size-4" /> Snapshot Approved
            </span>
          ) : readinessQuery.data?.eligible ? (
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-emerald-600 bg-emerald-50 dark:bg-emerald-950/20 px-3 py-1.5 rounded-lg border border-emerald-250 flex items-center gap-1.5">
                <Check className="size-4" /> Ready for final approval
              </span>
              <Button
                onClick={() => setShowApprovalConfirm(true)}
                className="bg-violet-600 hover:bg-violet-750 text-white cursor-pointer px-4 py-1.5 h-8 text-xs font-bold"
              >
                Approve Graph
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-amber-600 bg-amber-50 dark:bg-amber-950/20 px-3 py-1.5 rounded-lg border border-amber-250 flex items-center gap-1.5">
                <AlertTriangle className="size-4" /> Unresolved items remain
              </span>
              <Button
                disabled
                className="bg-muted text-muted-foreground cursor-not-allowed px-4 py-1.5 h-8 text-xs font-bold border"
              >
                Approve Graph
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* 2. OCC Conflict Dialog Banner */}
      {occError && (
        <div className="p-4 border border-rose-200 bg-rose-50/20 dark:border-rose-950 dark:bg-rose-950/10 rounded-xl space-y-3">
          <div className="flex items-start gap-2.5">
            <AlertTriangle className="size-5 text-rose-600 mt-0.5" />
            <div className="space-y-1">
              <h4 className="text-sm font-semibold text-rose-800 dark:text-rose-400">Document Out of Sync</h4>
              <p className="text-xs text-muted-foreground leading-relaxed">{occError}</p>
            </div>
          </div>
          <div className="flex gap-2 pl-7">
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setOccError(null);
                queryClient.invalidateQueries({ queryKey: ["reviewSummary", uploadId] });
                queryClient.invalidateQueries({ queryKey: ["academicGraph", uploadId] });
              }}
              className="text-xs"
            >
              Reload Latest State
            </Button>
          </div>
        </div>
      )}

      {/* 3. Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <InfoCard title="Total Nodes">
          <div className="text-xl font-bold">{summary.total_nodes}</div>
          <p className="text-[10px] text-muted-foreground mt-1">Detected academic elements</p>
        </InfoCard>
        <InfoCard title="Unreviewed">
          <div className="text-xl font-bold text-violet-600">{summary.unreviewed_count}</div>
          <p className="text-[10px] text-muted-foreground mt-1">Awaiting verification</p>
        </InfoCard>
        <InfoCard title="Accepted">
          <div className="text-xl font-bold text-emerald-600">{summary.accepted_count}</div>
          <p className="text-[10px] text-muted-foreground mt-1">Confirmed correct</p>
        </InfoCard>
        <InfoCard title="Modified / Rejected">
          <div className="text-xl font-bold text-amber-500">
            {summary.modified_count} <span className="text-muted-foreground text-sm">/ {summary.rejected_count}</span>
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">Human overrides applied</p>
        </InfoCard>
        <InfoCard title="Stale / Conflicts">
          <div className="text-xl font-bold text-rose-500">
            {summary.stale_overrides_count} <span className="text-muted-foreground text-sm">/ {summary.conflicted_overrides_count}</span>
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">Reconciliation warnings</p>
        </InfoCard>
      </div>

      {/* 4. Left / Right Split Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-10 gap-6">
        {/* Left Side: Tree Viewer (60% width) */}
        <div className="lg:col-span-6 border rounded-xl p-4 space-y-4 bg-card">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold flex items-center gap-2">
              <GitBranch className="size-4 text-violet-600" /> Academic Hierarchy
            </h3>
            <Button
              size="sm"
              onClick={() => setShowCreateModal(true)}
              className="gap-1 bg-violet-600 hover:bg-violet-700 text-white cursor-pointer h-7 text-[11px]"
            >
              <Plus className="size-3" /> Add Node
            </Button>
          </div>

          {/* Filtering Tools */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-2 size-3.5 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search nodes..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-8 pr-2 py-1 text-xs border rounded-lg bg-muted/20 focus:outline-none focus:ring-1 focus:ring-violet-500"
              />
            </div>

            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="w-full p-1 text-xs border rounded-lg bg-muted/20 text-foreground"
            >
              <option value="">All Categories</option>
              {VALID_CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>

            <select
              value={reviewStateFilter}
              onChange={(e) => setReviewStateFilter(e.target.value)}
              className="w-full p-1 text-xs border rounded-lg bg-muted/20 text-foreground"
            >
              <option value="">All States</option>
              <option value="UNREVIEWED">UNREVIEWED</option>
              <option value="ACCEPTED">ACCEPTED</option>
              <option value="MODIFIED">MODIFIED</option>
              <option value="REJECTED">REJECTED</option>
            </select>
          </div>

          <div className="flex gap-4 px-1 text-[10px] text-muted-foreground font-semibold">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={lowConfidenceFilter === true}
                onChange={(e) => setLowConfidenceFilter(e.target.checked ? true : null)}
                className="accent-violet-600"
              />
              Show Low Confidence
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={orphanFilter === true}
                onChange={(e) => setOrphanFilter(e.target.checked ? true : null)}
                className="accent-violet-600"
              />
              Show Orphans Only
            </label>
          </div>

          {/* Hierarchical tree listing */}
          <div className="max-h-[500px] overflow-y-auto pr-2 space-y-3">
            {rootNodes.length === 0 ? (
              <div className="text-center py-12 text-xs text-muted-foreground">
                No academic structure matches filters or search criteria.
              </div>
            ) : (
              rootNodes.map((node) => <TreeNode key={node.node_id} node={node} />)
            )}
          </div>
        </div>

        {/* Right Side: Detail Panel (40% width) */}
        <div className="lg:col-span-4 border rounded-xl p-4 bg-card h-fit space-y-4">
          <h3 className="text-sm font-bold flex items-center gap-2 border-b pb-2">
            <Settings className="size-4 text-violet-600" /> Node Inspector
          </h3>

          {!selectedNodeId ? (
            <div className="text-center py-20 text-xs text-muted-foreground">
              Select an academic node from the tree to inspect details, view classification evidence, or submit overrides.
            </div>
          ) : nodeDetailsQuery.isLoading ? (
            <div className="text-center py-20 text-xs text-muted-foreground flex flex-col items-center gap-2">
              <RefreshCw className="size-6 animate-spin text-violet-600" />
              <span>Loading details...</span>
            </div>
          ) : (
            (() => {
              const detail = nodeDetailsQuery.data!;
              const hasUnsavedTitle = localTitle !== detail.title;
              const hasUnsavedCat = localCategory !== detail.category;
              const hasUnsavedParent = localParentId !== (detail.parent_id || "");

              return (
                <div className="space-y-4 text-xs">
                  {/* General details */}
                  <div className="grid grid-cols-2 gap-3 bg-muted/15 p-3 rounded-lg border">
                    <div>
                      <span className="text-[10px] text-muted-foreground uppercase font-bold block">Review State</span>
                      <span className={`inline-block mt-0.5 px-2 py-0.5 rounded font-bold text-[10px] ${getReviewBadgeColor(detail.review_state)}`}>
                        {detail.review_state}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-muted-foreground uppercase font-bold block">Confidence</span>
                      <span className="font-semibold text-foreground">{Math.round(detail.confidence * 100)}%</span>
                    </div>
                    <div className="col-span-2">
                      <span className="text-[10px] text-muted-foreground uppercase font-bold block">Provenance</span>
                      <span className="text-foreground capitalize">{detail.provenance.toLowerCase().replace(/_/g, " ")}</span>
                    </div>
                  </div>

                  {/* Title editor */}
                  <div className="space-y-1.5">
                    <label className="text-[10px] text-muted-foreground uppercase font-bold block">Node Title</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={localTitle}
                        onChange={(e) => setLocalTitle(e.target.value)}
                        disabled={summary.document_review_state === "APPROVED"}
                        className="flex-1 p-1.5 border rounded bg-background text-foreground"
                      />
                      {hasUnsavedTitle && summary.document_review_state !== "APPROVED" && (
                        <Button
                          size="sm"
                          onClick={() => handleApplyNodeEdits("RENAME_TITLE")}
                          className="bg-amber-500 hover:bg-amber-600 text-white cursor-pointer px-2"
                        >
                          Save
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* Category editor */}
                  <div className="space-y-1.5">
                    <label className="text-[10px] text-muted-foreground uppercase font-bold block">Academic Category</label>
                    <div className="flex gap-2">
                      <select
                        value={localCategory}
                        onChange={(e) => setLocalCategory(e.target.value)}
                        disabled={summary.document_review_state === "APPROVED"}
                        className="flex-1 p-1.5 border rounded bg-background text-foreground"
                      >
                        {VALID_CATEGORIES.map((c) => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                      {hasUnsavedCat && summary.document_review_state !== "APPROVED" && (
                        <Button
                          size="sm"
                          onClick={() => handleApplyNodeEdits("CHANGE_CATEGORY")}
                          className="bg-amber-500 hover:bg-amber-600 text-white cursor-pointer px-2"
                        >
                          Save
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* Parent editor */}
                  <div className="space-y-1.5">
                    <label className="text-[10px] text-muted-foreground uppercase font-bold block">Containment Parent</label>
                    <div className="flex gap-2">
                      <select
                        value={localParentId}
                        onChange={(e) => setLocalParentId(e.target.value)}
                        disabled={summary.document_review_state === "APPROVED"}
                        className="flex-1 p-1.5 border rounded bg-background text-foreground"
                      >
                        <option value="">[None]</option>
                        {nodes
                          .filter((n) => n.node_id !== detail.node_id)
                          .map((n) => (
                            <option key={n.node_id} value={n.node_id}>
                              [{n.category}] {n.title}
                            </option>
                          ))}
                      </select>
                      {hasUnsavedParent && summary.document_review_state !== "APPROVED" && (
                        <Button
                          size="sm"
                          onClick={() => handleApplyNodeEdits("REPARENT_NODE")}
                          className="bg-amber-500 hover:bg-amber-600 text-white cursor-pointer px-2"
                        >
                          Save
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* Comment box */}
                  <div className="space-y-1">
                    <label className="text-[10px] text-muted-foreground uppercase font-bold block">Correction Comments</label>
                    <textarea
                      placeholder="Explain correction reason..."
                      value={mutationComment}
                      onChange={(e) => setMutationComment(e.target.value)}
                      disabled={summary.document_review_state === "APPROVED"}
                      className="w-full p-2 border rounded bg-background text-foreground h-12 text-xs"
                    />
                  </div>

                  {/* Quick Decision Panel */}
                  <div className="flex gap-2 pt-2 border-t">
                    <Button
                      onClick={() => handleQuickAction("ACCEPT_NODE")}
                      disabled={summary.document_review_state === "APPROVED" || detail.review_state === "ACCEPTED"}
                      className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white cursor-pointer text-xs h-8"
                    >
                      Accept Node
                    </Button>
                    <Button
                      onClick={() => handleQuickAction("DELETE_NODE")}
                      disabled={summary.document_review_state === "APPROVED" || detail.review_state === "REJECTED"}
                      variant="outline"
                      className="flex-1 border-rose-250 hover:bg-rose-50 text-rose-600 dark:hover:bg-rose-950/20 text-xs h-8"
                    >
                      Reject/Hide Node
                    </Button>
                  </div>
                </div>
              );
            })()
          )}
        </div>
      </div>

      {/* 5. Bottom Tabs (Audit Trails & Reconciliation Details & Approval History) */}
      <div className="border rounded-xl bg-card overflow-hidden">
        <div className="flex border-b bg-muted/20">
          <button
            onClick={() => setActiveBottomTab("audit")}
            className={`px-4 py-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 cursor-pointer transition-all ${
              activeBottomTab === "audit"
                ? "border-violet-600 text-violet-600 font-bold bg-background"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <History className="size-4" /> Audit Trails
          </button>
          <button
            onClick={() => setActiveBottomTab("reconciliation")}
            className={`px-4 py-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 cursor-pointer transition-all ${
              activeBottomTab === "reconciliation"
                ? "border-violet-600 text-violet-600 font-bold bg-background"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <AlertTriangle className="size-4" /> Reconciliation ({summary.stale_overrides_count + summary.conflicted_overrides_count})
          </button>
          <button
            onClick={() => setActiveBottomTab("history")}
            className={`px-4 py-3 text-xs font-semibold flex items-center gap-1.5 border-b-2 cursor-pointer transition-all ${
              activeBottomTab === "history"
                ? "border-violet-600 text-violet-600 font-bold bg-background"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Award className="size-4" /> Approval History ({summary.approval_history?.length || 0})
          </button>
        </div>

        <div className="p-4 max-h-[300px] overflow-y-auto text-xs">
          {activeBottomTab === "audit" ? (
            (() => {
              const logs = auditQuery.data?.audits || [];
              if (logs.length === 0) {
                return <div className="text-center py-8 text-muted-foreground">No audit trail records found.</div>;
              }
              return (
                <div className="space-y-3">
                  {logs.map((log) => (
                    <div key={log.audit_id} className="p-3 border rounded-lg bg-muted/10 space-y-1.5">
                      <div className="flex justify-between text-[10px] text-muted-foreground font-semibold">
                        <span>Reviewer: {log.user_id}</span>
                        <span>{new Date(log.timestamp * 1000).toLocaleString()}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="bg-violet-100 text-violet-800 dark:bg-violet-950/30 dark:text-violet-400 px-1.5 py-0.5 rounded font-bold text-[9px]">
                          {log.action_type}
                        </span>
                        <span className="font-semibold text-foreground">Node: {log.node_id}</span>
                      </div>
                      {log.comment && (
                        <p className="text-xs italic text-muted-foreground bg-background p-1.5 rounded border border-muted/50">
                          &ldquo;{log.comment}&rdquo;
                        </p>
                      )}
                      <div className="grid grid-cols-2 gap-2 text-[10px] pt-1">
                        <div className="text-muted-foreground">
                          <strong>Prev:</strong> {JSON.stringify(log.previous_state)}
                        </div>
                        <div className="text-muted-foreground">
                          <strong>New:</strong> {JSON.stringify(log.new_state)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              );
            })()
          ) : activeBottomTab === "reconciliation" ? (
            (() => {
              const stales = reconQuery.data?.stale_overrides || [];
              const conflicts = reconQuery.data?.conflicted_overrides || [];
              if (stales.length === 0 && conflicts.length === 0) {
                return (
                  <div className="text-center py-8 text-emerald-600 bg-emerald-50/20 rounded-lg p-4 border border-emerald-100">
                    No active reconciliation warnings. Overrides and anchor mapping resolved cleanly!
                  </div>
                );
              }

              return (
                <div className="space-y-4">
                  {stales.map((s) => (
                    <div key={s.override_id} className="p-3 border border-amber-200 bg-amber-50/20 dark:border-amber-950 dark:bg-amber-950/10 rounded-lg space-y-1">
                      <div className="flex items-center gap-2 text-amber-800 dark:text-amber-400 font-semibold">
                        <AlertTriangle className="size-4" /> Stale Override Detected
                      </div>
                      <p className="text-xs text-muted-foreground">{s.reason}</p>
                      <div className="text-[10px] text-muted-foreground">
                        Anchor Key: <code className="font-mono">{s.anchor_key}</code>
                      </div>
                    </div>
                  ))}

                  {conflicts.map((c) => (
                    <div key={c.override_id} className="p-3 border border-rose-200 bg-rose-50/20 dark:border-rose-950 dark:bg-rose-950/10 rounded-lg space-y-1">
                      <div className="flex items-center gap-2 text-rose-800 dark:text-rose-400 font-semibold">
                        <AlertTriangle className="size-4" /> Collision Override Warning
                      </div>
                      <p className="text-xs text-muted-foreground">{c.reason}</p>
                      <div className="text-[10px] text-muted-foreground">
                        Anchor Key: <code className="font-mono">{c.anchor_key}</code>
                      </div>
                    </div>
                  ))}
                </div>
              );
            })()
          ) : (
            (() => {
              const historyList = summary.approval_history || [];
              if (historyList.length === 0) {
                return <div className="text-center py-8 text-muted-foreground">No approved snapshots found in history.</div>;
              }
              return (
                <div className="space-y-3">
                  {historyList.map((hist) => (
                    <div key={hist.approval_version} className="p-3 border rounded-lg bg-muted/10 space-y-1.5">
                      <div className="flex justify-between text-[10px] text-muted-foreground font-semibold">
                        <span className="flex items-center gap-1"><User className="size-3" /> Reviewer: {hist.reviewer_id}</span>
                        <span className="flex items-center gap-1"><Calendar className="size-3" /> {new Date(hist.approval_timestamp * 1000).toLocaleString()}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="bg-emerald-100 text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-400 px-2 py-0.5 rounded font-bold text-[10px]">
                          Version {hist.approval_version}
                        </span>
                        <span className="text-[10px] text-muted-foreground">Approved Revision: <code className="font-mono">{hist.approved_revision}</code></span>
                      </div>
                      <div className="text-[10px] text-muted-foreground leading-relaxed space-y-0.5">
                        <div>Pipeline Run ID: <code className="font-mono">{hist.pipeline_run_id}</code></div>
                        <div>Resolved Fingerprint: <code className="font-mono text-violet-600">{hist.resolved_graph_fingerprint}</code></div>
                      </div>
                    </div>
                  ))}
                </div>
              );
            })()
          )}
        </div>
      </div>

      {/* 6. Create Node Modal Dialog */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-card border rounded-xl p-5 max-w-md w-full space-y-4">
            <h3 className="text-sm font-bold border-b pb-2">Create Academic Node</h3>

            <div className="space-y-3 text-xs">
              <div className="space-y-1">
                <label className="text-[10px] text-muted-foreground uppercase font-bold block">Node Title</label>
                <input
                  type="text"
                  placeholder="Enter Title..."
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="w-full p-2 border rounded bg-background text-foreground"
                />
              </div>

              <div className="space-y-1">
                <label className="text-[10px] text-muted-foreground uppercase font-bold block">Category</label>
                <select
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                  className="w-full p-2 border rounded bg-background text-foreground"
                >
                  {VALID_CATEGORIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-[10px] text-muted-foreground uppercase font-bold block">Optional Parent</label>
                <select
                  value={newParentId}
                  onChange={(e) => setNewParentId(e.target.value)}
                  className="w-full p-2 border rounded bg-background text-foreground"
                >
                  <option value="">[None]</option>
                  {nodes.map((n) => (
                    <option key={n.node_id} value={n.node_id}>
                      [{n.category}] {n.title}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex gap-2 justify-end pt-2">
              <Button variant="outline" onClick={() => setShowCreateModal(false)} className="cursor-pointer text-xs">
                Cancel
              </Button>
              <Button onClick={handleCreateNode} className="bg-violet-600 hover:bg-violet-700 text-white cursor-pointer text-xs">
                Create
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* 7. Approval Confirmation Dialog Modal */}
      {showApprovalConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-card border rounded-xl p-5 max-w-md w-full space-y-4 shadow-xl">
            <div className="flex items-center gap-2.5 text-violet-600 border-b pb-2">
              <Shield className="size-5" />
              <h3 className="text-sm font-bold">Approve Academic Graph?</h3>
            </div>
            
            <p className="text-xs text-muted-foreground leading-relaxed">
              This will freeze the current validated academic structure as an immutable version for downstream processing.
            </p>

            <div className="bg-muted/15 p-3 rounded-lg border space-y-2 text-[11px] leading-relaxed">
              <div className="flex justify-between">
                <span className="text-muted-foreground font-medium">Document:</span>
                <span className="font-bold text-foreground overflow-hidden text-ellipsis whitespace-nowrap max-w-[200px]" title={summary.upload_id}>
                  {summary.upload_id}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground font-medium">Total Academic Nodes:</span>
                <span className="font-bold text-foreground">{summary.total_nodes}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground font-medium">Reviewed Nodes:</span>
                <span className="font-bold text-foreground">
                  {summary.accepted_count + summary.modified_count} / {summary.total_nodes}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground font-medium">Warnings:</span>
                <span className="font-bold text-amber-600">{readinessQuery.data?.warnings?.length || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground font-medium">Current Concurrency Revision:</span>
                <span className="font-bold text-foreground font-mono">{currentRevision}</span>
              </div>
              <div className="space-y-0.5 border-t pt-1.5 mt-1.5">
                <span className="text-[10px] text-muted-foreground uppercase font-bold block">Resolved Fingerprint</span>
                <code className="text-[10px] text-violet-600 font-mono break-all">{summary.resolved_graph_fingerprint}</code>
              </div>
              <div className="flex justify-between border-t pt-1.5 mt-1.5">
                <span className="text-muted-foreground font-medium">Reviewer Identity:</span>
                <span className="font-bold text-foreground flex items-center gap-1"><User className="size-3" /> trusted_reviewer_user</span>
              </div>
            </div>

            <div className="flex gap-2 justify-end pt-2">
              <Button
                variant="outline"
                onClick={() => setShowApprovalConfirm(false)}
                disabled={approveGraphMutation.isPending}
                className="cursor-pointer text-xs"
              >
                Cancel
              </Button>
              <Button
                onClick={() => approveGraphMutation.mutate()}
                disabled={approveGraphMutation.isPending}
                className="bg-violet-600 hover:bg-violet-750 text-white cursor-pointer text-xs flex items-center gap-1.5"
              >
                {approveGraphMutation.isPending ? (
                  <>
                    <RefreshCw className="size-3 animate-spin" /> Approving...
                  </>
                ) : (
                  <>
                    <Check className="size-4" /> Confirm Approval
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* 8. Approval Success Dialog Modal */}
      {approvalSuccess && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-card border rounded-xl p-5 max-w-md w-full space-y-4 shadow-xl">
            <div className="flex flex-col items-center justify-center space-y-2 text-center pb-2">
              <div className="bg-emerald-100 dark:bg-emerald-950/30 p-3 rounded-full text-emerald-600">
                <Award className="size-8" />
              </div>
              <h3 className="text-base font-bold text-foreground">Academic Graph Approved!</h3>
              <p className="text-xs text-muted-foreground">
                The academic structure snapshot has been frozen and committed successfully.
              </p>
            </div>

            <div className="bg-muted/15 p-3 rounded-lg border space-y-2 text-[11px] leading-relaxed">
              <div className="flex justify-between">
                <span className="text-muted-foreground font-medium">Status:</span>
                <span className="font-bold text-emerald-600 flex items-center gap-1"><Check className="size-3" /> APPROVED</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground font-medium">Approval Version:</span>
                <span className="bg-emerald-100 text-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-400 px-2 py-0.5 rounded font-bold text-[10px]">
                  {approvalSuccess.approval_version}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground font-medium">Approved Revision:</span>
                <span className="font-bold text-foreground font-mono">{approvalSuccess.approved_revision}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground font-medium">Approved At:</span>
                <span className="font-bold text-foreground flex items-center gap-1">
                  <Calendar className="size-3" /> {new Date(approvalSuccess.approval_timestamp * 1000).toLocaleString()}
                </span>
              </div>
              <div className="space-y-0.5 border-t pt-1.5 mt-1.5">
                <span className="text-[10px] text-muted-foreground uppercase font-bold block">Resolved Graph Fingerprint</span>
                <code className="text-[10px] text-violet-600 font-mono break-all">{approvalSuccess.resolved_graph_fingerprint}</code>
              </div>
            </div>

            <div className="flex justify-center pt-2">
              <Button
                onClick={() => setApprovalSuccess(null)}
                className="bg-violet-600 hover:bg-violet-750 text-white cursor-pointer px-6 text-xs font-bold"
              >
                Done
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
