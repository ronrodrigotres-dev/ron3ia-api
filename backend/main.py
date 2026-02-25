import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import stripe
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, field_validator

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="RON3IA Paywall API")

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

SUCCESS_URL = os.environ.get(
    "SUCCESS_URL", "https://ronrodrigo3.com/pago-exitoso?session_id={CHECKOUT_SESSION_ID}"
)
CANCEL_URL = os.environ.get("CANCEL_URL", "https://ronrodrigo3.com/pago-cancelado")

DATA_FILE = Path(__file__).parent / "data" / "reports_status.json"


@app.on_event("startup")
async def log_startup() -> None:
    logger.info("[startup] service=%s file=%s", os.environ.get("K_SERVICE", "local"), __file__)


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
# API models
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    email: EmailStr
    reportId: str
    amount: int
    currency: str

    @field_validator("reportId")
    @classmethod
    def report_id_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reportId must not be empty")
        return value

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("amount must be > 0")
        return value

    @field_validator("currency")
    @classmethod
    def currency_clp(cls, value: str) -> str:
        if value.lower() != "clp":
            raise ValueError("currency must be 'clp'")
        return value.lower()


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "ron3ia-api", "entrypoint": "backend.main:app"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# A) POST /create-checkout-session
# ---------------------------------------------------------------------------

@app.post("/create-checkout-session")
async def create_checkout_session(body: CheckoutRequest) -> dict[str, str]:
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="STRIPE_SECRET_KEY no configurado")

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
        logger.error("Stripe error creating checkout session: %s", exc)
        raise HTTPException(status_code=502, detail="Error creating Stripe session") from exc

    return {"url": session.url}


# ---------------------------------------------------------------------------
# B) POST /stripe/webhook
# ---------------------------------------------------------------------------

@app.post("/stripe/webhook")
@app.post("/stripe-webhook", include_in_schema=False)
async def stripe_webhook(request: Request) -> Response:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as exc:
        logger.error("Webhook parse error: %s", exc)
        raise HTTPException(status_code=400, detail="Webhook error") from exc

    if event.get("type") != "checkout.session.completed":
        return Response(status_code=200)

    session = (event.get("data") or {}).get("object") or {}

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

    status = _read_status()
    record = status.get(report_id, {})
    if record.get("sent"):
        logger.info("Report %s already sent. Skipping (idempotent).", report_id)
        return Response(status_code=200)

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

    from services.pdf_report import generate_pdf
    from services.email_resend import send_report_email

    try:
        pdf_bytes = generate_pdf(report_id)
    except Exception as exc:
        logger.error("PDF generation failed for %s: %s", report_id, exc)
        return Response(status_code=200)

    try:
        send_report_email(email=email, report_id=report_id, pdf_bytes=pdf_bytes)
    except Exception as exc:
        logger.error("Email send failed for %s: %s", report_id, exc)
        return Response(status_code=200)

    status = _read_status()
    record = status.get(report_id, {})
    record.update({"sent": True, "sent_at": datetime.now(timezone.utc).isoformat()})
    status[report_id] = record
    _write_status(status)

    logger.info("Report %s processed and sent to %s.", report_id, email)
    return Response(status_code=200)
