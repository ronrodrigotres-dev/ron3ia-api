# RON3IA Paywall — Backend (Cloud Run en Windows)

Este backend está diseñado para desplegarse **solo** desde `./backend`.

## Por qué NO usar `--source .`

Desplegar desde la raíz puede hacer que Cloud Run tome un entrypoint incorrecto (`/workspace/main.py`) y mezcle dependencias raíz/backend. Para evitar errores por imports/entrypoints equivocados, el flujo oficial es:

- `gcloud run deploy ... --source .\backend`
- ASGI único: `backend/main.py` con `main:app`

## Dependencias y entrypoint de producción

- `backend/requirements.txt` incluye `gunicorn` + `uvicorn[standard]`.
- `backend/Procfile` usa `gunicorn --worker-class uvicorn.workers.UvicornWorker --bind :${PORT:-8080} main:app`.
- Cloud Run inyecta `PORT`; el bind queda en `8080` por defecto.

## Deploy recomendado (PowerShell)

```powershell
gcloud run deploy ron3ia-api `
  --source .\backend `
  --region southamerica-west1 `
  --allow-unauthenticated `
  --port 8080 `
  --set-build-env-vars=GOOGLE_PYTHON_VERSION=3.12 `
  --set-env-vars=ENABLE_TELEMETRY=false
```

> Tip PowerShell: el backtick (`` ` ``) debe ser el último carácter de cada línea (sin espacios después).

## Deploy equivalente (Windows CMD)

```bat
gcloud run deploy ron3ia-api ^
  --source .\backend ^
  --region southamerica-west1 ^
  --allow-unauthenticated ^
  --port 8080 ^
  --set-build-env-vars GOOGLE_PYTHON_VERSION=3.12 ^
  --set-env-vars ENABLE_TELEMETRY=false
```

## Override de emergencia (PowerShell, sin romper parsing)

Si necesitas forzar comando/args:

```powershell
gcloud run deploy ron3ia-api `
  --source .\backend `
  --region southamerica-west1 `
  --allow-unauthenticated `
  --command=gunicorn `
  --args='["--worker-class=uvicorn.workers.UvicornWorker","--bind=:8080","main:app"]'
```

## Verificación post-deploy

1. Revisar logs:

```powershell
gcloud run services logs read ron3ia-api --region southamerica-west1 --limit 100
```

2. Confirmar OpenAPI:

```powershell
curl https://<SERVICE_URL>/openapi.json
```

Debe incluir rutas:
- `/create-checkout-session`
- `/stripe/webhook`

3. Healthcheck rápido:

```powershell
curl https://<SERVICE_URL>/health
```

## Endpoints esperados

- `POST /create-checkout-session`
- `POST /stripe/webhook`
- `GET /openapi.json`
