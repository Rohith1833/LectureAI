/**
 * Centralized Design System Tokens for LectureAI
 * Provides layout constants, color schemes, font classes, and animation configurations
 */
export const DESIGN_TOKENS = {
  colors: {
    brand: {
      primary: "bg-violet-600 hover:bg-violet-700 text-white dark:bg-violet-500 dark:hover:bg-violet-600",
      secondary: "bg-indigo-600 hover:bg-indigo-700 text-white dark:bg-indigo-500 dark:hover:bg-indigo-600",
      accent: "text-violet-600 dark:text-violet-400",
      gradient: "bg-gradient-to-r from-violet-600 via-indigo-600 to-purple-600 dark:from-violet-400 dark:via-indigo-400 dark:to-purple-400",
    },
    state: {
      success: "bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-400",
      error: "bg-red-500/10 border-red-500/30 text-red-700 dark:text-red-400",
      warning: "bg-amber-500/10 border-amber-500/30 text-amber-700 dark:text-amber-400",
      info: "bg-blue-500/10 border-blue-500/30 text-blue-700 dark:text-blue-400",
    }
  },
  layout: {
    maxWidth: "max-w-6xl mx-auto px-4 sm:px-6 lg:px-8",
    cardPadding: "p-6 sm:p-8",
    sectionSpacing: "py-12 sm:py-16 lg:py-20",
  },
  shadows: {
    sm: "shadow-sm",
    md: "shadow-md dark:shadow-black/10",
    lg: "shadow-lg dark:shadow-black/20",
    glass: "shadow-md bg-background/80 backdrop-blur-lg border border-border/40",
  },
  transitions: {
    default: "transition-all duration-200 ease-in-out",
    slow: "transition-all duration-300 ease-in-out",
    fast: "transition-all duration-150 ease-in-out",
  },
  typography: {
    h1: "text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl",
    h2: "text-2xl font-bold tracking-tight sm:text-3xl",
    h3: "text-lg font-semibold tracking-tight sm:text-xl",
    body: "text-base text-muted-foreground leading-relaxed",
    small: "text-sm text-muted-foreground",
  }
} as const;
