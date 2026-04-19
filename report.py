import base64
import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# ── Brand colors ──────────────────────────────────────────────────────────────
TEAL = colors.HexColor("#0F766E")
DARK = colors.HexColor("#111827")
MUTED = colors.HexColor("#6B7280")
PASS_GREEN = colors.HexColor("#16A34A")
WARN_AMBER = colors.HexColor("#D97706")
FAIL_RED = colors.HexColor("#DC2626")
LIGHT_BG = colors.HexColor("#F9FAFB")
BORDER = colors.HexColor("#E5E7EB")

STATUS_COLOR = {"pass": PASS_GREEN, "warn": WARN_AMBER, "fail": FAIL_RED}
STATUS_LABEL = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}
STATUS_BG = {
    "pass": colors.HexColor("#DCFCE7"),
    "warn": colors.HexColor("#FEF3C7"),
    "fail": colors.HexColor("#FEE2E2"),
}


def generate_report(results, base_url):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    story = []

    # ── Header ─────────────────────────────────────────────────────────────────
    story.append(Paragraph(
        '<font color="#0F766E"><b>ERPNext Health Checker</b></font>',
        ParagraphStyle("title", fontSize=22, leading=28, alignment=TA_LEFT)
    ))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f'<font color="#6B7280">Instance: {base_url} &nbsp;&nbsp;|&nbsp;&nbsp; '
        f'Generated: {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}</font>',
        ParagraphStyle("sub", fontSize=9, leading=13)
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=6 * mm))

    # ── Score summary ──────────────────────────────────────────────────────────
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    warns = sum(1 for r in results if r["status"] == "warn")
    fails = sum(1 for r in results if r["status"] == "fail")
    score = int((passed / total) * 100) if total else 0

    score_color = PASS_GREEN if score >= 80 else (WARN_AMBER if score >= 50 else FAIL_RED)
    score_label = "Healthy" if score >= 80 else ("Needs Attention" if score >= 50 else "Critical Issues")

    summary_data = [
        [
            _score_cell(str(score) + "%", score_label, score_color),
            _stat_cell(str(passed), "Passed", PASS_GREEN),
            _stat_cell(str(warns), "Warnings", WARN_AMBER),
            _stat_cell(str(fails), "Failed", FAIL_RED),
        ]
    ]
    summary_table = Table(summary_data, colWidths=["40%", "20%", "20%", "20%"])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), LIGHT_BG),
        ("BACKGROUND", (1, 0), (3, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 1, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ROWPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 8 * mm))

    # ── Results by category ────────────────────────────────────────────────────
    categories = {}
    for r in results:
        categories.setdefault(r["category"], []).append(r)

    for category, checks in categories.items():
        story.append(Paragraph(
            f'<b><font color="#111827">{category}</font></b>',
            ParagraphStyle("cat", fontSize=12, leading=16, spaceBefore=4 * mm, spaceAfter=2 * mm)
        ))

        for check in checks:
            status = check["status"]
            bg = STATUS_BG[status]
            fg = STATUS_COLOR[status]
            label = STATUS_LABEL[status]

            row = [[
                Paragraph(
                    f'<font color="{fg.hexval()}"><b>[{label}]</b></font>  '
                    f'<font color="#111827"><b>{check["name"]}</b></font><br/>'
                    f'<font color="#6B7280" size="8">{check["message"]}</font>',
                    ParagraphStyle("check", fontSize=9, leading=13, leftIndent=2 * mm)
                )
            ]]

            t = Table(row, colWidths=["100%"])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("BOX", (0, 0), (-1, -1), 0.5, fg),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(t)

            if check.get("details"):
                details_text = "  •  ".join(check["details"])
                story.append(Paragraph(
                    f'<font color="#6B7280" size="7">↳ {details_text}</font>',
                    ParagraphStyle("details", fontSize=7, leading=10,
                                   leftIndent=4 * mm, spaceAfter=1 * mm)
                ))
            elif check.get("delta") and check["delta"] > 0:
                story.append(Paragraph(
                    f'<font color="{FAIL_RED.hexval()}" size="7">'
                    f'↳ Financial impact: {check["delta"]:,.2f}</font>',
                    ParagraphStyle("delta", fontSize=7, leading=10,
                                   leftIndent=4 * mm, spaceAfter=1 * mm)
                ))
            else:
                story.append(Spacer(1, 1.5 * mm))

    # ── Footer ─────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        '<font color="#6B7280" size="7">Generated by ERPNext Health Checker — '
        'for consulting use. Not a substitute for a full accounting audit.</font>',
        ParagraphStyle("footer", fontSize=7, alignment=TA_CENTER)
    ))

    doc.build(story)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def _score_cell(score, label, color):
    return Paragraph(
        f'<font size="28" color="{color.hexval()}"><b>{score}</b></font><br/>'
        f'<font size="9" color="#6B7280">{label}</font>',
        ParagraphStyle("score", alignment=TA_CENTER, leading=32)
    )


def _stat_cell(value, label, color):
    return Paragraph(
        f'<font size="20" color="{color.hexval()}"><b>{value}</b></font><br/>'
        f'<font size="8" color="#6B7280">{label}</font>',
        ParagraphStyle("stat", alignment=TA_CENTER, leading=24)
    )
