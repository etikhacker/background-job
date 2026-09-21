"""
AI-generated version of the report API.
Prompt: see ./prompt.md
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import inngest
from fastapi import FastAPI, HTTPException, status
from inngest.fast_api import serve
from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
class ReportStore:
    """Thread-safe in-memory store of report records."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def save(self, record: dict[str, Any]) -> None:
        async with self._lock:
            self._records[record["id"]] = record

    async def get(self, report_id: str) -> dict[str, Any] | None:
        async with self._lock:
            return self._records.get(report_id)

    async def list(self) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._records.values())

    async def summary(self) -> dict[str, int]:
        async with self._lock:
            counts = {"pending": 0, "done": 0, "failed": 0}
            for r in self._records.values():
                s = r.get("status", "pending")
                if s in counts:
                    counts[s] += 1
            return counts


STORE = ReportStore()


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class CreateReportRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200, description="Topic of the report")


class ReportResponse(BaseModel):
    id: str
    topic: str
    status: str
    created_at: str
    result: dict[str, Any] | None = None
    finished_at: str | None = None


# --------------------------------------------------------------------------- #
# Inngest
# --------------------------------------------------------------------------- #
inngest_client = inngest.Inngest(app_id="report-api")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@inngest_client.create_function(
    fn_id="make-report",
    name="Make report (slow work in background)",
    retries=2,
    trigger=inngest.TriggerEvent(event="report/requested"),
)
async def make_report(ctx: inngest.Context) -> dict[str, Any]:
    report_id: str = ctx.event.data["id"]
    topic: str = ctx.event.data["topic"]

    # Step 1: stand-in for the slow work.
    await ctx.step.sleep("do-the-slow-work", timedelta(seconds=8))

    # Step 2: build it.
    def _build() -> dict[str, Any]:
        if topic == "fail":
            raise RuntimeError("Build failed!")

        return {
            "id": report_id,
            "topic": topic,
            "status": "done",
            "result": {
                "headline": f"Report on {topic}",
                "lines": [f"{topic} line 1", f"{topic} line 2"],
                "word_count": 4,
            },
            "finished_at": _utc_now(),
        }

    payload = await ctx.step.run("build-report", _build)
    record = await STORE.get(report_id)
    if record is not None:
        record.update(payload)
        await STORE.save(record)
    return payload


@inngest_client.create_function(
    fn_id="heartbeat",
    name="Heartbeat (cron)",
    trigger=inngest.TriggerCron(cron="* * * * *"),
)
async def heartbeat(ctx: inngest.Context) -> dict[str, int]:
    def _summarise() -> dict[str, int]:
        return {"pending": 0, "done": 0, "failed": 0}  # AI stub

    summary = await ctx.step.run("summarise", _summarise)
    print(f"[heartbeat] {_utc_now()} summary={summary}", flush=True)
    return summary


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
app = FastAPI(title="report-api (ai-version)", version="0.1.0")


@app.post("/reports", status_code=status.HTTP_202_ACCEPTED, response_model=ReportResponse)
async def create_report(body: CreateReportRequest) -> ReportResponse:
    record = {
        "id": uuid.uuid4().hex[:12],
        "topic": body.topic,
        "status": "pending",
        "created_at": _utc_now(),
    }
    await STORE.save(record)
    await inngest_client.send(
        inngest.Event(name="report/requested", data={"id": record["id"], "topic": record["topic"]})
    )
    return ReportResponse(**record)


@app.get("/reports/{report_id}", response_model=ReportResponse)
async def get_report(report_id: str) -> ReportResponse:
    record = await STORE.get(report_id)
    if record is None:
        raise HTTPException(status_code=404, detail="not found")
    return ReportResponse(**record)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


serve(app, inngest_client, [make_report, heartbeat])