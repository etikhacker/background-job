# Your first background job

A tiny FastAPI service whose slow work happens **outside** the request.
The endpoint answers in milliseconds; an Inngest background function
spends 8 seconds building the report; a status endpoint reports progress.

Built for **FlyRank Internship — Backend Track — Week 4 — Assignment A7.**

---

## What this assignment is about

In every previous assignment, the work happened **inside** the request:
the client asks, the server does the work, the client waits. That is
fine for fast work. **It breaks for slow work.**

This assignment teaches the professional fix: there are **three different
ways work starts**, not one:

| Row | What starts it | Example | Where you see it in this repo |
|-----|---------------|---------|-------------------------------|
| 1 | A client asks and **waits** for the answer | `GET /health` | `app.py` — `@app.get("/health")` |
| 2 | A client asks, the work happens **later** | "make my report" → 202 now, report in 8s | `POST /reports` + `make-report` |
| 3 | Nobody asks. The **clock** starts it | "every day at 08:00, send the summary" | `heartbeat` cron + `cleanup` cron |

That table *is* the assignment. One endpoint from row 1, one job from
row 2, one job from row 3 — and the same tool (Inngest) does the heavy
lifting for rows 2 and 3.

### Why it matters in real life

Every "we'll email you when it's ready" message you have ever seen is
this pattern:

- YouTube renders a video → "ready in ~10 min"
- Stripe charges via 3-D Secure → "we'll let you know"
- GitHub Actions finishes a build → notification arrives
- FlyRank produces an SEO report or AI image → email arrives

If you built it the naive way (do the work inside the HTTP request),
the user's browser would time out, they would refresh, the work would
happen twice, and the server would melt. The whole professional world
uses row 2 — background jobs — for slow work.

---

## Architecture (in one picture)

```
   Client                FastAPI (this repo)               Inngest Dev Server
     │                          │                                 │
     │ POST /reports            │                                 │
     │ {"topic":"cats"}         │                                 │
     ├─────────────────────────►│                                 │
     │                          │ save {id,topic,status:pending}  │
     │                          │ send event "report/requested"   │
     │                          ├────────────────────────────────►│
     │                          │                                 │
     │                          │   function: make-report         │
     │                          │   ──────────────────────────────┤
     │                          │   step.sleep("do-the-slow-work",│
     │                          │             8s)                  │
     │                          │   step.run("build-report", ...) │
     │                          │   ──────────────────────────────┤
     │                          │   ◄── update REPORTS ───────────┤
     │                          │   write outbox/<id>.txt         │
     │  HTTP/1.1 202            │                                 │
     │  {"id":"afa0...","status":"pending"}                       │
     │◄─────────────────────────┤                                 │
     │                          │                                 │
     │                          │   ┌──────────┐  every minute    │
     │                          │   │heartbeat │  cron trigger    │
     │                          │   └──────────┘                  │
     │                          │                                 │
     │ GET /reports/afa0...  (poll)                                │
     ├─────────────────────────►│                                 │
     │  {"status":"pending"}     │                                 │
     │◄─────────────────────────┤                                 │
     │                          │                                 │
     │       ... 8 seconds ...   │                                 │
     │                          │                                 │
     │ GET /reports/afa0...      │                                 │
     ├─────────────────────────►│                                 │
     │  {"status":"done",        │                                 │
     │   "result":{...}}         │                                 │
     │◄─────────────────────────┤                                 │
```

Two terminals, no workers, no queue daemon, no cron scheduler. Inngest
runs all of that for you, locally, for free.

---

## How to run it

You need **two terminals** running at the same time.

### Terminal 1 — the API

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

### Terminal 2 — the Inngest Dev Server + dashboard

```powershell
npx inngest-cli@latest dev -u http://127.0.0.1:8000/api/inngest
```

Open the dashboard: **http://127.0.0.1:8288**

Every function, every run, every step, every retry — visible there.

That's it. Two commands. No account, no card.

---

## Endpoints

| Method | Path | Body | Returns | Notes |
|--------|------|------|---------|-------|
| `GET` | `/health` | – | `200 {"status":"ok"}` | Stage 0 — sanity check |
| `POST` | `/reports` | `{"topic":"cats"}` | `202` + `{id, topic, status, created_at}` | Stage 2 — instant. Topic missing/empty → `400` |
| `GET` | `/reports` | – | `[{...}, ...]` | Extra — control panel |
| `GET` | `/reports/<id>` | – | the record | First `pending`, later `done`. Unknown id → `404` |

