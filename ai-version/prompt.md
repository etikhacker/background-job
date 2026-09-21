# My prompt to the AI

This is the literal prompt I wrote myself, from memory, asking an AI
assistant to build this assignment. I tried to name every behaviour
that matters, without copying the assignment text.

---

> Build a Python service with FastAPI that has one slow endpoint. The
> endpoint should answer instantly (HTTP 202) and the slow work should
> run in a background job. Use Inngest (Python SDK) for the background
> job - register one function triggered by an event called
> `report/requested` whose event data is `{"id": "...", "topic": "..."}`.
>
> The endpoint is `POST /reports` and takes a JSON body with a single
> field `topic`. If `topic` is missing or empty, respond with `400` and
> do not fire any event. If it's there and non-empty, generate a random
> id, save `{id, topic, status:"pending", created_at}` in an in-memory
> dict, fire the event, and respond `202` with the saved object.
>
> The Inngest function must do its work in two steps:
> 1. `step.sleep("do-the-slow-work", timedelta(seconds=8))` — stand-in
>    for an AI call or DB export.
> 2. `step.run("build-report", ...)` — actually build the result. If the
>    topic is `"fail"`, raise an exception so we can see retries. Otherwise
>    build a result with `headline`, `lines`, `word_count`, save the
>    payload into the in-memory dict with `status:"done"`, and return it.
>
> The function must have `retries=2` so a failing run retries three
> times total with backoff.
>
> Also add `GET /reports/<id>` that returns the saved object — first
> `pending`, later `done`. Unknown id → 404.
>
> Then add an Inngest cron function called `heartbeat` with schedule
> `* * * * *` (every minute). It should print one line summarising how
> many records are pending, done, and failed.
>
> The Inngest SDK functions must be served at `/api/inngest` using
> `inngest.fast_api.serve(app, client, [...functions...])`.
>
> Don't use a database. Everything is in-memory.