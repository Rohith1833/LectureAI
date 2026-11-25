import { BookOpen, FileText, Sparkles } from "lucide-react";

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-10 py-10">
      <div className="text-center space-y-3">
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">About LectureAI</h1>
        <p className="text-base text-muted-foreground leading-relaxed">
          LectureAI transforms textbook PDFs—whether digital, scanned, or mixed—into
          structured, ready-to-teach PowerPoint presentations in minutes.
        </p>
      </div>

      <div className="grid gap-6 sm:grid-cols-3">
        {[
          {
            icon: FileText,
            title: "Digital & Scanned PDFs",
            desc: "Automatically detects selectable text and runs optical character recognition on scanned pages.",
          },
          {
            icon: BookOpen,
            title: "Educational Structure",
            desc: "Identifies definitions, core concepts, processes, tables, and worked examples.",
          },
          {
            icon: Sparkles,
            title: "Editable PowerPoint",
            desc: "Generates clean, multi-layout 16:9 slides with speaker notes you can customize freely.",
          },
        ].map((item) => (
          <div
            key={item.title}
            className="rounded-xl border border-border bg-card p-5 space-y-2"
          >
            <item.icon className="size-5 text-indigo-600 dark:text-indigo-400" />
            <h2 className="font-semibold text-sm text-foreground">{item.title}</h2>
            <p className="text-xs text-muted-foreground leading-relaxed">{item.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
