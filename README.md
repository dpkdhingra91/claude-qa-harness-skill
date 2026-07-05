# claude-qa-harness-skill

A [Claude Code](https://claude.com/claude-code) skill that orchestrates end-to-end smoke tests of Pipecat voice agents.

When you say to Claude Code: **"smoke test the voice agent"**, **"run nightly QA"**, or **"check the voice pipeline"** — this skill:

1. Pre-flights the voice + backend endpoints
2. Spins up a candidate bot via [`voice-agent-qa`](https://github.com/dpkdhingra91/voice-agent-qa)
3. Waits for N bot turns (default 6) or a wall-clock cap
4. Fetches the resulting report from your backend
5. Diffs against a known-good baseline (structural, not lexical — voice has natural variance)
6. Summarizes pass/fail in a markdown table with one-paragraph synthesis

## Install

```bash
mkdir -p .claude/skills/voice-qa-harness/
cp -r claude-qa-harness-skill/* .claude/skills/voice-qa-harness/
```

Or globally:

```bash
mkdir -p ~/.claude/skills/voice-qa-harness/
cp -r claude-qa-harness-skill/* ~/.claude/skills/voice-qa-harness/
```

Install the underlying bot:

```bash
pip install voice-agent-qa
```

## Configure

Drop a `.qa-harness.json` at your repo root (see [`examples/qa-harness.json.example`](examples/qa-harness.json.example)):

```json
{
  "pipecatBaseUrl": "https://pipecat.example.com",
  "pipecatMeetingId": "3f4ff883-...",
  "backendBaseUrl": "https://api.example.com",
  "baselinePath": "tests/voice-baseline.json",
  "maxTurns": 6,
  "connectParams": { "language_code": "en", "...": "..." }
}
```

Or set env vars: `PIPECAT_BASE_URL`, `PIPECAT_MEETING_ID`, `BACKEND_BASE_URL`, `BASELINE_PATH`, `MAX_TURNS`, `MAX_SECONDS`, `CONNECT_PARAMS_JSON`.

## Use it

In Claude Code:

> Run the voice QA smoke test.

The skill triggers, runs the harness, and reports back something like:

```
| Step                 | Status | Detail                            |
| -------------------- | ------ | --------------------------------- |
| Pipecat health       | ✓      | 200 in 124ms                      |
| Backend health       | ✓      | 200 in 89ms                       |
| Bot turns            | ✓      | 6 / 6 expected                    |
| User transcripts     | ✓      | 5 finals captured                 |
| Transcript persist   | ✓      | latest snapshot has 11 messages   |
| Report generation    | ✗      | 404 — report never created        |
| Baseline diff        | n/a    | skipped (report missing)          |

Voice pipeline is healthy except for report generation — the Celery task
is not firing or failing silently. Check tasks.py:process_meeting logs.
```

## Use it on cron

The two scripts work fine standalone — wire them into cron / GitHub Actions / Render Cron without Claude Code:

```bash
# Nightly at 02:30 UTC
30 2 * * * cd ~/qa && python scripts/run_bot.py > runs/$(date +%FT%H%M).json && \
                       python scripts/diff_report.py \
                         --baseline tests/voice-baseline.json \
                         --actual runs/$(ls runs | tail -1) > runs/$(date +%FT%H%M).diff.json
```

## What's in the box

```
SKILL.md                       # Claude Code skill spec (the brain)
scripts/
  run_bot.py                  # voice-agent-qa driver, JSON output
  diff_report.py              # structural diff between baseline and actual report
examples/
  qa-harness.json.example     # config file template
```

## Exit codes (run_bot.py)

| Code | Meaning                                            |
|------|----------------------------------------------------|
| 0    | Clean run, turn threshold met                      |
| 1    | Could not connect (network / 5xx)                  |
| 2    | Turn count below threshold (user-gate stuck? crash?) |
| 3    | Internal harness error                             |

## Origin

The pattern extracted from a production AI-interview voice pipeline that runs this harness nightly against prod. Has caught: silent LLM model swaps, RAI false-positive bursts, transcript-persist race conditions, and Celery worker drift — none of which manual QA was finding before users hit them.

## License

MIT — see [LICENSE](LICENSE).

---

*Extracted from the production voice stack of [AI Interview Agents](https://www.aiinterviewagents.com) — an AI voice interviewer that runs real two-way spoken interviews and screens candidates at scale.*
