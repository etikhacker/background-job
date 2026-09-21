# AI vs me - REVIEW

My hand-built version: [`../app.py`](../app.py)
The AI's version: [`./app.py`](./app.py) (generated from the prompt in [`prompt.md`](prompt.md))

I generated the AI version with a fresh AI assistant (a different session,
no shared memory of how I built the hand-built one) and a prompt I wrote
from memory, without copying the assignment text.

## What the AI did *better*

| # | What | Why I think it did it |
|---|------|-----------------------|
| 1 | **Pydantic models for request/response.** `CreateReportRequest` and `ReportResponse` give the AI's API OpenAPI docs and validation for free. | Common AI habit - reach for the typed abstraction. |
| 2 | **Thread-safe `ReportStore` with `asyncio.Lock`.** My hand-built version uses a plain dict because the spec said "in-memory" - but on a real multi-worker uvicorn the AI's pattern is closer to what you'd ship. | Real-world instinct. |
| 3 | **Used `status.HTTP_202_ACCEPTED`** as the constant instead of the magic `202`. | A small style win. |
| 4 | **Field constraints on the schema** (`min_length=1, max_length=200`). I do this check by hand. | Pydantic's strength. |

## What the AI got *wrong* or silently *ignored*

| # | What | What's missing |
|---|------|----------------|
| 1 | **It forgot the empty-string check that I asked for.** I said "missing **or empty**" - my hand-built code checks both. Pydantic's `min_length=1` saves the AI here *only by accident* (because `""` is below length 1), but the AI never re-stated that it understood the requirement. | Behaviour I asked for, delivered by coincidence. |
| 2 | **`heartbeat` returns `{"pending": 0, "done": 0, "failed": 0}` always.** It built a stub `_summarise` that does nothing. The hand-built version actually scans `REPORTS`. The AI saw "summary" in the prompt and stubbed it. | The AI silently decided the *contents* of the summary without asking. |
| 3 | **No idempotency guard in `_build()`.** If the function ran twice (which Inngest retries *do*), my hand-built version refuses to overwrite a `done` record. The AI happily overwrites. | I asked for retries; the AI forgot that idempotency is what makes retries safe. |
| 4 | **No `outbox/<id>.txt` writing.** The assignment doesn't *require* it, but I had it as an extra; the AI matched the prompt exactly. | An extra - not an error, but a missed opportunity. |
| 5 | **No list endpoint, no cleanup cron.** I added them as extras. The AI matched the prompt only - it did exactly what was asked, nothing more. | Honest behaviour - but a reminder that AI = spec, not intention. |
| 6 | **No `GET /reports` (list)** endpoint | AI didn't anticipate it. |
| 7 | **The `on_failure` handler.** I added one to mark failed reports in REPORTS; the AI doesn't. | Behaviour difference, not a bug. |

## What *my prompt* forgot to specify

| # | What | What the AI decided silently |
|---|------|-------------------------------|
| 1 | **What the summary line in `heartbeat` should look like.** The AI stubbed it. I should have said: "the summary is the count of records in each state." | The AI made up its own stub. |
| 2 | **What happens if the in-memory record is missing in `make-report`'s second step** (because the API was restarted). The AI writes nothing useful; mine writes the payload but skips the outbox because the record is gone. | Both of us fail this case - but in different ways. |
| 3 | **The shape of the result** (`headline` / `lines` / `word_count`). I let the AI invent the schema. | The AI chose something reasonable. |
| 4 | **Whether to validate `topic` length.** I said "max 200"; the AI did the same. Lucky guess - I could've left it open. | OK. |

## Diff highlights

```bash
# Run this to see them side by side:
git diff --no-index ../app.py ./app.py | head -200
```

Largest single difference: my hand-built version has **two cron functions**
(`heartbeat` and `cleanup`) plus an outbox writer plus an idempotency
guard plus an `on_failure` handler plus a list endpoint - roughly **+130 lines** that all
exist because I knew the assignment had a "stretch" section and an
"extras" list. The AI matched the prompt exactly and didn't try to
anticipate either.

## Lesson (one line)

An AI's output is exactly as good as your specification - and you could
only judge it because you built the thing yourself first.

---

## One rematch

I re-ran the prompt once, this time with the additions below, and the
AI's output added: idempotency on `_build`, the `outbox/<id>.txt` write,
and an accurate `summary` in the heartbeat. What I added to the prompt
to make it work:

> "The `_build` step must be **idempotent**: if the in-memory record is
> already `done`, do not overwrite. Also write the finished payload to
> `outbox/<id>.txt`. In `heartbeat`, `summary` must be the real count of
> records by status - call the store's summary method."

The diff shrank from ~130 extra lines to ~30.