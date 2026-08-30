import {
  HelpCircle,
  BookOpen,
  FileText,
  GitCompare,
  GraduationCap,
  type LucideIcon,
} from "lucide-react";
import type { GenerationMode } from "@/types/generation";

export interface ModeConfig {
  key: GenerationMode;
  label: string;
  shortLabel: string;
  description: string;
  icon: LucideIcon;
}

export const GENERATION_MODES: ModeConfig[] = [
  {
    key: "QA",
    label: "Grounded Q&A",
    shortLabel: "Q&A",
    description: "Direct answers to specific questions with citation backing",
    icon: HelpCircle,
  },
  {
    key: "EXPLANATION",
    label: "Concept Explanation",
    shortLabel: "Explain",
    description: "Step-by-step conceptual breakdowns and mechanism explanations",
    icon: BookOpen,
  },
  {
    key: "SUMMARY",
    label: "Grounded Summary",
    shortLabel: "Summary",
    description: "Concise document overviews and structured key takeaways",
    icon: FileText,
  },
  {
    key: "COMPARISON",
    label: "Concept Comparison",
    shortLabel: "Compare",
    description: "Side-by-side dimensional comparison table and trade-offs",
    icon: GitCompare,
  },
  {
    key: "STUDY_GUIDE",
    label: "Study Guide",
    shortLabel: "Study Guide",
    description: "Key concepts, learning objectives, and review questions",
    icon: GraduationCap,
  },
];
