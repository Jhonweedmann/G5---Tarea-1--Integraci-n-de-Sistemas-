import markdown
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
import re

# Register fonts
fonts_dir = "C:/Windows/Fonts"
pdfmetrics.registerFont(TTFont("ARIAL", os.path.join(fonts_dir, "arial.ttf")))
pdfmetrics.registerFont(TTFont("ARIAL-BOLD", os.path.join(fonts_dir, "arialbd.ttf")))
cour_path = None
for f in os.listdir(fonts_dir):
    if f.lower().startswith("cour") and "bd" not in f.lower() and "i" not in f.lower():
        cour_path = os.path.join(fonts_dir, f)
        break
if cour_path:
    pdfmetrics.registerFont(TTFont("COURIER", cour_path))

# Styles
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="BodyES", parent=styles["BodyText"], fontName="ARIAL", fontSize=11, leading=16, alignment=TA_JUSTIFY))
styles.add(ParagraphStyle(name="CodeES", parent=styles["BodyText"], fontName="COURIER", fontSize=8.5, leading=11))
styles.add(ParagraphStyle(name="BulletES", parent=styles["Bullet"], fontName="ARIAL", fontSize=11, leading=16, alignment=TA_JUSTIFY))
styles.add(ParagraphStyle(name="TitleES", parent=styles["Title"], fontName="ARIAL-BOLD", fontSize=20, leading=28, textColor=colors.HexColor("#1a3a6b")))
styles.add(ParagraphStyle(name="Heading1ES", parent=styles["Heading1"], fontName="ARIAL-BOLD", fontSize=15, leading=20, textColor=colors.HexColor("#1a3a6b"), spaceAfter=8))
styles.add(ParagraphStyle(name="Heading2ES", parent=styles["Heading2"], fontName="ARIAL-BOLD", fontSize=13, leading=18, textColor=colors.HexColor("#1a3a6b"), spaceAfter=6))
styles.add(ParagraphStyle(name="TableCell", parent=styles["BodyText"], fontName="ARIAL", fontSize=9, leading=12))
styles.add(ParagraphStyle(name="TableCellBold", parent=styles["TableCell"], fontName="ARIAL-BOLD"))
styles.add(ParagraphStyle(name="TableHeader", parent=styles["TableCell"], fontName="ARIAL-BOLD", textColor=colors.white))

# Helper to clean markdown text
def clean_text(text):
    return text.strip()

def parse_inline(text):
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`(.+?)`', r'<font name="COURIER" size="9">\1</font>', text)
    return text

