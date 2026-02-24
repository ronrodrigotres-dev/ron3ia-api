import os
from typing import Any, Optional

import stripe
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic import BaseModel

# -----------------------------
# Configuración
# -----------------------------

SERVICE_NAME = os.getenv("K_SERVICE", "fastapi-service")

STRIPE_API_KEY = os.getenv("STRIPE_API_KEY", "").strip()
endpoint_secret = os.getenv("STRIPE_ENDPOINT_SECRET", "").strip()
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "").strip()
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "").strip()
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "").strip()

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]


def _setup_tracing() -> None:
    try:
        resource = Resource.create({"service.name": SERVICE_NAME})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
        trace.set_tracer_provider(provider)
    except Exception as e:
        print(f"Tracing disabled (startup error): {e}")


_setup_tracing()

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

FastAPIInstrumentor.instrument_app(app)

# -----------------------------
# Config Stripe
# -----------------------------

if STRIPE_API_KEY:
    stripe.api_key = STRIPE_API_KEY

# -----------------------------
# Modelos
# -----------------------------


class AnalyzeRequest(BaseModel):
    text: Optional[str] = None
    url: Optional[str] = None


class AnalyzeResponse(BaseModel):
    ok: bool
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
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CreateCheckoutSessionResponse(BaseModel):
    ok: bool
    url: str


# -----------------------------
# Webhook Stripe
# -----------------------------


@app.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(default=None, alias="stripe-signature"),
) -> dict[str, Any]:
    if not endpoint_secret:
        raise HTTPException(
            status_code=503,
            detail="Stripe endpoint secret no configurado (STRIPE_ENDPOINT_SECRET).",
        )

    payload = await request.body()
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Falta header Stripe-Signature.")

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, endpoint_secret)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Payload inválido: {e}") from e
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=f"Firma inválida: {e}") from e

    event_type = event.get("type", "unknown")
    data_object = (event.get("data") or {}).get("object") or {}

    return {"received": True, "type": event_type, "object": data_object}


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

    # Diagnóstico gratuito (básico) — deja tensión para el premium.
    errors: list[str] = []
    if body.url and not (body.url.startswith("http://") or body.url.startswith("https://")):
        errors.append("La URL debe comenzar con http:// o https://")
    if len(subject) < 8:
        errors.append("El input es demasiado corto para un diagnóstico fiable.")

    summary = "Análisis básico listo. El veredicto premium desbloquea el plan de acción completo."
    return AnalyzeResponse(
        ok=True,
        result={
            "summary": summary,
            "errors_detected": errors,
            "preview": {"length": len(subject)},
        },
    )


@app.post("/create-checkout-session", response_model=CreateCheckoutSessionResponse)
async def create_checkout_session(
    request: Request,
    body: CreateCheckoutSessionRequest,
) -> CreateCheckoutSessionResponse:
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="STRIPE_API_KEY no configurado.")
    if not STRIPE_PRICE_ID:
        raise HTTPException(status_code=503, detail="STRIPE_PRICE_ID no configurado.")

    origin = request.headers.get("origin") or ""
    fallback_success = f"{origin}/?checkout=success" if origin else ""
    fallback_cancel = f"{origin}/?checkout=cancel" if origin else ""

    success_url = (body.success_url or STRIPE_SUCCESS_URL or fallback_success).strip()
    cancel_url = (body.cancel_url or STRIPE_CANCEL_URL or fallback_cancel).strip()
    if not success_url or not cancel_url:
        raise HTTPException(
            status_code=503,
            detail="Faltan STRIPE_SUCCESS_URL/STRIPE_CANCEL_URL (o header Origin para fallback).",
        )

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}") from e

    if not session.url:
        raise HTTPException(status_code=502, detail="Stripe no devolvió session.url.")

    return CreateCheckoutSessionResponse(ok=True, url=session.url)


@app.post("/run-production", response_model=RunProductionResponse)
async def run_production(body: RunProductionRequest) -> RunProductionResponse:
    return RunProductionResponse(
        ok=True,
        job=body.job,
        status="queued",
        details={"params": body.params},
    )
