import os
import json
import time
import uuid
from typing import Any, Optional

import stripe
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# -----------------------------
# Configuración
# -----------------------------

SERVICE_NAME = os.getenv("K_SERVICE", "ron3ia-api")
IS_CLOUD_RUN = bool(os.getenv("K_SERVICE") or os.getenv("K_REVISION") or os.getenv("PORT"))

# Stripe (NO hardcode)
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_REPAIR_PRICE_ID = os.getenv("STRIPE_REPAIR_PRICE_ID", "").strip()

# Frontend URL base (used for success/cancel redirects)
FRONTEND_URL = os.getenv("FRONTEND_URL", "").strip().rstrip("/")

# BigQuery
BQ_DATASET = os.getenv("BQ_DATASET", "ron3ia_db").strip()
BQ_TABLE = os.getenv("BQ_TABLE", "reports").strip()
BQ_TABLE_FQN = os.getenv("BQ_TABLE_FQN", "").strip()

# SendGrid
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip()

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

# -----------------------------
# app = FastAPI()
# -----------------------------

app = FastAPI(title=SERVICE_NAME)

# Evidencia clara en logs de qué app levantó Cloud Run
@app.on_event("startup")
async def _log_startup() -> None:
    has_checkout = any(getattr(r, "path", "") == "/create-checkout-session" for r in app.routes)
    print(f"[startup] service={SERVICE_NAME} file={__file__} has_/create-checkout-session={has_checkout}")

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
# Persistencia (BigQuery / fallback local)
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

