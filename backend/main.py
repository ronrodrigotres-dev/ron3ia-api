import os
import time
import uuid
from typing import Any, Optional

import stripe
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# -----------------------------
# Configuración
# -----------------------------

SERVICE_NAME = os.getenv("K_SERVICE", "ron3ia-api")

# Stripe (NO hardcode)
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()

# Frontend URL base (used for success/cancel redirects)
FRONTEND_URL = os.getenv("FRONTEND_URL", "").strip().rstrip("/")

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

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
# Persistencia (placeholder)
# -----------------------------

class ReportStore:
    def create_report(self, report: dict[str, Any]) -> str:  # pragma: no cover
        raise NotImplementedError

    def get_report(self, report_id: str) -> Optional[dict[str, Any]]:  # pragma: no cover
        raise NotImplementedError

    def update_report(self, report_id: str, updates: dict[str, Any]) -> None:  # pragma: no cover
        raise NotImplementedError


class MemoryReportStore(ReportStore):
    def __init__(self) -> None:
        self._db: dict[str, dict[str, Any]] = {}

    def create_report(self, report: dict[str, Any]) -> str:
        report_id = report["report_id"]
        self._db[report_id] = report
        return report_id

    def get_report(self, report_id: str) -> Optional[dict[str, Any]]:
        return self._db.get(report_id)

    def update_report(self, report_id: str, updates: dict[str, Any]) -> None:
        if report_id not in self._db:
            return
        self._db[report_id].update(updates)


STORE: ReportStore = MemoryReportStore()

# -----------------------------
# Modelos
# -----------------------------

class AnalyzeRequest(BaseModel):
    dominio: str
    nombre: str
    email: str
    selectedModules: list[str] = []


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
    report_id: str
    email: str


class CreateCheckoutSessionResponse(BaseModel):
    checkout_url: str


class ReportResponse(BaseModel):
    ok: bool
    report: dict[str, Any]

# -----------------------------
# Webhook Stripe
# -----------------------------


@app.post("/stripe-webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(default=None, alias="stripe-signature"),
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
        raise HTTPException(status_code=400, detail=f"Payload inválido: {e}") from e
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail=f"Firma inválida: {e}") from e

    event_type = event.get("type", "unknown")
    data_object = (event.get("data") or {}).get("object") or {}

    if event_type == "checkout.session.completed":
        metadata = data_object.get("metadata") or {}
        report_id = (metadata.get("report_id") or "").strip()
        user_email = (metadata.get("user_email") or "").strip()

        if report_id:
            # Placeholder update (sin DB aún)
            STORE.update_report(
                report_id,
                {
                    "paid": True,
                    "paid_at": int(time.time()),
                    "stripe_session_id": data_object.get("id"),
                    "user_email": user_email,
                },
            )

    return {"received": True, "type": event_type}


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
    dominio = body.dominio.strip()
    nombre = body.nombre.strip()
    email = body.email.strip()
    selected = body.selectedModules

    if not dominio or not nombre or not email:
        raise HTTPException(status_code=422, detail="Faltan campos: dominio, nombre, email.")

    report_id = uuid.uuid4().hex

    # Análisis base (placeholder realista)
    problemas = []
    for m in selected:
        problemas.append(f"[{m}] Señal de mejora detectada en {dominio}.")

    suggested_actions = [
        "Optimizar velocidad percibida (LCP/CLS).",
        "Corregir jerarquía H1/H2 y metadata.",
        "Revisar CTA y fricción del formulario.",
    ]

    report = {
        "report_id": report_id,
        "dominio": dominio,
        "nombre": nombre,
        "email": email,
        "modules": selected,
        "problemas_detectados": problemas,
        "suggested_actions": suggested_actions,
        "paid": False,
        "created_at": int(time.time()),
    }
    STORE.create_report(report)

    return AnalyzeResponse(
        ok=True,
        result={
            "report_id": report_id,
            "resumen_tecnico": "Diagnóstico base completado. El informe premium desbloquea el veredicto completo.",
            "problemas_detectados": problemas,
            "modulos_bloqueados": selected,
            "total_usd": None,
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

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=f"{FRONTEND_URL}/?checkout=success&report_id={body.report_id}",
            cancel_url=f"{FRONTEND_URL}/?checkout=cancel&report_id={body.report_id}",
            customer_email=body.email,
            metadata={"report_id": body.report_id, "user_email": body.email},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}") from e

    if not session.url:
        raise HTTPException(status_code=502, detail="Stripe no devolvió session.url.")

    return CreateCheckoutSessionResponse(checkout_url=session.url)


@app.get("/report/{report_id}", response_model=ReportResponse)
async def get_report(report_id: str) -> ReportResponse:
    report = STORE.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Reporte no encontrado.")
    # No exponer datos sensibles innecesarios
    public_report = {
        "report_id": report.get("report_id"),
        "dominio": report.get("dominio"),
        "modules": report.get("modules", []),
        "problemas_detectados": report.get("problemas_detectados", []),
        "suggested_actions": report.get("suggested_actions", []),
        "paid": bool(report.get("paid")),
        "full_report": report.get("full_report") if report.get("paid") else None,
    }
    return ReportResponse(ok=True, report=public_report)


@app.post("/run-production", response_model=RunProductionResponse)
async def run_production(body: RunProductionRequest) -> RunProductionResponse:
    return RunProductionResponse(
        ok=True,
        job=body.job,
        status="queued",
        details={"params": body.params},
    )
