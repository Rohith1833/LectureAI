import os
import sys
import tempfile
import asyncio
from pathlib import Path
from typing import Any, Dict, List

import fitz
from PIL import Image, ImageDraw, ImageFont

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.document import (
    BlockSchema,
    BlockType,
    BoundingBox,
    DocumentExtractionResult,
    DocumentMetadataSchema,
    PageSchema,
)
from app.schemas.presentation import BulletItem, SlideLayoutType, SlideSpec
from app.services.generation.base import LLMGenerationRequest, LLMGenerationResponse
from app.services.presentation_engine import (
    PresentationEngine,
    _allocate_chunk_budgets,
    _consolidate_to_target,
    _deduplicate_slides,
)
from app.agents.ocr_agent import OCRAgent
from app.services import pdf_extractor
from app.services.ocr.page_detector import OCRStrategy


class _FakeLLMProvider:
    """Deterministic test LLM returning predictable slide plans and validation audits."""

    def __init__(self, reject_last_slide: bool = False):
        self.requests: List[LLMGenerationRequest] = []
        self.reject_last_slide = reject_last_slide
        self._slide_seq = 0

    async def generate(self, request: LLMGenerationRequest) -> LLMGenerationResponse:
        self.requests.append(request)
        schema = request.json_schema or {}
        props = schema.get("properties", {})

        # 1. Distillation call
        if "section_summary" in props:
            return LLMGenerationResponse(
                raw_response="{}",
                structured_output={"section_summary": "Core summary of chapter concepts, definitions, and examples."},
                model_name="fake-llm",
            )

        # 2. Validation audit call
        if "slide_reviews" in props:
            import json
            raw = request.prompt
            slides_json = raw.split("<generated_slides>\n")[1].split("\n</generated_slides>")[0]
            slides = json.loads(slides_json)
            reviews = []
            issues = []
            for idx, s in enumerate(slides):
                if self.reject_last_slide and idx == len(slides) - 1:
                    reviews.append({
                        "slide_index": idx,
                        "action": "remove",
                        "content_origin": "textbook",
                        "reason": "Unsupported extra claim removed by audit.",
                    })
                    issues.append("Removed unsupported slide.")
                elif idx == 0:
                    reviews.append({
                        "slide_index": idx,
                        "action": "fix",
                        "content_origin": "textbook_with_explanation",
                        "reason": "Clarified heading accuracy.",
                        "fixed_title": s["title"] + " (Verified)",
                    })
                    issues.append("Clarified heading on slide 0.")
                else:
                    reviews.append({
                        "slide_index": idx,
                        "action": "keep",
                        "content_origin": "textbook",
                    })
            return LLMGenerationResponse(
                raw_response="{}",
                structured_output={
                    "overall_status": "corrected" if issues else "passed",
                    "issues_found": issues,
                    "missing_concepts": [],
                    "summary": f"Audited {len(slides)} slides against source.",
                    "slide_reviews": reviews,
                },
                model_name="fake-llm",
            )

        # 3. Slide planning call: parse requested budget if present
        import re
        m = re.search(r"Generate EXACTLY (\d+) slide", request.prompt)
        count = int(m.group(1)) if m else 4
        req_id = len(self.requests)
        topic_bank = [
            ("Mitochondria Energetics", "Generates adenosine triphosphate via oxidative phosphorylation.", "Cristae Folding", "Inner folds maximize surface area for respiratory complexes.", "Proton Gradient", "Chemiosmotic flow drives rotary catalysis in matrix."),
            ("Ribosomal Translation", "Decodes messenger RNA codons into polypeptide chains.", "Peptide Bonding", "Catalyzes covalent linkage between adjacent amino acids.", "Elongation Factors", "GTP hydrolysis advances translocation along mRNA strand."),
            ("Golgi Apparatus Sorting", "Modifies, packages, and routes nascent glycoproteins.", "Cisternal Maturation", "Enzymes attach oligosaccharide tags across medial stacks.", "Vesicle Budding", "Clathrin coats direct cargo toward secretory destinations."),
            ("Lysosomal Autophagy", "Digests worn organelles inside acidic hydrolytic lumen.", "Acid Hydrolases", "V-type proton pumps maintain pH near 4.8 for breakdown.", "Recycling Amino Acids", "Degraded monomers return to cytosol for reuse."),
            ("Chloroplast Photochemistry", "Captures solar photons to fix atmospheric carbon dioxide.", "Photosystem II", "Splits water molecules releasing oxygen and electrons.", "Calvin Fixation", "RuBisCO incorporates carbon into three-carbon sugars."),
            ("Cytoskeletal Dynamics", "Maintains cellular shape and powers intracellular trafficking.", "Microtubule Tracks", "Kinesin and dynein motors walk along tubulin polymers.", "Actin Filaments", "Myosin cross-bridges drive contractile ring cleavage."),
            ("Sodium Potassium Pump", "Exports three sodium ions while importing two potassium ions.", "Electrochemical Gradient", "ATP hydrolysis alters pump conformation across bilayer.", "Resting Potential", "Maintains negative intracellular voltage in neurons."),
            ("Enzyme Allosteric Control", "Regulates metabolic flux through conformational inhibition.", "Feedback Loop", "End product binds allosteric pocket reducing affinity.", "Induced Fit", "Active site reshapes around transition state geometry."),
            ("Glycolytic Catabolism", "Splits six-carbon glucose into two pyruvate molecules.", "Substrate Phosphorylation", "Kinases transfer phosphate groups yielding net two ATP.", "NADH Reduction", "High-energy electrons shuttle toward aerobic respiration."),
            ("Fermentation Pathways", "Regenerates NAD+ when terminal oxygen is unavailable.", "Lactic Acid Route", "Lactate dehydrogenase reduces pyruvate in muscle tissue.", "Alcoholic Route", "Yeast decarboxylate pyruvate into ethanol and carbon dioxide."),
            ("DNA Replication Fork", "Unwinds double helix and synthesizes complementary daughter strands.", "Helicase Unwinding", "Separates hydrogen-bonded base pairs ahead of polymerase.", "Okazaki Fragments", "Lagging strand forms discontinuously via ligase joining."),
            ("Transcription Initiation", "RNA polymerase binds promoter sequences upstream of coding genes.", "Sigma Recognition", "Recruits catalytic core to TATA consensus box.", "Elongation Bubble", "Synthesizes nascent ribonucleic transcript five-to-three prime."),
            ("Mendelian Segregation", "Allele pairs separate independently during meiotic gamete formation.", "Dominant Phenotype", "Heterozygous genotype expresses dominant trait allele.", "Dihybrid Cross", "Independent assortment produces classic nine-three-three-one ratio."),
            ("Natural Selection Dynamics", "Differential reproductive success shifts population allele frequencies.", "Adaptive Fitness", "Heritable variants confer survival advantages in specific niches.", "Directional Shift", "Environmental pressure moves trait distribution toward optimum."),
            ("Synaptic Neurotransmission", "Action potentials trigger neurotransmitter release across synaptic cleft.", "Calcium Influx", "Voltage-gated channels open upon axonal terminal depolarization.", "Postsynaptic Receptors", "Ligand binding modulates excitatory or inhibitory ion currents."),
            ("Endocrine Hormone Signaling", "Secreted chemical messengers travel via bloodstream to target organs.", "Steroid Receptors", "Lipophilic hormones diffuse across bilayers to bind nuclear factors.", "Peptide Cascades", "Surface GPCRs activate cyclic AMP second-messenger pathways."),
            ("Adaptive Immunity Response", "Lymphocytes mount antigen-specific defense and long-term memory.", "Clonal Selection", "B-cells proliferate into antibody-secreting plasma cells.", "Cytotoxic T-Cells", "Recognize MHC class I peptides on infected host cells."),
            ("Ecosystem Trophic Pyramids", "Solar energy flows upward through producers and consumers.", "Primary Productivity", "Autotrophs convert inorganic carbon into organic biomass.", "Ten Percent Rule", "Metabolic heat limits energy transfer between trophic levels."),
            ("Cardiovascular Circulation", "Heart chambers pump oxygenated and deoxygenated blood continuously.", "Pulmonary Circuit", "Right ventricle sends venous blood toward alveolar capillaries.", "Systemic Arteries", "Left ventricle delivers high-pressure arterial flow to tissues."),
            ("Renal Filtration Homeostasis", "Nephrons filter plasma and regulate water-electrolyte balance.", "Glomerular Pressure", "Bowman capsule collects ultrafiltrate excluding large proteins.", "Loop Countercurrent", "Concentrates urine via osmotic gradient in renal medulla."),
        ]
        slides = []
        for i in range(count):
            t_title, t_def, h1, d1, h2, d2 = topic_bank[self._slide_seq % len(topic_bank)]
            self._slide_seq += 1
            slides.append({
                "layout": "concept",
                "title": f"{t_title} ({req_id}-{i + 1})",
                "subtitle": "",
                "key_definition": t_def,
                "bullets": [
                    {"heading": h1, "detail": d1},
                    {"heading": h2, "detail": d2},
                ],
                "speaker_notes": f"Discuss {t_title} clearly using textbook examples.",
                "content_origin": "textbook",
            })
        return LLMGenerationResponse(
            raw_response="{}",
            structured_output={"deck_title": "Test Textbook Deck", "slides": slides},
            model_name="fake-llm",
        )


