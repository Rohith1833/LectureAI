import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { InfoCard } from "@/components/ui/card";
import { Input, Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import { Search, Filter, BookOpen, Clock, Layers, ArrowRight, Check } from "lucide-react";
import { usePresentation } from "@/contexts/presentationContext";

interface UnitMock {
  id: string;
  number: number;
  title: string;
  desc: string;
  category: "Foundations" | "Core" | "Advanced";
  chapterCount: number;
  estimatedSlides: number;
}

const mockUnits: UnitMock[] = [
  {
    id: "1",
    number: 1,
    title: "Introduction to Computer Networking",
    desc: "Basic concepts of computer networks, ISO OSI reference model, protocols and network architectures.",
    category: "Foundations",
    chapterCount: 3,
    estimatedSlides: 12,
  },
  {
    id: "2",
    number: 2,
    title: "Physical and Data Link Layers",
    desc: "Transmission media, signal encoding, error detection/correction, and MAC protocol protocols.",
    category: "Foundations",
    chapterCount: 4,
    estimatedSlides: 18,
  },
  {
    id: "3",
    number: 3,
    title: "Network Layer and IP Routing",
    desc: "IPv4 & IPv6 addressing schemes, routing protocols (OSPF, BGP), and subnetting practices.",
    category: "Core",
    chapterCount: 5,
    estimatedSlides: 22,
  },
  {
    id: "4",
    number: 4,
    title: "Transport Protocols (TCP & UDP)",
    desc: "Reliable data transfer mechanics, congestion control algorithms, and sliding window flows.",
    category: "Core",
    chapterCount: 3,
    estimatedSlides: 15,
  },
  {
    id: "5",
    number: 5,
    title: "Application Layer & Protocols",
    desc: "DNS architecture, HTTP/HTTPS client interactions, SMTP email structure, and WebSocket connections.",
    category: "Core",
    chapterCount: 4,
    estimatedSlides: 20,
  },
  {
    id: "6",
    number: 6,
    title: "Network Security & Cryptography",
    desc: "Symmetric/Asymmetric encryption, TLS handshake procedures, firewalls, and modern network threat mitigations.",
    category: "Advanced",
    chapterCount: 4,
    estimatedSlides: 16,
  },
];

export default function UnitsPage() {
  const navigate = useNavigate();
  const { setUnits } = usePresentation();

  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [selectedUnitIds, setSelectedUnitIds] = useState<string[]>(["1", "3", "5"]); // preselect a few

  const handleToggleSelect = (id: string) => {
    setSelectedUnitIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const handleSelectAll = () => {
    if (selectedUnitIds.length === filteredUnits.length) {
      setSelectedUnitIds([]);
    } else {
      setSelectedUnitIds(filteredUnits.map((u) => u.id));
    }
  };

  const filteredUnits = mockUnits.filter((unit) => {
    const matchesSearch =
      unit.title.toLowerCase().includes(search.toLowerCase()) ||
      unit.desc.toLowerCase().includes(search.toLowerCase());
    const matchesCategory = categoryFilter === "all" || unit.category === categoryFilter;
    return matchesSearch && matchesCategory;
  });

  const handleProceed = () => {
    const chosenUnits = mockUnits
      .filter((u) => selectedUnitIds.includes(u.id))
      .map((u) => ({
        id: u.id,
        title: `Unit ${u.number}: ${u.title}`,
        description: u.desc,
        selected: true,
      }));
    setUnits(chosenUnits);
    navigate("/outline");
  };

  return (
    <div className="space-y-6 py-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-3xl font-bold tracking-tight">Select Textbook Units</h1>
          <p className="text-sm text-muted-foreground">
            Choose which modules/chapters you want to generate presentation materials for.
          </p>
        </div>
        <Button
          onClick={handleProceed}
          disabled={selectedUnitIds.length === 0}
          className="gap-2 bg-violet-600 hover:bg-violet-700 text-white dark:bg-violet-500 dark:hover:bg-violet-600 font-semibold shrink-0"
        >
          Generate Outlines <ArrowRight className="size-4" />
        </Button>
      </div>

      {/* Toolbar Search / Filter */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" />
          <Input
            placeholder="Search units, topics or keywords..."
            value={search}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="w-full sm:w-48 shrink-0">
          <Select value={categoryFilter} onValueChange={setCategoryFilter}>
            <SelectTrigger>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                <Filter className="size-3.5" />
                <SelectValue placeholder="All Categories" />
              </div>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Categories</SelectItem>
              <SelectItem value="Foundations">Foundations</SelectItem>
              <SelectItem value="Core">Core</SelectItem>
              <SelectItem value="Advanced">Advanced</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Selection Control Panel */}
      <div className="flex justify-between items-center px-2 py-1 text-sm border-b border-border/40 pb-3">
        <span className="text-muted-foreground">
          Showing <span className="font-semibold text-foreground">{filteredUnits.length}</span> units (
          <span className="font-semibold text-foreground">{selectedUnitIds.length}</span> selected)
        </span>
        <Button variant="ghost" size="sm" onClick={handleSelectAll} className="h-8 text-xs font-semibold">
          {selectedUnitIds.length === filteredUnits.length ? "Deselect All" : "Select All"}
        </Button>
      </div>

      {/* Units Grid */}
      <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {filteredUnits.map((unit) => {
          const isSelected = selectedUnitIds.includes(unit.id);
          return (
            <InfoCard
              key={unit.id}
              title={`Unit ${unit.number}: ${unit.title}`}
              description={unit.desc}
              className={`cursor-pointer transition-all border ${
                isSelected
                  ? "border-violet-500 bg-violet-500/5 dark:bg-violet-950/5 shadow-xs"
                  : "border-border/60 hover:border-border"
              }`}
              onClick={() => handleToggleSelect(unit.id)}
              action={
                <button
                  type="button"
                  aria-label={`Toggle selection of Unit ${unit.number}`}
                  className={`size-5 rounded-md border flex items-center justify-center transition-colors cursor-pointer outline-hidden focus-visible:ring-2 focus-visible:ring-ring ${
                    isSelected ? "bg-primary border-primary text-primary-foreground" : "border-input"
                  }`}
                  onClick={(e: React.MouseEvent<HTMLButtonElement>) => {
                    e.stopPropagation();
                    handleToggleSelect(unit.id);
                  }}
                >
                  {isSelected && <Check className="size-3.5" />}
                </button>
              }
            >
              {/* Unit Info Metadata */}
              <div className="flex gap-4 pt-4 border-t border-border/40 mt-4 text-xs text-muted-foreground">
                <div className="flex items-center gap-1">
                  <BookOpen className="size-3.5" />
                  <span>{unit.chapterCount} chapters</span>
                </div>
                <div className="flex items-center gap-1">
                  <Layers className="size-3.5" />
                  <span>{unit.category}</span>
                </div>
                <div className="flex items-center gap-1">
                  <Clock className="size-3.5" />
                  <span>~{unit.estimatedSlides} slides</span>
                </div>
              </div>
            </InfoCard>
          );
        })}
      </div>
    </div>
  );
}