def md_to_flowables(md_text):
    flowables = []
    lines = md_text.split("\n")
    i = 0
    in_pre = False
    pre_lines = []
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            if in_pre:
                code_content = "\n".join(pre_lines)
                flowables.append(Paragraph(f'<font name="COURIER" size="8.5">{code_content}</font>', styles["CodeES"]))
                flowables.append(Spacer(1, 10))
                in_pre = False
                pre_lines = []
            else:
                in_pre = True
                pre_lines = []
            i += 1
            continue
        if in_pre:
            pre_lines.append(line)
            i += 1
            continue
        if line.strip().startswith("# ") and not line.strip().startswith("## #"):
            if not flowables:
                flowables.append(Spacer(1, 4 * cm))
            flowables.append(Paragraph(line.strip()[2:], styles["TitleES"]))
            flowables.append(Spacer(1, 18))
            i += 1
            continue
        if line.strip().startswith("## "):
            flowables.append(Paragraph(line.strip()[3:], styles["Heading1ES"]))
            flowables.append(Spacer(1, 12))
            i += 1
            continue
        if line.strip().startswith("### "):
            flowables.append(Paragraph(line.strip()[4:], styles["Heading2ES"]))
            flowables.append(Spacer(1, 8))
            i += 1
            continue
        if line.strip().startswith("- **") or line.strip().startswith("- "):
            content = line.strip()[2:]
            flowables.append(Paragraph(f'<font name="ARIAL-BOLD" size="11">&bull;</font> {parse_inline(content)}', styles["BulletES"]))
            i += 1
            continue
        if line.strip().startswith("1.") or line.strip().startswith("2.") or line.strip().startswith("3.") or line.strip().startswith("4.") or line.strip().startswith("5."):
            num = re.match(r'^(\d+)\.', line.strip()).group(1)
            content = re.sub(r'^\d+\.\s*', '', line.strip())
            flowables.append(Paragraph(f'<b>{num}.</b> {parse_inline(content)}', styles["BulletES"]))
            i += 1
            continue
        if line.strip().startswith("|") and "|" in line.strip()[1:]:
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            if len(table_lines) > 1:
                header_cells = [c.strip() for c in table_lines[0].split("|")[1:-1]]
                data = []
                for tl in table_lines[1:]:
                    cells = [c.strip() for c in tl.split("|")[1:-1]]
                    data.append(cells)
                if header_cells and not all(set(c.strip()) == set(["---"]) for c in header_cells):
                    table_data = [[Paragraph(f'<b>{c}</b>', styles["TableHeader"]) for c in header_cells]]
                    for row in data:
                        if row and not all(set(c.strip()) == set(["---"]) for c in row):
                            table_data.append([Paragraph(c, styles["TableCell"]) for c in row])
                    if len(table_data) > 1:
                        col_widths = [cm * 4] * len(header_cells)
                        t = Table(table_data, colWidths=col_widths)
                        t.setStyle(TableStyle([
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999")),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a6b")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]))
                        flowables.append(t)
                        flowables.append(Spacer(1, 12))
            continue
        if line.strip() == "---":
            flowables.append(Spacer(1, 8))
            flowables.append(Paragraph("<hr/>", styles["BodyES"]))
            flowables.append(Spacer(1, 8))
            i += 1
            continue
        if line.strip():
            flowables.append(Paragraph(parse_inline(line.strip()), styles["BodyES"]))
            i += 1
            continue
        i += 1
    return flowables

def build_pdf():
    md_path = os.path.join(os.getcwd(), "docs", "Documento-Forma-A.md")
    pdf_path = os.path.join(os.getcwd(), "docs", "Documento-Forma-A.pdf")

    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    story = []
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph("Forma A", styles["TitleES"]))
    story.append(Paragraph("Sistema de Gesti&#243;n de Cursos y Matr&#237;culas", ParagraphStyle("Subtitle", parent=styles["TitleES"], fontSize=14, textColor=colors.HexColor("#333"))))
    story.append(Spacer(1, 2 * cm))
    story.append(Paragraph("Informe de Integraci&#243;n de Sistemas", ParagraphStyle("Subtitle2", parent=styles["BodyES"], fontSize=14)))
    story.append(Spacer(1, 2 * cm))
    story.append(Paragraph("<b>Dominio:</b> Forma A", styles["BodyES"]))
    story.append(Paragraph("<b>Grupo:</b> Forma A", styles["BodyES"]))
    story.append(Paragraph("<b>Integrantes:</b> [Integrante 1], [Integrante 2], [Integrante 3]", styles["BodyES"]))
    story.append(Paragraph("<b>Asignatura:</b> Integraci&#243;n de Sistemas", styles["BodyES"]))
    story.append(Paragraph("<b>Fecha:</b> Septiembre 2026", styles["BodyES"]))
    story.append(Paragraph("<b>Universidad de Concepci&#243;n &#8212; Facultad de Ingenier&#237;a</b>", styles["BodyES"]))
    story.append(PageBreak())

    sections = md_content.split("---")
    first_section = True
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if section.startswith("# ") or section.startswith("## ") or section.startswith("### "):
            if first_section:
                first_section = False
            flowables.extend(md_to_flowables(section))
        elif section.startswith("## Anexo") or section.startswith("Anexo"):
            flowables.append(PageBreak())
            flowables.extend(md_to_flowables(section))
        else:
            flowables.extend(md_to_flowables(section))

    doc = SimpleDocTemplate(pdf_path, pagesize=A4, leftMargin=2.2*cm, rightMargin=2.2*cm, topMargin=2*cm, bottomMargin=2*cm)
    doc.build(story)
    print("PDF generated:", pdf_path)
    print("Size:", os.path.getsize(pdf_path), "bytes")

    from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    print("Pages:", len(reader.pages))

if __name__ == "__main__":
    build_pdf()
