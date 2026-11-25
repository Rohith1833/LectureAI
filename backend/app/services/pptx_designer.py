import os
import pptx
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from app.schemas.presentation import PresentationDeck, SlideLayoutType, SlideSpec


# Design System Colors
NAVY_DARK = RGBColor(0x0F, 0x17, 0x2A)      # #0F172A
SLATE_DARK = RGBColor(0x1E, 0x29, 0x3B)     # #1E293B
SLATE_TEXT = RGBColor(0x33, 0x41, 0x55)     # #334155
MUTED_TEXT = RGBColor(0x64, 0x74, 0x8B)     # #64748B
BG_LIGHT = RGBColor(0xF8, 0xFA, 0xFC)       # #F8FAFC
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BORDER_GRAY = RGBColor(0xCB, 0xD5, 0xE1)    # #CBD5E1
ROW_ALT = RGBColor(0xF1, 0xF5, 0xF9)        # #F1F5F9

INDIGO = RGBColor(0x4F, 0x46, 0xE5)         # #4F46E5
INDIGO_LIGHT = RGBColor(0xEE, 0xF2, 0xFF)   # #EEF2FF
TEAL = RGBColor(0x0D, 0x94, 0x88)           # #0D9488
TEAL_LIGHT = RGBColor(0xF0, 0xFD, 0xFA)     # #F0FDFA
AMBER = RGBColor(0xD9, 0x77, 0x06)          # #D97706
AMBER_LIGHT = RGBColor(0xFF, 0xFB, 0xEB)    # #FFFBEB

FONT_FAMILY = "Calibri"
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


