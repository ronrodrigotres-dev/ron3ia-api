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
    text: str


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
    return AnalyzeResponse(ok=True, result={"length": len(body.text)})


@app.post("/run-production", response_model=RunProductionResponse)
async def run_production(body: RunProductionRequest) -> RunProductionResponse:
    return RunProductionResponse(
        ok=True,
        job=body.job,
        status="queued",
        details={"params": body.params},
    )
