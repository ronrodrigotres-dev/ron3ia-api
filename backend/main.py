import json
import logging
import os
import tempfile
from pathlib import Path

import stripe
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, validator

from services.email_resend import send_report_email
from services.pdf_report import generate_pdf

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="RON3IA Paywall API")

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

SUCCESS_URL = "https://ronrodrigo3.com/pago-exitoso?session_id={CHECKOUT_SESSION_ID}"
CANCEL_URL = "https://ronrodrigo3.com/pago-cancelado"

DATA_FILE = Path(__file__).parent / "data" / "reports_status.json"


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _read_status() -> dict:
    if not DATA_FILE.exists():
        return {}
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_status(data: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=DATA_FILE.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, DATA_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# A) POST /create-checkout-session
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    email: EmailStr
    reportId: str
    amount: int
    currency: str

    @validator("reportId")
    def report_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("reportId must not be empty")
        return v

    @validator("amount")
    def amount_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("amount must be > 0")
        return v

    @validator("currency")
    def currency_clp(cls, v: str) -> str:
        if v.lower() != "clp":
            raise ValueError("currency must be 'clp'")
        return v.lower()


@app.post("/create-checkout-session")
async def create_checkout_session(body: CheckoutRequest):
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            customer_email=body.email,
            line_items=[
                {
                    "price_data": {
                        "currency": body.currency,
                        "unit_amount": body.amount,
                        "product_data": {"name": f"Reporte RON3IA — {body.reportId}"},
                    },
                    "quantity": 1,
                }
            ],
            metadata={"reportId": body.reportId},
            success_url=SUCCESS_URL,
            cancel_url=CANCEL_URL,
        )
    except stripe.error.StripeError as exc:
        logger.error("Stripe error: %s", exc.user_message)
        raise HTTPException(status_code=502, detail="Error creating Stripe session")
    return {"url": session.url}


# ---------------------------------------------------------------------------
# B) POST /stripe/webhook
# ---------------------------------------------------------------------------

@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as exc:
        logger.error("Webhook parse error: %s", exc)
        raise HTTPException(status_code=400, detail="Webhook error")

    if event["type"] != "checkout.session.completed":
        return Response(status_code=200)

    session = event["data"]["object"]

    if session.get("payment_status") != "paid":
        logger.info("Session %s not paid yet, skipping.", session.get("id"))
        return Response(status_code=200)

    report_id: str = (session.get("metadata") or {}).get("reportId", "")
    email: str = (
        (session.get("customer_details") or {}).get("email")
        or session.get("customer_email")
        or ""
    )
    session_id: str = session.get("id", "")
    event_id: str = event.get("id", "")

    if not report_id or not email:
        logger.error("Missing reportId or email in session %s", session_id)
        return Response(status_code=200)

    # --- Idempotency check ---
    status = _read_status()
    record = status.get(report_id, {})

    if record.get("sent"):
        logger.info("Report %s already sent. Skipping (idempotent).", report_id)
        return Response(status_code=200)

    # --- Mark paid ---
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    record.update(
        {
            "paid": True,
            "sent": False,
            "email": email,
            "stripe_session_id": session_id,
            "last_event_id": event_id,
            "updated_at": now,
        }
    )
    status[report_id] = record
    _write_status(status)

    # --- Generate PDF ---
    try:
        pdf_bytes = generate_pdf(report_id)
    except Exception as exc:
        logger.error("PDF generation failed for %s: %s", report_id, exc)
        return Response(status_code=200)

    # --- Send email ---
    try:
        send_report_email(email=email, report_id=report_id, pdf_bytes=pdf_bytes)
    except Exception as exc:
        logger.error("Email send failed for %s: %s", report_id, exc)
        return Response(status_code=200)

    # --- Mark sent ---
    status = _read_status()
    record = status.get(report_id, {})
    record.update({"sent": True, "sent_at": datetime.now(timezone.utc).isoformat()})
    status[report_id] = record
    _write_status(status)

    logger.info("Report %s processed and sent to %s.", report_id, email)
    return Response(status_code=200)
