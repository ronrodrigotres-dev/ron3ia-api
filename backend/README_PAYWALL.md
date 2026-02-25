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

## Deploy to Cloud Run (Windows — command prompt)

```bat
gcloud run deploy ron3ia-api ^
  --source .\backend ^
  --region southamerica-west1 ^
  --allow-unauthenticated ^
  --set-env-vars APP_URL=https://ronrodrigo3.com ^
  --set-secrets STRIPE_SECRET_KEY=STRIPE_SECRET_KEY:latest,STRIPE_WEBHOOK_SECRET=STRIPE_WEBHOOK_SECRET:latest,RESEND_API_KEY=RESEND_API_KEY:latest
```

Production webhook URL:
```
https://ron3ia-api-819648047297.southamerica-west1.run.app/stripe/webhook
```

Configure this URL in the Stripe Dashboard → Developers → Webhooks → Add endpoint,
listening for the `checkout.session.completed` event.

---

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
