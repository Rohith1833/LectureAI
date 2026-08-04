import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import {
  UploadCloud,
  Loader2,
  ListTodo,
  FileText,
  Sliders,
  Settings,
  ChevronLeft,
  ChevronRight,
  HelpCircle,
} from "lucide-react";
import { useState } from "react";
import { Button } from "./ui/button";
import { useUpload } from "@/contexts/uploadContext";

const steps = [
  { to: "/upload", label: "Upload Textbook", icon: UploadCloud },
  { to: "/processing", label: "Processing AI", icon: Loader2 },
  { to: "/units", label: "Select Units", icon: ListTodo },
  { to: "/outline", label: "Slide Outline", icon: FileText },
  { to: "/preview", label: "Slide Preview", icon: Sliders },
  { to: "/settings", label: "Settings", icon: Settings },
] as const;

export default function Sidebar() {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const { jobId } = useUpload();

  // Check if we are currently in the creation workflow pages
  const isWorkflowActive = steps.some(
    (step) =>
      location.pathname === step.to ||
      (step.to === "/processing" && location.pathname.startsWith("/processing/"))
  );

  if (!isWorkflowActive) return null;

  return (
    <aside
      className={cn(
        "hidden md:flex flex-col border-r border-border/40 bg-card/60 backdrop-blur-sm transition-all duration-300 relative shrink-0",
        collapsed ? "w-16" : "w-64"
      )}
    >
      {/* Collapse button */}
      <Button
        variant="outline"
        size="icon"
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-3 size-6 rounded-full shadow-xs border bg-background"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <ChevronRight className="size-3" /> : <ChevronLeft className="size-3" />}
      </Button>

      {/* Nav steps */}
      <div className="flex-1 px-3 py-6 space-y-1.5">
        {!collapsed && (
          <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground px-3 mb-4">
            Create Presentation
          </p>
        )}
        <nav className="space-y-1">
          {steps.map((step) => {
            const isActive =
              location.pathname === step.to ||
              (step.to === "/processing" && location.pathname.startsWith("/processing/"));
            const isProcessing = step.to === "/processing" && isActive;
            const stepTo = step.to === "/processing" && jobId ? `/processing/${jobId}` : step.to;

            return (
              <Link key={step.to} to={stepTo}>
                <Button
                  variant={isActive ? "secondary" : "ghost"}
                  className={cn(
                    "w-full justify-start gap-3 text-sm h-10 px-3 transition-colors",
                    collapsed ? "justify-center px-0 size-10" : ""
                  )}
                  aria-current={isActive ? "page" : undefined}
                >
                  <step.icon
                    className={cn(
                      "size-4 shrink-0",
                      isActive ? "text-primary" : "text-muted-foreground",
                      isProcessing && "animate-spin"
                    )}
                  />
                  {!collapsed && <span className="truncate">{step.label}</span>}
                </Button>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Bottom info banner */}
      {!collapsed && (
        <div className="p-4 border-t border-border/40 bg-muted/20">
          <div className="flex items-start gap-2.5">
            <HelpCircle className="size-4 text-muted-foreground mt-0.5" />
            <div className="text-xs text-muted-foreground leading-normal">
              <span className="font-semibold text-foreground">Need help?</span> Read the{" "}
              <Link to="/about" className="underline hover:text-foreground">
                About page
              </Link> for roadmap and tips.
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
