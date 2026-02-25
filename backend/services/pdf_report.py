"""PDF report generation using ReportLab."""
from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def generate_pdf(report_id: str) -> bytes:
    """Return a PDF as bytes for the given report_id."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=20,
        spaceAfter=12,
        alignment=1,  # centre
    )
    body_style = styles["BodyText"]
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Italic"],
        fontSize=10,
        alignment=1,
        spaceBefore=30,
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    story = [
        Paragraph("RON3IA — REPORTE OFICIAL", title_style),
        Spacer(1, 0.5 * cm),
        Paragraph(f"<b>Report ID:</b> {report_id}", body_style),
        Paragraph(f"<b>Fecha/Hora:</b> {now}", body_style),
        Spacer(1, 0.8 * cm),
        Paragraph("• Análisis de presencia digital — placeholder", body_style),
        Paragraph("• Evaluación de reputación online — placeholder", body_style),
        Paragraph("• Recomendaciones personalizadas — placeholder", body_style),
        Spacer(1, 1 * cm),
        Paragraph("Gracias por confiar en RON3IA", footer_style),
    ]

    doc.build(story)
    return buffer.getvalue()
