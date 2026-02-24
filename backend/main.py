import os
import time
import uuid
from typing import Any, Optional

import httpx
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

# Checkout #1 (Veredicto): prices por módulo
STRIPE_PRICE_INTELLIGENCE = os.getenv("STRIPE_PRICE_INTELLIGENCE", "").strip()
STRIPE_PRICE_CONVERSION = os.getenv("STRIPE_PRICE_CONVERSION", "").strip()
STRIPE_PRICE_SEO = os.getenv("STRIPE_PRICE_SEO", "").strip()
STRIPE_PRICE_GROWTH = os.getenv("STRIPE_PRICE_GROWTH", "").strip()
STRIPE_PRICE_COMMERCE = os.getenv("STRIPE_PRICE_COMMERCE", "").strip()
STRIPE_PRICE_EXPANSION = os.getenv("STRIPE_PRICE_EXPANSION", "").strip()
STRIPE_PRICE_GEO = os.getenv("STRIPE_PRICE_GEO", "").strip()

# Checkout #2 (Repair)
STRIPE_PRICE_REPAIR = os.getenv("STRIPE_PRICE_REPAIR", "").strip()

# Redirects
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "").strip()
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "").strip()

# Email (SendGrid)
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip()

PUBLIC_REPAIR_URL_BASE = os.getenv("PUBLIC_REPAIR_URL_BASE", "https://ronrodrigo3.com/repair").strip()

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
# Persistencia (Firestore / fallback memory)
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


def _get_firestore_store() -> Optional[ReportStore]:
    try:
        from google.cloud import firestore  # type: ignore

        class FirestoreReportStore(ReportStore):
            def __init__(self) -> None:
                self._client = firestore.Client()
                self._col = self._client.collection("ron3ia_reports")

            def create_report(self, report: dict[str, Any]) -> str:
                report_id = report["report_id"]
                self._col.document(report_id).set(report)
                return report_id

            def get_report(self, report_id: str) -> Optional[dict[str, Any]]:
                doc = self._col.document(report_id).get()
                return doc.to_dict() if doc.exists else None

            def update_report(self, report_id: str, updates: dict[str, Any]) -> None:
                self._col.document(report_id).set(updates, merge=True)

        return FirestoreReportStore()
    except Exception as e:
        print(f"Firestore disabled (startup error): {e}")
        return None


STORE: ReportStore = _get_firestore_store() or MemoryReportStore()

# -----------------------------
# Modelos
# -----------------------------

MODULE_CATALOG: dict[str, dict[str, Any]] = {
    "Intelligence": {"price_id": STRIPE_PRICE_INTELLIGENCE, "amount_usd": 29},
    "Conversion": {"price_id": STRIPE_PRICE_CONVERSION, "amount_usd": 29},
    "SEO": {"price_id": STRIPE_PRICE_SEO, "amount_usd": 29},
    "Growth": {"price_id": STRIPE_PRICE_GROWTH, "amount_usd": 29},
    "Commerce": {"price_id": STRIPE_PRICE_COMMERCE, "amount_usd": 29},
    "Expansion": {"price_id": STRIPE_PRICE_EXPANSION, "amount_usd": 29},
    "GEO": {"price_id": STRIPE_PRICE_GEO, "amount_usd": 29},
}


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
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CreateCheckoutSessionResponse(BaseModel):
    ok: bool
    url: str

class CreateRepairCheckoutSessionRequest(BaseModel):
    report_id: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class ReportResponse(BaseModel):
    ok: bool
    report: dict[str, Any]


