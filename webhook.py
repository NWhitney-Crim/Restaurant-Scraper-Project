import os
import logging
import httpx
import asyncio
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Restaurant Agent Webhook", version="3.0.0")

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


async def forward_to_manus(url: str, record_id: str):
    """Forward request to Manus in the background."""
    logger.info("Background task — forwarding to Manus: %s", url)
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(
                f"{MANUS_URL}/trigger",
                json={"url": url, "record_id": record_id}
            )
            result = resp.json()
            logger.info("Manus completed successfully: %s", result)
    except Exception as e:
        logger.error("Failed to reach Manus: %s", e)


@app.post("/trigger")
async def trigger(req: TriggerRequest, background_tasks: BackgroundTasks):
    logger.info("Received trigger — url=%s record_id=%s", req.url, req.record_id)
    if not MANUS_URL:
        return {"status": "error", "message": "MANUS_URL environment variable is not set"}
    
    background_tasks.add_task(forward_to_manus, req.url, req.record_id)
    
    return {
        "status": "accepted",
        "message": "Request received and forwarding to Manus agent",
        "url": req.url,
        "record_id": req.record_id
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("webhook:app", host="0.0.0.0", port=port, reload=False)
