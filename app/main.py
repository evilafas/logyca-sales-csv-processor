from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="LOGYCA Sales Processor",
    description="Sistema de procesamiento asíncrono de archivos CSV de ventas",
    version="1.0.0",
)

app.include_router(router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
