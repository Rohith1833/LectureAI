import os
import sys
import tempfile
import time
from pathlib import Path

import fitz  # PyMuPDF
import pptx
from PIL import Image, ImageDraw, ImageFont
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app


def _make_rich_multichapter_pdf(path: str) -> None:
    """Create a rich 4-chapter textbook PDF with ~700 words so 10- and 20-slide targets are well supported."""
    doc = fitz.open()
    chapters = [
        (
            "Chapter 1: Cell Structure and Organelles",
            "All living organisms are composed of cells, the basic structural and functional units of life. "
            "Eukaryotic cells contain membrane-bound organelles suspended in cytoplasm, whereas prokaryotic "
            "cells such as bacteria lack a membrane-enclosed nucleus and instead store DNA in a nucleoid region.\n\n"
            "1.1 Nucleus and Genetic Control\n"
            "The nucleus houses linear chromosomes composed of DNA and histone proteins. Its double-membrane "
            "nuclear envelope contains nuclear pores that regulate RNA and protein transport. Inside the nucleus, "
            "the nucleolus assembles ribosomal RNA (rRNA) with proteins to form ribosomal subunits.\n\n"
            "1.2 Mitochondria and Energy Production\n"
            "Mitochondria are double-membraned organelles that generate adenosine triphosphate (ATP) through "
            "aerobic cellular respiration. Their inner membrane folds into cristae, dramatically increasing the "
            "surface area available for the electron transport chain and ATP synthase complexes.",
        ),
        (
            "Chapter 2: Membrane Transport Mechanisms",
            "The plasma membrane consists of a phospholipid bilayer embedded with integral and peripheral proteins, "
            "cholesterol, and carbohydrate chains following the fluid mosaic model. Its selective permeability "
            "regulates nutrient uptake, waste removal, and ion gradients.\n\n"
            "2.1 Passive Transport: Diffusion and Osmosis\n"
            "Simple diffusion moves small nonpolar molecules such as oxygen and carbon dioxide down their "
            "concentration gradient without ATP expenditure. Facilitated diffusion uses channel or carrier "
            "proteins to transport polar ions and glucose. Osmosis describes water movement across a semipermeable "
            "membrane from lower solute concentration (hypotonic) to higher solute concentration (hypertonic).\n\n"
            "2.2 Active Transport and Vesicular Processes\n"
            "Primary active transport consumes ATP directly, exemplified by the sodium-potassium pump, which "
            "exports three Na+ ions and imports two K+ ions per ATP hydrolyzed. Large macromolecules cross the "
            "membrane via endocytosis (phagocytosis and pinocytosis) and exocytosis.",
        ),
        (
            "Chapter 3: Enzymes and Metabolic Pathways",
            "Enzymes are biological catalysts, typically globular proteins, that accelerate biochemical reactions "
            "by lowering activation energy without being consumed in the reaction.\n\n"
            "3.1 Induced-Fit Model and Kinetics\n"
            "Substrates bind to a specific three-dimensional active site. Upon binding, the enzyme undergoes a "
            "conformational change (induced fit) that stabilizes the transition state. Reaction rates increase with "
            "substrate concentration until all active sites reach saturation (Vmax).\n\n"
            "3.2 Enzyme Regulation and Inhibition\n"
            "Competitive inhibitors resemble the substrate and bind reversibly to the active site, whereas "
            "noncompetitive inhibitors bind to an allosteric site and alter enzyme shape. Feedback inhibition "
            "prevents overproduction when the final pathway product inhibits an early allosteric enzyme.",
        ),
        (
            "Chapter 4: Cellular Respiration and Fermentation",
            "Cells harvest chemical energy from glucose through sequential oxidation pathways.\n\n"
            "4.1 Glycolysis and the Citric Acid Cycle\n"
            "Glycolysis occurs in the cytosol, splitting one six-carbon glucose molecule into two three-carbon "
            "pyruvate molecules while producing a net yield of 2 ATP and 2 NADH. In the mitochondrial matrix, "
            "pyruvate is converted to acetyl-CoA and enters the citric acid (Krebs) cycle, releasing CO2 and "
            "generating NADH and FADH2 electron carriers.\n\n"
            "4.2 Oxidative Phosphorylation vs. Fermentation\n"
            "In the inner mitochondrial membrane, NADH and FADH2 donate electrons to the electron transport chain, "
            "pumping protons into the intermembrane space to drive chemiosmosis via ATP synthase (~30-32 ATP total). "
            "Without oxygen, muscle cells perform lactic acid fermentation and yeast perform alcoholic fermentation "
            "to regenerate NAD+ so glycolysis can continue.",
        ),
    ]
    for title, body in chapters:
        page = doc.new_page()
        page.insert_text((50, 65), title, fontsize=17)
        rect = fitz.Rect(50, 100, 545, 790)
        page.insert_textbox(rect, body, fontsize=11)
    doc.save(path)
    doc.close()