## Inngest functions

| Function | Trigger | Steps | Retries | Why it exists |
|----------|---------|-------|---------|---------------|
| `say-hello` | event `test/hello` | `sleep(5s)` | 0 | Stage 1 smoke test |
| `make-report` | event `report/requested` | `sleep(8s)` → `run(build-report)` | 2 | Stage 2 — does the slow work. Raises if `topic=="fail"` for Stage 3. |
| `heartbeat` | cron `* * * * *` | `run(summarise)` | 0 | Stage 4 — logs `{pending, done, failed}` every minute |
| `cleanup` | cron `*/5 * * * *` | `run(purge-old-done)` | 0 | Extra — drops `done` reports older than 10 min |

---

## Stage checkpoints — what was verified

### Stage 0 — hello server
```powershell
PS> curl.exe -i http://127.0.0.1:8000/health
HTTP/1.1 200 OK
content-type: application/json
{"status":"ok"}
```

### Stage 1 — Inngest wired up
Open http://127.0.0.1:8288 → you should see 4 functions registered
under the app name `report-api`. Click **Invoke** on `say-hello` →
after 5s the run shows **Completed** with the step `do-the-slow-work`.

### Stage 2 — 202 + background + status
```powershell
PS> curl.exe -i -X POST http://127.0.0.1:8000/reports `
    -H "Content-Type: application/json" `
    -d '{"topic":"cats"}'
HTTP/1.1 202 Accepted
content-type: application/json
{"id":"afa07e1079f8","topic":"cats","status":"pending","created_at":"..."}

PS> curl.exe http://127.0.0.1:8000/reports/afa07e1079f8
{"id":"afa07e1079f8","topic":"cats","status":"pending", ...}      # ~t=0

# ... wait ~9 seconds (8s sleep + 1s build) ...

PS> curl.exe http://127.0.0.1:8000/reports/afa07e1079f8
{"id":"afa07e1079f8","topic":"cats","status":"done",
 "result":{"headline":"All about cats","lines":["cats is genuinely interesting.",
                                                  "Real apps would call an AI or a DB here - we just sleep and pretend.",
                                                  "Generated at 2026-09-20T15:44:52Z"],
           "word_count":3},
 "finished_at":"2026-09-20T15:44:52Z"}

PS> Get-Content outbox\afa07e1079f8.txt
Report id:     afa07e1079f8
Topic:         cats
Status:        done
Finished at:   2026-09-20T15:44:52.126556+00:00
Headline:      All about cats
----
cats is genuinely interesting.
Real apps would call an AI or a DB here - we just sleep and pretend.
Generated at 2026-09-20T15:44:52.126549+00:00
```

The endpoint answered in **<10 ms**. The work happened 8 seconds later,
in the background. Same id, same record, just `pending → done`.

### Stage 3 — retries + validation
```powershell
# Bad input: rejected at the door, no event sent
PS> curl.exe -i -X POST http://127.0.0.1:8000/reports `
    -H "Content-Type: application/json" -d '{}'
HTTP/1.1 400 Bad Request
{"error":"`topic` is required and must be a non-empty string"}

# Good input that will fail at the build step:
PS> curl.exe -i -X POST http://127.0.0.1:8000/reports `
    -H "Content-Type: application/json" -d '{"topic":"fail"}'