def _make_extraction(word_count: int = 320, num_sections: int = 3) -> DocumentExtractionResult:
    blocks = []
    words_per_sec = max(10, word_count // num_sections)
    sample_words = ["biology", "cellular", "membrane", "enzyme", "energy", "glucose", "proton", "gradient", "reaction", "protein"]
    order = 1
    for s in range(num_sections):
        blocks.append(
            BlockSchema(
                block_id=f"h-{s}",
                page_number=s + 1,
                reading_order=order,
                block_type=BlockType.HEADING,
                heading_level=1,
                text=f"Chapter {s + 1}: Core Topic {s + 1}",
                bounding_box=BoundingBox(x0=50, y0=50, x1=400, y1=80),
                confidence=1.0,
                provenance="NATIVE",
            )
        )
        order += 1
        body = " ".join(sample_words[i % len(sample_words)] for i in range(words_per_sec))
        blocks.append(
            BlockSchema(
                block_id=f"p-{s}",
                page_number=s + 1,
                reading_order=order,
                block_type=BlockType.PARAGRAPH,
                text=body,
                bounding_box=BoundingBox(x0=50, y0=100, x1=500, y1=300),
                confidence=1.0,
                provenance="NATIVE",
            )
        )
        order += 1

    return DocumentExtractionResult(
        upload_id="u-test",
        status="processed",
        metadata=DocumentMetadataSchema(title="Test Book", page_count=num_sections),
        pages=[PageSchema(page_number=i + 1, width=595, height=842) for i in range(num_sections)],
        blocks=blocks,
        tables=[],
        images=[],
        extraction_version="1.0.0",
        extraction_timestamp="2026-11-25T00:00:00Z",
        processing_time=0.1,
    )


def test_chunk_budget_allocation():
    budgets = _allocate_chunk_budgets(["a" * 100, "b" * 300, "c" * 200], body_target=12)
    assert sum(budgets) == 12
    assert all(b >= 1 for b in budgets)
    assert budgets[1] > budgets[0]


def test_deduplicate_slides_removes_repeated():
    s1 = SlideSpec(
        layout=SlideLayoutType.CONCEPT,
        title="Mitosis Overview",
        bullets=[BulletItem(heading="Prophase", detail="Chromosomes condense inside the nucleus prior to division.")],
    )
    s2 = SlideSpec(
        layout=SlideLayoutType.CONCEPT,
        title="Mitosis Overview",
        bullets=[BulletItem(heading="Prophase", detail="Chromosomes condense inside the nucleus prior to division.")],
    )
    kept, notes = _deduplicate_slides([s1, s2])
    assert len(kept) == 1
    assert len(notes) == 1


def test_fixed_and_insufficient_slide_counts():
    async def _run():
        # 1. Fixed 10, 20, and custom 14 slides on sufficient content
        ext_rich = _make_extraction(word_count=600, num_sections=4)
        for target in (10, 14, 20):
            provider = _FakeLLMProvider()
            engine = PresentationEngine(provider)
            deck = await engine.generate_deck(ext_rich, "bio.pdf", target_slide_count=target)
            assert len(deck.slides) == target, f"Expected {target}, got {len(deck.slides)}"
            assert deck.validation_report is not None
            assert deck.validation_report.status == "corrected"
            assert deck.slides[1].content_origin == "textbook_with_explanation"

        # 1b. Auto slide count
        provider_auto = _FakeLLMProvider()
        deck_auto = await PresentationEngine(provider_auto).generate_deck(ext_rich, "bio.pdf", target_slide_count=None)
        assert len(deck_auto.slides) >= 4
        assert deck_auto.validation_report is not None

        # 2. Requesting 30 slides on a tiny 50-word single-section note triggers notice without padding
        ext_short = _make_extraction(word_count=50, num_sections=1)
        deck_capped = await engine.generate_deck(ext_short, "short.pdf", target_slide_count=30)
        assert len(deck_capped.slides) < 30
        assert deck_capped.notice is not None
        assert "supports up to" in deck_capped.notice

    asyncio.run(_run())


def test_http_e2e_multichapter_scanned_and_custom_counts():
    """Verify full HTTP upload -> generate -> poll -> download -> python-pptx reopen with real parallel OCR."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    import pptx
    from app.main import app

    pages_lines = [
        ["Chapter 1: Foundations of Microeconomics", "Scarcity arises because human wants exceed limited resources.", "Opportunity cost is the value of the next best alternative foregone."],
        ["Chapter 2: Supply and Demand Equilibrium", "Quantity demanded falls when price rises, ceteris paribus.", "Market equilibrium occurs where quantity demanded equals quantity supplied."],
        ["Chapter 3: Elasticity and Efficiency", "Price elasticity measures responsiveness of quantity demanded to price.", "Consumer surplus plus producer surplus equals total economic surplus."],
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "econ_scanned_3ch.pdf")
        doc = fitz.open()
        for idx, lines in enumerate(pages_lines):
            img = Image.new("RGB", (1400, 1900), color=(255, 255, 255))
            draw = ImageDraw.Draw(img)
            try:
                fnt = ImageFont.truetype("arial.ttf", 36)
            except Exception:
                fnt = ImageFont.load_default()
            y = 140
            for ln in lines:
                draw.text((90, y), ln, fill=(10, 10, 10), font=fnt)
                y += 70
            img_path = os.path.join(tmpdir, f"page_{idx}.png")
            img.save(img_path)
            p = doc.new_page(width=595, height=842)
            p.insert_image(p.rect, filename=img_path)
        doc.save(pdf_path)
        doc.close()

        client = TestClient(app)
        with patch("app.services.presentation_pipeline._get_llm_provider", return_value=_FakeLLMProvider()):
            with open(pdf_path, "rb") as f:
                up = client.post("/api/v1/upload", files={"file": ("econ_scanned_3ch.pdf", f, "application/pdf")})
            assert up.status_code == 200
            upload_id = up.json()["data"]["upload_id"]

            gen = client.post("/api/v1/presentations/generate", json={"upload_id": upload_id, "target_slide_count": 7})
            assert gen.status_code == 200
            job_id = gen.json()["job_id"]

            st = client.get(f"/api/v1/presentations/{job_id}")
            assert st.status_code == 200
            data = st.json()
            assert data["status"] == "completed", data.get("error")
            assert data["deck"]["stats"]["ocr_pages"] == 3
            assert len(data["deck"]["slides"]) == 7

            dl = client.get(f"/api/v1/presentations/{job_id}/download")
            assert dl.status_code == 200
            out_pptx = os.path.join(tmpdir, "out.pptx")
            with open(out_pptx, "wb") as f:
                f.write(dl.content)
            prs = pptx.Presentation(out_pptx)
            assert len(prs.slides) == 7


def test_parallel_multichapter_ocr():
    """Verify parallel OCRAgent processes 3 scanned chapters accurately and preserves reading order."""
    pages_lines = [
        ["Chapter 1: Thermodynamics", "First law states energy is conserved in isolated systems."],
        ["Chapter 2: Electromagnetism", "Faraday law relates changing magnetic flux to induced EMF."],
        ["Chapter 3: Quantum Mechanics", "Planck constant links photon energy to oscillation frequency."],
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "scanned3.pdf")
        doc = fitz.open()
        for idx, lines in enumerate(pages_lines):
            img = Image.new("RGB", (1240, 1754), color=(255, 255, 255))
            draw = ImageDraw.Draw(img)
            try:
                fnt = ImageFont.truetype("arial.ttf", 34)
            except Exception:
                fnt = ImageFont.load_default()
            y = 120
            for ln in lines:
                draw.text((90, y), ln, fill=(10, 10, 10), font=fnt)
                y += 65
            img_path = os.path.join(tmpdir, f"p{idx}.png")
            img.save(img_path)
            p = doc.new_page(width=595, height=842)
            p.insert_image(p.rect, filename=img_path)
        doc.save(pdf_path)
        doc.close()

        ext = pdf_extractor.extract_pdf_document("u-scan3", pdf_path)
        agent = OCRAgent()
        res = agent.process_document(ext, pdf_path, strategy=OCRStrategy.AUTO)
        assert res.ocr_status == "completed"
        all_text = " ".join(b.text for b in res.blocks).lower()
        assert "thermodynamics" in all_text
        assert "electromagnetism" in all_text
        assert "quantum" in all_text
        # Verify page ordering is strictly ascending
        pages_seq = [b.page_number for b in res.blocks]
        assert pages_seq == sorted(pages_seq)


if __name__ == "__main__":
    test_chunk_budget_allocation()
    test_deduplicate_slides_removes_repeated()
    test_fixed_and_insufficient_slide_counts()
    test_parallel_multichapter_ocr()
    test_http_e2e_multichapter_scanned_and_custom_counts()
    print("ALL UNIT TESTS PASSED!")
