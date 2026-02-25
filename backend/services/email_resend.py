"""Email delivery via Resend API using the requests library."""
import base64
import logging
import os

import requests

logger = logging.getLogger("uvicorn.error")

RESEND_API_URL = "https://api.resend.com/emails"
FROM_EMAIL = os.environ.get("FROM_EMAIL", "RON3IA <noreply@ronrodrigo3.com>")


def send_report_email(email: str, report_id: str, pdf_bytes: bytes) -> None:
    """Send the report PDF to *email* using the Resend API.

    Raises an exception if the request fails so the caller can decide how to handle it.
    """
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not set")

    subject = f"Tu Reporte RON3IA (PDF) — {report_id}"
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    text_body = (
        f"Hola,\n\n"
        f"Adjunto encontrarás tu Reporte Oficial RON3IA (ID: {report_id}).\n\n"
        f"Gracias por confiar en RON3IA.\n"
    )
    html_body = f"""
<html>
  <body style="font-family: Arial, sans-serif; color: #333;">
    <h2 style="color: #1a1a2e;">RON3IA — Reporte Oficial</h2>
    <p>Hola,</p>
    <p>Adjunto encontrarás tu <strong>Reporte Oficial RON3IA</strong> (ID: <code>{report_id}</code>).</p>
    <p>Gracias por confiar en <strong>RON3IA</strong>.</p>
    <hr style="border: none; border-top: 1px solid #eee;" />
    <p style="font-size: 12px; color: #888;">Este mensaje fue generado automáticamente.</p>
  </body>
</html>
""".strip()

    payload = {
        "from": FROM_EMAIL,
        "to": [email],
        "subject": subject,
        "text": text_body,
        "html": html_body,
        "attachments": [
            {
                "filename": f"reporte-ron3ia-{report_id}.pdf",
                "content": pdf_b64,
            }
        ],
    }

    response = requests.post(
        RESEND_API_URL,
        json=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            f"Resend API error {response.status_code}: {response.text}"
        )

    logger.info("Email sent to %s for report %s", email, report_id)
