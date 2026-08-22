import { useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { listFinalizedVersions } from "@/services/knowledgeService";
import { getDocument } from "@/services/documentService";
import { queryRetrieval } from "@/services/retrievalService";
import { Button } from "@/components/ui/button";
import {
  ArrowLeft,
  Search,
  Sliders,
  AlertTriangle,
  Info,
  BookOpen,
  Link as LinkIcon,
  FileText,
  Clock
} from "lucide-react";
import type { RetrievalRequest, RetrievedEntity, RetrievalResult } from "@/types/retrieval";

const ENTITY_TYPES = [
  "CHAPTER", "SECTION", "TOPIC", "CONCEPT", "DEFINITION",
  "THEOREM", "PROOF", "FORMULA", "ALGORITHM", "EXAMPLE",
  "EXERCISE", "SUMMARY"
];

export default function RetrievalInspectorPage() {
  const { id: documentId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // State parameters
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [queryText, setQueryText] = useState<string>("");
  const [topK, setTopK] = useState<number>(10);
  const [relationshipDepth, setRelationshipDepth] = useState<number>(1);
  const [includeRelationships, setIncludeRelationships] = useState<boolean>(true);
  const [includeEvidence, setIncludeEvidence] = useState<boolean>(true);
  const [includePassages, setIncludePassages] = useState<boolean>(true);
  const [selectedEntityTypes, setSelectedEntityTypes] = useState<string[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<string>("LEXICAL");

  // Selection state for viewing results
  const [selectedEntity, setSelectedEntity] = useState<RetrievedEntity | null>(null);
  const [showOptions, setShowOptions] = useState<boolean>(false);

  // 1. Fetch Document Details
  const docQuery = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => getDocument(documentId!),
    enabled: !!documentId,
  });

  // 2. Fetch Ingested/Finalized Versions
  const versionsQuery = useQuery({
    queryKey: ["versionsList", documentId],
    queryFn: () => listFinalizedVersions(documentId!),
    enabled: !!documentId,
  });

  // Automatically select latest version as default when list loads
  useMemo(() => {
    if (versionsQuery.data && versionsQuery.data.length > 0 && !selectedVersionId) {
      // Keep it as null to signify "Latest Finalized" on backend scope resolver,
      // or we can allow dropdown selection.
    }
  }, [versionsQuery.data, selectedVersionId]);

  // 3. Mutation for Retrieval Execution
  const retrievalMutation = useMutation({
    mutationFn: (req: RetrievalRequest) => queryRetrieval(req),
    onSuccess: (data: RetrievalResult) => {
      if (data.entities.length > 0) {
        setSelectedEntity(data.entities[0]);
      } else {
        setSelectedEntity(null);
      }
    }
  });

  const handleRunRetrieval = (e: React.FormEvent) => {
    e.preventDefault();
    if (!queryText.trim()) return;

    const requestBody: RetrievalRequest = {
      query: queryText.trim(),
      scope: {
        document_id: documentId!,
        version_id: selectedVersionId || null, // null resolves backend-side to latest
        entity_types: selectedEntityTypes.length > 0 ? selectedEntityTypes : null,
        relationship_types: null
      },
      options: {
        top_k: topK,
        include_relationships: includeRelationships,
        include_evidence: includeEvidence,
        include_passages: includePassages,
        relationship_depth: relationshipDepth,
        strategy: selectedStrategy
      }
    };

    retrievalMutation.mutate(requestBody);
  };

  const handleEntityTypeToggle = (type: string) => {
    setSelectedEntityTypes(prev =>
      prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]
    );
  };

  const doc = docQuery.data?.data;

  // Loading / Error handling for document fetching
  if (docQuery.isLoading || versionsQuery.isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] gap-3">
        <div className="size-8 border-4 border-violet-600 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm text-muted-foreground animate-pulse">Loading Retrieval Inspector...</p>
      </div>
    );
  }

  if (versionsQuery.data && versionsQuery.data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 text-center max-w-lg mx-auto p-4">
        <div className="p-4 bg-amber-50 dark:bg-amber-950/20 text-amber-600 rounded-full">
          <AlertTriangle className="size-12" />
        </div>
        <h2 className="text-2xl font-bold tracking-tight">No Finalized Knowledge Available</h2>
        <p className="text-muted-foreground text-sm">
          This document has not been compiled into the canonical knowledge model yet. 
          Complete human validation of the academic graph to perform context retrieval.
        </p>
        <Button onClick={() => navigate(-1)} variant="outline">Go Back</Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-2 sm:p-4">
      
      {/* 1. Header Section */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-5">
        <div className="flex flex-col gap-1">
          <Button
            onClick={() => navigate(`/documents/${documentId}`)}
            variant="ghost"
            className="pl-0 gap-1.5 text-muted-foreground hover:text-foreground cursor-pointer justify-start"
          >
            <ArrowLeft className="size-4" /> Back to Document Details
          </Button>
          <h1 className="text-2xl font-extrabold tracking-tight truncate max-w-xl">
            Retrieval Inspector
          </h1>
          <p className="text-xs text-muted-foreground">
            Document: <span className="font-semibold text-foreground">{doc?.metadata?.title || documentId}</span>
          </p>
        </div>

        {/* Version Selector */}
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-muted-foreground">Target Version:</span>
          <select
            value={selectedVersionId || ""}
            onChange={(e) => {
              setSelectedVersionId(e.target.value || null);
            }}
            className="bg-muted text-foreground text-xs font-medium border border-input rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-violet-500 cursor-pointer"
          >
            <option value="">Latest Finalized Version</option>
            {versionsQuery.data?.map((v) => (
              <option key={v.id} value={v.id}>
                Version {v.approval_version} ({new Date(v.created_at * 1000).toLocaleDateString()})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* 2. Query Options Form */}
      <form onSubmit={handleRunRetrieval} className="border border-border bg-card rounded-xl p-4 shadow-sm flex flex-col gap-4">
        <div className="flex items-center justify-between border-b border-border pb-2">
          <h2 className="text-sm font-bold tracking-wide uppercase text-muted-foreground flex items-center gap-1.5">
            <Sliders className="size-4 text-violet-600" /> Config & Options
          </h2>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setShowOptions(!showOptions)}
            className="text-xs text-violet-600 dark:text-violet-400 font-semibold"
          >
            {showOptions ? "Hide Advanced" : "Show Advanced Options"}
          </Button>
        </div>

        {/* Query Input */}
        <div className="flex flex-col sm:flex-row gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
            <input
              type="text"
              value={queryText}
              onChange={(e) => setQueryText(e.target.value)}
              placeholder="Type keyword query (e.g. binary search complexity)..."
              required
              className="w-full pl-9 pr-4 py-2 text-sm bg-muted/50 border border-input rounded-lg focus:outline-none focus:ring-1 focus:ring-violet-500 text-foreground"
            />
          </div>
          <Button
            type="submit"
            disabled={!queryText.trim() || retrievalMutation.isPending}
            className="bg-violet-600 hover:bg-violet-700 text-white rounded-lg px-4 py-2 text-sm font-semibold flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
          >
            {retrievalMutation.isPending ? (
              <div className="size-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            ) : (
              <Search className="size-4" />
            )}
            Run Retrieval
          </Button>
        </div>

        {/* Collapsible Advanced Options */}
        {showOptions && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-2 border-t border-dashed border-border animate-in fade-in duration-200">
            {/* Options Left: Toggles */}
            <div className="flex flex-col gap-3">
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Features included</span>
              <label className="flex items-center gap-2 text-xs font-medium cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeRelationships}
                  onChange={(e) => setIncludeRelationships(e.target.checked)}
                  className="rounded border-input text-violet-600 focus:ring-violet-500"
                />
                Include Relationships
              </label>
              <label className="flex items-center gap-2 text-xs font-medium cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeEvidence}
                  onChange={(e) => setIncludeEvidence(e.target.checked)}
                  className="rounded border-input text-violet-600 focus:ring-violet-500"
                />
                Include Evidence Coordinates
              </label>
              <label className="flex items-center gap-2 text-xs font-medium cursor-pointer">
                <input
                  type="checkbox"
                  checked={includePassages}
                  onChange={(e) => setIncludePassages(e.target.checked)}
                  className="rounded border-input text-violet-600 focus:ring-violet-500"
                />
                Include Verbatim Passages
              </label>
            </div>

            {/* Options Center: Strategy & Parameters */}
            <div className="flex flex-col gap-3">
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Retrieval Strategy</span>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs text-muted-foreground">Search Strategy</label>
                <select
                  value={selectedStrategy}
                  onChange={(e) => setSelectedStrategy(e.target.value)}
                  className="bg-muted text-foreground text-xs font-medium border border-input rounded-lg p-2 focus:outline-none focus:ring-1 focus:ring-violet-500"
                >
                  <option value="LEXICAL">LEXICAL (Token Search)</option>
                  <option value="SEMANTIC" disabled>SEMANTIC (Disabled - Unsupported)</option>
                  <option value="HYBRID" disabled>HYBRID (Disabled - Unsupported)</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-2 mt-1">
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground">Top K ({topK})</label>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={topK}
                    onChange={(e) => setTopK(parseInt(e.target.value) || 10)}
                    className="bg-muted text-foreground text-xs font-medium border border-input rounded-lg p-1.5 focus:outline-none"
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-xs text-muted-foreground">Hop Depth ({relationshipDepth})</label>
                  <input
                    type="number"
                    min={0}
                    max={3}
                    value={relationshipDepth}
                    onChange={(e) => setRelationshipDepth(parseInt(e.target.value) || 0)}
                    className="bg-muted text-foreground text-xs font-medium border border-input rounded-lg p-1.5 focus:outline-none"
                  />
                </div>
              </div>
            </div>

            {/* Options Right: Preferred Types */}
            <div className="flex flex-col gap-2">
              <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Preferred Types</span>
              <div className="grid grid-cols-2 gap-1.5 max-h-[140px] overflow-y-auto pr-1 border border-border rounded-lg p-2 bg-muted/10">
                {ENTITY_TYPES.map(type => (
                  <button
                    key={type}
                    type="button"
                    onClick={() => handleEntityTypeToggle(type)}
                    className={`text-left text-[10px] font-semibold px-2 py-1 rounded transition-colors ${
                      selectedEntityTypes.includes(type)
                        ? "bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-400"
                        : "bg-muted hover:bg-muted/80 text-muted-foreground"
                    }`}
                  >
                    {type}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </form>

      {/* Error state */}
      {retrievalMutation.isError && (
        <div className="flex items-center gap-3 p-4 bg-rose-50 dark:bg-rose-950/20 text-rose-600 dark:text-rose-400 border border-rose-100 dark:border-rose-900/50 rounded-xl text-sm font-medium">
          <AlertTriangle className="size-5 shrink-0" />
          <span>Failed to run retrieval: {(retrievalMutation.error as any)?.response?.data?.message || retrievalMutation.error.message}</span>
        </div>
      )}

      {/* 3. Main Split Panels view */}
      {retrievalMutation.data && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          
          {/* Left Panel: Ranked Candidates list */}
          <div className="lg:col-span-2 flex flex-col gap-4 border border-border bg-card rounded-xl p-4 shadow-sm">
            <h2 className="text-sm font-bold tracking-wide uppercase text-muted-foreground flex items-center justify-between pb-2 border-b border-border">
              <span>Ranked Candidates</span>
              <span className="text-xs bg-muted text-muted-foreground font-semibold px-2 py-0.5 rounded-full">
                {retrievalMutation.data.entities.length} shown
              </span>
            </h2>

            {retrievalMutation.data.entities.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center gap-2">
                <Info className="size-8 text-muted-foreground" />
                <p className="text-xs font-semibold text-muted-foreground">No candidate matches found</p>
                <p className="text-[10px] text-muted-foreground/80 max-w-[200px]">Try adjusting options or typing different keywords.</p>
              </div>
            ) : (
              <div className="flex flex-col gap-2 max-h-[600px] overflow-y-auto pr-1">
                {retrievalMutation.data.entities.map((cand, idx) => (
                  <div
                    key={cand.entity.id}
                    onClick={() => setSelectedEntity(cand)}
                    className={`flex flex-col gap-1.5 p-3 rounded-lg border text-left cursor-pointer transition-all hover:bg-muted/30 ${
                      selectedEntity?.entity.id === cand.entity.id
                        ? "border-violet-300 dark:border-violet-900 bg-violet-50/30 dark:bg-violet-950/20 ring-1 ring-violet-200 dark:ring-violet-800"
                        : "border-border bg-muted/10"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex flex-col min-w-0">
                        <span className="text-[10px] font-bold text-violet-600 dark:text-violet-400">
                          #{idx + 1} &bull; {cand.entity.entity_type}
                        </span>
                        <h3 className="text-sm font-bold text-foreground truncate max-w-[200px] sm:max-w-none">
                          {cand.entity.title}
                        </h3>
                      </div>
                      <div className="flex flex-col items-end shrink-0">
                        <span className="text-xs font-black text-foreground">
                          {cand.score.toFixed(3)}
                        </span>
                        <span className="text-[9px] text-muted-foreground italic">
                          Score
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                      <span className="px-1.5 py-0.5 rounded bg-muted font-mono">{cand.match_reason}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right Panel: Selected Entity detail information */}
          <div className="lg:col-span-3 flex flex-col gap-6">
            {selectedEntity ? (
              <div className="flex flex-col gap-6">
                
                {/* Entity Details Card */}
                <div className="border border-border bg-card rounded-xl p-5 shadow-sm flex flex-col gap-4">
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 border-b border-border pb-3">
                    <div className="flex flex-col min-w-0">
                      <span className="text-xs font-bold text-violet-600 dark:text-violet-400">
                        {selectedEntity.entity.entity_type}
                      </span>
                      <h2 className="text-lg font-extrabold text-foreground tracking-tight">
                        {selectedEntity.entity.title}
                      </h2>
                    </div>
                    <div className="text-right shrink-0">
                      <span className="text-2xl font-black text-violet-600 dark:text-violet-400">
                        {selectedEntity.score.toFixed(4)}
                      </span>
                      <p className="text-[10px] text-muted-foreground">relevance score</p>
                    </div>
                  </div>

                  {/* Verbatim Content */}
                  <div className="flex flex-col gap-1.5">
                    <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">Concept Content</span>
                    <p className="text-xs text-foreground bg-muted/20 border border-border/50 rounded-lg p-3 whitespace-pre-wrap leading-relaxed font-medium">
                      {selectedEntity.entity.content}
                    </p>
                  </div>
                </div>

                {/* Scopes Decomposition */}
                <div className="border border-border bg-card rounded-xl p-5 shadow-sm flex flex-col gap-3">
                  <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                    <Info className="size-4 text-violet-600" /> Scoring Features breakdown
                  </h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                    {/* Constituent scores display */}
                    <div className="border border-border bg-muted/5 rounded-lg p-2.5 flex flex-col gap-0.5">
                      <span className="text-[10px] text-muted-foreground uppercase font-semibold">Title match</span>
                      <span className="text-sm font-extrabold text-foreground">
                        {/* We don't have detailed breakdown properties exposed in RetrievedEntity,
                            so we can approximate or display the match_reason.
                            Let's estimate title score based on match reason code */}
                        {selectedEntity.match_reason.startsWith("title_exact") ? "1.000" :
                         selectedEntity.match_reason.startsWith("title_prefix") ? "0.800" :
                         selectedEntity.match_reason.startsWith("title_contains") ? "0.600" :
                         selectedEntity.match_reason.startsWith("title_term") ? "0.400" : "0.000"}
                      </span>
                    </div>
                    <div className="border border-border bg-muted/5 rounded-lg p-2.5 flex flex-col gap-0.5">
                      <span className="text-[10px] text-muted-foreground uppercase font-semibold">Content match</span>
                      <span className="text-sm font-extrabold text-foreground">
                        {selectedEntity.match_reason === "content_contains" ? "1.000" : "0.000"}
                      </span>
                    </div>
                    <div className="border border-border bg-muted/5 rounded-lg p-2.5 flex flex-col gap-0.5">
                      <span className="text-[10px] text-muted-foreground uppercase font-semibold">Graph hops</span>
                      <span className="text-sm font-extrabold text-foreground">
                        {selectedEntity.match_reason === "graph_neighbor" ? "Hop Neighbor" : "Direct Seed"}
                      </span>
                    </div>
                    <div className="border border-border bg-muted/5 rounded-lg p-2.5 flex flex-col gap-0.5">
                      <span className="text-[10px] text-muted-foreground uppercase font-semibold">Traceable</span>
                      <span className="text-sm font-extrabold text-foreground">
                        {selectedEntity.evidence.length > 0 ? "Yes" : "No"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Relationships display */}
                {includeRelationships && (
                  <div className="border border-border bg-card rounded-xl p-5 shadow-sm flex flex-col gap-4">
                    <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1 pb-2 border-b border-border">
                      <LinkIcon className="size-4 text-violet-600" /> Graph Relationships ({selectedEntity.outgoing_relationships.length + selectedEntity.incoming_relationships.length})
                    </h3>
                    
                    {selectedEntity.outgoing_relationships.length === 0 && selectedEntity.incoming_relationships.length === 0 ? (
                      <p className="text-xs text-muted-foreground italic py-2">No relationships resolved within search bounds.</p>
                    ) : (
                      <div className="flex flex-col gap-3 max-h-[300px] overflow-y-auto pr-1">
                        {selectedEntity.outgoing_relationships.map(rel => (
                          <div key={rel.id} className="flex items-center justify-between text-xs p-2 bg-muted/20 border border-border/50 rounded-lg">
                            <div className="flex items-center gap-1.5 min-w-0">
                              <span className="px-1.5 py-0.5 bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-400 rounded-[4px] text-[10px] font-bold shrink-0">OUTGOING</span>
                              <span className="font-semibold text-foreground shrink-0">{selectedEntity.entity.title}</span>
                              <span className="text-muted-foreground font-mono text-[10px]">{rel.relationship_type.toLowerCase()}</span>
                              <span className="font-bold text-foreground truncate">{rel.target_entity_id}</span>
                            </div>
                            <span className="text-[10px] font-bold bg-muted px-1.5 py-0.5 rounded text-muted-foreground">Conf: {rel.confidence.toFixed(2)}</span>
                          </div>
                        ))}
                        {selectedEntity.incoming_relationships.map(rel => (
                          <div key={rel.id} className="flex items-center justify-between text-xs p-2 bg-muted/20 border border-border/50 rounded-lg">
                            <div className="flex items-center gap-1.5 min-w-0">
                              <span className="px-1.5 py-0.5 bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-400 rounded-[4px] text-[10px] font-bold shrink-0">INCOMING</span>
                              <span className="font-bold text-foreground truncate shrink-0">{rel.source_entity_id}</span>
                              <span className="text-muted-foreground font-mono text-[10px]">{rel.relationship_type.toLowerCase()}</span>
                              <span className="font-semibold text-foreground truncate">{selectedEntity.entity.title}</span>
                            </div>
                            <span className="text-[10px] font-bold bg-muted px-1.5 py-0.5 rounded text-muted-foreground">Conf: {rel.confidence.toFixed(2)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Evidence coordinates display */}
                {includeEvidence && (
                  <div className="border border-border bg-card rounded-xl p-5 shadow-sm flex flex-col gap-4">
                    <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1 pb-2 border-b border-border">
                      <FileText className="size-4 text-violet-600" /> Evidence Provenance coordinates ({selectedEntity.evidence.length})
                    </h3>
                    
                    {selectedEntity.evidence.length === 0 ? (
                      <p className="text-xs text-muted-foreground italic py-2">No evidence coordinates linked.</p>
                    ) : (
                      <div className="flex flex-col gap-3 max-h-[300px] overflow-y-auto pr-1">
                        {selectedEntity.evidence.map(ev => {
                          const isStale = ev.x0 === null || ev.page_number === null;
                          return (
                            <div key={ev.id} className="flex flex-col gap-2 p-3 bg-muted/20 border border-border/50 rounded-lg text-left">
                              <div className="flex items-center justify-between text-xs border-b border-border/30 pb-1.5">
                                <div className="flex items-center gap-1.5">
                                  <span className="font-bold text-foreground">Page {ev.page_number || "?"}</span>
                                  {ev.section_title && (
                                    <span className="text-[10px] text-muted-foreground">in &quot;{ev.section_title}&quot;</span>
                                  )}
                                </div>
                                {isStale ? (
                                  <span className="px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-400 font-bold text-[9px]">
                                    Source passage unavailable (Stale)
                                  </span>
                                ) : (
                                  <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400 font-bold text-[9px]">
                                    Active Coordinates
                                  </span>
                                )}
                              </div>
                              <p className="text-xs text-foreground italic bg-background/50 p-2 rounded border border-border/30 font-medium">
                                &quot;{ev.text_reference || "No verbatim reference text"}&quot;
                              </p>
                              {!isStale && (
                                <span className="text-[9px] font-mono text-muted-foreground">
                                  Bounding Box: [{ev.x0?.toFixed(1)}, {ev.y0?.toFixed(1)}, {ev.x1?.toFixed(1)}, {ev.y1?.toFixed(1)}]
                                </span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                {/* Source passages display */}
                {includePassages && includeEvidence && (
                  <div className="border border-border bg-card rounded-xl p-5 shadow-sm flex flex-col gap-4">
                    <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1 pb-2 border-b border-border">
                      <BookOpen className="size-4 text-violet-600" /> Resolved Source passages ({selectedEntity.passages.length})
                    </h3>

                    {selectedEntity.passages.length === 0 ? (
                      <p className="text-xs text-muted-foreground italic py-2">No overlapping text passages resolved.</p>
                    ) : (
                      <div className="flex flex-col gap-4 max-h-[400px] overflow-y-auto pr-1">
                        {selectedEntity.passages.map(pass => (
                          <div key={pass.block_id} className="flex flex-col gap-2 p-3 bg-muted/20 border border-border/50 rounded-lg text-left">
                            <div className="flex items-center justify-between text-xs border-b border-border/30 pb-1.5">
                              <span className="font-bold text-foreground">Block ID: {pass.block_id} &bull; Page {pass.page_number}</span>
                              <span className="px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono text-[9px]">
                                {pass.block_type}
                              </span>
                            </div>
                            <div className="flex flex-col gap-1.5">
                              <span className="text-[9px] font-bold text-violet-600 dark:text-violet-400 uppercase">Primary Passage</span>
                              <p className="text-xs text-foreground bg-background/50 border border-border/30 rounded-lg p-3 whitespace-pre-wrap leading-relaxed font-semibold">
                                {pass.text}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

              </div>
            ) : (
              <div className="border border-border bg-card rounded-xl p-8 shadow-sm flex flex-col items-center justify-center text-center gap-3 min-h-[300px]">
                <Info className="size-10 text-muted-foreground" />
                <h3 className="text-sm font-bold text-foreground">No candidate selected</h3>
                <p className="text-xs text-muted-foreground max-w-[240px]">
                  Select any candidate on the left to inspect its ranking features, evidence logs, and verbatim passages.
                </p>
              </div>
            )}
          </div>

          {/* 4. Retrieval Provenance panel */}
          <div className="lg:col-span-5 border border-border bg-muted/10 rounded-xl p-4 flex flex-col gap-3">
            <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
              <Clock className="size-4 text-violet-600" /> Pipeline Provenance Metadata
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-left pt-1">
              <div className="flex flex-col">
                <span className="text-[10px] text-muted-foreground font-semibold uppercase">Resolved version</span>
                <span className="text-xs font-mono font-bold text-foreground truncate">
                  {retrievalMutation.data.provenance.knowledge_version_id}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-[10px] text-muted-foreground font-semibold uppercase">Approval Version</span>
                <span className="text-xs font-bold text-foreground">
                  {retrievalMutation.data.provenance.approval_version}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-[10px] text-muted-foreground font-semibold uppercase">Query Terms</span>
                <span className="text-xs font-bold text-foreground truncate">
                  {retrievalMutation.data.provenance.query_terms.join(", ") || "None"}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-[10px] text-muted-foreground font-semibold uppercase">Candidates Considered</span>
                <span className="text-xs font-bold text-foreground">
                  {retrievalMutation.data.provenance.total_candidates_considered} (Graph Total: {retrievalMutation.data.total_entity_count})
                </span>
              </div>
            </div>
          </div>

        </div>
      )}

    </div>
  );
}
