import os
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI()

STATUS_ONLINE = "RON3IA ONLINE"


class RunProductionRequest(BaseModel):
    dominio: str | None = Field(default=None, description="Domínio alvo")
    modulos: list[str] | None = Field(default=None, description="Módulos a executar")


class RunProductionResponse(BaseModel):
    status: str
    dominio: str | None = None
    modulos: list[str] | None = None


@app.get("/")
def health():
    return {"status": STATUS_ONLINE}

@app.post("/run-production", status_code=202, response_model=RunProductionResponse)
async def run_production(data: RunProductionRequest) -> RunProductionResponse:
    return RunProductionResponse(
        status="job accepted",
        dominio=data.dominio,
        modulos=data.modulos,
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
from backend.main import app