HTTP/1.1 202 Accepted
{"id":"ea4c1092d4da","topic":"fail","status":"pending", ...}
```
Open the run in the dashboard — three attempts, each ending in
`Failed`, with back-off between them.

**The one-sentence difference (the assignment asks for this):**

> A request with a missing `topic` is rejected at the door (`400`, no
> event sent) because the *input* is invalid — but a request with
> `topic:"fail"` is accepted and retried because the input is fine and
> the *moment* just happened to fail. **Retries are for transient
> moments, not for bad data.**

### Stage 4 — heartbeat cron
Two consecutive dashboard runs of `heartbeat`, one minute apart, both
printing to the API terminal:
```
[heartbeat] 2026-09-20T15:45:00.011047+00:00 summary={'pending': 0, 'done': 1, 'failed': 0}
[heartbeat] 2026-09-20T15:46:00.011091+00:00 summary={'pending': 1, 'done': 1, 'failed': 0}
```

**Cron expressions (built on https://crontab.guru):**

| Schedule | Cron expression |
|----------|-----------------|
| Every minute | `* * * * *` |
| Every day at 08:00 | `0 8 * * *` |
| Every Sunday at 22:00 | `0 22 * * 0` |
| Every 15 minutes | `*/15 * * * *` |
| Every 5 minutes | `*/5 * * * *` (what `cleanup` uses) |

The five fields, left-to-right: **minute · hour · day-of-month · month · day-of-week**. `*` means "every".

---

## Extras

All of these are optional — pick what sounds fun. This build did all four.

### 1. List endpoint — `GET /reports`
A control-panel view of every report we know about. Useful for ops
and debugging.

### 2. The "email" — `outbox/<id>.txt`
The job writes its finished payload to `outbox/<id>.txt`. This is the
stand-in for "sending mail from a job" — which is where this pattern
lives in real products (Stripe webhooks, GitHub commit emails, etc.).
In production the line that writes the file would call SendGrid, SES,
or whatever.

### 3. The cleanup cron — `*/5 * * * *`
Drops `done` reports older than 10 minutes (and their outbox files).
**Cron's most common real job is taking out the trash.** When you have
a database and a job system, you accumulate stale rows; a tiny cron
that deletes them is the simplest, cheapest answer.

### 4. The restart experiment — durability proof
1. `POST /reports {"topic":"dogs"}` → instant 202.
2. Mid-way through the 8 s `step.sleep`, kill the API process
   (`Stop-Process -Name python` in another terminal).
3. Restart the API in Terminal 1.
4. Watch the dashboard.

**What happened:** the *worker* (the Inngest Dev Server) never died;
it kept the function's checkpointed state in its SQLite store. When
the API came back, the dev server re-invoked `make-report` to finish
the job. **The job survived; the API didn't have to.**

In this run, `REPORTS` is in-memory, so the API restart cleared it and
the outbox file was *not* written — the second observation is that
**durability is only as good as your state store**. With a real
database for `REPORTS`, the report would have been written; idempotency
guards in `_build()` already prevent overwriting a `done` record.

This property — work that survives crashes and restarts, because each
step's result is saved — is called being **durable**, and it's the
deep magic of tools like Inngest.

---

## Idempotency, concurrency, and other hardening ideas

These are mentioned in the assignment as stretch goals. The hand-built
version already has idempotency; the others are left as exercises.

- **Idempotency** — sending the same `report/requested` event twice
  with the same id must build the report only once. My `_build()`
  checks `record["status"] != "done"` before writing. **Why it
  matters:** jobs WILL run twice someday; idempotent jobs don't care.
- **Concurrency limit** — `concurrency=2` would let at most 2
  `make-report` runs execute at once; the rest queue. **When would you
  *want* a queue to be slow?** When the downstream service (an AI API,
  a database) has its own rate limits and benefits from a steady,
  paced trickle rather than a thundering herd.
- **Durable proven** — the restart experiment above is the proof.

---

## File map

```
background-job/
├── app.py                 # FastAPI + Inngest (everything in one file, ~270 lines)
├── requirements.txt
├── .gitignore
├── README.md              # you are here
├── outbox/                # extra: written by make-report on success
│   └── <id>.txt           # (one file per finished report)
├── ai-version/            # Stage 6: AI-generated alternative (separate folder)
│   ├── app.py             # a fresh AI assistant's implementation
│   ├── prompt.md          # the literal prompt I gave it (from memory, no cheating)
│   └── REVIEW.md          # diff, what it did better, what it missed
└── screenshots/           # empty placeholder for dashboard screenshots
```

---

## Tech notes — what was tricky

| Problem | What happened | Fix |
|---------|--------------|-----|
| `inngest` 0.4.20 sent a request body the Python SDK couldn't parse (500 error) | Dev server (very recent) ↔ SDK (slightly older) protocol mismatch on `ServerRequest` | Upgraded SDK to `inngest==0.5.19` — SDK and Dev Server match. |
| `step.sleep("id", "8s")` doesn't accept a string in Python SDK | The Python SDK's `sleep()` takes `timedelta` or int (ms), not the JS-style `"8s"` | Use `timedelta(seconds=8)`. The README code reflects this. |
| First attempt at `on_failure(ctx, step)` returned 500 | The Python SDK's on_failure handler signature is `Callable[[Context], Awaitable[T]]` — one arg, not two | Simplified to a single `(ctx)` argument; the handler scans REPORTS to find the pending one to mark failed. |
| Git repo root was at `C:\Users\User`, not the workspace | The first `git init` happened at the wrong level | Used `git subtree split --prefix=background-job` to extract a flat history, then `git push --force` to rewrite the GitHub repo with files at root. README is now at the repo root. |

---

## Glossary (every bold word in the assignment, plain-language)

| Word | What it means |
|------|---------------|
| **API** | A set of doors a program offers so other programs can talk to it — here, your report service. |
| **Background job** | Work your server starts but doesn't finish inside the request. The client gets an answer now; the work finishes later, elsewhere. |
| **Worker** | The program that actually does background work. In this assignment, Inngest plays the worker's role for you. |
| **Event** | A small message that says "something happened" — like `report/requested`. Functions can be set up to run whenever a matching event arrives. |
| **Trigger** | The thing that starts a function: an event ("when a report is requested") or a schedule ("every minute"). |
| **Status endpoint** | An endpoint whose only job is to report progress: `GET /reports/:id` → `pending`, `done`, or `failed`. |
| **Polling** | Asking the status endpoint again and again until the answer changes. Simple, and completely normal. |
| **202 Accepted** | The status code that means: "I received your request and work will happen — but it is not done yet." |
| **Status code** | The 3-digit number in every response saying how it went: `200`, `202`, `400`, `404`. |
| **Eventual consistency** | The state of the world between "accepted" and "done": the answer exists *soon*, not *now*. |
| **In-memory** | Data kept in your program's variables. Fast and simple — and gone when the program stops. |
| **Step** | One named piece of a job. Job tools save each finished step, so a re-run can skip what is already done. |
| **Retry** | Running a failed job again automatically. Good for temporary failures, wrong for bad input. |
| **Backoff** | Waiting longer before each retry — 5 s, then 30 s, then 2 min — so a struggling service gets air instead of more punches. |
| **Cron job** | A task started by a scheduler at fixed times — every minute, every day at 08:00 — with no request involved. |
| **Cron expression** | The five-field code that describes a schedule. `0 8 * * *` = every day at 08:00. |
| **Inngest** | The free tool this assignment uses to run background jobs and cron jobs. Your code defines the functions; Inngest triggers, retries, and shows them in a dashboard. |
| **Dev Server** | Inngest's local engine + dashboard, started with one command. Runs only on your machine, no account. |
| **Dashboard** | The Dev Server's web page at `localhost:8288`: every function, every run, every step, every retry. |
| **Idempotent** | Running the same job twice causes the effect *once*. Jobs *will* run twice someday; idempotent jobs don't care. |
| **Durable** | Work that survives crashes and restarts: because each step's result is saved, a restarted job resumes where it stopped. |

---

## Submission

The public repo link: **https://github.com/etikhacker/background-job**

Everything the assignment asks for lives in this repo:

- ✅ FastAPI service that returns 202 + id in under a second
- ✅ Background function with two steps (sleep + build) — visible in dashboard
- ✅ Status endpoint: `pending` first, `done` later, unknown id → 404
- ✅ Missing topic → 400, no event sent (input rejected at the door)
- ✅ `topic:"fail"` shows 3 attempts ending Failed (retries for transient moments)
- ✅ Cron function runs every minute and logs the summary
- ✅ ≥ 6 meaningful commits (this repo has 8)
- ✅ README with the two run commands, endpoint/function table, pasted 202 + two polls, Stage 3 & 4 sentences
- ✅ Stage 6 (Bonus): AI-generated code in `ai-version/` + diff review

---

## Stage 6 — AI vs me

`ai-version/` is what an AI assistant produced when I asked it, in my
own words from memory, to build this system from scratch. I ran its
endpoints, diffed its file against `app.py`, and wrote the review in
[`ai-version/REVIEW.md`](ai-version/REVIEW.md). One-sentence lesson:

> An AI's output is exactly as good as your specification — and you
> could only judge it because you built the thing yourself first.