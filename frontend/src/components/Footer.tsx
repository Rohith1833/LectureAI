import { Heart } from "lucide-react";

export default function Footer() {
  return (
    <footer className="border-t border-border/40 bg-background/50 backdrop-blur-sm">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-4 py-6 sm:flex-row sm:px-6 lg:px-8">
        <p className="text-sm text-muted-foreground">
          &copy; {new Date().getFullYear()} LectureAI. All rights reserved.
        </p>
        <p className="flex items-center gap-1 text-sm text-muted-foreground">
          Built with <Heart className="size-3.5 fill-red-500 text-red-500" />{" "}
          for educators
        </p>
      </div>
    </footer>
  );
}
