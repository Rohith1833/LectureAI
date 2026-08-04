import { Link, useLocation } from "react-router-dom";
import { ChevronRight, Home } from "lucide-react";
import { cn } from "@/lib/utils";

export function Breadcrumb({ className }: { className?: string }) {
  const location = useLocation();
  const pathnames = location.pathname.split("/").filter((x) => x);

  // Capitalize name mapping helper
  const routeNameMap: Record<string, string> = {
    upload: "Upload Textbook",
    processing: "Processing AI",
    units: "Select Units",
    outline: "Edit Outline",
    preview: "Slide Preview",
    settings: "Settings",
    about: "About Us",
  };

  return (
    <nav aria-label="Breadcrumb" className={cn("flex items-center gap-1.5 text-xs text-muted-foreground mb-4", className)}>
      <Link
        to="/"
        className="flex items-center gap-1 hover:text-foreground transition-colors outline-hidden focus-visible:ring-1 focus-visible:ring-ring"
      >
        <Home className="size-3.5" />
        <span className="sr-only">Home</span>
      </Link>

      {pathnames.length > 0 && <ChevronRight className="size-3 text-muted-foreground/60" />}

      {pathnames.map((value, index) => {
        const to = `/${pathnames.slice(0, index + 1).join("/")}`;
        const isLast = index === pathnames.length - 1;
        const name = routeNameMap[value] || value.charAt(0).toUpperCase() + value.slice(1);

        return (
          <div key={to} className="flex items-center gap-1.5">
            {isLast ? (
              <span className="font-semibold text-foreground truncate max-w-[200px]" aria-current="page">
                {name}
              </span>
            ) : (
              <Link
                to={to}
                className="hover:text-foreground transition-colors truncate max-w-[150px] outline-hidden focus-visible:ring-1 focus-visible:ring-ring"
              >
                {name}
              </Link>
            )}
            {!isLast && <ChevronRight className="size-3 text-muted-foreground/60" />}
          </div>
        );
      })}
    </nav>
  );
}
