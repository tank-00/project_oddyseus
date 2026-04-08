from fastapi import FastAPI

app = FastAPI(title="Shield Registry", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "registry"}
