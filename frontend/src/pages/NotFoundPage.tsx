import { Link } from "react-router-dom";
import { Home, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DESIGN_TOKENS } from "@/config/design";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-4 text-center space-y-6">
      {/* 404 Visual badge */}
      <div className="relative">
        <h1 className="text-9xl font-black text-violet-500/10 tracking-widest select-none">404</h1>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={cn(DESIGN_TOKENS.typography.h2, "font-bold")}>Page Not Found</span>
        </div>
      </div>

      <p className="text-sm text-muted-foreground max-w-sm leading-relaxed">
        The page you are looking for does not exist or has been moved. You can navigate back to the landing page.
      </p>

      <div className="flex gap-3 justify-center pt-2">
        <Link to="/">
          <Button className="gap-2 bg-violet-600 hover:bg-violet-700 text-white dark:bg-violet-500 dark:hover:bg-violet-600">
            <Home className="size-4" /> Return Home
          </Button>
        </Link>
        <Link to="/upload">
          <Button variant="ghost" className="gap-1.5 text-xs">
            Start Creating <ArrowRight className="size-3.5" />
          </Button>
        </Link>
      </div>
    </div>
  );
}

import { cn } from "@/lib/utils";
