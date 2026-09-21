# Your first background job

A tiny FastAPI service whose slow work happens **outside** the request.
The endpoint answers in milliseconds; an Inngest background function
spends 8 seconds building the report; a status endpoint reports progress.

Built for FlyRank Internship — Backend Track — Week 4 — Assignment A7.

---

## What this is

Three ways work starts, three parts of the assignment:

| Row | What starts it | This repo |
|-----|---------------|-----------|
| A client asks and waits | request/response | `GET /health` |
| A client asks, work happens later | background job (event-driven) | `POST /reports` + `make-report` |
| Nobody asks; the clock starts it | cron job | `heartbeat` (every minute) + `cleanup` (every 5 min) |

The whole thing is ~270 lines of Python plus one Inngest Dev Server.
No queues, no workers, no cron daemon — Inngest does all three.

---

## How to run it

You need **two terminals**, both running on your machine.

### Terminal 1 — the API

```bash
# from the repo root
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

You should see `Uvicorn running on http://127.0.0.1:8000`.

### Terminal 2 — the Inngest Dev Server + dashboard

```bash
npx inngest-cli@latest dev -u http://127.0.0.1:8000/api/inngest
```

Open the dashboard: **http://127.0.0.1:8288** — every function and every
run is visible there.

That's it. Two commands. No account, no card.

---

## Endpoints

| Method | Path | Body | Returns | Notes |
|--------|------|------|---------|-------|
| `GET` | `/health` | – | `{"status":"ok"}` | Stage 0 |
| `POST` | `/reports` | `{"topic":"cats"}` | `202 Accepted` + `{id, topic, status, created_at}` | Stage 2 — instant. Topic missing/empty → `400` (Stage 3) |
| `GET` | `/reports` | – | `[{...}, ...]` | Extra — control-panel view |
| `GET` | `/reports/<id>` | – | the record | First `pending`, later `done`. Unknown id → `404` |

## Inngest functions

| Function | Trigger | Steps | Retries | Why it exists |
|----------|---------|-------|---------|---------------|
| `say-hello` | event `test/hello` | `sleep(5s)` | 0 | Stage 1 smoke-test function |
| `make-report` | event `report/requested` | `sleep(8s)` → `run(build-report)` | 2 | Stage 2 — does the slow work. Raises if `topic == "fail"` so Stage 3 can watch retries. |
| `heartbeat` | cron `* * * * *` | `run(summarise)` | 0 | Stage 4 — logs `{pending, done, failed}` counts every minute |
| `cleanup` | cron `*/5 * * * *` | `run(purge-old-done)` | 0 | Extra — drops `done` reports older than 10 minutes |

The four functions live in `app.py`. The Inngest dashboard at
`http://127.0.0.1:8288` shows each function, every run, every step,
every retry — the visual proof that "background work" is real.

---

## Stage checkpoints — what was verified

### Stage 0 — hello server
```bash
$ curl -i http://127.0.0.1:8000/health
HTTP/1.1 200 OK
content-type: application/json
{"status":"ok"}
```

### Stage 2 — 202 + background + status
```bash
$ curl -i -X POST http://127.0.0.1:8000/reports \
    -H "Content-Type: application/json" -d '{"topic":"cats"}'
HTTP/1.1 202 Accepted
content-type: application/json
{"id":"afa07e1079f8","topic":"cats","status":"pending","created_at":"2026-09-20T15:44:43Z"}

$ curl http://127.0.0.1:8000/reports/afa07e1079f8
{"id":"afa07e1079f8","topic":"cats","status":"pending", ...}      # ~ t=0

# ... wait ~9 seconds (8 s sleep + build) ...

$ curl http://127.0.0.1:8000/reports/afa07e1079f8
{"id":"afa07e1079f8","topic":"cats","status":"done",
 "result":{"headline":"All about cats","lines":[...],"word_count":3},
 "finished_at":"2026-09-20T15:44:52Z"}
```

The endpoint returned in **<10 ms**. The work happened in the background,
8 seconds later. Same id, same record, just `pending` → `done`.

### Stage 3 — retries + validation
```bash
$ curl -i -X POST http://127.0.0.1:8000/reports \
    -H "Content-Type: application/json" -d '{}'
HTTP/1.1 400 Bad Request
{"error":"`topic` is required and must be a non-empty string"}

$ curl -i -X POST http://127.0.0.1:8000/reports \
    -H "Content-Type: application/json" -d '{"topic":"fail"}'
HTTP/1.1 202 Accepted
{"id":"...","topic":"fail","status":"pending"}
```
Open the dashboard run — three attempts, each ending in `Failed`, with
back-off between them.

**The difference (one sentence):** a request with a missing `topic` is
rejected at the door (`400`, no event sent) because the input is
*invalid* — but a request with `topic:"fail"` is accepted and retried
because the input is fine and the *moment* just happened to fail; the
retry is for transient moments, not bad data.

### Stage 4 — heartbeat cron
Two consecutive dashboard runs of `heartbeat`, one minute apart, both
printing `[heartbeat] 2026-09-20T... summary={'pending': 1, 'done': 1, 'failed': 0}`.

**Cron expressions (built on crontab.guru):**
- Every day at 08:00 → `0 8 * * *`
- Every Sunday at 22:00 → `0 22 * * 0`

---

## Extras

- `GET /reports` returns every record — a control-panel view of the job
  system's state.
- The job writes the finished report to `outbox/<id>.txt` — a stand-in
  for "email from a job". This is what `outbox/afa07e1079f8.txt` looks
  like after a successful run:
  ```
  Report id:     afa07e1079f8
  Topic:         cats
  Status:        done
  ...
  ```
- `cleanup` cron — every 5 minutes, drop `done` reports older than
  10 minutes (and their outbox files). Cron's most common real job is
  taking out the trash.

### Restart experiment — durability proof

1. POST a slow report (`topic:"dogs"`).
2. Mid-way through the 8 s `step.sleep`, kill the API process
   (`Ctrl-C` / `Stop-Process -Name python`).
3. Restart the API in Terminal 1.
4. Watch the dashboard.

**What happened:** the *worker* (the Inngest Dev Server) never died;
it kept the function's checkpointed state in its SQLite store. When the
API came back, the dev server re-invoked `make-report` to finish the
job. The job survived; the API didn't have to.

In this run, `REPORTS` is in-memory, so the API restart cleared it and
the outbox file was *not* written — the second observation is that
**durability is only as good as your state store**. With a real database
for `REPORTS`, the report would have been written twice — idempotency
guards handle that, but durability does not.

---

## File map

```
background-job/
├── app.py                # FastAPI + Inngest functions (everything)
├── requirements.txt
├── .gitignore
├── outbox/               # extra: written by make-report on success
├── ai-version/           # stage 6: AI-generated alternative (see below)
├── screenshots/          # dashboard screenshots (optional)
└── README.md
```

---

## Stage 6 — AI vs me

`ai-version/` is what an AI assistant produced when I asked it, in my own
words, to build this system from scratch. I ran its endpoints, diffed
its file against `app.py`, and wrote the review below — see
[`ai-version/REVIEW.md`](ai-version/REVIEW.md).