class PPTXDesigner:
    """Renders a PresentationDeck into a professionally designed, editable 16:9 PPTX file."""

    def render(self, deck: PresentationDeck, output_path: str) -> str:
        tmp_path = f"{output_path}.tmp"
        try:
            prs = pptx.Presentation()
            prs.slide_width = SLIDE_W
            prs.slide_height = SLIDE_H
            blank_layout = prs.slide_layouts[6]

            total = len(deck.slides)
            for idx, spec in enumerate(deck.slides):
                slide = prs.slides.add_slide(blank_layout)
                self._render_slide(slide, spec, deck.title, idx + 1, total)

            prs.save(tmp_path)
            os.replace(tmp_path, output_path)
            return output_path
        except Exception as e:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            raise e

    def _set_bg(self, slide, color: RGBColor) -> None:
        bg = slide.background
        fill = bg.fill
        fill.solid()
        fill.fore_color.rgb = color

    def _add_rect(
        self,
        slide,
        left,
        top,
        width,
        height,
        fill_color: RGBColor,
        border_color: RGBColor = None,
        rounded: bool = False,
    ):
        shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
        shape = slide.shapes.add_shape(shape_type, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill_color
        if border_color:
            shape.line.color.rgb = border_color
            shape.line.width = Pt(1)
        else:
            shape.line.fill.background()
        if rounded and len(shape.adjustments) > 0:
            shape.adjustments[0] = 0.04
        return shape

    def _add_header(self, slide, title: str, tag: str, subtitle: str = "") -> float:
        """Render consistent slide header and return Y position where body content can start."""
        # Top thin accent bar
        self._add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.07), INDIGO)

        # Category tag pill
        pill = self._add_rect(
            slide, Inches(0.65), Inches(0.32), Inches(1.55), Inches(0.28), INDIGO_LIGHT, rounded=True
        )
        tf_pill = pill.text_frame
        tf_pill.margin_left = Inches(0.08)
        tf_pill.margin_right = Inches(0.08)
        tf_pill.margin_top = Inches(0.02)
        tf_pill.margin_bottom = Inches(0.02)
        tf_pill.vertical_anchor = MSO_ANCHOR.MIDDLE
        p_pill = tf_pill.paragraphs[0]
        p_pill.text = tag.upper()
        p_pill.alignment = PP_ALIGN.CENTER
        p_pill.font.name = FONT_FAMILY
        p_pill.font.size = Pt(9.5)
        p_pill.font.bold = True
        p_pill.font.color.rgb = INDIGO

        # Title
        tb = slide.shapes.add_textbox(Inches(0.65), Inches(0.66), Inches(12.0), Inches(0.65))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = 0
        tf.margin_top = 0
        p = tf.paragraphs[0]
        p.text = title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(24)
        p.font.bold = True
        p.font.color.rgb = NAVY_DARK

        y_next = 1.32
        if subtitle:
            sb = slide.shapes.add_textbox(Inches(0.65), Inches(1.22), Inches(12.0), Inches(0.35))
            stf = sb.text_frame
            stf.word_wrap = True
            stf.margin_left = 0
            stf.margin_top = 0
            sp = stf.paragraphs[0]
            sp.text = subtitle
            sp.font.name = FONT_FAMILY
            sp.font.size = Pt(12.5)
            sp.font.color.rgb = MUTED_TEXT
            y_next = 1.62

        # Subtle divider
        self._add_rect(slide, Inches(0.65), Inches(y_next), Inches(12.03), Inches(0.015), BORDER_GRAY)
        return y_next + 0.16

    def _add_footer(self, slide, deck_title: str, slide_num: int, total: int) -> None:
        self._add_rect(slide, Inches(0.65), Inches(7.02), Inches(12.03), Inches(0.01), BORDER_GRAY)

        tb_l = slide.shapes.add_textbox(Inches(0.65), Inches(7.08), Inches(9.0), Inches(0.3))
        p_l = tb_l.text_frame.paragraphs[0]
        p_l.text = deck_title[:80]
        p_l.font.name = FONT_FAMILY
        p_l.font.size = Pt(9.5)
        p_l.font.color.rgb = MUTED_TEXT

        tb_r = slide.shapes.add_textbox(Inches(10.5), Inches(7.08), Inches(2.18), Inches(0.3))
        p_r = tb_r.text_frame.paragraphs[0]
        p_r.text = f"Slide {slide_num} of {total}"
        p_r.alignment = PP_ALIGN.RIGHT
        p_r.font.name = FONT_FAMILY
        p_r.font.size = Pt(9.5)
        p_r.font.color.rgb = MUTED_TEXT

    def _render_slide(
        self, slide, spec: SlideSpec, deck_title: str, slide_num: int, total: int
    ) -> None:
        if spec.layout == SlideLayoutType.TITLE:
            self._render_title(slide, spec)
        elif spec.layout == SlideLayoutType.SECTION:
            self._render_section(slide, spec, deck_title, slide_num, total)
        elif spec.layout == SlideLayoutType.TWO_COLUMN:
            self._render_two_column(slide, spec, deck_title, slide_num, total)
        elif spec.layout == SlideLayoutType.PROCESS:
            self._render_process(slide, spec, deck_title, slide_num, total)
        elif spec.layout == SlideLayoutType.TABLE:
            self._render_table(slide, spec, deck_title, slide_num, total)
        elif spec.layout == SlideLayoutType.EXAMPLE:
            self._render_example(slide, spec, deck_title, slide_num, total)
        elif spec.layout == SlideLayoutType.SUMMARY:
            self._render_summary(slide, spec, deck_title, slide_num, total)
        else:
            self._render_concept(slide, spec, deck_title, slide_num, total)

        if spec.speaker_notes:
            notes_slide = slide.notes_slide
            notes_slide.notes_text_frame.text = spec.speaker_notes

    def _render_title(self, slide, spec: SlideSpec) -> None:
        self._set_bg(slide, NAVY_DARK)
        # Left vertical accent bar & top-right geometric accent
        self._add_rect(slide, Inches(0), Inches(0), Inches(0.28), SLIDE_H, INDIGO)
        self._add_rect(slide, Inches(0.28), Inches(0), Inches(0.08), SLIDE_H, TEAL)

        # Badge
        badge = self._add_rect(
            slide, Inches(1.1), Inches(1.65), Inches(2.5), Inches(0.36), SLATE_DARK, rounded=True
        )
        btf = badge.text_frame
        btf.vertical_anchor = MSO_ANCHOR.MIDDLE
        bp = btf.paragraphs[0]
        bp.text = "LECTURE PRESENTATION"
        bp.alignment = PP_ALIGN.CENTER
        bp.font.name = FONT_FAMILY
        bp.font.size = Pt(10.5)
        bp.font.bold = True
        bp.font.color.rgb = RGBColor(0x5E, 0xEA, 0xD4)  # soft teal

        # Main Title
        tb = slide.shapes.add_textbox(Inches(1.1), Inches(2.25), Inches(10.8), Inches(2.2))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = spec.title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(40)
        p.font.bold = True
        p.font.color.rgb = WHITE

        # Subtitle
        if spec.subtitle:
            sb = slide.shapes.add_textbox(Inches(1.1), Inches(4.55), Inches(10.5), Inches(1.2))
            stf = sb.text_frame
            stf.word_wrap = True
            sp = stf.paragraphs[0]
            sp.text = spec.subtitle
            sp.font.name = FONT_FAMILY
            sp.font.size = Pt(17)
            sp.font.color.rgb = RGBColor(0xCB, 0xD5, 0xE1)

        # Bottom line
        self._add_rect(slide, Inches(1.1), Inches(6.35), Inches(3.0), Inches(0.05), TEAL)

    def _render_section(
        self, slide, spec: SlideSpec, deck_title: str, slide_num: int, total: int
    ) -> None:
        self._set_bg(slide, SLATE_DARK)
        self._add_rect(slide, Inches(0), Inches(2.3), Inches(0.22), Inches(2.9), TEAL)

        tb = slide.shapes.add_textbox(Inches(1.0), Inches(2.4), Inches(11.0), Inches(1.6))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = spec.title
        p.font.name = FONT_FAMILY
        p.font.size = Pt(34)
        p.font.bold = True
        p.font.color.rgb = WHITE

        if spec.subtitle:
            sb = slide.shapes.add_textbox(Inches(1.0), Inches(4.15), Inches(10.5), Inches(1.0))
            stf = sb.text_frame
            stf.word_wrap = True
            sp = stf.paragraphs[0]
            sp.text = spec.subtitle
            sp.font.name = FONT_FAMILY
            sp.font.size = Pt(16)
            sp.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

        # Footer text in light slate
        tb_r = slide.shapes.add_textbox(Inches(10.5), Inches(7.05), Inches(2.18), Inches(0.3))
        p_r = tb_r.text_frame.paragraphs[0]
        p_r.text = f"Slide {slide_num} of {total}"
        p_r.alignment = PP_ALIGN.RIGHT
        p_r.font.name = FONT_FAMILY
        p_r.font.size = Pt(9.5)
        p_r.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

    def _render_concept(
        self, slide, spec: SlideSpec, deck_title: str, slide_num: int, total: int
    ) -> None:
        self._set_bg(slide, BG_LIGHT)
        y = self._add_header(slide, spec.title, "Core Concept", spec.subtitle)

        # Optional Key Definition Callout Box
        if spec.key_definition:
            def_h = 0.92
            self._add_rect(
                slide, Inches(0.65), Inches(y), Inches(12.03), Inches(def_h), INDIGO_LIGHT, rounded=True
            )
            self._add_rect(slide, Inches(0.65), Inches(y), Inches(0.1), Inches(def_h), INDIGO)
            tb = slide.shapes.add_textbox(
                Inches(0.92), Inches(y + 0.08), Inches(11.6), Inches(def_h - 0.16)
            )
            tf = tb.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = tf.paragraphs[0]
            run_lbl = p.add_run()
            run_lbl.text = "Key Definition: "
            run_lbl.font.name = FONT_FAMILY
            run_lbl.font.size = Pt(13)
            run_lbl.font.bold = True
            run_lbl.font.color.rgb = INDIGO

            run_txt = p.add_run()
            run_txt.text = spec.key_definition
            run_txt.font.name = FONT_FAMILY
            run_txt.font.size = Pt(13)
            run_txt.font.color.rgb = NAVY_DARK
            y += def_h + 0.18

        # Bullet Cards
        bullets = spec.bullets[:5]
        if bullets:
            avail_h = 6.85 - y
            gap = 0.12
            card_h = min(1.05, (avail_h - gap * (len(bullets) - 1)) / len(bullets))

            for idx, b in enumerate(bullets):
                cy = y + idx * (card_h + gap)
                self._add_rect(
                    slide, Inches(0.65), Inches(cy), Inches(12.03), Inches(card_h), WHITE, BORDER_GRAY, rounded=True
                )
                # Numbered circle badge
                badge = slide.shapes.add_shape(
                    MSO_SHAPE.OVAL, Inches(0.85), Inches(cy + (card_h - 0.34) / 2), Inches(0.34), Inches(0.34)
                )
                badge.fill.solid()
                badge.fill.fore_color.rgb = INDIGO
                badge.line.fill.background()
                btf = badge.text_frame
                btf.vertical_anchor = MSO_ANCHOR.MIDDLE
                bp = btf.paragraphs[0]
                bp.text = str(idx + 1)
                bp.alignment = PP_ALIGN.CENTER
                bp.font.name = FONT_FAMILY
                bp.font.size = Pt(11)
                bp.font.bold = True
                bp.font.color.rgb = WHITE

                tb = slide.shapes.add_textbox(
                    Inches(1.35), Inches(cy + 0.06), Inches(11.15), Inches(card_h - 0.12)
                )
                tf = tb.text_frame
                tf.word_wrap = True
                tf.vertical_anchor = MSO_ANCHOR.MIDDLE
                p = tf.paragraphs[0]
                r1 = p.add_run()
                r1.text = f"{b.heading}: "
                r1.font.name = FONT_FAMILY
                r1.font.size = Pt(13.5)
                r1.font.bold = True
                r1.font.color.rgb = NAVY_DARK

                r2 = p.add_run()
                r2.text = b.detail
                r2.font.name = FONT_FAMILY
                r2.font.size = Pt(13)
                r2.font.color.rgb = SLATE_TEXT

        self._add_footer(slide, deck_title, slide_num, total)

    def _render_two_column(
        self, slide, spec: SlideSpec, deck_title: str, slide_num: int, total: int
    ) -> None:
        self._set_bg(slide, BG_LIGHT)
        y = self._add_header(slide, spec.title, "Comparison", spec.subtitle)

        col_w = 5.82
        col_h = 6.82 - y
        left_x = 0.65
        right_x = 0.65 + col_w + 0.39

        for x, col_title, items, accent in [
            (left_x, spec.left_title or "Key Aspects", spec.left_items, INDIGO),
            (right_x, spec.right_title or "Applications & Contrast", spec.right_items, TEAL),
        ]:
            self._add_rect(
                slide, Inches(x), Inches(y), Inches(col_w), Inches(col_h), WHITE, BORDER_GRAY, rounded=True
            )
            self._add_rect(slide, Inches(x), Inches(y), Inches(col_w), Inches(0.48), accent)

            htb = slide.shapes.add_textbox(Inches(x + 0.2), Inches(y + 0.06), Inches(col_w - 0.4), Inches(0.38))
            htf = htb.text_frame
            htf.vertical_anchor = MSO_ANCHOR.MIDDLE
            hp = htf.paragraphs[0]
            hp.text = col_title
            hp.font.name = FONT_FAMILY
            hp.font.size = Pt(15)
            hp.font.bold = True
            hp.font.color.rgb = WHITE

            btb = slide.shapes.add_textbox(
                Inches(x + 0.24), Inches(y + 0.62), Inches(col_w - 0.48), Inches(col_h - 0.78)
            )
            btf = btb.text_frame
            btf.word_wrap = True
            for i, item in enumerate(items[:6]):
                p = btf.paragraphs[0] if i == 0 else btf.add_paragraph()
                p.text = f"•  {item}"
                p.space_after = Pt(10)
                p.font.name = FONT_FAMILY
                p.font.size = Pt(13)
                p.font.color.rgb = SLATE_TEXT

        self._add_footer(slide, deck_title, slide_num, total)

    def _render_process(
        self, slide, spec: SlideSpec, deck_title: str, slide_num: int, total: int
    ) -> None:
        self._set_bg(slide, BG_LIGHT)
        y = self._add_header(slide, spec.title, "Process & Flow", spec.subtitle)

        steps = spec.steps[:6]
        n = len(steps)
        if n == 0:
            self._add_footer(slide, deck_title, slide_num, total)
            return

        # 1 row if <= 4 steps, 2 rows if 5-6 steps
        cols = n if n <= 4 else (n + 1) // 2
        rows = 1 if n <= 4 else 2

        arrow_w = 0.28
        total_w = 12.03
        card_w = (total_w - arrow_w * (cols - 1)) / cols
        avail_h = 6.80 - y
        row_gap = 0.28
        card_h = (avail_h - (row_gap if rows == 2 else 0)) / rows
        card_h = min(card_h, 3.6)

        for idx, step in enumerate(steps):
            r = idx // cols
            c = idx % cols
            cx = 0.65 + c * (card_w + arrow_w)
            cy = y + r * (card_h + row_gap)

            self._add_rect(
                slide, Inches(cx), Inches(cy), Inches(card_w), Inches(card_h), WHITE, BORDER_GRAY, rounded=True
            )
            self._add_rect(slide, Inches(cx), Inches(cy), Inches(card_w), Inches(0.08), TEAL if r else INDIGO)

            # Step number circle
            badge = slide.shapes.add_shape(
                MSO_SHAPE.OVAL, Inches(cx + 0.18), Inches(cy + 0.2), Inches(0.38), Inches(0.38)
            )
            badge.fill.solid()
            badge.fill.fore_color.rgb = TEAL if r else INDIGO
            badge.line.fill.background()
            bp = badge.text_frame.paragraphs[0]
            bp.text = str(idx + 1)
            bp.alignment = PP_ALIGN.CENTER
            bp.font.name = FONT_FAMILY
            bp.font.size = Pt(12)
            bp.font.bold = True
            bp.font.color.rgb = WHITE

            # Step title
            ttb = slide.shapes.add_textbox(
                Inches(cx + 0.65), Inches(cy + 0.18), Inches(card_w - 0.8), Inches(0.55)
            )
            ttf = ttb.text_frame
            ttf.word_wrap = True
            tp = ttf.paragraphs[0]
            tp.text = step.step_title
            tp.font.name = FONT_FAMILY
            tp.font.size = Pt(13.5)
            tp.font.bold = True
            tp.font.color.rgb = NAVY_DARK

            # Step description
            dtb = slide.shapes.add_textbox(
                Inches(cx + 0.18), Inches(cy + 0.78), Inches(card_w - 0.36), Inches(card_h - 0.9)
            )
            dtf = dtb.text_frame
            dtf.word_wrap = True
            dp = dtf.paragraphs[0]
            dp.text = step.description
            dp.font.name = FONT_FAMILY
            dp.font.size = Pt(12)
            dp.font.color.rgb = SLATE_TEXT

            # Right arrow between steps in the same row
            if c < cols - 1 and idx < n - 1:
                arr = slide.shapes.add_shape(
                    MSO_SHAPE.RIGHT_ARROW,
                    Inches(cx + card_w + 0.04),
                    Inches(cy + card_h / 2 - 0.14),
                    Inches(arrow_w - 0.08),
                    Inches(0.28),
                )
                arr.fill.solid()
                arr.fill.fore_color.rgb = MUTED_TEXT
                arr.line.fill.background()

        self._add_footer(slide, deck_title, slide_num, total)

    def _render_table(
        self, slide, spec: SlideSpec, deck_title: str, slide_num: int, total: int
    ) -> None:
        self._set_bg(slide, BG_LIGHT)
        y = self._add_header(slide, spec.title, "Structured Data", spec.subtitle)

        headers = spec.headers
        rows = spec.rows[:8]
        n_rows = len(rows) + 1
        n_cols = len(headers)

        if n_cols == 0:
            self._add_footer(slide, deck_title, slide_num, total)
            return

        tbl_h = min(5.1, n_rows * 0.58)
        table_shape = slide.shapes.add_table(
            n_rows, n_cols, Inches(0.65), Inches(y), Inches(12.03), Inches(tbl_h)
        )
        table = table_shape.table

        for c_idx, h_text in enumerate(headers):
            cell = table.cell(0, c_idx)
            cell.fill.solid()
            cell.fill.fore_color.rgb = SLATE_DARK
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            p.text = str(h_text)
            p.font.name = FONT_FAMILY
            p.font.size = Pt(12.5)
            p.font.bold = True
            p.font.color.rgb = WHITE

        for r_idx, row_vals in enumerate(rows):
            bg_c = WHITE if r_idx % 2 == 0 else ROW_ALT
            for c_idx in range(n_cols):
                val = row_vals[c_idx] if c_idx < len(row_vals) else ""
                cell = table.cell(r_idx + 1, c_idx)
                cell.fill.solid()
                cell.fill.fore_color.rgb = bg_c
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                p = cell.text_frame.paragraphs[0]
                p.text = str(val)
                p.font.name = FONT_FAMILY
                p.font.size = Pt(11.5)
                p.font.bold = (c_idx == 0)
                p.font.color.rgb = NAVY_DARK if c_idx == 0 else SLATE_TEXT

        self._add_footer(slide, deck_title, slide_num, total)

    def _render_example(
        self, slide, spec: SlideSpec, deck_title: str, slide_num: int, total: int
    ) -> None:
        self._set_bg(slide, BG_LIGHT)
        y = self._add_header(slide, spec.title, "Worked Example", spec.subtitle)

        if spec.scenario:
            sh = 0.95
            self._add_rect(slide, Inches(0.65), Inches(y), Inches(12.03), Inches(sh), AMBER_LIGHT, rounded=True)
            self._add_rect(slide, Inches(0.65), Inches(y), Inches(0.1), Inches(sh), AMBER)
            tb = slide.shapes.add_textbox(Inches(0.92), Inches(y + 0.08), Inches(11.6), Inches(sh - 0.16))
            tf = tb.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = tf.paragraphs[0]
            r1 = p.add_run()
            r1.text = "Scenario: "
            r1.font.name = FONT_FAMILY
            r1.font.size = Pt(13)
            r1.font.bold = True
            r1.font.color.rgb = AMBER
            r2 = p.add_run()
            r2.text = spec.scenario
            r2.font.name = FONT_FAMILY
            r2.font.size = Pt(13)
            r2.font.color.rgb = NAVY_DARK
            y += sh + 0.16

        takeaway_h = 0.85 if spec.takeaway else 0.0
        walk_h = 6.82 - y - (takeaway_h + 0.16 if takeaway_h else 0.0)

        if spec.walkthrough:
            self._add_rect(
                slide, Inches(0.65), Inches(y), Inches(12.03), Inches(walk_h), WHITE, BORDER_GRAY, rounded=True
            )
            tb = slide.shapes.add_textbox(
                Inches(0.9), Inches(y + 0.14), Inches(11.55), Inches(walk_h - 0.28)
            )
            tf = tb.text_frame
            tf.word_wrap = True
            for i, step_text in enumerate(spec.walkthrough[:6]):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                r1 = p.add_run()
                r1.text = f"Step {i + 1}: "
                r1.font.name = FONT_FAMILY
                r1.font.size = Pt(13)
                r1.font.bold = True
                r1.font.color.rgb = INDIGO
                r2 = p.add_run()
                r2.text = step_text
                r2.font.name = FONT_FAMILY
                r2.font.size = Pt(13)
                r2.font.color.rgb = SLATE_TEXT
                p.space_after = Pt(8)
            y += walk_h + 0.16

        if spec.takeaway:
            self._add_rect(slide, Inches(0.65), Inches(y), Inches(12.03), Inches(takeaway_h), TEAL_LIGHT, rounded=True)
            self._add_rect(slide, Inches(0.65), Inches(y), Inches(0.1), Inches(takeaway_h), TEAL)
            tb = slide.shapes.add_textbox(Inches(0.92), Inches(y + 0.06), Inches(11.6), Inches(takeaway_h - 0.12))
            tf = tb.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = tf.paragraphs[0]
            r1 = p.add_run()
            r1.text = "Key Takeaway: "
            r1.font.name = FONT_FAMILY
            r1.font.size = Pt(13)
            r1.font.bold = True
            r1.font.color.rgb = TEAL
            r2 = p.add_run()
            r2.text = spec.takeaway
            r2.font.name = FONT_FAMILY
            r2.font.size = Pt(13)
            r2.font.color.rgb = NAVY_DARK

        self._add_footer(slide, deck_title, slide_num, total)

    def _render_summary(
        self, slide, spec: SlideSpec, deck_title: str, slide_num: int, total: int
    ) -> None:
        self._set_bg(slide, BG_LIGHT)
        y = self._add_header(slide, spec.title, "Key Takeaways", spec.subtitle)

        bullets = spec.bullets[:6]
        if bullets:
            avail_h = 6.85 - y
            gap = 0.12
            card_h = min(1.0, (avail_h - gap * (len(bullets) - 1)) / len(bullets))

            for idx, b in enumerate(bullets):
                cy = y + idx * (card_h + gap)
                self._add_rect(
                    slide, Inches(0.65), Inches(cy), Inches(12.03), Inches(card_h), WHITE, BORDER_GRAY, rounded=True
                )
                self._add_rect(slide, Inches(0.65), Inches(cy), Inches(0.08), Inches(card_h), TEAL)

                tb = slide.shapes.add_textbox(
                    Inches(0.92), Inches(cy + 0.06), Inches(11.55), Inches(card_h - 0.12)
                )
                tf = tb.text_frame
                tf.word_wrap = True
                tf.vertical_anchor = MSO_ANCHOR.MIDDLE
                p = tf.paragraphs[0]
                r1 = p.add_run()
                r1.text = f"{b.heading}: "
                r1.font.name = FONT_FAMILY
                r1.font.size = Pt(13.5)
                r1.font.bold = True
                r1.font.color.rgb = TEAL
                r2 = p.add_run()
                r2.text = b.detail
                r2.font.name = FONT_FAMILY
                r2.font.size = Pt(13)
                r2.font.color.rgb = SLATE_TEXT

        self._add_footer(slide, deck_title, slide_num, total)
