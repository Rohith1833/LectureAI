import csv
import os
from pathlib import Path
from app.schemas.artifact import ArtifactPlan

class CSVRenderer:
    """Renders ArtifactPlan into CSV Flashcards."""
    def render(self, plan: ArtifactPlan, output_path: str) -> str:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(out_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(["Front", "Back", "Notes"])
            
            for slide in (plan.slides or []):
                front = (slide.title or "").strip()
                back = "\n".join(str(item) for item in slide.content) if slide.content else ""
                notes = (slide.speaker_notes or "").strip()
                writer.writerow([front, back, notes])
                
        return str(out_file)
