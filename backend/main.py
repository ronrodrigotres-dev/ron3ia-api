import os
import uuid
from typing import Any, Optional

import stripe
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

# -----------------------------
# Configuracion
# -----------------------------

SERVICE_NAME = os.getenv("K_SERVICE", "ron3ia-api")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "").strip()
FRONTEND_URL = os.getenv("FRONTEND_URL", "").strip().rstrip("/")

# Backwards-compatible fallback (optional): allow older var name if set
if not STRIPE_SECRET_KEY:
    STRIPE_SECRET_KEY = os.getenv("STRIPE_API_KEY", "").strip()

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]
if FRONTEND_URL and FRONTEND_URL not in ALLOWED_ORIGINS:
    ALLOWED_ORIGINS.append(FRONTEND_URL)


# -----------------------------
# app = FastAPI()
# -----------------------------

app = FastAPI(title=SERVICE_NAME)

# -----------------------------
# Middlewares
# -----------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Config Stripe
# -----------------------------

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# -----------------------------
# Modelos
# -----------------------------


class AnalyzeRequest(BaseModel):
    text: Optional[str] = None
    url: Optional[str] = None


class AnalyzeResponse(BaseModel):
    ok: bool
    report_id: str
    result: dict[str, Any]


class RunProductionRequest(BaseModel):
    job: str
    params: dict[str, Any] = {}


class RunProductionResponse(BaseModel):
    ok: bool
    job: str
    status: str
    details: dict[str, Any] = {}

class CreateCheckoutSessionRequest(BaseModel):
    email: EmailStr
    report_id: str


class CreateCheckoutSessionResponse(BaseModel):
    checkout_url: str


# Placeholder: reemplazar por DB
REPORT_STATUS: dict[str, dict[str, Any]] = {}


# -----------------------------
# Webhook Stripe
# -----------------------------


@app.post("/stripe-webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, Any]:
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=503,
            detail="Stripe webhook secret no configurado (STRIPE_WEBHOOK_SECRET).",
        )

    payload = await request.body()
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Falta header Stripe-Signature.")

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Payload invalido: {e}") from e
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=f"Firma invalida: {e}") from e

    if event.get("type") == "checkout.session.completed":
        session = (event.get("data") or {}).get("object") or {}
        metadata = session.get("metadata") or {}
        report_id = (metadata.get("report_id") or "").strip()
        user_email = (metadata.get("user_email") or "").strip()
        if report_id:
            REPORT_STATUS[report_id] = {
                "status": "paid",
                "user_email": user_email,
                "stripe_session_id": session.get("id"),
            }

    return {"received": True}


# -----------------------------
# Endpoints principales
# -----------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": SERVICE_NAME}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(body: AnalyzeRequest) -> AnalyzeResponse:
    subject = (body.text or body.url or "").strip()
    if not subject:
        raise HTTPException(status_code=422, detail="Debes enviar 'url' o 'text'.")

    report_id = str(uuid.uuid4())

    # Diagnostico gratuito (basico) - deja tension para el premium.
    errors: list[str] = []
    if body.url and not (body.url.startswith("http://") or body.url.startswith("https://")):
        errors.append("La URL debe comenzar con http:// o https://")
    if len(subject) < 8:
        errors.append("El input es demasiado corto para un diagnostico fiable.")

    summary = "Analisis basico listo. El veredicto premium desbloquea el plan de accion completo."
    REPORT_STATUS[report_id] = {"status": "free_preview_ready"}
    return AnalyzeResponse(
        ok=True,
        report_id=report_id,
        result={
            "summary": summary,
            "errors_detected": errors,
            "preview": {"length": len(subject)},
            "report_id": report_id,
        },
    )


@app.post("/create-checkout-session", response_model=CreateCheckoutSessionResponse)
async def create_checkout_session(
    body: CreateCheckoutSessionRequest,
) -> CreateCheckoutSessionResponse:
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="STRIPE_SECRET_KEY no configurado.")
    if not STRIPE_PRICE_ID:
        raise HTTPException(status_code=503, detail="STRIPE_PRICE_ID no configurado.")
    if not FRONTEND_URL:
        raise HTTPException(status_code=503, detail="FRONTEND_URL no configurado.")

    success_url = f"{FRONTEND_URL}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{FRONTEND_URL}/?checkout=cancel"

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=str(body.email),
            metadata={"report_id": body.report_id, "user_email": str(body.email)},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}") from e

    if not session.url:
        raise HTTPException(status_code=502, detail="Stripe no devolvio session.url.")

    REPORT_STATUS[body.report_id] = {"status": "checkout_created", "session_id": session.id}
    return CreateCheckoutSessionResponse(checkout_url=session.url)


@app.post("/run-production", response_model=RunProductionResponse)
async def run_production(body: RunProductionRequest) -> RunProductionResponse:
    return RunProductionResponse(
        ok=True,
        job=body.job,
        status="queued",
        details={"params": body.params},
    )
