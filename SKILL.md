---
name: voice-qa-harness
description: |
  Run an end-to-end smoke test against a Pipecat voice agent: spin up a candidate
  bot via voice-agent-qa, drive N turns, persist the transcript to the backend,
  fetch the resulting report, and diff against a known-good baseline. Surface
  regressions clearly. Use when the user says "smoke test the voice agent",
  "run nightly QA", "check the voice pipeline", "test the bot end-to-end",
  or similar.
---

# voice-qa-harness — end-to-end smoke test for Pipecat voice agents

You are running a smoke test of a voice agent. The goal is to detect regressions in:

- WebSocket connectivity + handshake
- Bot transcript generation (LLM responding)
- User transcript capture (STT working)
- Turn-gate orchestration (no deadlocks)
- Transcript persistence to the backend
- Report generation pipeline (if applicable)

The harness leans on [`voice-agent-qa`](https://github.com/dpkdhingra91/voice-agent-qa) as the underlying Pipecat client.

## Inputs you should gather (ask once if missing)

Before running, confirm:

1. **`PIPECAT_BASE_URL`** — e.g. `https://pipecat.example.com`
2. **`PIPECAT_MEETING_ID`** — a server-side test session id (reusable, doesn't expire, no one-time-use guard)
3. **`BACKEND_BASE_URL`** — for fetching the report after the run, e.g. `https://api.example.com`
4. **`BASELINE_PATH`** — path to the known-good baseline JSON (skip diff step if absent)
5. **`MAX_TURNS`** (default 6) — how many bot turns to wait for before disconnecting
6. **`MAX_SECONDS`** (default 600) — wall-clock cap

If the project has a `.qa-harness.json` config file at the repo root, read those values from it instead of asking.

## Execution plan

Run these steps in order. **Do not parallelize.** Each step depends on the previous.

### 1. Pre-flight

- `curl -fsS $PIPECAT_BASE_URL/health` — verify the voice pipeline is reachable. If 5xx or timeout, STOP and report; nothing else will work.
- `curl -fsS $BACKEND_BASE_URL/health` — same for the backend.
- Check `pip list | grep voice-agent-qa`. If missing: `pip install voice-agent-qa`.

### 2. Run the bot

Invoke `scripts/run_bot.py` (in this skill repo) with the env vars above set. It calls voice-agent-qa, registers transcript callbacks, waits for `MAX_TURNS` bot turns, then disconnects.

Output is JSON to stdout — capture it into a variable for step 3:

```bash
RESULT=$(python scripts/run_bot.py 2>&1)
echo "$RESULT" | tail -20
```

The script exits 0 on a clean run, 1 on connection failure, 2 on turn-count below threshold, 3 on internal error. Report the exit code to the user.

### 3. Fetch the report (if applicable)

```bash
curl -fsS "$BACKEND_BASE_URL/meetings/$PIPECAT_MEETING_ID/report" -o /tmp/run-$(date +%s).json
```

If the backend returns 404 or empty: the report-generation pipeline didn't fire. **This is a regression** — report it.

### 4. Diff against baseline (if BASELINE_PATH is set)

Use `scripts/diff_report.py` to compare:

```bash
python scripts/diff_report.py --baseline "$BASELINE_PATH" --actual /tmp/run-*.json
```

The diff focuses on **structural** changes (missing keys, type changes, sign flips) rather than exact text matching — voice transcripts have natural variance.

### 5. Summarize

Output a Markdown table to the user:

| Step | Status | Detail |
|---|---|---|
| Pipecat health | ✓ | 200 in 124ms |
| Backend health | ✓ | 200 in 89ms |
| Bot turns | ✓ | 6 / 6 expected |
| User transcripts | ✓ | 5 finals captured |
| Transcript persist | ✓ | latest snapshot has 11 messages |
| Report generation | ✗ | 404 — report never created |
| Baseline diff | n/a | skipped (report missing) |

End with one paragraph: "Voice pipeline is healthy except for report generation — the Celery task is not firing or is failing silently. Suggest checking `tasks.py:process_meeting` logs."

## DO NOT

- Don't retry on first failure — surface it to the user. Flaky tests teach bad habits.
- Don't burn through real production meeting IDs — this MUST use the reusable test meeting id.
- Don't speak any audio. The harness is text-flow only; if the server requires actual mic input to progress past turn 1, document that as a finding and stop.
- Don't write the run JSON anywhere other than `/tmp/` — these are throwaway snapshots, not artifacts.
- Don't modify the baseline unless the user explicitly says "accept the new shape as baseline".

## When to escalate to the user

- Any step that fails with a non-obvious error (5xx with HTML body, timeout, schema-changed-without-warning) — print the relevant detail and STOP. Don't speculate.
- If turn count < threshold but bot transcripts are present — likely the user-turn gate isn't enabling (a real bug). Flag it explicitly.
- If the report exists but the diff shows >5 structural changes — schema drift, escalate.

## Configuration file format

If `.qa-harness.json` is present at the repo root:

```json
{
  "pipecatBaseUrl": "https://pipecat.example.com",
  "pipecatMeetingId": "3f4ff883-336a-496e-b96e-5904b10bcf96",
  "backendBaseUrl": "https://api.example.com",
  "baselinePath": "tests/voice-baseline.json",
  "maxTurns": 6,
  "maxSeconds": 600,
  "connectParams": {
    "position": "Backend Engineer",
    "candidate_name": "QA Probe",
    "language_code": "en"
  }
}
```

If absent, fall back to env vars (`PIPECAT_BASE_URL`, `PIPECAT_MEETING_ID`, etc.) — or ask the user.