class BigQueryReportStore(ReportStore):
    def __init__(self, table_fqn: str) -> None:
        from google.cloud import bigquery  # type: ignore

        self._client = bigquery.Client()
        project = os.getenv("BQ_PROJECT", "").strip() or self._client.project
        table_fqn = table_fqn or f"{project}.{BQ_DATASET}.{BQ_TABLE}"
        self._table_fqn = table_fqn

        # Fail fast in Cloud Run if the table is not reachable.
        try:
            self._client.get_table(self._table_fqn)
        except Exception as e:
            raise RuntimeError(
                f"BigQuery table not reachable: {self._table_fqn}. Error: {e}"
            ) from e

    def create_report(self, report: dict[str, Any]) -> str:
        report_id = report["report_id"]

        # Store as row + JSON blobs (simple, schema-stable)
        row = {
            "report_id": report_id,
            "domain": report.get("dominio"),
            "user_name": report.get("nombre"),
            "user_email": report.get("email"),
            "selected_modules": json.dumps(report.get("modules") or []),
            "status": report.get("status", "locked"),
            "created_at": int(time.time()),
            "paid_at": None,
            "stripe_session_id": None,
            "report_basic": json.dumps(report.get("report_basic") or {}),
            "report_full": None,
            "repair_status": report.get("repair_status", "locked"),
            "repair_paid_at": None,
            "repair_stripe_session_id": None,
        }

        errors = self._client.insert_rows_json(self._table_fqn, [row])
        if errors:
            raise RuntimeError(f"BigQuery insert failed: {errors}")
        return report_id

    def get_report(self, report_id: str) -> Optional[dict[str, Any]]:
        from google.cloud import bigquery  # type: ignore

        q = f"SELECT * FROM `{self._table_fqn}` WHERE report_id = @report_id LIMIT 1"
        job = self._client.query(
            q,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("report_id", "STRING", report_id)
                ]
            ),
        )
        rows = list(job.result())
        if not rows:
            return None
        row = dict(rows[0].items())
        return row

    def update_report(self, report_id: str, updates: dict[str, Any]) -> None:
        from google.cloud import bigquery  # type: ignore

        if not updates:
            return

        set_exprs: list[str] = []
        params: list[Any] = [bigquery.ScalarQueryParameter("report_id", "STRING", report_id)]

        for k, v in updates.items():
            param_name = f"p_{k}"
            if v is None:
                set_exprs.append(f"{k} = NULL")
                continue

            if isinstance(v, (dict, list)):
                v = json.dumps(v)
            if isinstance(v, bool):
                params.append(bigquery.ScalarQueryParameter(param_name, "BOOL", v))
            elif isinstance(v, int):
                params.append(bigquery.ScalarQueryParameter(param_name, "INT64", v))
            else:
                params.append(bigquery.ScalarQueryParameter(param_name, "STRING", str(v)))
            set_exprs.append(f"{k} = @{param_name}")

        q = f"UPDATE `{self._table_fqn}` SET {', '.join(set_exprs)} WHERE report_id = @report_id"
        self._client.query(q, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()


def _init_store() -> ReportStore:
    try:
        store = BigQueryReportStore(BQ_TABLE_FQN)
        return store
    except Exception as e:
        if IS_CLOUD_RUN:
            raise
        print(f"BigQuery disabled (local fallback): {e}")
        return MemoryReportStore()


STORE: ReportStore = _init_store()

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
    dominio: str
    nombre: str
    email: str
    selectedModules: list[str] = []


class RunProductionResponse(BaseModel):
    ok: bool
    report_id: str
    status: str

class CreateCheckoutSessionRequest(BaseModel):
    report_id: str
    email: str


class CreateCheckoutSessionResponse(BaseModel):
    checkout_url: str

class CreateRepairCheckoutSessionRequest(BaseModel):
    report_id: str
    email: Optional[str] = None


class ReportStatusResponse(BaseModel):
    ok: bool
    report_id: str
    status: str
    basic: Optional[dict[str, Any]] = None
    full: Optional[dict[str, Any]] = None


class ReportResponse(BaseModel):
    ok: bool
    report: dict[str, Any]


def _send_email_sendgrid(to_email: str, subject: str, text: str, html: str) -> None:
    if not SENDGRID_API_KEY or not EMAIL_FROM:
        raise RuntimeError("SendGrid no configurado (SENDGRID_API_KEY/EMAIL_FROM).")
    from sendgrid import SendGridAPIClient  # type: ignore
    from sendgrid.helpers.mail import Mail  # type: ignore

    message = Mail(
        from_email=EMAIL_FROM,
        to_emails=to_email,
        subject=subject,
        plain_text_content=text,
        html_content=html,
    )
    SendGridAPIClient(SENDGRID_API_KEY).send(message)

# -----------------------------
# Webhook Stripe
# -----------------------------


@app.post("/stripe-webhook")
async def stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
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
        payment_type = (metadata.get("type") or "verdict").strip()

        if report_id:
            if payment_type == "repair":
                STORE.update_report(
                    report_id,
                    {
                        "repair_status": "active",
                        "repair_paid_at": int(time.time()),
                        "repair_stripe_session_id": data_object.get("id"),
                    },
                )
            else:
                full_report = {
                    "title": "RON3IA — Veredicto Premium",
                    "report_id": report_id,
                    "generated_at": int(time.time()),
                    "verdict": "Desbloqueado: informe premium generado.",
                }
                STORE.update_report(
                    report_id,
                    {
                        "status": "unlocked",
                        "paid_at": int(time.time()),
                        "stripe_session_id": data_object.get("id"),
                        "report_full": full_report,
                    },
                )

                # Envío de email NO bloqueante
                if user_email:
                    report_url = f"{FRONTEND_URL}/report/{report_id}"
                    repair_url = f"{FRONTEND_URL}/repair?report_id={report_id}"
                    subject = "RON3IA — Tu Veredicto Premium + Reparación Automática"
                    text = f"Tu veredicto premium está listo: {report_url}\n\nReparar automáticamente: {repair_url}\n"
                    html = (
                        f"<p>Tu veredicto premium está listo:</p><p><a href=\"{report_url}\">{report_url}</a></p>"
                        f"<p><strong>REPARAR AUTOMÁTICAMENTE CON RON3IA</strong></p><p><a href=\"{repair_url}\">{repair_url}</a></p>"
                    )
                    try:
                        if background_tasks is not None:
                            background_tasks.add_task(_send_email_sendgrid, user_email, subject, text, html)
                        else:
                            _send_email_sendgrid(user_email, subject, text, html)
                    except Exception as e:
                        print(f"Email send failed (non-blocking): {e}")

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

    report_basic = {
        "resumen_tecnico": "Diagnóstico base completado. El veredicto premium desbloquea el informe completo.",
        "problemas_detectados": problemas,
        "modulos_bloqueados": selected,
    }

    report = {
        "report_id": report_id,
        "dominio": dominio,
        "nombre": nombre,
        "email": email,
        "modules": selected,
        "status": "locked",
        "report_basic": report_basic,
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

    report = STORE.get_report(body.report_id)
    if not report:
        raise HTTPException(status_code=404, detail="report_id no encontrado.")
    status = (report.get("status") or "locked").strip()
    if status != "locked":
        raise HTTPException(status_code=409, detail=f"Estado inválido para checkout: {status}")

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url=f"{FRONTEND_URL}/report/{body.report_id}?checkout=success",
            cancel_url=f"{FRONTEND_URL}/report/{body.report_id}?checkout=cancel",
            customer_email=body.email,
            metadata={"report_id": body.report_id, "user_email": body.email, "type": "verdict"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}") from e

    if not session.url:
        raise HTTPException(status_code=502, detail="Stripe no devolvió session.url.")

    return CreateCheckoutSessionResponse(checkout_url=session.url)


@app.post("/create-repair-checkout-session", response_model=CreateCheckoutSessionResponse)
async def create_repair_checkout_session(
    body: CreateRepairCheckoutSessionRequest,
) -> CreateCheckoutSessionResponse:
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="STRIPE_SECRET_KEY no configurado.")
    if not STRIPE_REPAIR_PRICE_ID:
        raise HTTPException(status_code=503, detail="STRIPE_REPAIR_PRICE_ID no configurado.")
    if not FRONTEND_URL:
        raise HTTPException(status_code=503, detail="FRONTEND_URL no configurado.")

    report = STORE.get_report(body.report_id)
    if not report:
        raise HTTPException(status_code=404, detail="report_id no encontrado.")
    status = (report.get("status") or "").strip()
    if status != "unlocked":
        raise HTTPException(status_code=409, detail=f"Reporte no desbloqueado: {status}")

    email = (body.email or report.get("user_email") or report.get("user_email") or "").strip()
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": STRIPE_REPAIR_PRICE_ID, "quantity": 1}],
            success_url=f"{FRONTEND_URL}/repair?report_id={body.report_id}&checkout=success",
            cancel_url=f"{FRONTEND_URL}/repair?report_id={body.report_id}&checkout=cancel",
            customer_email=email or None,
            metadata={"report_id": body.report_id, "user_email": email, "type": "repair"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}") from e

    if not session.url:
        raise HTTPException(status_code=502, detail="Stripe no devolvió session.url.")

    return CreateCheckoutSessionResponse(checkout_url=session.url)


@app.get("/report-status/{report_id}", response_model=ReportStatusResponse)
async def report_status(report_id: str) -> ReportStatusResponse:
    report = STORE.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Reporte no encontrado.")
    status = (report.get("status") or "locked").strip()

    basic_raw = report.get("report_basic")
    full_raw = report.get("report_full")

    def _maybe_json(v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, (dict, list)):
            return v
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return {"raw": v}
        return {"raw": str(v)}

    return ReportStatusResponse(
        ok=True,
        report_id=report_id,
        status=status,
        basic=_maybe_json(basic_raw),
        full=_maybe_json(full_raw) if status == "unlocked" else None,
    )

@app.get("/report/{report_id}", response_model=ReportResponse)
async def get_report(report_id: str) -> ReportResponse:
    report = STORE.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Reporte no encontrado.")
    # No exponer datos sensibles innecesarios
    modules_raw = report.get("selected_modules") or report.get("modules") or "[]"
    try:
        modules = json.loads(modules_raw) if isinstance(modules_raw, str) else list(modules_raw)
    except Exception:
        modules = []

    public_report = {
        "report_id": report.get("report_id"),
        "dominio": report.get("domain") or report.get("dominio"),
        "modules": modules,
        "problemas_detectados": [],
        "suggested_actions": [],
        "paid": (report.get("status") == "unlocked"),
        "full_report": report.get("report_full") if report.get("status") == "unlocked" else None,
    }
    return ReportResponse(ok=True, report=public_report)


@app.post("/run-production", response_model=RunProductionResponse)
async def run_production(body: RunProductionRequest) -> RunProductionResponse:
    # En producción, este endpoint crea un reporte "locked" listo para monetizar.
    dominio = body.dominio.strip()
    nombre = body.nombre.strip()
    email = body.email.strip()
    selected = body.selectedModules
    if not dominio or not nombre or not email:
        raise HTTPException(status_code=422, detail="Faltan campos: dominio, nombre, email.")

    report_id = uuid.uuid4().hex
    report_basic = {"resumen_tecnico": "Run production creado (locked).", "selectedModules": selected}
    STORE.create_report(
        {
            "report_id": report_id,
            "dominio": dominio,
            "nombre": nombre,
            "email": email,
            "modules": selected,
            "status": "locked",
            "report_basic": report_basic,
            "created_at": int(time.time()),
        }
    )
    return RunProductionResponse(ok=True, report_id=report_id, status="locked")
