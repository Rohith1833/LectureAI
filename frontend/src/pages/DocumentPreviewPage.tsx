import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { InfoCard } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/form";
import {
  getDocument,
  getDocumentBlocks,
  getDocumentStatistics,
} from "@/services/documentService";
import {
  FileText,
  Layers,
  ArrowLeft,
  Cpu,
  Bookmark,
  Calendar,
  User,
  Hash,
  Activity,
} from "lucide-react";

export default function DocumentPreviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<"metadata" | "blocks" | "tables" | "images">("metadata");
  const [selectedPageFilter, setSelectedPageFilter] = useState<number | null>(null);
  const [showRawJson, setShowRawJson] = useState<boolean>(false);

  // 1. Fetch Document Base Metadata
  const docQuery = useQuery({
    queryKey: ["document", id],
    queryFn: () => getDocument(id!),
    enabled: !!id,
  });

  // 2. Fetch Document Extraction Blocks, Tables, and Images
  const blocksQuery = useQuery({
    queryKey: ["documentBlocks", id],
    queryFn: () => getDocumentBlocks(id!),
    enabled: !!id,
  });

  // 3. Fetch Document Extraction Statistics
  const statsQuery = useQuery({
    queryKey: ["documentStatistics", id],
    queryFn: () => getDocumentStatistics(id!),
    enabled: !!id,
  });

  const isLoading = docQuery.isLoading || blocksQuery.isLoading || statsQuery.isLoading;
  const isError = docQuery.isError || blocksQuery.isError || statsQuery.isError;

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="text-center space-y-3">
          <LoaderSpinner />
          <p className="text-sm text-muted-foreground animate-pulse">Loading extracted document structures...</p>
        </div>
      </div>
    );
  }

  if (isError || !docQuery.data || !blocksQuery.data) {
    return (
      <div className="max-w-xl mx-auto space-y-4 py-8">
        <div className="p-4 border border-red-500/20 bg-red-500/5 text-red-700 dark:text-red-400 rounded-xl">
          <h4 className="font-semibold text-sm">Failed to Load Document Details</h4>
          <p className="text-xs leading-normal mt-1">
            Could not fetch layout nodes or database records for Document ID: <code>{id}</code>.
          </p>
        </div>
        <div className="flex justify-center">
          <Button variant="outline" onClick={() => navigate("/upload")}>
            <ArrowLeft className="size-4 mr-2" /> Back to Upload
          </Button>
        </div>
      </div>
    );
  }

  const doc = docQuery.data.data;
  const stats = statsQuery.data?.data;
  const { blocks, tables, images } = blocksQuery.data.data;

  // Filter blocks by page number if selected
  const filteredBlocks = selectedPageFilter
    ? blocks.filter((b) => b.page_number === selectedPageFilter)
    : blocks;

  const filteredTables = selectedPageFilter
    ? tables.filter((t) => t.page_number === selectedPageFilter)
    : tables;

  const filteredImages = selectedPageFilter
    ? images.filter((img) => img.page_number === selectedPageFilter)
    : images;

  // Get unique page numbers
  const uniquePages = Array.from(new Set(blocks.map((b) => b.page_number))).sort((a, b) => a - b);

  return (
    <div className="space-y-6 py-6 max-w-6xl mx-auto">
      {/* Back button & Page Title */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="space-y-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/upload")}
            className="pl-0 gap-1.5 text-muted-foreground hover:text-foreground cursor-pointer"
          >
            <ArrowLeft className="size-4" /> Back to Upload
          </Button>
          <h1 className="text-2xl font-bold tracking-tight truncate max-w-xl">
            {doc.metadata?.title || "Extracted Document Review"}
          </h1>
          <p className="text-xs text-muted-foreground">
            Document ID: <code className="select-all font-mono text-violet-600 dark:text-violet-400">{doc.id}</code>
          </p>
        </div>

        {/* Raw JSON toggle */}
        <div className="flex items-center gap-2">
          <Switch
            checked={showRawJson}
            onCheckedChange={setShowRawJson}
            label="Raw JSON View"
            id="raw-json-toggle"
          />
        </div>
      </div>

      {/* Summary Stats Grid */}
      {stats && !showRawJson && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MiniStatCard label="Total Pages" val={stats.page_count} desc="PDF count" icon={FileText} />
          <MiniStatCard label="Total Words" val={stats.word_count} desc="Extracted text" icon={Activity} />
          <MiniStatCard label="Tables Found" val={stats.tables_count} desc="Cell matrices" icon={Layers} />
          <MiniStatCard label="Images Found" val={stats.images_count} desc="Visual shapes" icon={Cpu} />
        </div>
      )}

      {/* Audit Stats Banner */}
      {!showRawJson && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 p-4 rounded-xl border bg-muted/20 text-xs text-muted-foreground">
          <div>
            <strong>Extraction Engine:</strong> PyMuPDF v{doc.extraction_version}
          </div>
          <div>
            <strong>Processing Duration:</strong> {doc.processing_time} seconds
          </div>
          <div>
            <strong>Extracted On:</strong> {new Date(doc.extraction_timestamp).toLocaleString()}
          </div>
        </div>
      )}

      {/* Raw JSON Mode */}
      {showRawJson ? (
        <InfoCard title="Canonical Document Payload (Raw JSON)">
          <div className="max-h-[600px] overflow-y-auto rounded-lg border bg-muted/40 p-4 font-mono text-[11px] leading-relaxed select-all">
            <pre>
              {JSON.stringify(
                {
                  document: doc,
                  statistics: stats,
                  blocks: blocks,
                  tables: tables,
                  images: images,
                },
                null,
                2
              )}
            </pre>
          </div>
        </InfoCard>
      ) : (
        <div className="grid gap-6 md:grid-cols-4">
          {/* Sidebar Page Filters */}
          <div className="space-y-4 md:col-span-1">
            <InfoCard title="Filter Page">
              <div className="flex flex-col gap-1 max-h-72 overflow-y-auto pr-1">
                <Button
                  variant={selectedPageFilter === null ? "secondary" : "ghost"}
                  size="sm"
                  onClick={() => setSelectedPageFilter(null)}
                  className="w-full justify-start text-xs h-8 cursor-pointer"
                >
                  All Pages ({blocks.length} blocks)
                </Button>
                {uniquePages.map((pageNum) => {
                  const pCount = blocks.filter((b) => b.page_number === pageNum).length;
                  return (
                    <Button
                      key={pageNum}
                      variant={selectedPageFilter === pageNum ? "secondary" : "ghost"}
                      size="sm"
                      onClick={() => setSelectedPageFilter(pageNum)}
                      className="w-full justify-start text-xs h-8 cursor-pointer"
                    >
                      Page {pageNum} ({pCount} blocks)
                    </Button>
                  );
                })}
              </div>
            </InfoCard>
          </div>

          {/* Main Tabs preview content */}
          <div className="md:col-span-3 space-y-4">
            {/* Tab selection links */}
            <div className="flex border-b border-border">
              {(["metadata", "blocks", "tables", "images"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-2.5 text-xs font-semibold uppercase tracking-wider border-b-2 transition-all cursor-pointer ${
                    activeTab === tab
                      ? "border-primary text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* TAB CONTENT: Metadata */}
            {activeTab === "metadata" && (
              <InfoCard title="Extracted File Metadata" className="bg-card/50">
                <div className="divide-y divide-border/40 text-xs">
                  <MetadataRow label="Title" val={doc.metadata?.title} icon={Bookmark} />
                  <MetadataRow label="Author" val={doc.metadata?.author} icon={User} />
                  <MetadataRow label="Subject" val={doc.metadata?.subject} icon={FileText} />
                  <MetadataRow label="Keywords" val={doc.metadata?.keywords} icon={Hash} />
                  <MetadataRow label="PDF Version" val={doc.metadata?.pdf_version} icon={Layers} />
                  <MetadataRow label="Producer" val={doc.metadata?.producer} icon={Cpu} />
                  <MetadataRow label="Creation Date" val={doc.metadata?.creation_date} icon={Calendar} />
                  <MetadataRow label="Page Count" val={doc.metadata?.page_count} icon={FileText} />
                  <MetadataRow label="OCR Status" val={doc.status} icon={Activity} highlight />
                </div>
              </InfoCard>
            )}

            {/* TAB CONTENT: Blocks */}
            {activeTab === "blocks" && (
              <div className="space-y-4">
                {filteredBlocks.length === 0 ? (
                  <div className="p-8 text-center border border-dashed rounded-xl text-muted-foreground text-xs">
                    No text layout blocks found matching the selection.
                  </div>
                ) : (
                  filteredBlocks.map((b) => (
                    <div
                      key={b.block_id}
                      className="p-4 rounded-xl border bg-card/60 backdrop-blur-sm space-y-3 shadow-xs transition-hover hover:border-border/80"
                    >
                      {/* Block metadata header */}
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/20 pb-2 text-[10px] text-muted-foreground">
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded-full bg-violet-500/10 text-violet-700 dark:text-violet-400 font-bold uppercase tracking-wider font-mono">
                            {b.block_type}
                          </span>
                          {b.heading_level && (
                            <span className="px-1.5 py-0.5 rounded-md bg-amber-500/10 text-amber-700 font-bold font-mono">
                              H{b.heading_level}
                            </span>
                          )}
                          <span>
                            Page {b.page_number} • Order #{b.reading_order}
                          </span>
                        </div>
                        <div className="font-mono text-muted-foreground">
                          ID: <span className="select-all">{b.block_id}</span>
                        </div>
                      </div>

                      {/* Text content block */}
                      <p
                        className={`text-sm leading-relaxed text-foreground select-text whitespace-pre-wrap ${
                          b.block_type === "HEADING"
                            ? "font-bold text-base text-violet-700 dark:text-violet-400"
                            : b.block_type === "LIST"
                            ? "pl-4 list-item list-disc"
                            : b.block_type === "CAPTION"
                            ? "italic text-xs text-muted-foreground"
                            : ""
                        }`}
                      >
                        {b.text}
                      </p>

                      {/* Layout stats details footer */}
                      <div className="flex flex-wrap gap-x-4 gap-y-2 pt-2 border-t border-border/20 text-[10px] text-muted-foreground font-mono">
                        {b.font_family && (
                          <span>
                            Font: {b.font_family} ({b.font_size?.toFixed(1)}pt)
                          </span>
                        )}
                        {b.bold && <span className="font-bold">Bold</span>}
                        {b.italic && <span className="italic">Italic</span>}
                        <span>
                          Box: [{b.bounding_box.x0.toFixed(0)}, {b.bounding_box.y0.toFixed(0)},{" "}
                          {b.bounding_box.x1.toFixed(0)}, {b.bounding_box.y1.toFixed(0)}]
                        </span>
                        {b.parent_block_id && (
                          <span>
                            Parent: <span className="select-all text-muted-foreground">{b.parent_block_id}</span>
                          </span>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* TAB CONTENT: Tables */}
            {activeTab === "tables" && (
              <div className="space-y-6">
                {filteredTables.length === 0 ? (
                  <div className="p-8 text-center border border-dashed rounded-xl text-muted-foreground text-xs">
                    No extracted tables detected on this selection.
                  </div>
                ) : (
                  filteredTables.map((t) => (
                    <InfoCard
                      key={t.table_id}
                      title={`Table (${t.rows_count}x{t.columns_count}) — Page ${t.page_number}`}
                      description={`Table ID: ${t.table_id}`}
                      className="border border-violet-500/20 bg-card/60 overflow-hidden"
                    >
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs text-left border-collapse">
                          <thead>
                            <tr className="border-b border-border bg-muted/40">
                              {t.data[0]?.map((col, idx) => (
                                <th key={idx} className="p-2.5 font-bold text-muted-foreground border-r border-border/40">
                                  {col || `Col ${idx + 1}`}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {t.data.slice(1).map((row, rIdx) => (
                              <tr key={rIdx} className="border-b border-border/40 hover:bg-muted/10">
                                {row.map((cell, cIdx) => (
                                  <td key={cIdx} className="p-2.5 border-r border-border/40 font-normal">
                                    {cell}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <div className="mt-4 pt-2 border-t border-border/40 text-[9px] text-muted-foreground font-mono">
                        Bounding Box: [{t.bounding_box.x0.toFixed(0)}, {t.bounding_box.y0.toFixed(0)},{" "}
                        {t.bounding_box.x1.toFixed(0)}, {t.bounding_box.y1.toFixed(0)}]
                      </div>
                    </InfoCard>
                  ))
                )}
              </div>
            )}

            {/* TAB CONTENT: Images */}
            {activeTab === "images" && (
              <div className="grid gap-6 sm:grid-cols-2">
                {filteredImages.length === 0 ? (
                  <div className="sm:col-span-2 p-8 text-center border border-dashed rounded-xl text-muted-foreground text-xs">
                    No images registered on this selection.
                  </div>
                ) : (
                  filteredImages.map((img) => (
                    <div
                      key={img.image_id}
                      className="p-4 rounded-xl border bg-card/60 space-y-4 shadow-xs border-violet-500/20"
                    >
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-violet-500/10 text-violet-600 dark:bg-violet-500/20 dark:text-violet-400">
                          <Cpu className="size-5" />
                        </div>
                        <div className="min-w-0">
                          <h4 className="font-semibold text-sm truncate">Page {img.page_number} Image Object</h4>
                          <p className="text-[10px] text-muted-foreground font-mono">
                            ID: <span className="select-all">{img.image_id}</span>
                          </p>
                        </div>
                      </div>

                      <div className="p-4 rounded-lg bg-muted/40 border flex flex-col items-center justify-center min-h-[120px] text-xs text-muted-foreground space-y-1 text-center">
                        <span className="font-semibold">Image Container Box</span>
                        <span>
                          Dimensions: {img.width.toFixed(0)}px x {img.height.toFixed(0)}px
                        </span>
                        <span className="font-mono text-[9px]">
                          Box: [{img.bounding_box.x0.toFixed(0)}, {img.bounding_box.y0.toFixed(0)},{" "}
                          {img.bounding_box.x1.toFixed(0)}, {img.bounding_box.y1.toFixed(0)}]
                        </span>
                      </div>

                      {img.caption && (
                        <div className="p-3 rounded-lg border border-emerald-500/10 bg-emerald-500/5 text-xs text-emerald-800 dark:text-emerald-400">
                          <strong>Associated Caption:</strong> {img.caption}
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* Subcomponents */

function LoaderSpinner() {
  return (
    <div className="relative size-12 mx-auto">
      <div className="absolute inset-0 rounded-full border-4 border-muted" />
      <div className="absolute inset-0 rounded-full border-4 border-violet-600 border-t-transparent animate-spin" />
    </div>
  );
}

interface MiniStatProps {
  label: string;
  val: number;
  desc: string;
  icon: any;
}

function MiniStatCard({ label, val, desc, icon: Icon }: MiniStatProps) {
  return (
    <div className="p-4 rounded-xl border bg-card/60 backdrop-blur-sm flex items-center gap-4 shadow-xs">
      <div className="p-2.5 rounded-xl bg-violet-500/10 text-violet-600 dark:bg-violet-500/20 dark:text-violet-400 shrink-0">
        <Icon className="size-5" />
      </div>
      <div>
        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">
          {label}
        </span>
        <span className="text-xl font-bold block mt-0.5">{val}</span>
        <span className="text-[10px] text-muted-foreground block mt-0.5">{desc}</span>
      </div>
    </div>
  );
}

interface MetadataRowProps {
  label: string;
  val: any;
  icon: any;
  highlight?: boolean;
}

function MetadataRow({ label, val, icon: Icon, highlight }: MetadataRowProps) {
  return (
    <div className="flex items-center justify-between py-2.5 gap-4">
      <div className="flex items-center gap-2 text-muted-foreground min-w-0">
        <Icon className="size-4 shrink-0 text-violet-600 dark:text-violet-400" />
        <span className="truncate">{label}:</span>
      </div>
      <span
        className={`font-semibold text-right select-all truncate max-w-sm ${
          highlight
            ? val === "needs_ocr"
              ? "text-amber-600 dark:text-amber-400"
              : "text-emerald-600 dark:text-emerald-400"
            : "text-foreground"
        }`}
      >
        {val === null || val === undefined ? "—" : String(val)}
      </span>
    </div>
  );
}
