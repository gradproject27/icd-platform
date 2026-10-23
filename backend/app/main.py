from fastapi import FastAPI

app = FastAPI(title="ICD API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    # T1-04 extends this with a database connectivity check.
    return {"status": "ok"}
