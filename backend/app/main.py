from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.db import check_database

app = FastAPI(title="ICD API", version="0.1.0")


@app.get("/health")
def health() -> JSONResponse:
    if check_database():
        return JSONResponse({"status": "ok", "database": "ok"})
    return JSONResponse({"status": "degraded", "database": "unavailable"}, status_code=503)
