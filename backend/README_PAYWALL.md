# RON3IA Paywall — Backend

FastAPI backend for the end-to-end paywall flow:
**Emitir veredicto → pagar → Stripe confirma → webhook → generar PDF → enviar email → marcar paid/sent**

---

## Env vars

| Variable | Required | Description |
|---|---|---|
| `STRIPE_SECRET_KEY` | ✅ | Stripe secret key (`sk_live_…` or `sk_test_…`) |
| `STRIPE_WEBHOOK_SECRET` | ✅ | Webhook signing secret from Stripe Dashboard / CLI |
| `RESEND_API_KEY` | ✅ | API key from [resend.com](https://resend.com) |
| `APP_URL` | ✅ | Base URL of the deployed app (e.g. `https://ronrodrigo3.com`) |
| `FROM_EMAIL` | optional | Sender address (default: `RON3IA <noreply@ronrodrigo3.com>`) |

---

## Run locally

```bash
cd backend
pip install -r requirements.txt

export STRIPE_SECRET_KEY=sk_test_...
export STRIPE_WEBHOOK_SECRET=whsec_...
export RESEND_API_KEY=re_...

uvicorn main:app --reload
```

---

## Listen for Stripe webhooks locally (Stripe CLI)

```bash
stripe listen --forward-to localhost:8000/stripe/webhook
```

Copy the `whsec_…` printed by the CLI and set it as `STRIPE_WEBHOOK_SECRET`.

---

## Trigger a test payment

1. Start the backend and Stripe CLI listener (see above).
2. Run the test script:
   ```bash
   cd backend
   python scripts/test_checkout_local.py
   ```
3. Open the printed Checkout URL in your browser and complete the payment with a [Stripe test card](https://stripe.com/docs/testing#cards) (e.g. `4242 4242 4242 4242`).
4. The CLI will forward the `checkout.session.completed` event to your local webhook.
5. Check `backend/data/reports_status.json` — the record should show `"paid": true, "sent": true`.

---

## Deploy to Cloud Run (Windows PowerShell — recommended)

> ✅ Deploy from `./backend` and avoid `--command/--args` overrides.
> This keeps Buildpacks on `backend/main.py` (`main:app`) and avoids loading root `main.py`.

```powershell
gcloud run deploy ron3ia-api `
  --source .\backend `
  --region southamerica-west1 `
  --allow-unauthenticated `
  --set-build-env-vars=GOOGLE_PYTHON_VERSION=3.12 `
  --set-env-vars=APP_URL=https://ronrodrigo3.com,ENABLE_TELEMETRY=false `
  --set-secrets=STRIPE_SECRET_KEY=STRIPE_SECRET_KEY:latest,STRIPE_WEBHOOK_SECRET=STRIPE_WEBHOOK_SECRET:latest,RESEND_API_KEY=RESEND_API_KEY:latest
```

PowerShell tip: the backtick (`` ` ``) must be the last character on each continued line.

## Deploy to Cloud Run (Windows Command Prompt)

```bat
gcloud run deploy ron3ia-api ^
  --source .\backend ^
  --region southamerica-west1 ^
  --allow-unauthenticated ^
  --set-build-env-vars GOOGLE_PYTHON_VERSION=3.12 ^
  --set-env-vars APP_URL=https://ronrodrigo3.com,ENABLE_TELEMETRY=false ^
  --set-secrets STRIPE_SECRET_KEY=STRIPE_SECRET_KEY:latest,STRIPE_WEBHOOK_SECRET=STRIPE_WEBHOOK_SECRET:latest,RESEND_API_KEY=RESEND_API_KEY:latest
```

Production webhook URL:
```
https://ron3ia-api-819648047297.southamerica-west1.run.app/stripe/webhook
```

Configure this URL in the Stripe Dashboard → Developers → Webhooks → Add endpoint,
listening for the `checkout.session.completed` event.

---


## Verificación post deploy (evitar shim de raíz)

Después de desplegar con `--source ./backend`, revisa logs y confirma:
- no aparece `/workspace/main.py` en el traceback/startup,
- el arranque muestra `file=.../backend/main.py`,
- y Gunicorn/Uvicorn levanta `main:app` desde el source `backend/`.

Ejemplo (PowerShell):
```bat
gcloud run services logs read ron3ia-api --region southamerica-west1 --limit 100
```

Si quieres forzar comando/args (solo emergencia), en PowerShell usa una forma que no empiece con `-k`:
```powershell
gcloud run deploy ron3ia-api `
  --source .\backend `
  --region southamerica-west1 `
  --allow-unauthenticated `
  --command=gunicorn `
  --args="--worker-class=uvicorn.workers.UvicornWorker,--bind=:8080,main:app"
```

## Endpoints

### `POST /create-checkout-session`

```json
{
  "email": "cliente@dominio.com",
  "reportId": "rep_xxx",
  "amount": 9900,
  "currency": "clp"
}
```

Returns:
```json
{ "url": "https://checkout.stripe.com/..." }
```

### `POST /stripe/webhook`

Stripe webhook endpoint. Verifies signature, processes `checkout.session.completed`,
generates the PDF, sends it via email, and persists state to `data/reports_status.json`.
