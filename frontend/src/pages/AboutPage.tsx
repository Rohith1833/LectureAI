import { Code2, Layers, ShieldCheck } from "lucide-react";
import { InfoCard } from "@/components/ui/card";

export default function AboutPage() {
  return (
    <div className="space-y-12 py-6">
      {/* Title Header */}
      <div className="text-center space-y-3">
        <h1 className="text-4xl font-bold tracking-tight">About LectureAI</h1>
        <p className="text-base text-muted-foreground max-w-2xl mx-auto leading-relaxed">
          An advanced orchestration platform combining multi-agent layouts and structured 
          compilation models to help teachers focus on what matters most: teaching.
        </p>
      </div>

      {/* Philosophy Grid */}
      <div className="grid gap-6 md:grid-cols-3">
        <InfoCard title="Empowering Educators">
          <p className="text-sm text-muted-foreground leading-relaxed">
            Lecture preparation consumes hours of manual effort. Our platform automates the heavy-lifting
            of parsing content outlines, so teachers can concentrate on delivering engaging lectures.
          </p>
        </InfoCard>

        <InfoCard title="Clean Architecture">
          <p className="text-sm text-muted-foreground leading-relaxed">
            Engineered with strict separation of concerns, decoupling HTTP routing (API), business logic 
            (Services), and visual rendering (Layouts) for future adaptability.
          </p>
        </InfoCard>

        <InfoCard title="Agentic Intelligence">
          <p className="text-sm text-muted-foreground leading-relaxed">
            Using cooperative agents where individual LLM models focus on layout parsing, unit categorization, 
            and quality verification rather than single monolith prompts.
          </p>
        </InfoCard>
      </div>

      {/* Technology Stack details */}
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-center">Modern Technology Stack</h2>
        <div className="grid gap-6 sm:grid-cols-2">
          {/* Frontend Stack */}
          <div className="p-6 rounded-2xl border border-border/60 bg-card">
            <h3 className="font-semibold text-lg mb-4 text-violet-600 dark:text-violet-400 flex items-center gap-2">
              <Code2 className="size-5" /> Frontend Architecture
            </h3>
            <ul className="space-y-3 text-sm text-muted-foreground">
              <li><strong>Framework:</strong> React (v19) + TypeScript for type-safety</li>
              <li><strong>Build system:</strong> Vite for near-instant hot module reloading</li>
              <li><strong>Design elements:</strong> Tailwind CSS v4 styling + Custom shadcn/ui custom components</li>
              <li><strong>Routing:</strong> React Router for structured creation states</li>
              <li><strong>Queries:</strong> TanStack React Query + Axios for server connection hooks</li>
            </ul>
          </div>

          {/* Backend Stack */}
          <div className="p-6 rounded-2xl border border-border/60 bg-card">
            <h3 className="font-semibold text-lg mb-4 text-indigo-600 dark:text-indigo-400 flex items-center gap-2">
              <Layers className="size-5" /> Backend Infrastructure
            </h3>
            <ul className="space-y-3 text-sm text-muted-foreground">
              <li><strong>Framework:</strong> FastAPI (Python) for asynchronous endpoints</li>
              <li><strong>Data contracts:</strong> Pydantic v2 for request validation</li>
              <li><strong>Logging:</strong> Structured, level-based Loguru logging</li>
              <li><strong>Configs:</strong> Pydantic-Settings loaded from environment variables</li>
              <li><strong>Execution:</strong> Uvicorn running in high-performance reload modes</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Roadmap timeline */}
      <div className="space-y-6 pt-4">
        <h2 className="text-2xl font-bold text-center">Development Roadmap</h2>
        <div className="max-w-xl mx-auto space-y-4">
          {[
            { phase: "Phase 1: Project Foundation", status: "Completed", desc: "FastAPI server infrastructure and initial React setup." },
            { phase: "Phase 2: UI Design & Foundation", status: "Active", desc: "Establishing custom styles, responsive layouts, page definitions, and contexts." },
            { phase: "Phase 3: Document Upload & PDF Parsing", status: "Upcoming", desc: "Integrating layout detection, optical characters transcription (OCR), and file processing." },
            { phase: "Phase 4: Agent Core & Slide Generation", status: "Upcoming", desc: "Setting up LLM model calls, compiling lecture outline objectives, and exporting PowerPoint files." },
          ].map((item, idx) => (
            <div key={idx} className="flex gap-4 p-4 rounded-xl border border-border/40 bg-muted/10 relative">
              <div className="flex size-7 items-center justify-center rounded-full bg-primary/10 text-primary shrink-0 font-bold text-xs mt-0.5">
                {idx + 1}
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h4 className="font-semibold text-sm">{item.phase}</h4>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${
                    item.status === "Completed" ? "bg-emerald-500/10 text-emerald-600" :
                    item.status === "Active" ? "bg-violet-500/10 text-violet-600" : "bg-muted text-muted-foreground"
                  }`}>
                    {item.status}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground leading-normal">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Heart footer note */}
      <div className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground pt-4">
        <ShieldCheck className="size-4 text-emerald-500" /> Fully responsive WCAG AA color-contrast compatible.
      </div>
    </div>
  );
}
