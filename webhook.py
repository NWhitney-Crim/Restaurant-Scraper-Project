import os
import logging
import httpx
from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Restaurant Agent Webhook", version="2.0.0")

MANUS_URL = os.environ.get("MANUS_URL", "")


class TriggerRequest(BaseModel):
    url: str
    record_id: str


@app.get("/")
def health():
    return {
        "status": "online",
        "service": "Restaurant Webhook",
        "manus_configured": bool(MANUS_URL)
    }


@app.post("/trigger")
async def trigger(req: TriggerRequest):
    logger.info("Forwarding to Manus — url=%s record_id=%s", req.url, req.record_id)
    if not MANUS_URL:
        return {"status": "error", "message": "MANUS_URL environment variable is not set"}
    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{MANUS_URL}/trigger",
                json={"url": req.url, "record_id": req.record_id}
            )
            result = resp.json()
            logger.info("Manus response: %s", result)
            return result
    except Exception as e:
        logger.error("Failed to reach Manus: %s", e)
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("webhook:app", host="0.0.0.0", port=port, reload=False)
