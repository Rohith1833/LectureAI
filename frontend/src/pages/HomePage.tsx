import { useState } from "react";
import { ArrowRight, BookOpen, Sparkles, Zap, Layers, Cpu, FileSliders, FileText } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { FeatureCard, InfoCard, StatusCard } from "@/components/ui/card";
import { Spinner } from "@/components/ui/feedback";
import { useHealthCheck } from "@/hooks/useHealthCheck";
import { DESIGN_TOKENS } from "@/config/design";

export default function HomePage() {
  const [checkEnabled, setCheckEnabled] = useState(false);
  const { data, isLoading, isError, error } = useHealthCheck(checkEnabled);

  return (
    <div className="relative overflow-hidden space-y-16">
      {/* Background decoration */}
      <div className="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2">
        <div className="h-[500px] w-[800px] rounded-full bg-gradient-to-br from-violet-500/10 via-indigo-500/5 to-transparent blur-3xl" />
      </div>

      {/* 1. Hero Section */}
      <section className="text-center pt-16 pb-8 space-y-6">
        <div className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/40 px-4 py-1.5 text-xs font-medium text-muted-foreground">
          <Sparkles className="size-3.5 text-violet-600 dark:text-violet-400" />
          Production-Ready Design System
        </div>

        <h1 className={DESIGN_TOKENS.typography.h1}>
          Transform Textbooks into
          <span className={DESIGN_TOKENS.colors.brand.gradient + " mt-2 block bg-clip-text text-transparent"}>
            Professional Lectures
          </span>
        </h1>

        <p className="mx-auto max-w-2xl text-lg text-muted-foreground leading-relaxed">
          LectureAI coordinates intelligent agents to extract structure from your textbooks, 
          build learning objectives, and compile tailored presentation slides instantly.
        </p>

        <div className="flex flex-col items-center justify-center gap-4 sm:flex-row pt-4">
          <Link to="/upload">
            <Button size="lg" className="gap-2 font-semibold shadow-md bg-violet-600 hover:bg-violet-700 text-white dark:bg-violet-500 dark:hover:bg-violet-600">
              Start Creating <ArrowRight className="size-4" />
            </Button>
          </Link>
          <Button
            variant="outline"
            size="lg"
            onClick={() => setCheckEnabled(true)}
            disabled={isLoading}
            className="font-medium"
          >
            {isLoading ? (
              <span className="flex items-center gap-2"><Spinner size="sm" /> Checking...</span>
            ) : (
              "Check Backend Connection"
            )}
          </Button>
        </div>

        {/* Health Status Display */}
        {checkEnabled && (
          <div className="mx-auto mt-6 max-w-md animate-in fade-in slide-in-from-top-2 duration-200">
            {isLoading && (
              <StatusCard
                status="info"
                title="Connecting..."
                message="Verifying communication link with FastAPI backend."
              />
            )}
            {data && (
              <StatusCard
                status="success"
                title="System Operational"
                message={`${data.message} (Status: ${data.data.status.toUpperCase()})`}
              />
            )}
            {isError && (
              <StatusCard
                status="error"
                title="System Offline"
                message={error instanceof Error ? error.message : "Unable to reach the server. Make sure it is running."}
              />
            )}
          </div>
        )}
      </section>

      {/* 2. Workflow Visualization */}
      <section className="space-y-6">
        <div className="text-center space-y-2">
          <h2 className={DESIGN_TOKENS.typography.h2}>How It Works</h2>
          <p className="text-sm text-muted-foreground">The automated agent-driven presentation pipeline</p>
        </div>

        <div className="grid gap-6 md:grid-cols-4 relative">
          {[
            { step: "1", title: "Upload PDF", desc: "Drag & drop your textbook PDF files.", icon: BookOpen },
            { step: "2", title: "AI Extraction", desc: "Agent analyzes layout and reads pages.", icon: Cpu },
            { step: "3", title: "Select Units", desc: "Filter and outline learning objectives.", icon: FileSliders },
            { step: "4", title: "Build Slides", desc: "Review, edit notes, and export to PPT.", icon: FileText },
          ].map((w, idx) => (
            <InfoCard
              key={w.title}
              title={`${w.step}. ${w.title}`}
              description={w.desc}
              className="border border-border/40 relative hover:border-violet-500/20 transition-all bg-card/60 backdrop-blur-xs"
            >
              <div className="flex justify-between items-center mt-2">
                <div className="p-2.5 rounded-lg bg-muted text-muted-foreground">
                  <w.icon className="size-5" />
                </div>
                {idx < 3 && (
                  <div className="hidden md:block absolute -right-3 top-1/2 -translate-y-1/2 z-10 text-muted-foreground/40">
                    <ArrowRight className="size-5 animate-pulse" />
                  </div>
                )}
              </div>
            </InfoCard>
          ))}
        </div>
      </section>

      {/* 3. Feature Highlights */}
      <section className="space-y-6">
        <div className="text-center space-y-2">
          <h2 className={DESIGN_TOKENS.typography.h2}>Features</h2>
          <p className="text-sm text-muted-foreground">Premium tools designed specifically for educators</p>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          <FeatureCard
            icon={BookOpen}
            title="Syllabus Focused"
            description="Extract core topics from heavy textbook formats and shape them around national learning modules."
          />
          <FeatureCard
            icon={Layers}
            title="Multi-Agent OCR"
            description="Leverage specialized processing pipelines to transcribe tables, charts, math and images."
          />
          <FeatureCard
            icon={Zap}
            title="Express Exports"
            description="Instantly compile outlines into PowerPoint slides embedded with speaker notes and academic structures."
          />
        </div>
      </section>
    </div>
  );
}
