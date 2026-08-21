import { useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  listFinalizedVersions,
  listEntities,
  getEntityEvidence,
  getEntityRelationships
} from "@/services/knowledgeService";
import { getDocument } from "@/services/documentService";
import { Button } from "@/components/ui/button";
import { StatisticsCard } from "@/components/ui/card";
import {
  ArrowLeft,
  BookOpen,
  Link as LinkIcon,
  FileText,
  ChevronLeft,
  ChevronRight,
  Info,
  CheckCircle2,
  AlertTriangle,
  Layers,
  Search,
  ExternalLink
} from "lucide-react";

export default function KnowledgeExplorerPage() {
  const { id: documentId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // State parameters
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [entityTypeFilter, setEntityTypeFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [page, setPage] = useState<number>(0);
  const limit = 10;

  // View state toggle for responsive layouts on mobile
  const [mobileDetailView, setMobileDetailView] = useState<boolean>(false);

  // 1. Fetch Document Details
  const docQuery = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => getDocument(documentId!),
    enabled: !!documentId,
  });

  // 2. Fetch Version List (to populate dropdown version switcher)
  const versionsQuery = useQuery({
    queryKey: ["versionsList", documentId],
    queryFn: () => listFinalizedVersions(documentId!),
    enabled: !!documentId,
  });

  // Automatically select the latest finalized version when the list loads
  useMemo(() => {
    if (versionsQuery.data && versionsQuery.data.length > 0 && !selectedVersionId) {
      setSelectedVersionId(versionsQuery.data[0].id);
    }
  }, [versionsQuery.data, selectedVersionId]);

  const selectedVersion = useMemo(() => {
    return versionsQuery.data?.find(v => v.id === selectedVersionId) || null;
  }, [versionsQuery.data, selectedVersionId]);

  // 3. Fetch all entities under this version to construct a map for relationship lookup
  const allEntitiesLookupQuery = useQuery({
    queryKey: ["allEntitiesLookup", selectedVersionId],
    queryFn: () => listEntities(selectedVersionId!, { limit: 1000 }),
    enabled: !!selectedVersionId,
  });

  const entityLookupMap = useMemo(() => {
    const map: Record<string, { title: string; entity_type: string; stable_id: string }> = {};
    if (allEntitiesLookupQuery.data?.items) {
      allEntitiesLookupQuery.data.items.forEach(item => {
        map[item.id] = {
          title: item.title,
          entity_type: item.entity_type,
          stable_id: item.stable_id
        };
      });
    }
    return map;
  }, [allEntitiesLookupQuery.data]);

  // 4. Fetch Paginated & Filtered Entities for the Browser panel
  const offset = page * limit;
  const apiEntityType = entityTypeFilter === "ALL" ? undefined : entityTypeFilter;

  const entitiesQuery = useQuery({
    queryKey: ["entitiesList", selectedVersionId, apiEntityType, offset],
    queryFn: () => listEntities(selectedVersionId!, {
      entity_type: apiEntityType,
      limit,
      offset
    }),
    enabled: !!selectedVersionId,
  });

  // Selected Entity Details
  const selectedEntity = useMemo(() => {
    if (!selectedEntityId) return null;
    return allEntitiesLookupQuery.data?.items.find(e => e.id === selectedEntityId) || null;
  }, [allEntitiesLookupQuery.data, selectedEntityId]);

  // 5. Fetch Evidence for the Selected Entity
  const evidenceQuery = useQuery({
    queryKey: ["entityEvidence", selectedVersionId, selectedEntityId],
    queryFn: () => getEntityEvidence(selectedVersionId!, selectedEntityId!),
    enabled: !!selectedVersionId && !!selectedEntityId,
  });

  // 6. Fetch Relationships for the Selected Entity
  const relationshipsQuery = useQuery({
    queryKey: ["entityRelationships", selectedVersionId, selectedEntityId],
    queryFn: () => getEntityRelationships(selectedVersionId!, selectedEntityId!),
    enabled: !!selectedVersionId && !!selectedEntityId,
  });

  // Apply search filtering locally over the current page's items
  const filteredEntities = useMemo(() => {
    const items = entitiesQuery.data?.items || [];
    if (!searchQuery.trim()) return items;
    const query = searchQuery.toLowerCase();
    return items.filter(e => e.title.toLowerCase().includes(query));
  }, [entitiesQuery.data, searchQuery]);

  const doc = docQuery.data?.data;

  // Category Color Map helper
  const getCategoryColor = (cat: string) => {
    switch (cat) {
      case "CHAPTER":
        return "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 border-amber-200 dark:border-amber-800/50";
      case "SECTION":
        return "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300 border-orange-200 dark:border-orange-800/50";
      case "TOPIC":
        return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300 border-yellow-200 dark:border-yellow-800/50";
      case "CONCEPT":
        return "bg-violet-100 text-violet-800 dark:bg-violet-900/30 dark:text-violet-300 border-violet-200 dark:border-violet-800/50";
      case "DEFINITION":
        return "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 border-blue-200 dark:border-blue-800/50";
      case "THEOREM":
        return "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800/50";
      case "PROOF":
        return "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300 border-purple-200 dark:border-purple-800/50";
      case "FORMULA":
        return "bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-300 border-pink-200 dark:border-pink-800/50";
      case "ALGORITHM":
        return "bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-300 border-cyan-200 dark:border-cyan-800/50";
      case "EXAMPLE":
        return "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800/50";
      case "EXERCISE":
        return "bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300 border-teal-200 dark:border-teal-800/50";
      case "SUMMARY":
        return "bg-lime-100 text-lime-800 dark:bg-lime-900/30 dark:text-lime-300 border-lime-200 dark:border-lime-800/50";
      default:
        return "bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300 border-gray-200 dark:border-gray-800/50";
    }
  };

  // Loading States render
  const isGlobalLoading = docQuery.isLoading || versionsQuery.isLoading;

  if (isGlobalLoading) {
    return (
      <div className="flex flex-col gap-6 animate-pulse p-4">
        <div className="h-10 bg-muted rounded w-2/3"></div>
        <div className="h-32 bg-muted rounded"></div>
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          <div className="lg:col-span-2 h-96 bg-muted rounded"></div>
          <div className="lg:col-span-3 h-96 bg-muted rounded"></div>
        </div>
      </div>
    );
  }

  if (!versionsQuery.data || versionsQuery.data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-6 text-center max-w-lg mx-auto p-4">
        <div className="p-4 bg-amber-50 dark:bg-amber-950/20 text-amber-600 rounded-full">
          <AlertTriangle className="size-12 animate-bounce" />
        </div>
        <h2 className="text-2xl font-bold tracking-tight">No Finalized Knowledge Available</h2>
        <p className="text-muted-foreground text-sm">
          This document has not been compiled into the canonical knowledge model yet. 
          To generate knowledge, complete the human review and validate/approve the academic graph.
        </p>
        <div className="flex gap-4">
          <Button
            onClick={() => navigate(-1)}
            variant="outline"
            className="cursor-pointer"
          >
            Go Back
          </Button>
          {doc?.upload_id && (
            <Button
              onClick={() => navigate(`/academic/review/${doc.upload_id}`)}
              className="bg-violet-600 hover:bg-violet-700 text-white cursor-pointer"
            >
              Go to Academic Review
            </Button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-1 sm:p-2">
      {/* 1. Header Navigation */}
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
            {doc?.metadata?.title || "Knowledge Explorer"}
          </h1>
          <p className="text-xs text-muted-foreground">
            Document ID: <code className="select-all font-mono">{documentId}</code>
          </p>
        </div>

        {/* Version Selector */}
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-muted-foreground">Version:</span>
          <select
            value={selectedVersionId || ""}
            onChange={(e) => {
              setSelectedVersionId(e.target.value);
              setSelectedEntityId(null);
              setPage(0);
            }}
            className="bg-muted text-foreground text-xs font-medium border border-input rounded-lg px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-violet-500 cursor-pointer"
          >
            {versionsQuery.data.map((v) => (
              <option key={v.id} value={v.id}>
                Approval Version {v.approval_version} ({new Date(v.created_at * 1000).toLocaleDateString()})
              </option>
            ))}
          </select>

          {doc?.upload_id && (
            <Button
              onClick={() => navigate(`/academic/review/${doc.upload_id}`)}
              variant="outline"
              size="sm"
              className="gap-1 px-3 py-1.5 text-xs font-semibold border-violet-200 text-violet-700 hover:bg-violet-50 dark:border-violet-900/50 dark:text-violet-400 dark:hover:bg-violet-950/20 cursor-pointer"
            >
              Academic Review <ExternalLink className="size-3" />
            </Button>
          )}
        </div>
      </div>

      {/* 2. Version Metadata Summary Cards */}
      {selectedVersion && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatisticsCard
            title="Ingestion Status"
            value={selectedVersion.status}
            icon={CheckCircle2}
          />
          <StatisticsCard
            title="Total Entities"
            value={selectedVersion.entity_count}
            icon={Layers}
          />
          <StatisticsCard
            title="Relationships"
            value={selectedVersion.relationship_count}
            icon={LinkIcon}
          />
          <StatisticsCard
            title="Traceable Evidence"
            value={selectedVersion.evidence_count}
            icon={FileText}
          />
        </div>
      )}

      {/* 3. Split Layout Browser / Detail Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        
        {/* Left Panel: Entity Browser (Hidden on mobile when detail view is active) */}
        <div className={`lg:col-span-2 flex flex-col gap-4 border border-border bg-card rounded-xl p-4 shadow-sm ${mobileDetailView ? "hidden lg:flex" : "flex"}`}>
          <div className="flex flex-col gap-2 pb-3 border-b border-border">
            <h2 className="text-sm font-bold tracking-wide uppercase text-muted-foreground flex items-center gap-1.5">
              <BookOpen className="size-4" /> Entity Browser
            </h2>
          </div>

          {/* Browser Controls */}
          <div className="flex flex-col sm:flex-row lg:flex-col gap-2">
            {/* Category Filter */}
            <div className="flex-1">
              <select
                value={entityTypeFilter}
                onChange={(e) => {
                  setEntityTypeFilter(e.target.value);
                  setPage(0);
                }}
                className="w-full bg-background border border-input rounded-lg px-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-violet-500 cursor-pointer"
              >
                <option value="ALL">All Entity Types</option>
                <option value="CHAPTER">CHAPTER</option>
                <option value="SECTION">SECTION</option>
                <option value="TOPIC">TOPIC</option>
                <option value="CONCEPT">CONCEPT</option>
                <option value="DEFINITION">DEFINITION</option>
                <option value="THEOREM">THEOREM</option>
                <option value="PROOF">PROOF</option>
                <option value="FORMULA">FORMULA</option>
                <option value="ALGORITHM">ALGORITHM</option>
                <option value="EXAMPLE">EXAMPLE</option>
                <option value="EXERCISE">EXERCISE</option>
                <option value="SUMMARY">SUMMARY</option>
              </select>
            </div>

            {/* Local Title Search (Strictly labeled as local page filter) */}
            <div className="relative flex-1">
              <span className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-muted-foreground">
                <Search className="size-3.5" />
              </span>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter loaded page titles..."
                className="w-full bg-background border border-input rounded-lg pl-9 pr-3 py-2 text-xs focus:outline-none focus:ring-1 focus:ring-violet-500"
              />
            </div>
          </div>

          {/* Entities List */}
          {entitiesQuery.isLoading ? (
            <div className="flex flex-col gap-2 py-8 animate-pulse">
              <div className="h-8 bg-muted rounded"></div>
              <div className="h-8 bg-muted rounded"></div>
              <div className="h-8 bg-muted rounded"></div>
            </div>
          ) : filteredEntities.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground gap-2">
              <Info className="size-8 text-muted-foreground" />
              <p className="text-xs font-medium">No entities match the filters on this page.</p>
            </div>
          ) : (
            <div className="flex flex-col gap-1.5 max-h-[50vh] lg:max-h-[60vh] overflow-y-auto pr-1">
              {filteredEntities.map((e) => (
                <button
                  key={e.id}
                  onClick={() => {
                    setSelectedEntityId(e.id);
                    setMobileDetailView(true);
                  }}
                  className={`w-full text-left p-3 rounded-lg border text-xs transition-all cursor-pointer flex flex-col gap-1.5 ${
                    selectedEntityId === e.id
                      ? "bg-violet-50/50 border-violet-300 dark:bg-violet-950/20 dark:border-violet-800"
                      : "bg-background border-border hover:bg-muted/50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold border tracking-wide uppercase ${getCategoryColor(e.entity_type)}`}>
                      {e.entity_type}
                    </span>
                    <span className="text-[10px] text-muted-foreground font-mono truncate max-w-[120px]">
                      {e.stable_id.length > 25 ? `${e.stable_id.substring(0, 22)}...` : e.stable_id}
                    </span>
                  </div>
                  <h3 className="font-semibold text-foreground leading-tight truncate">
                    {e.title}
                  </h3>
                </button>
              ))}
            </div>
          )}

          {/* Pagination Controls */}
          {entitiesQuery.data && (
            <div className="flex items-center justify-between border-t border-border pt-3 mt-auto">
              <span className="text-[10px] text-muted-foreground">
                Showing {offset + 1}-{Math.min(offset + limit, entitiesQuery.data.total)} of {entitiesQuery.data.total}
              </span>
              <div className="flex items-center gap-1">
                <Button
                  onClick={() => setPage(p => Math.max(p - 1, 0))}
                  disabled={page === 0}
                  variant="outline"
                  size="sm"
                  className="p-1 size-7 cursor-pointer"
                >
                  <ChevronLeft className="size-4" />
                </Button>
                <Button
                  onClick={() => setPage(p => p + 1)}
                  disabled={offset + limit >= entitiesQuery.data.total}
                  variant="outline"
                  size="sm"
                  className="p-1 size-7 cursor-pointer"
                >
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Right Panel: Entity Inspector */}
        <div className={`lg:col-span-3 flex flex-col gap-6 border border-border bg-card rounded-xl p-6 shadow-sm ${!mobileDetailView ? "hidden lg:flex" : "flex"}`}>
          {/* Back button for mobile view */}
          {mobileDetailView && (
            <Button
              onClick={() => setMobileDetailView(false)}
              variant="outline"
              size="sm"
              className="lg:hidden gap-1.5 self-start mb-2 cursor-pointer"
            >
              <ArrowLeft className="size-4" /> Back to Browser
            </Button>
          )}

          {!selectedEntity ? (
            <div className="flex flex-col items-center justify-center py-24 text-center text-muted-foreground gap-3 max-w-sm mx-auto">
              <Layers className="size-10 text-muted-foreground" />
              <h3 className="font-bold text-foreground text-sm">Entity Inspector</h3>
              <p className="text-xs">
                Select an entity from the browser to inspect its properties, evidence layouts, and relational mappings.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-6">
              
              {/* Entity Base info */}
              <div className="flex flex-col gap-2 pb-4 border-b border-border">
                <div className="flex items-center gap-2">
                  <span className={`px-2.5 py-0.5 rounded text-xs font-bold border tracking-wide uppercase ${getCategoryColor(selectedEntity.entity_type)}`}>
                    {selectedEntity.entity_type}
                  </span>
                  <span className="text-[10px] text-muted-foreground font-mono">
                    Stable ID: <code className="bg-muted px-1.5 py-0.5 rounded font-semibold select-all text-violet-600 dark:text-violet-400">{selectedEntity.stable_id}</code>
                  </span>
                </div>
                <h2 className="text-xl font-bold tracking-tight text-foreground">
                  {selectedEntity.title}
                </h2>
              </div>

              {/* Entity Content */}
              <div className="flex flex-col gap-2">
                <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wide">Content Definition</h3>
                <div className="p-4 bg-muted/30 rounded-lg text-sm leading-relaxed border border-border text-foreground">
                  {selectedEntity.content}
                </div>
              </div>

              {/* Entity Relationships Visualization */}
              <div className="flex flex-col gap-4">
                <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                  <LinkIcon className="size-4" /> Graph Connections
                </h3>
                {relationshipsQuery.isLoading ? (
                  <div className="h-20 bg-muted animate-pulse rounded"></div>
                ) : !relationshipsQuery.data || 
                  (relationshipsQuery.data.incoming.length === 0 && relationshipsQuery.data.outgoing.length === 0) ? (
                  <div className="p-3 bg-muted/10 text-muted-foreground text-xs rounded-lg text-center font-medium">
                    This entity has no relationships in this version.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Outgoing relationships */}
                    <div className="flex flex-col gap-2 border border-border rounded-lg p-3 bg-background">
                      <h4 className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider border-b border-border pb-1.5 mb-1 flex justify-between">
                        <span>Outgoing Edges</span>
                        <span className="text-[9px] text-violet-500 font-medium">source → target</span>
                      </h4>
                      {relationshipsQuery.data.outgoing.length === 0 ? (
                        <p className="text-[11px] text-muted-foreground italic py-1">No outgoing edges.</p>
                      ) : (
                        <ul className="flex flex-col gap-1.5">
                          {relationshipsQuery.data.outgoing.map((r) => {
                            const targetMeta = entityLookupMap[r.target_entity_id];
                            return (
                              <li key={r.id} className="text-xs flex flex-wrap items-center gap-1">
                                <span className="font-bold text-violet-600 dark:text-violet-400 font-mono text-[10px]">
                                  {r.relationship_type.toLowerCase()}
                                </span>
                                <span className="text-muted-foreground text-[11px]">→</span>
                                {targetMeta ? (
                                  <span className="font-semibold text-foreground truncate max-w-[150px] inline-flex items-center gap-1" title={targetMeta.title}>
                                    {targetMeta.title}
                                    <span className="text-[9px] px-1 bg-muted border border-border rounded font-normal text-muted-foreground tracking-wide uppercase scale-90">
                                      {targetMeta.entity_type}
                                    </span>
                                  </span>
                                ) : (
                                  <span className="font-mono text-[11px] text-muted-foreground truncate max-w-[120px]">{r.target_entity_id}</span>
                                )}
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </div>

                    {/* Incoming relationships */}
                    <div className="flex flex-col gap-2 border border-border rounded-lg p-3 bg-background">
                      <h4 className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider border-b border-border pb-1.5 mb-1 flex justify-between">
                        <span>Incoming Edges</span>
                        <span className="text-[9px] text-violet-500 font-medium font-mono">target ← source</span>
                      </h4>
                      {relationshipsQuery.data.incoming.length === 0 ? (
                        <p className="text-[11px] text-muted-foreground italic py-1">No incoming edges.</p>
                      ) : (
                        <ul className="flex flex-col gap-1.5">
                          {relationshipsQuery.data.incoming.map((r) => {
                            const sourceMeta = entityLookupMap[r.source_entity_id];
                            return (
                              <li key={r.id} className="text-xs flex flex-wrap items-center gap-1">
                                <span className="font-bold text-violet-600 dark:text-violet-400 font-mono text-[10px]">
                                  {r.relationship_type.toLowerCase()}
                                </span>
                                <span className="text-muted-foreground text-[11px]">←</span>
                                {sourceMeta ? (
                                  <span className="font-semibold text-foreground truncate max-w-[150px] inline-flex items-center gap-1" title={sourceMeta.title}>
                                    {sourceMeta.title}
                                    <span className="text-[9px] px-1 bg-muted border border-border rounded font-normal text-muted-foreground tracking-wide uppercase scale-90">
                                      {sourceMeta.entity_type}
                                    </span>
                                  </span>
                                ) : (
                                  <span className="font-mono text-[11px] text-muted-foreground truncate max-w-[120px]">{r.source_entity_id}</span>
                                )}
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* Entity Evidence */}
              <div className="flex flex-col gap-4">
                <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wide flex items-center gap-1.5">
                  <FileText className="size-4" /> Traceability Evidence
                </h3>
                {evidenceQuery.isLoading ? (
                  <div className="h-16 bg-muted animate-pulse rounded"></div>
                ) : !evidenceQuery.data || evidenceQuery.data.length === 0 ? (
                  <div className="p-3 bg-muted/10 text-muted-foreground text-xs rounded-lg text-center font-medium">
                    No source evidence coordinates exist for this entity.
                  </div>
                ) : (
                  <div className="flex flex-col gap-3">
                    {evidenceQuery.data.map((ev) => (
                      <div key={ev.id} className="flex flex-col gap-2 p-4 bg-muted/15 border border-border rounded-lg text-xs">
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-2 mb-1">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-violet-600 dark:text-violet-400">
                              {ev.page_number !== null ? `Page ${ev.page_number}` : "Page: Unknown"}
                            </span>
                            {ev.section_title && (
                              <span className="text-muted-foreground">
                                • Section: <span className="font-medium text-foreground">{ev.section_title}</span>
                              </span>
                            )}
                          </div>
                          <span className="px-1.5 py-0.5 rounded text-[9px] border bg-background font-semibold text-muted-foreground select-none uppercase tracking-wide">
                            Prov: {ev.provenance}
                          </span>
                        </div>

                        {ev.text_reference && (
                          <div className="text-[11px] italic bg-background p-2 border border-border rounded font-mono text-muted-foreground leading-relaxed">
                            "{ev.text_reference}"
                          </div>
                        )}

                        {/* Coordinates presented strictly as read-only metadata (no coordinate interaction) */}
                        {ev.x0 !== null && (
                          <div className="text-[10px] text-muted-foreground font-mono flex items-center gap-2 pt-1">
                            <span>Layout Coordinates:</span>
                            <span className="bg-background border border-border px-1.5 py-0.5 rounded">
                              x: [{ev.x0.toFixed(1)}, {ev.x1?.toFixed(1)}], y: [{ev.y0?.toFixed(1)}, {ev.y1?.toFixed(1)}]
                            </span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Navigation path back to review */}
              <div className="mt-4 pt-4 border-t border-border flex items-center justify-between text-xs text-muted-foreground bg-muted/10 p-3 rounded-lg border border-dashed">
                <span className="flex items-center gap-1">
                  <Info className="size-3.5 text-violet-500" /> Need to modify or correct this knowledge mapping?
                </span>
                {doc?.upload_id && (
                  <Button
                    onClick={() => navigate(`/academic/review/${doc.upload_id}`)}
                    variant="link"
                    className="p-0 h-auto text-xs text-violet-600 hover:text-violet-700 dark:text-violet-400 dark:hover:text-violet-300 font-semibold cursor-pointer"
                  >
                    Go back to Academic Review
                  </Button>
                )}
              </div>

            </div>
          )}
        </div>

      </div>
    </div>
  );
}
