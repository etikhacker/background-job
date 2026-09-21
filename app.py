"""Stage 0..2 - hello server + Inngest + POST /reports + background make-report + status."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import inngest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from inngest.fast_api import serve

app = FastAPI(title="report-api", version="0.3.0")
inngest_client = inngest.Inngest(app_id="report-api", is_production=False)

REPORTS: dict[str, dict[str, Any]] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/reports")
async def create_report(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = None

    if not isinstance(body, dict):
        return JSONResponse(
            {"error": "JSON body with a `topic` field is required"},
            status_code=400,
        )

    topic_raw = body.get("topic")
    if not isinstance(topic_raw, str) or not topic_raw.strip():
        return JSONResponse(
            {"error": "`topic` is required and must be a non-empty string"},
            status_code=400,
        )

    topic = topic_raw.strip()
    report_id = uuid.uuid4().hex[:12]

    record: dict[str, Any] = {
        "id": report_id,
        "topic": topic,
        "status": "pending",
        "created_at": _utc_now_iso(),
    }
    REPORTS[report_id] = record

    await inngest_client.send(
        inngest.Event(name="report/requested", data={"id": report_id, "topic": topic})
    )

    return JSONResponse(record, status_code=202)


@app.get("/reports/{report_id}")
async def get_report(report_id: str):
    record = REPORTS.get(report_id)
    if record is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return record


def _build_report_payload(report_id: str, topic: str) -> dict[str, Any]:
    if topic == "fail":
        # Stage 3: trigger retries - Inngest sees this exception and retries
        # because retries=2 is set on the function.
        raise RuntimeError("The report oven is broken!")

    return {
        "id": report_id,
        "topic": topic,
        "status": "done",
        "result": {
            "headline": f"All about {topic}",
            "lines": [
                f"{topic} is genuinely interesting.",
                "Real apps would call an AI or a DB here - we just sleep and pretend.",
                f"Generated at {_utc_now_iso()}",
            ],
            "word_count": 3,
        },
        "finished_at": _utc_now_iso(),
    }


@inngest_client.create_function(
    fn_id="make-report",
    name="Make report (slow work in background)",
    retries=2,
    trigger=inngest.TriggerEvent(event="report/requested"),
)
async def make_report(ctx: inngest.Context) -> dict[str, Any]:
    report_id = ctx.event.data["id"]
    topic = ctx.event.data["topic"]

    await ctx.step.sleep("do-the-slow-work", timedelta(seconds=8))

    def _build() -> dict[str, Any]:
        return _build_report_payload(report_id, topic)

    return await ctx.step.run("build-report", _build)


@inngest_client.create_function(
    fn_id="say-hello",
    name="Say hello (smoke test)",
    trigger=inngest.TriggerEvent(event="test/hello"),
)
async def say_hello(ctx: inngest.Context) -> str:
    await ctx.step.sleep("do-the-slow-work", timedelta(seconds=5))
    return "Hello from the background!"


# --------------------------------------------------------------------------- #
# Stage 4 - cron heartbeat: every minute, log how many of each status we hold
# --------------------------------------------------------------------------- #
@inngest_client.create_function(
    fn_id="heartbeat",
    name="Heartbeat (cron)",
    trigger=inngest.TriggerCron(cron="* * * * *"),
)
async def heartbeat(ctx: inngest.Context) -> dict[str, int]:
    def _summarise() -> dict[str, int]:
        summary = {"pending": 0, "done": 0, "failed": 0}
        for r in REPORTS.values():
            s = r.get("status", "pending")
            if s in summary:
                summary[s] += 1
        line = f"[heartbeat] {_utc_now_iso()} summary={summary}"
        print(line, flush=True)
        return summary

    return await ctx.step.run("summarise", _summarise)


serve(app, inngest_client, [say_hello, make_report, heartbeat])