import { createContext, useContext, useEffect, useState } from "react";

export type AIProvider = "gemini" | "groq" | "ollama";
export type PPTTemplate = "default" | "academic" | "creative" | "professional";

export interface AppSettings {
  slideCount: number;
  pptTemplate: PPTTemplate;
  aiProvider: AIProvider;
}

interface SettingsContextType {
  settings: AppSettings;
  updateSettings: (newSettings: Partial<AppSettings>) => void;
  resetSettings: () => void;
}

const defaultSettings: AppSettings = {
  slideCount: 15,
  pptTemplate: "default",
  aiProvider: "gemini",
};

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<AppSettings>(() => {
    try {
      const saved = localStorage.getItem("app_settings");
      if (saved) {
        const parsed = JSON.parse(saved);
        // Basic schema verification
        return {
          slideCount: typeof parsed.slideCount === "number" ? parsed.slideCount : defaultSettings.slideCount,
          pptTemplate: ["default", "academic", "creative", "professional"].includes(parsed.pptTemplate)
            ? parsed.pptTemplate
            : defaultSettings.pptTemplate,
          aiProvider: ["gemini", "groq", "ollama"].includes(parsed.aiProvider)
            ? parsed.aiProvider
            : defaultSettings.aiProvider,
        };
      }
    } catch {
      // Ignore parsing errors and fallback
    }
    return defaultSettings;
  });

  useEffect(() => {
    localStorage.setItem("app_settings", JSON.stringify(settings));
  }, [settings]);

  const updateSettings = (newSettings: Partial<AppSettings>) => {
    setSettings((prev) => ({ ...prev, ...newSettings }));
  };

  const resetSettings = () => {
    setSettings(defaultSettings);
  };

  return (
    <SettingsContext.Provider value={{ settings, updateSettings, resetSettings }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error("useSettings must be used within a SettingsProvider");
  }
  return context;
}
