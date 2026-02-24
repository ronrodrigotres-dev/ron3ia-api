# RON3IA — Paywall en producción

## Estructura

```
ron3ia-api/
 ├── backend/
 │    ├── main.py
 │    ├── requirements.txt
 │    ├── Dockerfile
 ├── frontend/
```

## Backend (Cloud Run)

### Endpoints

- `POST /analyze`
- `POST /create-checkout-session`
- `POST /stripe-webhook`
- `POST /run-production`
- `GET /health`

### Variables de entorno (NO hardcode)

- `STRIPE_SECRET_KEY`: clave secreta de Stripe
- `STRIPE_PRICE_ID`: Price ID del producto premium
- `STRIPE_WEBHOOK_SECRET`: secret del webhook de Stripe
- `FRONTEND_URL`: URL pública del frontend (ej. `https://ronrodrigo3.com`)
- `ALLOWED_ORIGINS` (opcional): lista separada por comas para CORS. Si no se define, se usa `FRONTEND_URL` (si existe) + localhost.

### Deploy (OBLIGATORIO desde `./backend`)

Desde la raíz del repo:

```bash
gcloud run deploy ron3ia-api \
  --source ./backend \
  --region southamerica-west1 \
  --allow-unauthenticated \
  --clear-base-image
```

### Validación rápida (endpoint existe: no 404)

Si falta configuración de Stripe, es **normal** recibir `400/503` (lo importante es que no sea `404`):

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -X POST "https://ron3ia-api-819648047297.southamerica-west1.run.app/create-checkout-session" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","report_id":"test"}'
```

## Frontend

### Config

- `VITE_RON3IA_API_URL`: base URL del backend (Cloud Run)

Ejemplo en `frontend/.env.example`.
