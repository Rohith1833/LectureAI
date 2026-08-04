import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Switch } from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import { GripVertical, Plus, Edit3, Trash2, ChevronDown, ChevronUp, ArrowRight, Eye } from "lucide-react";
import { usePresentation, type SlideOutline } from "@/contexts/presentationContext";

interface OutlineMockItem {
  id: string;
  unitTitle: string;
  slideCount: number;
  objectives: string[];
  isOpen: boolean;
}

const mockOutlines: OutlineMockItem[] = [
  {
    id: "1",
    unitTitle: "Unit 1: Introduction to Computer Networking",
    slideCount: 12,
    objectives: [
      "Understand the basic layers of the OSI model.",
      "Identify the differences between LAN, WAN, and MAN network types.",
      "Describe packet encapsulation and standard networking protocol stacks.",
    ],
    isOpen: true,
  },
  {
    id: "3",
    unitTitle: "Unit 3: Network Layer and IP Routing",
    slideCount: 22,
    objectives: [
      "Explain the fundamental design principles of IPv4 & IPv6 networks.",
      "Calculate subnetting routes and construct CIDR IP blocks.",
      "Differentiate OSPF link-state routing from BGP path-vector methods.",
    ],
    isOpen: true,
  },
  {
    id: "5",
    unitTitle: "Unit 5: Application Layer & Protocols",
    slideCount: 20,
    objectives: [
      "Detail the DNS lookup resolution tree from root to local caching servers.",
      "Describe HTTP header mechanics, response state codes, and SSL handshakes.",
      "Compare SMTP message transfer flow with IMAP/POP pull operations.",
    ],
    isOpen: false,
  },
];

export default function OutlinePage() {
  const navigate = useNavigate();
  const { setOutline } = usePresentation();
  const [outlines, setOutlines] = useState<OutlineMockItem[]>(mockOutlines);
  const [focusObjectives, setFocusObjectives] = useState(true);

  const toggleSection = (id: string) => {
    setOutlines((prev) =>
      prev.map((item) => (item.id === id ? { ...item, isOpen: !item.isOpen } : item))
    );
  };

  const handleSlideCountChange = (id: string, change: number) => {
    setOutlines((prev) =>
      prev.map((item) =>
        item.id === id
          ? { ...item, slideCount: Math.max(5, Math.min(40, item.slideCount + change)) }
          : item
      )
    );
  };

  const handleProceed = () => {
    const slideOutlines: SlideOutline[] = outlines.map((o) => ({
      title: o.unitTitle,
      objectives: o.objectives,
      slideCount: o.slideCount,
    }));
    setOutline(slideOutlines);
    navigate("/preview");
  };

  return (
    <div className="space-y-6 py-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-3xl font-bold tracking-tight">Refine Lecture Outline</h1>
          <p className="text-sm text-muted-foreground">
            Adjust the slide counts, reorder sections, and edit learning objectives.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => navigate("/units")}
          >
            Back
          </Button>
          <Button
            onClick={handleProceed}
            className="gap-2 bg-violet-600 hover:bg-violet-700 text-white dark:bg-violet-500 dark:hover:bg-violet-600 font-semibold"
          >
            Preview Presentation <Eye className="size-4" />
          </Button>
        </div>
      </div>

      {/* Main Settings bar */}
      <div className="flex items-center justify-between p-4 bg-muted/30 border border-border/40 rounded-xl text-sm">
        <div className="flex items-center gap-4">
          <Switch
            checked={focusObjectives}
            onCheckedChange={setFocusObjectives}
            label="Incorporate Learning Objectives"
          />
        </div>
        <span className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
          Total Slides: {outlines.reduce((acc, curr) => acc + curr.slideCount, 0)}
        </span>
      </div>

      {/* Accordion / Expandable sections */}
      <div className="space-y-4">
        {outlines.map((item) => (
          <div
            key={item.id}
            className="border border-border/40 rounded-xl bg-card overflow-hidden shadow-xs"
          >
            {/* Header row */}
            <div
              className="flex items-center justify-between p-4 sm:p-5 cursor-pointer hover:bg-muted/10 transition-colors"
              onClick={() => toggleSection(item.id)}
            >
              <div className="flex items-center gap-3">
                <div className="cursor-grab text-muted-foreground/60 hover:text-muted-foreground p-1 rounded-sm shrink-0">
                  <GripVertical className="size-4.5" />
                </div>
                <h3 className="font-semibold text-base sm:text-lg">{item.unitTitle}</h3>
              </div>

              <div className="flex items-center gap-4" onClick={(e) => e.stopPropagation()}>
                {/* Counter */}
                <div className="flex items-center border border-border rounded-lg bg-background shadow-2xs h-8">
                  <button
                    onClick={() => handleSlideCountChange(item.id, -1)}
                    className="px-2.5 hover:bg-muted h-full font-bold text-sm rounded-l-lg outline-none cursor-pointer"
                  >
                    -
                  </button>
                  <span className="px-3 text-xs font-semibold select-none w-12 text-center">
                    {item.slideCount} slides
                  </span>
                  <button
                    onClick={() => handleSlideCountChange(item.id, 1)}
                    className="px-2.5 hover:bg-muted h-full font-bold text-sm rounded-r-lg outline-none cursor-pointer"
                  >
                    +
                  </button>
                </div>

                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => toggleSection(item.id)}
                  className="size-8"
                  aria-label={item.isOpen ? "Collapse section" : "Expand section"}
                >
                  {item.isOpen ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
                </Button>
              </div>
            </div>

            {/* Content panel */}
            {item.isOpen && (
              <div className="px-5 pb-5 pt-1 border-t border-border/40 space-y-4 bg-card animate-in fade-in slide-in-from-top-1 duration-150">
                {/* Objectives list */}
                {focusObjectives && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                      <span>Learning Objectives</span>
                      <Button variant="ghost" size="sm" className="h-7 text-xs gap-1">
                        <Plus className="size-3" /> Add Objective
                      </Button>
                    </div>

                    <div className="space-y-2">
                      {item.objectives.map((obj, idx) => (
                        <div key={idx} className="flex gap-2 items-center bg-muted/20 p-2.5 rounded-lg border border-border/40 text-sm">
                          <span className="text-xs text-muted-foreground w-4 shrink-0">{idx + 1}.</span>
                          <span className="flex-1 min-w-0 truncate">{obj}</span>
                          <div className="flex items-center gap-1">
                            <Button variant="ghost" size="icon" className="size-7" aria-label="Edit Objective">
                              <Edit3 className="size-3.5 text-muted-foreground" />
                            </Button>
                            <Button variant="ghost" size="icon" className="size-7 text-destructive hover:bg-destructive/10" aria-label="Delete Objective">
                              <Trash2 className="size-3.5" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Additional controls */}
                <div className="flex justify-between items-center text-xs text-muted-foreground pt-2">
                  <span>Custom theme: Default Inherit</span>
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" className="h-7 text-xs">
                      Re-generate Outline
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Continue */}
      <div className="flex justify-end pt-4">
        <Button onClick={handleProceed} size="lg" className="gap-2 bg-violet-600 hover:bg-violet-700 text-white dark:bg-violet-500 dark:hover:bg-violet-600 font-semibold shadow-lg">
          Generate Presentation <ArrowRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}
