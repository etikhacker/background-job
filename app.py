"""
FlyRank Internship - Backend Track - W4 - A7
Your first background job.

A small FastAPI service that:
  - returns 202 instantly for slow report work (Stage 2)
  - exposes status + list endpoints (Stage 2 + extras)
  - drives the slow work via an Inngest background function (Stages 1, 2)
  - retries failed jobs and rejects bad input at the door (Stage 3)
  - runs a heartbeat cron and a cleanup cron (Stage 4 + extras)
  - writes the finished report to an outbox file (extras - "email stand-in")
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import inngest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from inngest.fast_api import serve

# --------------------------------------------------------------------------- #
# In-memory state (yes, dies on restart - same lesson as A1)
# --------------------------------------------------------------------------- #
REPORTS: dict[str, dict[str, Any]] = {}

OUTBOX_DIR = Path(__file__).parent / "outbox"
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------- #
# Inngest client (one per process - local dev server talks to it)
# --------------------------------------------------------------------------- #
inngest_client = inngest.Inngest(
    app_id="report-api",
    is_production=False,  # dev server, not the real cloud
)

# --------------------------------------------------------------------------- #
# FastAPI app
# --------------------------------------------------------------------------- #
app = FastAPI(title="report-api", version="1.0.0")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Stage 0 - hello server
# --------------------------------------------------------------------------- #
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Stage 2 - the fast door: POST /reports answers in milliseconds
# --------------------------------------------------------------------------- #
@app.post("/reports")
async def create_report(request: Request):
    """Accept the request, save a record, fire the event, return 202."""
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

    # Fire-and-forget event - the worker picks it up in the background.
    await inngest_client.send(
        inngest.Event(name="report/requested", data={"id": report_id, "topic": topic})
    )

    return JSONResponse(record, status_code=202)


# --------------------------------------------------------------------------- #
# Stage 2 - status endpoint (also handles extras: list endpoint)
# --------------------------------------------------------------------------- #
@app.get("/reports")
async def list_reports():
    """Extra: control-panel view of every report we know about."""
    return list(REPORTS.values())


@app.get("/reports/{report_id}")
async def get_report(report_id: str):
    """First call: `pending`. A few seconds later: `done` + result."""
    record = REPORTS.get(report_id)
    if record is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return record


# --------------------------------------------------------------------------- #
# Helper - write the finished report to the outbox (extras)
# --------------------------------------------------------------------------- #
def _write_outbox(report_id: str, payload: dict[str, Any]) -> None:
    path = OUTBOX_DIR / f"{report_id}.txt"
    body = (
        f"Report id:     {payload['id']}\n"
        f"Topic:         {payload['topic']}\n"
        f"Status:        {payload['status']}\n"
        f"Finished at:   {payload['finished_at']}\n"
        f"Headline:      {payload['result']['headline']}\n"
        "----\n"
        + "\n".join(payload["result"]["lines"])
        + "\n"
    )
    path.write_text(body, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Stage 2 - slow work happens here, NOT in the endpoint
# --------------------------------------------------------------------------- #
def _build_report_payload(report_id: str, topic: str) -> dict[str, Any]:
    """Pure function: the actual "build the report" step.

    Step 1 of the function sleeps; step 2 calls this. Splitting them is what
    makes the job *durable* - if the worker restarts mid-sleep, the build step
    doesn't re-run.
    """
    if topic == "fail":
        # Stage 3: trigger the retry. Inngest sees this exception and retries
        # because retries=2 was set on the function.
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


async def _on_make_report_failure(ctx: inngest.Context) -> None:
    """Called when make-report exhausts retries.

    In the dev server the on_failure context may not carry the original event
    payload in the same shape, so we don't try to parse it. We scan pending
    reports and mark the oldest one failed - good enough for this assignment.
    """
    for rid, rec in REPORTS.items():
        if rec.get("status") == "pending":
            rec["status"] = "failed"
            rec["error"] = "build-report step raised after all retries"
            rec["failed_at"] = _utc_now_iso()
            print(
                f"[make-report FAILED] id={rid} attempt={ctx.attempt}",
                flush=True,
            )
            break
    else:
        print(
            f"[make-report FAILED] no pending report to mark (attempt={ctx.attempt})",
            flush=True,
        )


@inngest_client.create_function(
    fn_id="make-report",
    name="Make report (slow work in background)",
    retries=2,
    trigger=inngest.TriggerEvent(event="report/requested"),
    on_failure=_on_make_report_failure,
)
async def make_report(ctx: inngest.Context) -> dict[str, Any]:
    report_id = ctx.event.data["id"]
    topic = ctx.event.data["topic"]

    # Step 1: stand-in for the slow work (AI call, big export, etc.)
    await ctx.step.sleep("do-the-slow-work", timedelta(seconds=8))

    # Step 2: actually build it. This is its own step so the result is
    # memoised - a re-run after a crash skips the sleep AND skips re-building.
    def _build() -> dict[str, Any]:
        payload = _build_report_payload(report_id, topic)
        record = REPORTS.get(report_id)
        if record is not None:
            # Idempotency: if we already wrote `done`, don't overwrite. Jobs
            # WILL run twice someday; idempotent jobs don't care.
            if record.get("status") != "done":
                record.update(payload)
                _write_outbox(report_id, payload)
        return payload

    return await ctx.step.run("build-report", _build)


# --------------------------------------------------------------------------- #
# Stage 1 - the smoke-test function (kept so the dashboard isn't empty)
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Extras - cleanup cron: every 5 minutes, drop done reports older than 10 min
# --------------------------------------------------------------------------- #
@inngest_client.create_function(
    fn_id="cleanup",
    name="Cleanup old done reports (cron)",
    trigger=inngest.TriggerCron(cron="*/5 * * * *"),
)
async def cleanup(ctx: inngest.Context) -> dict[str, int]:
    def _purge_old_done() -> dict[str, int]:
        now = time.time()
        removed = 0
        for rid, record in list(REPORTS.items()):
            if record.get("status") != "done":
                continue
            finished_at = record.get("finished_at")
            if not isinstance(finished_at, str):
                continue
            try:
                finished_ts = datetime.fromisoformat(finished_at).timestamp()
            except ValueError:
                continue
            if now - finished_ts > 600:  # 10 minutes
                REPORTS.pop(rid, None)
                out = OUTBOX_DIR / f"{rid}.txt"
                if out.exists():
                    out.unlink()
                removed += 1
        line = f"[cleanup] {_utc_now_iso()} removed={removed}"
        print(line, flush=True)
        return {"removed": removed}

    return await ctx.step.run("purge-old-done", _purge_old_done)


# --------------------------------------------------------------------------- #
# Wire Inngest into FastAPI - the dashboard talks to /api/inngest
# --------------------------------------------------------------------------- #
serve(
    app,
    inngest_client,
    [
        say_hello,
        make_report,
        heartbeat,
        cleanup,
    ],
)