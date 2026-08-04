import { InfoCard } from "@/components/ui/card";
import { Switch, Slider, Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/contexts/themeContext";
import { useSettings, type AIProvider, type PPTTemplate } from "@/contexts/settingsContext";
import { Save, ShieldAlert, RotateCcw } from "lucide-react";
import { useState } from "react";

export default function SettingsPage() {
  const { theme, toggleTheme } = useTheme();
  const { settings, updateSettings, resetSettings } = useSettings();

  const [savedSuccess, setSavedSuccess] = useState(false);

  const handleSlideCountChange = (value: number[]) => {
    if (value[0] !== undefined) {
      updateSettings({ slideCount: value[0] });
    }
  };

  const handleTemplateChange = (val: string) => {
    updateSettings({ pptTemplate: val as PPTTemplate });
  };

  const handleProviderChange = (val: string) => {
    updateSettings({ aiProvider: val as AIProvider });
  };

  const handleSave = () => {
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2000);
  };

  return (
    <div className="space-y-6 py-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 border-b border-border/40 pb-4">
        <div className="space-y-1">
          <h1 className="text-3xl font-bold tracking-tight">Application Settings</h1>
          <p className="text-sm text-muted-foreground">
            Configure default settings for presentation compiles, models, and UI variables.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={resetSettings} className="gap-1.5 text-xs">
            <RotateCcw className="size-3.5" /> Reset Defaults
          </Button>
          <Button
            onClick={handleSave}
            size="sm"
            className="gap-1.5 text-xs bg-violet-600 hover:bg-violet-700 text-white dark:bg-violet-500 dark:hover:bg-violet-600 font-semibold"
          >
            <Save className="size-3.5" /> Save Changes
          </Button>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Left main setting panel */}
        <div className="md:col-span-2 space-y-6">
          {/* UI Appearance */}
          <InfoCard title="Appearance" description="Configure visual display modes">
            <div className="flex items-center justify-between py-2 border-b border-border/40">
              <div>
                <h4 className="font-semibold text-sm">Theme Settings</h4>
                <p className="text-xs text-muted-foreground mt-0.5">Toggle between Light and Dark visual styles.</p>
              </div>
              <Switch
                checked={theme === "dark"}
                onCheckedChange={toggleTheme}
                label={theme === "dark" ? "Dark Mode" : "Light Mode"}
              />
            </div>
          </InfoCard>

          {/* AI Generation Settings */}
          <InfoCard title="AI Compilation Presets" description="Set presentation density parameters">
            <div className="space-y-6 py-2">
              {/* Slide count slider */}
              <Slider
                label="Default Slide Count"
                min={5}
                max={40}
                step={1}
                value={[settings.slideCount]}
                onValueChange={handleSlideCountChange}
              />

              {/* Template dropdown */}
              <div className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block">
                  Preferred PPT Template
                </span>
                <Select value={settings.pptTemplate} onValueChange={handleTemplateChange}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select template..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="default">Default Academic (Sleek Dark/Light)</SelectItem>
                    <SelectItem value="academic">Classic Textbook (Double Columns)</SelectItem>
                    <SelectItem value="creative">Vibrant Tech (Bold Accents & Icons)</SelectItem>
                    <SelectItem value="professional">Minimalist Business (Corporate Gray)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* AI model dropdown */}
              <div className="space-y-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground block">
                  AI Model Provider
                </span>
                <Select value={settings.aiProvider} onValueChange={handleProviderChange}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select AI provider..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="gemini">Google Gemini Pro 1.5</SelectItem>
                    <SelectItem value="groq">Groq Llama 3.1 (High Speed)</SelectItem>
                    <SelectItem value="ollama">Ollama Local Instance (Offline)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </InfoCard>
        </div>

        {/* Right Info sidebar */}
        <div className="space-y-6">
          <InfoCard title="Active Configurations">
            <div className="space-y-3 text-xs leading-normal">
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-muted-foreground">Visual Theme:</span>
                <span className="font-semibold capitalize text-foreground">{theme}</span>
              </div>
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-muted-foreground">Default Slides:</span>
                <span className="font-semibold text-foreground">{settings.slideCount} slides</span>
              </div>
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-muted-foreground">Template:</span>
                <span className="font-semibold capitalize text-foreground">{settings.pptTemplate}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">AI Engine:</span>
                <span className="font-semibold capitalize text-foreground">{settings.aiProvider}</span>
              </div>
            </div>
          </InfoCard>

          <InfoCard title="Local Storage">
            <div className="flex gap-2.5 items-start text-xs text-muted-foreground">
              <ShieldAlert className="size-4.5 text-amber-500 shrink-0 mt-0.5" />
              <p>
                All presets are stored in your local browser profile (<code>localStorage</code>) and will persist across sessions.
              </p>
            </div>
          </InfoCard>
        </div>
      </div>

      {savedSuccess && (
        <div className="fixed bottom-4 right-4 bg-emerald-500 text-white px-4 py-2.5 rounded-lg shadow-lg flex items-center gap-2 text-sm font-semibold animate-in fade-in slide-in-from-bottom-2 duration-300">
          <CheckCircle2 className="size-4" /> Configuration saved successfully
        </div>
      )}
    </div>
  );
}

// Quick check helper import
import { CheckCircle2 } from "lucide-react";
