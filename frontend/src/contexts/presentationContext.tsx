import { createContext, useContext, useState } from "react";

export interface Unit {
  id: string;
  title: string;
  description: string;
  selected: boolean;
}

export interface SlideOutline {
  title: string;
  objectives: string[];
  slideCount: number;
}

export interface Slide {
  id: string;
  title: string;
  bullets: string[];
  notes: string;
  imageUrl?: string;
}

interface PresentationContextType {
  units: Unit[];
  outline: SlideOutline[];
  slides: Slide[];
  setUnits: (units: Unit[]) => void;
  setOutline: (outline: SlideOutline[]) => void;
  setSlides: (slides: Slide[]) => void;
  resetPresentationState: () => void;
}

const PresentationContext = createContext<PresentationContextType | undefined>(undefined);

export function PresentationProvider({ children }: { children: React.ReactNode }) {
  const [units, setUnits] = useState<Unit[]>([]);
  const [outline, setOutline] = useState<SlideOutline[]>([]);
  const [slides, setSlides] = useState<Slide[]>([]);

  const resetPresentationState = () => {
    setUnits([]);
    setOutline([]);
    setSlides([]);
  };

  return (
    <PresentationContext.Provider
      value={{
        units,
        outline,
        slides,
        setUnits,
        setOutline,
        setSlides,
        resetPresentationState,
      }}
    >
      {children}
    </PresentationContext.Provider>
  );
}

export function usePresentation() {
  const context = useContext(PresentationContext);
  if (!context) {
    throw new Error("usePresentation must be used within a PresentationProvider");
  }
  return context;
}
