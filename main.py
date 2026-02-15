import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def health():
    return {"status": "RON3IA ONLINE"}

@app.post("/run-production")
async def run_production(data: dict):

    dominio = data.get("dominio")
    modulos = data.get("modulos")

    return {
        "status": "job accepted",
        "dominio": dominio,
        "modulos": modulos
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
