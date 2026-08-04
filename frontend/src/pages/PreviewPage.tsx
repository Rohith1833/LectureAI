import { useState } from "react";
import { InfoCard } from "@/components/ui/card";
import { Textarea } from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import {
  RefreshCw,
  Image,
  ChevronLeft,
  ChevronRight,
  Download,
  Presentation,
  CheckCircle2,
  Bookmark,
} from "lucide-react";
import { type Slide } from "@/contexts/presentationContext";

const mockSlides: Slide[] = [
  {
    id: "s1",
    title: "Introduction to Computer Networking",
    bullets: [
      "Define computer networks: interconnected autonomous computing nodes.",
      "Understand the key components: Hosts, Routers, Communication Links.",
      "Primary goals: Resource sharing, high reliability, scaling efficiency.",
    ],
    notes: "Welcome the students. Briefly state that this lecture sets the stage for computer networking protocols and architectures. Ask if anyone has configured their own home router.",
    imageUrl: "https://images.unsplash.com/photo-1544197150-b99a580bb7a8?w=800&auto=format&fit=crop&q=60&ixlib=rb-4.0.3",
  },
  {
    id: "s2",
    title: "The ISO OSI Reference Model",
    bullets: [
      "Layer 7 to Layer 1 hierarchy overview.",
      "Encapsulation: Headers are prepended as data moves down the stack.",
      "Decapsulation: Protocols read and strip headers on arrival.",
    ],
    notes: "Draw the 7 layers on the board. Make sure they understand that headers contain control info and data contains payloads. We will focus mostly on Layers 3 through 5 in this syllabus.",
  },
  {
    id: "s3",
    title: "Network Typologies: LAN, WAN & MAN",
    bullets: [
      "LAN (Local Area Network): High speed, low latency, confined to buildings.",
      "WAN (Wide Area Network): Geographically dispersed, links multiple LANs.",
      "MAN (Metropolitan Area Network): City-wide connectivity grids.",
    ],
    notes: "Point out that local campus networks act as LANs, while the global internet is a massive web of WAN routers. Focus on latency constraints of WAN routing.",
    imageUrl: "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=800&auto=format&fit=crop&q=60&ixlib=rb-4.0.3",
  },
  {
    id: "s4",
    title: "Protocol Layers and Encapsulation",
    bullets: [
      "Segments (Transport) -> Packets (Network) -> Frames (Link) -> Bits (Physical).",
      "Multiplexing and Demultiplexing mechanisms.",
      "End-to-end vs. Hop-by-hop message delivery structures.",
    ],
    notes: "Emphasize headers are added by each layer. Layer 4 handles segments (TCP), Layer 3 handles packets (IP), Layer 2 handles frames (Ethernet/Wifi).",
  },
];

