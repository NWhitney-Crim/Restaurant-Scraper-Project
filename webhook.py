"""
webhook.py — Minimal FastAPI webhook server for the restaurant scraping agent.

POST /trigger
  Body: { "url": "https://...", "record_id": "recXXXXXXXXXXXXXX" }

  1. Runs ingest_url_and_sync() on the provided URL.
  2. Updates the matching record in the Airtable "Pending URLs" table
     with the result (status, counts, restaurants added).
  3. Returns a JSON summary.

Environment variables required:
  AIRTABLE_API_KEY   — Personal Access Token
  AIRTABLE_BASE_ID   — e.g. app9Cv9zkVWD3lC9E
"""

import os
import logging
from datetime import datetime, timezone

import requests as http_requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Restaurant Agent Webhook", version="1.0.0")

# ---------------------------------------------------------------------------
# Airtable helpers
# ---------------------------------------------------------------------------
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "app9Cv9zkVWD3lC9E")


def _airtable_patch(table_name: str, record_id: str, fields: dict) -> dict:
    """PATCH a single record in an Airtable table."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_name}/{record_id}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = http_requests.patch(url, json={"fields": fields}, headers=headers, timeout=15)
    if not resp.ok:
        logger.warning("Airtable PATCH failed (%s): %s", resp.status_code, resp.text[:300])
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class TriggerRequest(BaseModel):
    url: str
    record_id: str


class TriggerResponse(BaseModel):
    status: str
    url: str
    record_id: str
    extracted: int
    skipped_duplicates: int
    created: int
    errors: int
    message: str
    restaurants_added: list[str]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@app.get("/")
def health():
    return {"status": "ok", "service": "restaurant-agent-webhook"}


@app.post("/trigger", response_model=TriggerResponse)
def trigger(body: TriggerRequest):
    """
    Accept a URL and Airtable record_id.
    Run the ingestion pipeline, then update the Pending URLs record with results.
    """
    logger.info("Received /trigger request — url=%s  record_id=%s", body.url, body.record_id)

    # ------------------------------------------------------------------
    # Step 1 — Run ingestion
    # ------------------------------------------------------------------
    try:
        from url_ingestion import ingest_url_and_sync  # local import to avoid circular deps

        result = ingest_url_and_sync(
            url=body.url,
            api_key=AIRTABLE_API_KEY,
            base_id=AIRTABLE_BASE_ID,
            table_id=os.environ.get("AIRTABLE_TABLE_ID", "tblxgwMGdH1TsozYF"),
        )
    except Exception as exc:
        logger.error("Ingestion failed: %s", exc)
        # Still attempt to update Airtable with the error status
        _safe_update_pending(body.record_id, {
            "Status": "Failed",
            "Result": str(exc),
        })
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}")

    # ------------------------------------------------------------------
    # Step 2 — Build the update payload for the Pending URLs record
    # ------------------------------------------------------------------
    restaurants_added: list[str] = result.get("restaurants_added", [])
    created   = result.get("created", 0)
    skipped   = result.get("skipped_duplicates", 0)
    extracted = result.get("extracted", 0)
    errors    = result.get("errors", 0)

    summary = (
        f"Extracted: {extracted} | New: {created} | Skipped: {skipped} | Errors: {errors}\n"
        f"Added: {', '.join(restaurants_added) if restaurants_added else 'none'}"
    )

    pending_fields = {
        "Status": "Complete",
        "Result": summary,
        "Restaurants Added": ', '.join(restaurants_added) if restaurants_added else 'None',
    }

    # ------------------------------------------------------------------
    # Step 3 — Update the Pending URLs record
    # ------------------------------------------------------------------
    _safe_update_pending(body.record_id, pending_fields)

    logger.info(
        "Trigger complete — extracted=%d  created=%d  skipped=%d  errors=%d",
        extracted, created, skipped, errors,
    )

    return TriggerResponse(
        status="success",
        url=body.url,
        record_id=body.record_id,
        extracted=extracted,
        skipped_duplicates=skipped,
        created=created,
        errors=errors,
        message=result.get("message", ""),
        restaurants_added=restaurants_added,
    )


def _safe_update_pending(record_id: str, fields: dict):
    """Update the Pending URLs record, logging any errors without raising."""
    try:
        _airtable_patch("Pending URLs", record_id, fields)
        logger.info("Updated Pending URLs record %s", record_id)
    except Exception as exc:
        logger.warning("Could not update Pending URLs record %s: %s", record_id, exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    logger.info("Starting webhook server on port %d", port)
    uvicorn.run("webhook:app", host="0.0.0.0", port=port, reload=False)
