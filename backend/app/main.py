from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import errors
from app.api.routes import router
from app.api.schemas import ErrorCode
from app.db import check_database
from app.settings import get_settings

app = FastAPI(title="ICD API", version="0.2.0")
errors.install(app)
app.include_router(router)

# Multipart framing around the file; a request bigger than the limit plus this is refused
# before its body is read.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


@app.middleware("http")
async def refuse_oversized_uploads(request: Request, call_next):
    length = request.headers.get("content-length")
    if request.method == "POST" and request.url.path == "/uploads" and length and length.isdigit():
        limit = get_settings().max_upload_bytes
        if int(length) > limit + MULTIPART_OVERHEAD_BYTES:
            return errors.error_response(
                413,
                ErrorCode.FILE_TOO_LARGE,
                f"The file is larger than the {limit // (1024 * 1024)} MB limit.",
            )
    return await call_next(request)


@app.get("/health")
def health() -> JSONResponse:
    if check_database():
        return JSONResponse({"status": "ok", "database": "ok"})
    return JSONResponse({"status": "degraded", "database": "unavailable"}, status_code=503)