export default function PreviewPage() {
  const [slides, setSlides] = useState<Slide[]>(mockSlides);
  const [activeSlideIdx, setActiveSlideIdx] = useState(0);
  const [exportSuccess, setExportSuccess] = useState(false);

  const activeSlide = slides[activeSlideIdx] || slides[0];

  const handleNotesChange = (text: string) => {
    setSlides((prev) =>
      prev.map((s, idx) => (idx === activeSlideIdx ? { ...s, notes: text } : s))
    );
  };

  const handleNext = () => {
    setActiveSlideIdx((prev) => Math.min(slides.length - 1, prev + 1));
  };

  const handlePrev = () => {
    setActiveSlideIdx((prev) => Math.max(0, prev - 1));
  };

  const handleExport = () => {
    setExportSuccess(true);
    setTimeout(() => setExportSuccess(false), 3000);
  };

  return (
    <div className="space-y-6 py-6 h-full flex flex-col">
      {/* Header Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border/40 pb-4">
        <div className="space-y-1">
          <h1 className="text-3xl font-bold tracking-tight">Presentation Preview</h1>
          <p className="text-sm text-muted-foreground">
            Browse Generated slides, adjust speaker notes, and download the PowerPoint template.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {exportSuccess && (
            <span className="text-xs text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1 mr-2 animate-in fade-in slide-in-from-right-2">
              <CheckCircle2 className="size-4" /> Export Complete
            </span>
          )}
          <Button
            onClick={handleExport}
            className="gap-2 bg-violet-600 hover:bg-violet-700 text-white dark:bg-violet-500 dark:hover:bg-violet-600 font-semibold"
          >
            Export to PowerPoint <Download className="size-4" />
          </Button>
        </div>
      </div>

      {/* Main Workspace Layout */}
      <div className="grid gap-6 lg:grid-cols-4 flex-1">
        {/* Left Sidebar: Thumbnails list */}
        <div className="lg:col-span-1 space-y-3 max-h-[600px] overflow-y-auto pr-1">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground px-1 pb-1">
            Slides ({slides.length})
          </div>
          <div className="space-y-3">
            {slides.map((slide, idx) => (
              <div
                key={slide.id}
                onClick={() => setActiveSlideIdx(idx)}
                className={`group border rounded-xl p-3 cursor-pointer transition-all ${
                  idx === activeSlideIdx
                    ? "border-violet-500 bg-violet-500/5 dark:bg-violet-950/5 shadow-xs"
                    : "border-border/60 hover:border-border"
                }`}
              >
                <div className="flex justify-between items-start mb-2">
                  <span className="text-[10px] font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                    Slide {idx + 1}
                  </span>
                  <Bookmark className="size-3.5 text-muted-foreground/60 opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
                <h4 className="font-semibold text-xs truncate text-foreground">{slide.title}</h4>
                <p className="text-[10px] text-muted-foreground line-clamp-2 mt-1">
                  {slide.bullets[0]}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Center/Right workspace */}
        <div className="lg:col-span-3 space-y-6 flex flex-col justify-between">
          {/* Main Slide Preview Area (mocking PPT slide aspect ratio 16:9) */}
          <div className="relative border border-border/80 bg-linear-to-b from-muted/50 to-muted/20 rounded-2xl p-6 sm:p-10 aspect-video flex flex-col justify-between shadow-lg overflow-hidden dark:bg-card">
            {/* Header branding slot */}
            <div className="flex justify-between items-center text-[10px] font-bold uppercase tracking-wider text-muted-foreground/80">
              <span>LectureAI Slide Deck</span>
              <span>Unit Module</span>
            </div>

            {/* Slide Body Grid */}
            <div className="grid gap-6 md:grid-cols-2 flex-1 items-center py-4">
              {/* Bullet texts */}
              <div className="space-y-4">
                <h2 className="text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight leading-tight border-b border-border/40 pb-2">
                  {activeSlide.title}
                </h2>
                <ul className="space-y-2.5 text-sm leading-relaxed text-muted-foreground list-disc pl-5">
                  {activeSlide.bullets.map((b, idx) => (
                    <li key={idx} className="marker:text-primary">
                      {b}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Graphic/Image Preview slot */}
              <div className="h-full min-h-[160px] rounded-xl border border-border/60 overflow-hidden bg-muted flex items-center justify-center relative">
                {activeSlide.imageUrl ? (
                  <img
                    src={activeSlide.imageUrl}
                    alt={activeSlide.title}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="text-center p-4">
                    <Presentation className="size-10 text-muted-foreground/40 mx-auto mb-2" />
                    <span className="text-xs text-muted-foreground">Slide Presentation Layout Only</span>
                  </div>
                )}
              </div>
            </div>

            {/* Footer row */}
            <div className="flex items-center justify-between border-t border-border/40 pt-3 text-[10px] text-muted-foreground">
              <span>LectureAI Project</span>
              <span>Slide {activeSlideIdx + 1} of {slides.length}</span>
            </div>
          </div>

          {/* Editor Action buttons */}
          <div className="flex flex-wrap items-center justify-between gap-3 p-4 bg-muted/30 border border-border/40 rounded-xl">
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handlePrev}
                disabled={activeSlideIdx === 0}
                aria-label="Previous Slide"
              >
                <ChevronLeft className="size-4" /> Prev
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleNext}
                disabled={activeSlideIdx === slides.length - 1}
                aria-label="Next Slide"
              >
                Next <ChevronRight className="size-4" />
              </Button>
            </div>

            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="gap-1.5 text-xs">
                <Image className="size-3.5" /> Replace Image (UI only)
              </Button>
              <Button variant="outline" size="sm" className="gap-1.5 text-xs text-primary">
                <RefreshCw className="size-3.5" /> Regenerate Slide (UI only)
              </Button>
            </div>
          </div>

          {/* Teacher/Speaker Notes panel */}
          <InfoCard title="Speaker Notes" className="border border-border/40">
            <Textarea
              placeholder="Write speaker instructions or narratives for this slide here..."
              value={activeSlide.notes}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => handleNotesChange(e.target.value)}
              className="min-h-[80px]"
              helperText="These notes will be compiled directly inside the exported PowerPoint notes panel."
            />
          </InfoCard>
        </div>
      </div>
    </div>
  );
}
