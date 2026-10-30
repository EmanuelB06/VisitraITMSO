from __future__ import annotations

import io
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .base import BaseExporter

HEADERS = ("Name", "ID", "Type", "Purpose", "Time In", "Time Out")
COLUMN_WIDTHS = (84, 56, 44, 154, 76, 76)


class PdfExporter(BaseExporter):
    key = "pdf"
    label = "PDF"
    extension = "pdf"
    content_type = "application/pdf"

    def build(self, visits, generated_at) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title="VisitraITMSO Visit Report",
            author="VisitraITMSO",
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "VisitraTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0A0F1E"),
            alignment=0,
            spaceAfter=2,
        )
        meta_style = ParagraphStyle(
            "VisitraMeta",
            parent=styles["Normal"],
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#4A5680"),
        )
        cell_style = ParagraphStyle(
            "VisitraCell",
            parent=styles["Normal"],
            fontSize=7.6,
            leading=9.5,
            textColor=colors.HexColor("#111827"),
        )
        head_cell_style = ParagraphStyle(
            "VisitraHeadCell",
            parent=cell_style,
            fontName="Helvetica-Bold",
            textColor=colors.white,
        )

        story = [
            Paragraph("VisitraITMSO — Visit Report", title_style),
            Paragraph(
                f"Generated {generated_at:%b %d, %Y %I:%M %p} · {len(visits)} record(s)",
                meta_style,
            ),
            Spacer(1, 8),
        ]

        if visits:
            data = [[Paragraph(header, head_cell_style) for header in HEADERS]]
            for visit in visits:
                data.append(
                    [
                        Paragraph(escape(visit.visitor.name), cell_style),
                        Paragraph(escape(visit.visitor.identifier or "—"), cell_style),
                        Paragraph(escape(visit.visitor.type_label), cell_style),
                        Paragraph(escape(visit.display_purpose), cell_style),
                        Paragraph(
                            timezone.localtime(visit.time_in).strftime("%b %d, %I:%M %p"),
                            cell_style,
                        ),
                        Paragraph(
                            timezone.localtime(visit.time_out).strftime("%b %d, %I:%M %p")
                            if visit.time_out
                            else "—",
                            cell_style,
                        ),
                    ]
                )

            table = Table(data, colWidths=COLUMN_WIDTHS, repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5C7CFA")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7DEF5")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6FC")]),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(table)
        else:
            story.append(Paragraph("No records match the selected filters.", meta_style))

        def footer(canvas, document):
            canvas.saveState()
            canvas.setFont("Helvetica", 7.5)
            canvas.setFillColor(colors.HexColor("#6B7FC4"))
            canvas.drawString(18 * mm, 10 * mm, "VisitraITMSO · St. Bridget College Batangas")
            canvas.drawRightString(
                A4[0] - 18 * mm,
                10 * mm,
                f"Page {document.page}",
            )
            canvas.restoreState()

        doc.build(story, onFirstPage=footer, onLaterPages=footer)
        return buffer.getvalue()
