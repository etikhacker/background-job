"""Stage 0+1 - hello server + Inngest connected, first function runs."""
from datetime import timedelta

import inngest
from fastapi import FastAPI
from inngest.fast_api import serve

app = FastAPI(title="report-api", version="0.2.0")

inngest_client = inngest.Inngest(app_id="report-api", is_production=False)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@inngest_client.create_function(
    fn_id="say-hello",
    name="Say hello (smoke test)",
    trigger=inngest.TriggerEvent(event="test/hello"),
)
async def say_hello(ctx: inngest.Context) -> str:
    await ctx.step.sleep("do-the-slow-work", timedelta(seconds=5))
    return "Hello from the background!"


serve(app, inngest_client, [say_hello])