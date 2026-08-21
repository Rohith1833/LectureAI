import { BrowserRouter, Routes, Route } from "react-router-dom";
import MainLayout from "@/layouts/MainLayout";
import HomePage from "@/pages/HomePage";
import UploadPage from "@/pages/UploadPage";
import ProcessingPage from "@/pages/ProcessingPage";
import UnitsPage from "@/pages/UnitsPage";
import OutlinePage from "@/pages/OutlinePage";
import PreviewPage from "@/pages/PreviewPage";
import SettingsPage from "@/pages/SettingsPage";
import AboutPage from "@/pages/AboutPage";
import NotFoundPage from "@/pages/NotFoundPage";

// Context providers
import { ThemeProvider } from "@/contexts/themeContext";
import { SettingsProvider } from "@/contexts/settingsContext";
import { UploadProvider } from "@/contexts/uploadContext";
import { PresentationProvider } from "@/contexts/presentationContext";

import DocumentPreviewPage from "@/pages/DocumentPreviewPage";
import AcademicReviewPage from "@/pages/AcademicReviewPage";

export default function App() {
  return (
    <ThemeProvider>
      <SettingsProvider>
        <UploadProvider>
          <PresentationProvider>
            <BrowserRouter>
              <Routes>
                <Route element={<MainLayout />}>
                  <Route path="/" element={<HomePage />} />
                  <Route path="/upload" element={<UploadPage />} />
                  <Route path="/processing/:jobId" element={<ProcessingPage />} />
                  <Route path="/documents/:id" element={<DocumentPreviewPage />} />
                  <Route path="/academic/review/:uploadId" element={<AcademicReviewPage />} />
                  <Route path="/units" element={<UnitsPage />} />
                  <Route path="/outline" element={<OutlinePage />} />
                  <Route path="/preview" element={<PreviewPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/about" element={<AboutPage />} />
                  <Route path="*" element={<NotFoundPage />} />
                </Route>
              </Routes>
            </BrowserRouter>
          </PresentationProvider>
        </UploadProvider>
      </SettingsProvider>
    </ThemeProvider>
  );
}
