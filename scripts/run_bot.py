"""Drive a Pipecat voice agent through N turns, then disconnect.

Reads env vars (or .qa-harness.json at CWD), runs the bot via voice-agent-qa,
emits a JSON summary to stdout.

Exit codes:
    0 — clean run, turn threshold met
    1 — could not connect (network / 5xx)
    2 — turn count below threshold (user-turn gate stuck? bot crashed?)
    3 — internal harness error
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    from voice_agent_qa import PipecatClient
except ImportError:
    print(
        json.dumps({"error": "voice-agent-qa not installed. pip install voice-agent-qa"}),
        file=sys.stderr,
    )
    sys.exit(3)


def load_config() -> dict[str, Any]:
    config_path = Path.cwd() / ".qa-harness.json"
    if config_path.exists():
        return json.loads(config_path.read_text())
    return {
        "pipecatBaseUrl": os.environ.get("PIPECAT_BASE_URL"),
        "pipecatMeetingId": os.environ.get("PIPECAT_MEETING_ID"),
        "maxTurns": int(os.environ.get("MAX_TURNS", "6")),
        "maxSeconds": int(os.environ.get("MAX_SECONDS", "600")),
        "connectParams": json.loads(os.environ.get("CONNECT_PARAMS_JSON", "{}")),
    }


async def main() -> int:
    cfg = load_config()
    if not cfg.get("pipecatBaseUrl") or not cfg.get("pipecatMeetingId"):
        print(
            json.dumps({"error": "missing pipecatBaseUrl or pipecatMeetingId in config/env"}),
            file=sys.stderr,
        )
        return 3

    client = PipecatClient(base_url=cfg["pipecatBaseUrl"])

    started_at = time.time()
    bot_turns: list[str] = []
    user_finals: list[str] = []
    errors: list[dict] = []
    gate_events: list[str] = []
    turn_threshold = int(cfg.get("maxTurns", 6))
    done = asyncio.Event()

    async def on_bot(text: str) -> None:
        bot_turns.append(text)
        if len(bot_turns) >= turn_threshold:
            done.set()

    async def on_user(text: str, final: bool) -> None:
        if final:
            user_finals.append(text)

    async def on_error(data: dict) -> None:
        errors.append(data)
        if data.get("fatal"):
            done.set()

    def on_turn_enabled() -> None:
        gate_events.append("enabled")

    def on_turn_disabled() -> None:
        gate_events.append("disabled")

    client.register_bot_transcript_callback(on_bot)
    client.register_user_transcript_callback(on_user)
    client.register_error_callback(on_error)
    client.register_turn_enabled_callback(on_turn_enabled)
    client.register_turn_disabled_callback(on_turn_disabled)

    try:
        await client.connect(
            meeting_id=cfg["pipecatMeetingId"],
            extra_params=cfg.get("connectParams", {}),
        )
    except Exception as exc:
        print(
            json.dumps({"error": "connect failed", "detail": str(exc)}),
            file=sys.stderr,
        )
        return 1

    try:
        await asyncio.wait_for(
            asyncio.wait([
                asyncio.create_task(done.wait()),
                asyncio.create_task(client.wait_closed()),
            ], return_when=asyncio.FIRST_COMPLETED),
            timeout=cfg.get("maxSeconds", 600),
        )
    except asyncio.TimeoutError:
        pass
    finally:
        await client.disconnect()

    elapsed = round(time.time() - started_at, 1)
    result = {
        "elapsed_seconds": elapsed,
        "bot_turns_received": len(bot_turns),
        "bot_turns_expected": turn_threshold,
        "user_finals_received": len(user_finals),
        "gate_events": gate_events,
        "errors": errors,
        "bot_turns_text": bot_turns,
        "user_finals_text": user_finals,
    }
    print(json.dumps(result, indent=2))

    if len(bot_turns) < turn_threshold:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
