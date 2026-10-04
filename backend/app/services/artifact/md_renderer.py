import os
from pathlib import Path
from app.schemas.artifact import ArtifactPlan

class MDRenderer:
    """Renders ArtifactPlan into a Markdown Study Guide or Practice Exam."""
    def render(self, plan: ArtifactPlan, output_path: str) -> str:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        
        lines = []
        metadata = plan.metadata or {}
        doc_title = metadata.get("title") or "Study Material"
        
        lines.append(f"# {doc_title}")
        lines.append("")
        
        for slide in (plan.slides or []):
            title = (slide.title or "Section").strip()
            lines.append(f"## {title}")
            lines.append("")
            
            if slide.content:
                for point in slide.content:
                    lines.append(f"- {point}")
            
            if slide.speaker_notes:
                lines.append("")
                lines.append(f"**Notes/Explanation:** {slide.speaker_notes.strip()}")
            
            lines.append("")
            
        with open(out_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            
        return str(out_file)