async def _send_email_sendgrid(to_email: str, subject: str, text: str, html: str) -> None:
    if not SENDGRID_API_KEY or not EMAIL_FROM:
        raise RuntimeError("Email no configurado (SENDGRID_API_KEY/EMAIL_FROM).")

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": EMAIL_FROM},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": text},
            {"type": "text/html", "value": html},
        ],
    }

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {SENDGRID_API_KEY}"},
            json=payload,
        )
        if r.status_code >= 300:
            raise RuntimeError(f"SendGrid error {r.status_code}: {r.text}")


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

    if event_type == "checkout.session.completed":
        metadata = data_object.get("metadata") or {}
        report_id = (metadata.get("report_id") or "").strip()
        flow = (metadata.get("flow") or "").strip()

        if report_id:
            if flow == "verdict":
                STORE.update_report(
                    report_id,
                    {
                        "paid": True,
                        "paid_at": int(time.time()),
                        "stripe_session_id": data_object.get("id"),
                    },
                )
                report = STORE.get_report(report_id) or {}
                repair_url = f"{PUBLIC_REPAIR_URL_BASE}?report_id={report_id}"

                # Generar informe completo (placeholder)
                full_report = {
                    "veredicto": "Informe premium generado.",
                    "acciones_sugeridas": report.get("suggested_actions", []),
                    "repair_url": repair_url,
                }
                STORE.update_report(report_id, {"full_report": full_report})

                # Email con link a repair
                try:
                    to_email = report.get("email") or ""
                    if to_email:
                        subject = "Tu Veredicto RON3IA (Premium) + Reparación Automática"
                        text = (
                            "Tu veredicto premium ya está listo.\n\n"
                            f"REPARAR AUTOMÁTICAMENTE CON RON3IA:\n{repair_url}\n"
                        )
                        html = (
                            "<p>Tu veredicto premium ya está listo.</p>"
                            f"<p><a href=\"{repair_url}\">REPARAR AUTOMÁTICAMENTE CON RON3IA</a></p>"
                        )
                        await _send_email_sendgrid(to_email, subject, text, html)
                except Exception as e:
                    print(f"Email send failed: {e}")

            elif flow == "repair":
                STORE.update_report(
                    report_id,
                    {
                        "repair_active": True,
                        "repair_paid_at": int(time.time()),
                        "repair_stripe_session_id": data_object.get("id"),
                    },
                )
                print(f"Repair activated for report_id={report_id}")

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
    selected = [m for m in body.selectedModules if m in MODULE_CATALOG]

    if not dominio or not nombre or not email:
        raise HTTPException(status_code=422, detail="Faltan campos: dominio, nombre, email.")
    if not selected:
        raise HTTPException(status_code=422, detail="Debes seleccionar al menos 1 módulo.")

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

    total_usd = sum(int(MODULE_CATALOG[m]["amount_usd"]) for m in selected)

    report = {
        "report_id": report_id,
        "dominio": dominio,
        "nombre": nombre,
        "email": email,
        "modules": selected,
        "problemas_detectados": problemas,
        "suggested_actions": suggested_actions,
        "paid": False,
        "repair_active": False,
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
            "total_usd": total_usd,
        },
    )


@app.post("/create-checkout-session", response_model=CreateCheckoutSessionResponse)
async def create_checkout_session(
    request: Request,
    body: CreateCheckoutSessionRequest,
) -> CreateCheckoutSessionResponse:
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="STRIPE_API_KEY no configurado.")
    report = STORE.get_report(body.report_id)
    if not report:
        raise HTTPException(status_code=404, detail="report_id no encontrado.")
    modules = report.get("modules") or []
    if not modules:
        raise HTTPException(status_code=422, detail="El reporte no tiene módulos.")

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

    line_items = []
    missing_prices = []
    for m in modules:
        price_id = (MODULE_CATALOG.get(m) or {}).get("price_id") or ""
        if not price_id:
            missing_prices.append(m)
            continue
        line_items.append({"price": price_id, "quantity": 1})
    if missing_prices:
        raise HTTPException(
            status_code=503,
            detail=f"Faltan price IDs Stripe para módulos: {', '.join(missing_prices)}",
        )

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=line_items,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"report_id": body.report_id, "flow": "verdict"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}") from e

    if not session.url:
        raise HTTPException(status_code=502, detail="Stripe no devolvió session.url.")

    return CreateCheckoutSessionResponse(ok=True, url=session.url)


@app.post("/create-repair-checkout-session", response_model=CreateCheckoutSessionResponse)
async def create_repair_checkout_session(
    request: Request,
    body: CreateRepairCheckoutSessionRequest,
) -> CreateCheckoutSessionResponse:
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="STRIPE_API_KEY no configurado.")
    if not STRIPE_PRICE_REPAIR:
        raise HTTPException(status_code=503, detail="STRIPE_PRICE_REPAIR no configurado.")
    report = STORE.get_report(body.report_id)
    if not report:
        raise HTTPException(status_code=404, detail="report_id no encontrado.")

    origin = request.headers.get("origin") or ""
    fallback_success = f"{origin}/repair?report_id={body.report_id}&checkout=success" if origin else ""
    fallback_cancel = f"{origin}/repair?report_id={body.report_id}&checkout=cancel" if origin else ""
    success_url = (body.success_url or STRIPE_SUCCESS_URL or fallback_success).strip()
    cancel_url = (body.cancel_url or STRIPE_CANCEL_URL or fallback_cancel).strip()
    if not success_url or not cancel_url:
        raise HTTPException(status_code=503, detail="Faltan success_url/cancel_url para repair.")

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": STRIPE_PRICE_REPAIR, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"report_id": body.report_id, "flow": "repair"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}") from e

    if not session.url:
        raise HTTPException(status_code=502, detail="Stripe no devolvió session.url.")

    return CreateCheckoutSessionResponse(ok=True, url=session.url)


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
        "repair_active": bool(report.get("repair_active")),
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
