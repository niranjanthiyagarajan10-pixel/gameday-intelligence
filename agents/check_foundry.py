"""Check the Foundry connection end to end: one real key moment through the Narrator and Verifier.

    az login
    (put FOUNDRY_PROJECT_ENDPOINT and MODEL_STRONG in .env, see .env.example)
    python -m agents.check_foundry

Prints each trace step and the card a fan would see. Exit code 0 means the Narrator's draft
passed the Verifier through Microsoft Foundry; 1 means the template fallback was used.
"""

from __future__ import annotations

import asyncio
import sys

from agents.desk import CardDesk
from agents.llm import LLM
from engine.models import Moment

SAMPLE = Moment(
    moment_id="check-mo-01", minute=81, kind="goal", leverage=1.4, team="away", players=["AV08"],
    evidence={"xg": 0.08, "player": "AV08", "score": "1-1", "wp_before": 0.12, "wp_after": 0.3, "leverage": 1.4},
    state_ref="check@4860.0",
)


async def main() -> int:
    from app.env import load_env

    load_env()
    llm = LLM.from_env()
    print(f"backend: {llm.backend.name}, model: {llm.strong}")
    if not llm.live:
        print("No Foundry endpoint: set FOUNDRY_PROJECT_ENDPOINT (and run az login) first.")
    desk = CardDesk(llm, {"AV08": "Callum Hale"}, {"home": "Kingsport Rovers", "away": "Ashford Vale"}, "check")
    ok = True
    for audience in ("casual", "analyst"):
        written = await desk.write(SAMPLE, audience)
        for s in written.steps:
            print(f"  {s.agent:<9} {s.action:<10} {s.status:<9} {s.ms:>5} ms  {s.detail}")
        print(f"{audience} ({written.source}): {written.cue.text()}\n")
        ok = ok and written.source == "narrator"
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
