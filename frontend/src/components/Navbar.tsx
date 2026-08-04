import { Link, useLocation } from "react-router-dom";
import { BookOpen, Menu, X, Sun, Moon, Settings, Layers, FolderClosed, FileSliders } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/contexts/themeContext";
import { useUpload } from "@/contexts/uploadContext";

const navLinks = [
  { to: "/", label: "Home" },
  { to: "/upload", label: "Create" },
  { to: "/about", label: "About" },
] as const;

export default function Navbar() {
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
  const { jobId } = useUpload();

  return (
    <header className="sticky top-0 z-50 border-b border-border/40 bg-background/80 backdrop-blur-lg">
      <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Logo */}
        <Link
          to="/"
          className="flex items-center gap-2 text-lg font-bold tracking-tight outline-hidden focus-visible:ring-2 focus-visible:ring-ring rounded-md"
        >
          <BookOpen className="size-6 text-primary" />
          <span className="bg-gradient-to-r from-foreground to-foreground/70 bg-clip-text text-transparent">
            LectureAI
          </span>
        </Link>

        {/* Desktop Navigation */}
        <div className="hidden items-center gap-2 md:flex">
          {navLinks.map((link) => (
            <Link key={link.to} to={link.to}>
              <Button
                variant={
                  location.pathname === link.to ||
                  (link.to === "/upload" &&
                    ["/upload", "/processing", "/units", "/outline", "/preview", "/settings"].some((path) =>
                      location.pathname.startsWith(path)
                    ))
                    ? "secondary"
                    : "ghost"
                }
                size="sm"
              >
                {link.label}
              </Button>
            </Link>
          ))}

          <span className="h-4 w-px bg-border/60 mx-1" />

          {/* Theme Toggle */}
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleTheme}
            aria-label="Toggle theme"
            className="size-8"
          >
            {theme === "light" ? <Moon className="size-4" /> : <Sun className="size-4" />}
          </Button>
        </div>

        {/* Mobile controls */}
        <div className="flex items-center gap-1.5 md:hidden">
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleTheme}
            aria-label="Toggle theme"
            className="size-8"
          >
            {theme === "light" ? <Moon className="size-4" /> : <Sun className="size-4" />}
          </Button>

          <Button
            variant="ghost"
            size="icon"
            className="size-8"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label="Toggle navigation menu"
          >
            {mobileOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </Button>
        </div>
      </nav>

      {/* Mobile Drawer (Navigation Drawer) */}
      {mobileOpen && (
        <div className="border-t border-border/40 bg-background/95 backdrop-blur-lg md:hidden animate-in slide-in-from-top-3 duration-200">
          <div className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-3">
            {navLinks.map((link) => (
              <Link key={link.to} to={link.to} onClick={() => setMobileOpen(false)}>
                <Button
                  variant={location.pathname === link.to ? "secondary" : "ghost"}
                  className="w-full justify-start"
                >
                  {link.label}
                </Button>
              </Link>
            ))}

            {/* Creation Steps Sub-navigation inside mobile drawer */}
            {["/upload", "/processing", "/units", "/outline", "/preview", "/settings"].some((path) =>
              location.pathname.startsWith(path)
            ) && (
              <div className="mt-2 pt-2 border-t border-border/40 pl-3 space-y-1.5">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                  Creation Workflow
                </p>
                {[
                  { to: "/upload", label: "1. Upload File", icon: FolderClosed },
                  { to: "/processing", label: "2. Processing", icon: Layers },
                  { to: "/units", label: "3. Choose Units", icon: FileSliders },
                  { to: "/outline", label: "4. Slide Outline", icon: FileSliders },
                  { to: "/preview", label: "5. Slide Preview", icon: FileSliders },
                  { to: "/settings", label: "6. Build Settings", icon: Settings },
                ].map((item) => {
                  const isActive =
                    location.pathname === item.to ||
                    (item.to === "/processing" && location.pathname.startsWith("/processing/"));
                  const itemTo = item.to === "/processing" && jobId ? `/processing/${jobId}` : item.to;

                  return (
                    <Link key={item.to} to={itemTo} onClick={() => setMobileOpen(false)}>
                      <Button
                        variant={isActive ? "secondary" : "ghost"}
                        size="sm"
                        className="w-full justify-start text-xs h-8 pl-2 gap-2"
                      >
                        <item.icon className="size-3.5" />
                        {item.label}
                      </Button>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
