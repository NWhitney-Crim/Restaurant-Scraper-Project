import os
import logging
import httpx
from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

MANUS_URL = os.environ.get("MANUS_URL", "NOT_SET")


class TriggerRequest(BaseModel):
    url: str
    record_id: str


@app.get("/")
def health():
    return {
        "status": "online",
        "manus_url": MANUS_URL,
        "test_var": os.environ.get("TEST_VAR", "NOT_SET")
    }


@app.post("/trigger")
async def trigger(req: TriggerRequest):
    logger.info("MANUS_URL value: %s", MANUS_URL)
    if not MANUS_URL or MANUS_URL == "NOT_SET":
        return {"status": "error", "message": "MANUS_URL environment variable is not set"}
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{MANUS_URL}/trigger",
                json={"url": req.url, "record_id": req.record_id}
            )
            result = resp.json()
            return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("webhook:app", host="0.0.0.0", port=port, reload=False)