def _make_short_pdf(path: str) -> None:
    """Create a concise 1-page PDF (~70 words) to verify insufficient-content warning when requesting 30 slides."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 70), "Brief Note: Ohm's Law", fontsize=17)
    page.insert_text(
        (50, 115),
        "Ohm's Law states that the electric current through a conductor between two points\n"
        "is directly proportional to the voltage across the two points: V = I * R.\n"
        "Here V is voltage in volts, I is current in amperes, and R is resistance in ohms.\n"
        "For example, a 12-volt battery connected to a 4-ohm resistor produces 3 amperes of current.",
        fontsize=11,
    )
    doc.save(path)
    doc.close()


def _render_text_image(lines: list[str]) -> Image.Image:
    w, h = 1654, 2339
    img = Image.new("RGB", (w, h), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font_h = ImageFont.truetype("arial.ttf", 44)
        font_b = ImageFont.truetype("arial.ttf", 29)
    except Exception:
        font_h = ImageFont.load_default()
        font_b = ImageFont.load_default()

    y = 130
    for idx, line in enumerate(lines):
        fnt = font_h if idx == 0 else font_b
        draw.text((100, y), line, fill=(15, 15, 15), font=fnt)
        y += 75 if idx == 0 else 48
    return img


def _make_multichapter_scanned_pdf(path: str) -> None:
    """Create a 3-chapter purely scanned PDF (no selectable text) to test parallel multi-chapter OCR."""
    pages_lines = [
        [
            "Chapter 1: Foundations of Microeconomics",
            "Scarcity arises because human wants exceed limited productive resources.",
            "Opportunity cost is the value of the next best alternative foregone when",
            "making any economic choice. Rational decision makers compare marginal",
            "benefits against marginal costs when choosing optimal output levels.",
            "Example: Attending university has both tuition costs and foregone wages.",
        ],
        [
            "Chapter 2: Supply, Demand, and Market Equilibrium",
            "The Law of Demand states that quantity demanded falls when price rises,",
            "holding other factors constant. The Law of Supply states that quantity",
            "supplied rises as market price increases due to higher profit incentives.",
            "Market equilibrium occurs where quantity demanded equals quantity supplied,",
            "establishing an equilibrium price with neither surplus nor shortage.",
        ],
        [
            "Chapter 3: Elasticity and Market Efficiency",
            "Price elasticity of demand measures how strongly quantity demanded",
            "responds to a percentage change in price. Necessities like insulin tend",
            "to have inelastic demand, whereas luxury goods have elastic demand.",
            "Consumer surplus plus producer surplus equals total economic surplus",
            "in a competitive market operating at allocative efficiency.",
        ],
    ]
    doc = fitz.open()
    temp_imgs = []
    try:
        for lines in pages_lines:
            img = _render_text_image(lines)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                img_path = tf.name
            img.save(img_path)
            temp_imgs.append(img_path)
            page = doc.new_page(width=595, height=842)
            page.insert_image(page.rect, filename=img_path)
        doc.save(path)
        doc.close()
    finally:
        for p in temp_imgs:
            if os.path.exists(p):
                os.remove(p)


def _run_case(
    client: TestClient,
    label: str,
    pdf_path: str,
    target_slide_count: int | None,
    min_slides: int,
    max_slides: int,
    expect_ocr_pages: int = 0,
    expect_notice: bool = False,
) -> None:
    t0 = time.perf_counter()
    print(f"\n=== {label} (target={target_slide_count}) ===")
    with open(pdf_path, "rb") as f:
        up_res = client.post(
            "/api/v1/upload",
            files={"file": (os.path.basename(pdf_path), f, "application/pdf")},
        )
    assert up_res.status_code == 200, up_res.text
    upload_id = up_res.json()["data"]["upload_id"]

    payload = {"upload_id": upload_id, "target_slide_count": target_slide_count}
    gen_res = client.post("/api/v1/presentations/generate", json=payload)
    assert gen_res.status_code == 200, gen_res.text
    job_id = gen_res.json()["job_id"]

    status_data = None
    for _ in range(120):
        st_res = client.get(f"/api/v1/presentations/{job_id}")
        assert st_res.status_code == 200
        status_data = st_res.json()
        if status_data["status"] in ("completed", "failed"):
            break
        time.sleep(0.5)

    assert status_data is not None
    assert status_data["status"] == "completed", f"{label} failed: {status_data.get('error')}"
    deck = status_data["deck"]
    assert deck is not None
    slide_count = len(deck["slides"])
    assert min_slides <= slide_count <= max_slides, (
        f"{label}: expected {min_slides}..{max_slides} slides, got {slide_count}"
    )

    if expect_ocr_pages > 0:
        assert deck["stats"]["ocr_pages"] >= expect_ocr_pages, (
            f"{label}: expected >= {expect_ocr_pages} OCR pages, got {deck['stats']}"
        )

    assert deck.get("validation_report") is not None, f"{label}: missing validation_report"
    if expect_notice:
        assert deck.get("notice"), f"{label}: expected notice when target exceeds content depth"

    dl_res = client.get(f"/api/v1/presentations/{job_id}/download")
    assert dl_res.status_code == 200
    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tf:
        tf.write(dl_res.content)
        pptx_path = tf.name

    try:
        prs = pptx.Presentation(pptx_path)
        assert len(prs.slides) == slide_count
        for idx, slide in enumerate(prs.slides):
            has_text = any(
                sh.has_text_frame and sh.text_frame.text.strip()
                for sh in slide.shapes
            ) or any(
                sh.has_table and any(c.text.strip() for r in sh.table.rows for c in r.cells)
                for sh in slide.shapes
            )
            assert has_text, f"{label}: slide {idx + 1} is empty!"
    finally:
        if os.path.exists(pptx_path):
            os.remove(pptx_path)

    elapsed = round(time.perf_counter() - t0, 2)
    print(
        f"PASS [{label}] in {elapsed}s: {slide_count} slides | "
        f"validation={deck['validation_report']['status']} | "
        f"notice={deck.get('notice')!r}"
    )


def main() -> None:
    only_arg = None
    if len(sys.argv) > 1:
        only_arg = {x.strip() for x in sys.argv[1].split(",") if x.strip()}

    client = TestClient(app)
    with tempfile.TemporaryDirectory() as tmpdir:
        rich_pdf = os.path.join(tmpdir, "biology_4chapters.pdf")
        short_pdf = os.path.join(tmpdir, "short_note.pdf")
        scanned_multi_pdf = os.path.join(tmpdir, "microecon_3chapters_scanned.pdf")

        _make_rich_multichapter_pdf(rich_pdf)
        _make_short_pdf(short_pdf)
        _make_multichapter_scanned_pdf(scanned_multi_pdf)

        def should_run(idx: str) -> bool:
            return only_arg is None or idx in only_arg

        # 1. Auto slide count
        if should_run("1"):
            _run_case(
                client,
                "1. Auto slide count (4-chapter textbook)",
                rich_pdf,
                target_slide_count=None,
                min_slides=6,
                max_slides=35,
            )
        # 2. 10-slide presentation
        if should_run("2"):
            _run_case(
                client,
                "2. 10-slide presentation",
                rich_pdf,
                target_slide_count=10,
                min_slides=8,
                max_slides=10,
            )
        # 3. 20-slide presentation
        if should_run("3"):
            _run_case(
                client,
                "3. 20-slide presentation",
                rich_pdf,
                target_slide_count=20,
                min_slides=16,
                max_slides=20,
            )
        # 4. Custom slide count (e.g. 14 slides)
        if should_run("4"):
            _run_case(
                client,
                "4. Custom slide count (14 slides)",
                rich_pdf,
                target_slide_count=14,
                min_slides=11,
                max_slides=14,
            )
        # 5. Insufficient-content notice check (asking 30 slides for a 70-word note)
        if should_run("5"):
            _run_case(
                client,
                "5. Insufficient-content notice (30 requested on 70-word note)",
                short_pdf,
                target_slide_count=30,
                min_slides=3,
                max_slides=10,
                expect_notice=True,
            )
        # 6. Scanned textbook with multiple chapters (parallel OCR)
        if should_run("6"):
            _run_case(
                client,
                "6. Multi-chapter scanned textbook (3 scanned chapters)",
                scanned_multi_pdf,
                target_slide_count=None,
                min_slides=5,
                max_slides=20,
                expect_ocr_pages=3,
            )


if __name__ == "__main__":
    main()
