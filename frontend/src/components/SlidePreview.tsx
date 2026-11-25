import { useState } from "react";
import { ChevronLeft, ChevronRight, ArrowRight, MessageSquareText } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { PresentationDeck, SlideSpec } from "@/types/presentation";

interface SlidePreviewProps {
  deck: PresentationDeck;
}

function SlideCanvas({
  slide,
  deckTitle,
  index,
  total,
}: {
  slide: SlideSpec;
  deckTitle: string;
  index: number;
  total: number;
}) {
  if (slide.layout === "title") {
    return (
      <div className="relative aspect-[16/9] w-full overflow-hidden rounded-xl bg-slate-900 text-white shadow-lg flex flex-col justify-center px-10 sm:px-14 border border-slate-800">
        <div className="absolute inset-y-0 left-0 w-3 bg-indigo-600" />
        <div className="absolute inset-y-0 left-3 w-1 bg-teal-500" />
        <span className="inline-block w-fit rounded-md bg-slate-800 px-3 py-1 text-[11px] font-bold tracking-wider text-teal-300 uppercase mb-4">
          Lecture Presentation
        </span>
        <h2 className="text-2xl sm:text-4xl font-bold tracking-tight leading-tight max-w-3xl">
          {slide.title}
        </h2>
        {slide.subtitle && (
          <p className="mt-4 text-sm sm:text-base text-slate-300 max-w-2xl leading-relaxed">
            {slide.subtitle}
          </p>
        )}
        <div className="mt-8 h-1 w-28 rounded-full bg-teal-500" />
      </div>
    );
  }

  if (slide.layout === "section") {
    return (
      <div className="relative aspect-[16/9] w-full overflow-hidden rounded-xl bg-slate-800 text-white shadow-lg flex flex-col justify-center px-10 sm:px-14 border border-slate-700">
        <div className="absolute left-0 top-1/4 bottom-1/4 w-2.5 bg-teal-500" />
        <h2 className="text-2xl sm:text-3xl font-bold tracking-tight max-w-3xl">
          {slide.title}
        </h2>
        {slide.subtitle && (
          <p className="mt-3 text-sm sm:text-base text-slate-300 max-w-2xl">
            {slide.subtitle}
          </p>
        )}
        <div className="absolute bottom-3 right-6 text-[11px] text-slate-400">
          Slide {index + 1} of {total}
        </div>
      </div>
    );
  }

  const tagMap: Record<string, string> = {
    concept: "Core Concept",
    two_column: "Comparison",
    process: "Process & Flow",
    table: "Structured Data",
    example: "Worked Example",
    summary: "Key Takeaways",
  };

  return (
    <div className="relative aspect-[16/9] w-full overflow-hidden rounded-xl bg-slate-50 text-slate-800 shadow-lg flex flex-col border border-slate-200">
      <div className="h-1.5 w-full bg-indigo-600 shrink-0" />
      <div className="flex-1 flex flex-col px-6 sm:px-8 pt-4 pb-3 overflow-y-auto">
        <div className="flex items-center justify-between gap-2 mb-1">
          <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-indigo-600">
            {tagMap[slide.layout] || "Slide"}
          </span>
          {slide.content_origin && slide.content_origin !== "synthesized_summary" && (
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                slide.content_origin === "textbook_with_explanation"
                  ? "bg-amber-50 text-amber-700"
                  : "bg-emerald-50 text-emerald-700"
              }`}
            >
              {slide.content_origin === "textbook_with_explanation"
                ? "Textbook + Explanation"
                : "From Textbook"}
            </span>
          )}
        </div>
        <h3 className="text-lg sm:text-xl font-bold text-slate-900 leading-snug">
          {slide.title}
        </h3>
        {slide.subtitle && (
          <p className="text-xs text-slate-500 mt-0.5">{slide.subtitle}</p>
        )}
        <div className="my-2.5 h-px w-full bg-slate-200 shrink-0" />

        {/* Concept Layout */}
        {(slide.layout === "concept" || slide.layout === "summary") && (
          <div className="space-y-2.5 flex-1">
            {slide.key_definition && (
              <div className="rounded-lg bg-indigo-50/90 border-l-4 border-indigo-600 px-3.5 py-2 text-xs sm:text-sm text-slate-800">
                <span className="font-bold text-indigo-700">Key Definition: </span>
                {slide.key_definition}
              </div>
            )}
            <div className="space-y-2">
              {slide.bullets.map((b, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2.5 rounded-lg bg-white border border-slate-200 px-3 py-2 shadow-2xs"
                >
                  <span
                    className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold text-white ${
                      slide.layout === "summary" ? "bg-teal-600" : "bg-indigo-600"
                    }`}
                  >
                    {i + 1}
                  </span>
                  <p className="text-xs sm:text-sm leading-snug text-slate-700">
                    <span className="font-semibold text-slate-900">{b.heading}: </span>
                    {b.detail}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Two Column Layout */}
        {slide.layout === "two_column" && (
          <div className="grid grid-cols-2 gap-4 flex-1">
            {[
              { title: slide.left_title || "Key Aspects", items: slide.left_items, color: "bg-indigo-600" },
              { title: slide.right_title || "Applications", items: slide.right_items, color: "bg-teal-600" },
            ].map((col, idx) => (
              <div key={idx} className="rounded-lg bg-white border border-slate-200 overflow-hidden flex flex-col">
                <div className={`${col.color} px-3.5 py-2 text-xs sm:text-sm font-bold text-white`}>
                  {col.title}
                </div>
                <ul className="p-3 space-y-1.5 text-xs sm:text-sm text-slate-700">
                  {col.items.map((it, j) => (
                    <li key={j} className="flex gap-2">
                      <span className="text-slate-400">•</span>
                      <span>{it}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}

        {/* Process Layout */}
        {slide.layout === "process" && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 flex-1 items-stretch">
            {slide.steps.map((st, i) => (
              <div key={i} className="relative flex items-center gap-1.5">
                <div className="flex-1 h-full rounded-lg bg-white border border-slate-200 border-t-4 border-t-indigo-600 p-3 flex flex-col">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-[11px] font-bold text-white">
                      {i + 1}
                    </span>
                    <span className="text-xs sm:text-sm font-bold text-slate-900 leading-tight">
                      {st.step_title}
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 leading-snug">{st.description}</p>
                </div>
                {i < slide.steps.length - 1 && (
                  <ArrowRight className="hidden sm:block size-4 shrink-0 text-slate-400" />
                )}
              </div>
            ))}
          </div>
        )}

        {/* Table Layout */}
        {slide.layout === "table" && (
          <div className="overflow-x-auto flex-1">
            <table className="w-full text-left border-collapse rounded-lg overflow-hidden border border-slate-200 text-xs sm:text-sm">
              <thead>
                <tr className="bg-slate-800 text-white">
                  {slide.headers.map((h, i) => (
                    <th key={i} className="px-3 py-2 font-semibold">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {slide.rows.map((row, rIdx) => (
                  <tr key={rIdx} className={rIdx % 2 === 0 ? "bg-white" : "bg-slate-100"}>
                    {row.map((cell, cIdx) => (
                      <td
                        key={cIdx}
                        className={`px-3 py-2 border-t border-slate-200 ${
                          cIdx === 0 ? "font-semibold text-slate-900" : "text-slate-700"
                        }`}
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Example Layout */}
        {slide.layout === "example" && (
          <div className="space-y-2.5 flex-1">
            {slide.scenario && (
              <div className="rounded-lg bg-amber-50 border-l-4 border-amber-500 px-3.5 py-2 text-xs sm:text-sm text-slate-800">
                <span className="font-bold text-amber-700">Scenario: </span>
                {slide.scenario}
              </div>
            )}
            {slide.walkthrough.length > 0 && (
              <div className="rounded-lg bg-white border border-slate-200 p-3 space-y-1.5">
                {slide.walkthrough.map((w, i) => (
                  <p key={i} className="text-xs sm:text-sm text-slate-700">
                    <span className="font-bold text-indigo-600">Step {i + 1}: </span>
                    {w}
                  </p>
                ))}
              </div>
            )}
            {slide.takeaway && (
              <div className="rounded-lg bg-teal-50 border-l-4 border-teal-600 px-3.5 py-2 text-xs sm:text-sm text-slate-800">
                <span className="font-bold text-teal-700">Key Takeaway: </span>
                {slide.takeaway}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-slate-200 px-6 sm:px-8 py-1.5 text-[10px] text-slate-500 bg-slate-50 shrink-0">
        <span className="truncate max-w-[70%]">{deckTitle}</span>
        <span>
          Slide {index + 1} of {total}
        </span>
      </div>
    </div>
  );
}

export default function SlidePreview({ deck }: SlidePreviewProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const slides = deck.slides || [];
  const currentSlide = slides[currentIndex];

  if (!slides.length) return null;

  return (
    <div className="space-y-4">
      {/* Main Slide Canvas */}
      <SlideCanvas
        slide={currentSlide}
        deckTitle={deck.title}
        index={currentIndex}
        total={slides.length}
      />

      {/* Controls */}
      <div className="flex items-center justify-between gap-4">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setCurrentIndex((i) => Math.max(0, i - 1))}
          disabled={currentIndex === 0}
          className="gap-1.5"
        >
          <ChevronLeft className="size-4" /> Previous
        </Button>

        <span className="text-xs font-medium text-muted-foreground">
          Slide {currentIndex + 1} of {slides.length}
        </span>

        <Button
          variant="outline"
          size="sm"
          onClick={() => setCurrentIndex((i) => Math.min(slides.length - 1, i + 1))}
          disabled={currentIndex === slides.length - 1}
          className="gap-1.5"
        >
          Next <ChevronRight className="size-4" />
        </Button>
      </div>

      {/* Slide Thumbnails Strip */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {slides.map((s, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => setCurrentIndex(idx)}
            className={`shrink-0 w-36 rounded-lg border p-2 text-left transition-all cursor-pointer ${
              idx === currentIndex
                ? "border-indigo-600 bg-indigo-50/60 dark:bg-indigo-950/30 ring-1 ring-indigo-600"
                : "border-border bg-card hover:bg-muted/50"
            }`}
          >
            <div className="text-[10px] font-semibold text-muted-foreground uppercase">
              {idx + 1}. {s.layout.replace("_", " ")}
            </div>
            <div className="mt-0.5 text-xs font-medium truncate text-foreground">
              {s.title}
            </div>
          </button>
        ))}
      </div>

      {/* Speaker Notes */}
      {currentSlide.speaker_notes && (
        <div className="rounded-xl border border-border bg-muted/30 p-4 space-y-1">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            <MessageSquareText className="size-3.5" /> Speaker Notes
          </div>
          <p className="text-sm text-foreground/90 leading-relaxed">
            {currentSlide.speaker_notes}
          </p>
        </div>
      )}
    </div>
  );
}
