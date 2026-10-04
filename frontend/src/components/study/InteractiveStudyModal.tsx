import { useState, useEffect, useCallback, useMemo } from "react";
import type { SlideModel, ArtifactJobRead } from "@/types/artifact";
import {
  X,
  RotateCw,
  ChevronLeft,
  ChevronRight,
  Shuffle,
  CheckCircle2,
  XCircle,
  Sparkles,
  BookOpen,
  HelpCircle,
  List,
  Layers,
  Award,
  RefreshCw,
} from "lucide-react";

interface InteractiveStudyModalProps {
  job: ArtifactJobRead;
  isOpen: boolean;
  onClose: () => void;
}

type StudyMode = "FLASHCARDS" | "QUIZ" | "LIST";

export default function InteractiveStudyModal({
  job,
  isOpen,
  onClose,
}: InteractiveStudyModalProps) {
  const rawSlides: SlideModel[] = useMemo(() => {
    if (!job.plan || typeof job.plan !== "object") return [];
    const slides = (job.plan as { slides?: SlideModel[] }).slides;
    return Array.isArray(slides) ? slides : [];
  }, [job.plan]);

  const [slides, setSlides] = useState<SlideModel[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [mode, setMode] = useState<StudyMode>("FLASHCARDS");
  const [masteredIds, setMasteredIds] = useState<Set<number>>(new Set());
  const [practiceIds, setPracticeIds] = useState<Set<number>>(new Set());
  const [filterUnmasteredOnly, setFilterUnmasteredOnly] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [quizRevealed, setQuizRevealed] = useState<Record<number, boolean>>({});

  // Initialize or reset slides when job changes
  useEffect(() => {
    setSlides(rawSlides);
    setCurrentIndex(0);
    setIsFlipped(false);
    setMasteredIds(new Set());
    setPracticeIds(new Set());
    setQuizRevealed({});
  }, [rawSlides, isOpen]);

  // Active working set based on unmastered filter
  const activeDeck = useMemo(() => {
    if (!filterUnmasteredOnly) return slides;
    return slides.filter((_, idx) => !masteredIds.has(idx));
  }, [slides, filterUnmasteredOnly, masteredIds]);

  const currentSlide = activeDeck[currentIndex] || activeDeck[0];
  const totalCards = activeDeck.length;

  const handleNext = useCallback(() => {
    setIsFlipped(false);
    setCurrentIndex((prev) => (prev + 1 < totalCards ? prev + 1 : 0));
  }, [totalCards]);

  const handlePrev = useCallback(() => {
    setIsFlipped(false);
    setCurrentIndex((prev) => (prev - 1 >= 0 ? prev - 1 : totalCards - 1));
  }, [totalCards]);

  const handleFlip = useCallback(() => {
    setIsFlipped((prev) => !prev);
  }, []);

  const handleShuffle = () => {
    setIsFlipped(false);
    setSlides((prev) => [...prev].sort(() => Math.random() - 0.5));
    setCurrentIndex(0);
  };

  const handleMarkMastered = () => {
    const originalIndex = slides.indexOf(currentSlide);
    if (originalIndex !== -1) {
      setMasteredIds((prev) => {
        const next = new Set(prev);
        next.add(originalIndex);
        return next;
      });
      setPracticeIds((prev) => {
        const next = new Set(prev);
        next.delete(originalIndex);
        return next;
      });
    }
    handleNext();
  };

  const handleMarkPractice = () => {
    const originalIndex = slides.indexOf(currentSlide);
    if (originalIndex !== -1) {
      setPracticeIds((prev) => {
        const next = new Set(prev);
        next.add(originalIndex);
        return next;
      });
      setMasteredIds((prev) => {
        const next = new Set(prev);
        next.delete(originalIndex);
        return next;
      });
    }
    handleNext();
  };

  const handleResetMastery = () => {
    setMasteredIds(new Set());
    setPracticeIds(new Set());
    setFilterUnmasteredOnly(false);
    setCurrentIndex(0);
    setIsFlipped(false);
  };

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === " " && mode === "FLASHCARDS") {
        e.preventDefault();
        handleFlip();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        handleNext();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        handlePrev();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, mode, handleFlip, handleNext, handlePrev, onClose]);

  if (!isOpen) return null;

  const masteryPercent =
    slides.length > 0
      ? Math.round((masteredIds.size / slides.length) * 100)
      : 0;

  // Filtered list for LIST mode
  const filteredListSlides = slides.filter(
    (s) =>
      s.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      s.content.some((c) => c.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-4xl max-h-[92vh] flex flex-col bg-card border border-border rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-muted/40">
          <div className="flex items-center gap-3">
            <div className="size-9 rounded-xl bg-violet-600/10 text-violet-600 dark:text-violet-400 flex items-center justify-center font-bold">
              <Sparkles className="size-5" />
            </div>
            <div>
              <h2 className="text-base sm:text-lg font-bold text-foreground flex items-center gap-2">
                Interactive Study Deck
                <span className="text-xs font-normal text-muted-foreground bg-muted px-2.5 py-0.5 rounded-full">
                  {job.artifact_type.replace(/_/g, " ")}
                </span>
              </h2>
              <p className="text-xs text-muted-foreground">
                Master core concepts with active recall and self-assessment
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Mode Switcher */}
            <div className="hidden sm:flex items-center bg-muted p-1 rounded-xl text-xs font-medium border border-border">
              <button
                onClick={() => setMode("FLASHCARDS")}
                className={`px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 cursor-pointer ${
                  mode === "FLASHCARDS"
                    ? "bg-card text-foreground shadow-xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Layers className="size-3.5" />
                Flashcards
              </button>
              <button
                onClick={() => setMode("QUIZ")}
                className={`px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 cursor-pointer ${
                  mode === "QUIZ"
                    ? "bg-card text-foreground shadow-xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <HelpCircle className="size-3.5" />
                Practice Quiz
              </button>
              <button
                onClick={() => setMode("LIST")}
                className={`px-3 py-1.5 rounded-lg transition-all flex items-center gap-1.5 cursor-pointer ${
                  mode === "LIST"
                    ? "bg-card text-foreground shadow-xs font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <List className="size-3.5" />
                All Cards
              </button>
            </div>

            <button
              onClick={onClose}
              className="size-8 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
              title="Close (Esc)"
            >
              <X className="size-5" />
            </button>
          </div>
        </div>

        {/* Mobile Mode Switcher Bar */}
        <div className="sm:hidden flex items-center justify-around border-b border-border bg-muted/20 p-2 text-xs">
          <button
            onClick={() => setMode("FLASHCARDS")}
            className={`px-3 py-1 rounded-md ${
              mode === "FLASHCARDS" ? "bg-violet-600 text-white font-semibold" : "text-muted-foreground"
            }`}
          >
            Flashcards
          </button>
          <button
            onClick={() => setMode("QUIZ")}
            className={`px-3 py-1 rounded-md ${
              mode === "QUIZ" ? "bg-violet-600 text-white font-semibold" : "text-muted-foreground"
            }`}
          >
            Quiz
          </button>
          <button
            onClick={() => setMode("LIST")}
            className={`px-3 py-1 rounded-md ${
              mode === "LIST" ? "bg-violet-600 text-white font-semibold" : "text-muted-foreground"
            }`}
          >
            List
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 flex flex-col justify-between">
          {totalCards === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center gap-3">
              <BookOpen className="size-12 text-muted-foreground/40" />
              <h3 className="font-semibold text-foreground">No Cards Available</h3>
              <p className="text-xs text-muted-foreground max-w-sm">
                This artifact does not contain generated cards or sections to study.
              </p>
            </div>
          ) : mode === "FLASHCARDS" ? (
            <div className="flex flex-col items-center justify-center gap-6 max-w-2xl mx-auto w-full">
              {/* Progress & Mastery Header */}
              <div className="w-full flex items-center justify-between text-xs text-muted-foreground">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-foreground">
                    Card {currentIndex + 1} of {totalCards}
                  </span>
                  {currentSlide?.slide_type && (
                    <span className="px-2 py-0.5 rounded-full bg-violet-50 dark:bg-violet-950/40 text-violet-700 dark:text-violet-300 border border-violet-200 dark:border-violet-900/50 uppercase text-[10px] font-bold">
                      {currentSlide.slide_type}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium">
                    <CheckCircle2 className="size-3.5" /> {masteredIds.size} Mastered
                  </span>
                  <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400 font-medium">
                    <XCircle className="size-3.5" /> {practiceIds.size} Review
                  </span>
                  <button
                    onClick={handleShuffle}
                    className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                    title="Shuffle Deck"
                  >
                    <Shuffle className="size-3.5" />
                  </button>
                </div>
              </div>

              {/* Progress Bar */}
              <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-violet-600 transition-all duration-300"
                  style={{ width: `${((currentIndex + 1) / totalCards) * 100}%` }}
                />
              </div>

              {/* 3D Flip Flashcard */}
              <div
                className="w-full min-h-[300px] sm:min-h-[340px] cursor-pointer [perspective:1000px] select-none"
                onClick={handleFlip}
              >
                <div
                  className={`relative w-full h-full min-h-[300px] sm:min-h-[340px] rounded-2xl border transition-transform duration-500 [transform-style:preserve-3d] shadow-lg ${
                    isFlipped ? "[transform:rotateY(180deg)]" : ""
                  } ${
                    isFlipped
                      ? "border-violet-300 dark:border-violet-800 bg-gradient-to-br from-violet-500/5 to-purple-500/10"
                      : "border-border bg-card hover:border-violet-400 dark:hover:border-violet-600"
                  }`}
                >
                  {/* Front Side */}
                  <div className="absolute inset-0 w-full h-full p-6 sm:p-8 flex flex-col justify-between [backface-visibility:hidden]">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-violet-600 dark:text-violet-400">
                        Term / Prompt
                      </span>
                      <span className="text-[11px] text-muted-foreground/60">
                        Click or Space to flip
                      </span>
                    </div>

                    <div className="my-auto text-center py-6">
                      <h3 className="text-xl sm:text-2xl font-bold text-foreground leading-relaxed">
                        {currentSlide?.title}
                      </h3>
                    </div>

                    <div className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground/70">
                      <RotateCw className="size-3.5" />
                      <span>Flip to reveal answer</span>
                    </div>
                  </div>

                  {/* Back Side */}
                  <div className="absolute inset-0 w-full h-full p-6 sm:p-8 flex flex-col justify-between [transform:rotateY(180deg)] [backface-visibility:hidden]">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
                        Definition / Explanation
                      </span>
                      <span className="text-[11px] text-muted-foreground/60">
                        Click or Space to flip back
                      </span>
                    </div>

                    <div className="my-auto py-4 overflow-y-auto max-h-[220px]">
                      {currentSlide?.content && currentSlide.content.length > 0 ? (
                        <ul className="space-y-2 text-left text-sm sm:text-base text-foreground leading-relaxed">
                          {currentSlide.content.map((point, i) => (
                            <li key={i} className="flex items-start gap-2">
                              <span className="text-violet-500 font-bold">•</span>
                              <span>{point}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-center text-sm text-muted-foreground italic">
                          No additional details provided.
                        </p>
                      )}

                      {currentSlide?.speaker_notes && (
                        <div className="mt-4 pt-3 border-t border-border/60 text-xs text-muted-foreground text-left bg-muted/30 p-2.5 rounded-lg">
                          <strong className="text-foreground">Key Note:</strong>{" "}
                          {currentSlide.speaker_notes}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground/70">
                      <RotateCw className="size-3.5" />
                      <span>Flip back to prompt</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Action & Navigation Controls */}
              <div className="w-full flex flex-col sm:flex-row items-center justify-between gap-4 pt-2">
                {/* Left/Right Card Navigation */}
                <div className="flex items-center gap-2">
                  <button
                    onClick={handlePrev}
                    className="p-2.5 rounded-xl border border-border bg-card hover:bg-muted text-foreground transition-colors cursor-pointer"
                    title="Previous Card (Left Arrow)"
                  >
                    <ChevronLeft className="size-5" />
                  </button>
                  <button
                    onClick={handleFlip}
                    className="px-4 py-2.5 rounded-xl border border-border bg-card hover:bg-muted text-xs font-semibold text-foreground flex items-center gap-1.5 transition-colors cursor-pointer"
                  >
                    <RotateCw className="size-3.5" />
                    Flip Card
                  </button>
                  <button
                    onClick={handleNext}
                    className="p-2.5 rounded-xl border border-border bg-card hover:bg-muted text-foreground transition-colors cursor-pointer"
                    title="Next Card (Right Arrow)"
                  >
                    <ChevronRight className="size-5" />
                  </button>
                </div>

                {/* Self-Rating Feedback Buttons */}
                <div className="flex items-center gap-2.5 w-full sm:w-auto">
                  <button
                    onClick={handleMarkPractice}
                    className="flex-1 sm:flex-initial px-4 py-2.5 rounded-xl border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/20 text-amber-700 dark:text-amber-300 hover:bg-amber-100 dark:hover:bg-amber-900/30 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                  >
                    <XCircle className="size-4 text-amber-600" />
                    Needs Review
                  </button>
                  <button
                    onClick={handleMarkMastered}
                    className="flex-1 sm:flex-initial px-4 py-2.5 rounded-xl border border-emerald-200 dark:border-emerald-900/50 bg-emerald-50 dark:bg-emerald-950/20 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-900/30 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                  >
                    <CheckCircle2 className="size-4 text-emerald-600" />
                    Mastered
                  </button>
                </div>
              </div>
            </div>
          ) : mode === "QUIZ" ? (
            /* Quiz / Practice Mode */
            <div className="max-w-2xl mx-auto w-full flex flex-col gap-6 py-2">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span className="font-semibold text-foreground">
                  Question {currentIndex + 1} of {totalCards}
                </span>
                <span className="text-violet-600 dark:text-violet-400 font-semibold">
                  Score: {masteredIds.size} Correct / {slides.length}
                </span>
              </div>

              <div className="p-6 sm:p-8 rounded-2xl border border-border bg-card shadow-sm flex flex-col gap-5">
                <span className="text-xs font-bold uppercase tracking-wider text-violet-600">
                  Question / Concept
                </span>
                <h3 className="text-lg sm:text-xl font-bold text-foreground">
                  {currentSlide?.title}
                </h3>

                {quizRevealed[currentIndex] ? (
                  <div className="space-y-4 pt-4 border-t border-border animate-in fade-in duration-200">
                    <span className="text-xs font-bold uppercase tracking-wider text-emerald-600">
                      Answer & Explanation
                    </span>
                    <ul className="space-y-2 text-sm text-foreground">
                      {currentSlide?.content?.map((point, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <CheckCircle2 className="size-4 text-emerald-500 shrink-0 mt-0.5" />
                          <span>{point}</span>
                        </li>
                      ))}
                    </ul>

                    {currentSlide?.speaker_notes && (
                      <div className="p-3 bg-muted rounded-xl text-xs text-muted-foreground">
                        <strong className="text-foreground">Explanation:</strong>{" "}
                        {currentSlide.speaker_notes}
                      </div>
                    )}
                  </div>
                ) : (
                  <button
                    onClick={() =>
                      setQuizRevealed((prev) => ({ ...prev, [currentIndex]: true }))
                    }
                    className="w-full py-3.5 rounded-xl border border-dashed border-violet-300 dark:border-violet-700 bg-violet-50/50 dark:bg-violet-950/20 text-violet-700 dark:text-violet-300 font-semibold text-xs sm:text-sm hover:bg-violet-100/50 transition-colors cursor-pointer"
                  >
                    Click to Reveal Answer & Verification
                  </button>
                )}
              </div>

              {/* Quiz Navigation */}
              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={handlePrev}
                  className="px-4 py-2 rounded-xl border border-border bg-card hover:bg-muted text-xs font-semibold text-foreground flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <ChevronLeft className="size-4" /> Previous
                </button>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      handleMarkPractice();
                    }}
                    className="px-4 py-2 rounded-xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/30 text-rose-700 dark:text-rose-300 text-xs font-semibold hover:bg-rose-100 transition-colors cursor-pointer"
                  >
                    I Missed It
                  </button>
                  <button
                    onClick={() => {
                      handleMarkMastered();
                    }}
                    className="px-4 py-2 rounded-xl border border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-300 text-xs font-semibold hover:bg-emerald-100 transition-colors cursor-pointer"
                  >
                    I Got It!
                  </button>
                </div>

                <button
                  onClick={handleNext}
                  className="px-4 py-2 rounded-xl border border-border bg-card hover:bg-muted text-xs font-semibold text-foreground flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  Next <ChevronRight className="size-4" />
                </button>
              </div>
            </div>
          ) : (
            /* List View */
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between gap-3">
                <input
                  type="text"
                  placeholder="Filter cards by term or concept..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full sm:max-w-md px-3.5 py-2 text-xs border border-border bg-background rounded-xl focus:outline-none focus:ring-2 focus:ring-violet-500"
                />
                <span className="text-xs text-muted-foreground shrink-0">
                  {filteredListSlides.length} cards found
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 max-h-[460px] overflow-y-auto pr-1">
                {filteredListSlides.map((slide, idx) => (
                  <div
                    key={idx}
                    className="p-4 rounded-xl border border-border bg-card flex flex-col justify-between gap-3 hover:border-violet-300 dark:hover:border-violet-700 transition-colors"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <span className="text-[10px] font-bold text-violet-600 uppercase">
                          Card #{idx + 1}
                        </span>
                        {masteredIds.has(idx) && (
                          <span className="text-[10px] text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30 px-2 py-0.5 rounded-full font-semibold">
                            Mastered
                          </span>
                        )}
                      </div>
                      <h4 className="text-sm font-bold text-foreground">
                        {slide.title}
                      </h4>
                      <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                        {slide.content?.map((c, ci) => (
                          <li key={ci} className="line-clamp-2">
                            • {c}
                          </li>
                        ))}
                      </ul>
                    </div>

                    {slide.speaker_notes && (
                      <p className="text-[11px] text-muted-foreground/80 bg-muted/40 p-2 rounded-lg italic">
                        {slide.speaker_notes}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer with Mastery Rate & Reset */}
        <div className="px-5 py-3 border-t border-border bg-muted/30 flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <Award className="size-4 text-violet-600" />
            <span>
              Mastery Score: <strong>{masteryPercent}%</strong> ({masteredIds.size}/{slides.length} cards)
            </span>
          </div>

          <button
            onClick={handleResetMastery}
            className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors cursor-pointer text-xs"
          >
            <RefreshCw className="size-3" />
            Reset Progress
          </button>
        </div>
      </div>
    </div>
  );
}
