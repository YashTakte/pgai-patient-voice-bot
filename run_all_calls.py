"""
run_all_calls.py
----------------
Places every scenario call in sequence (one number, one call at a time),
so you get your 10+ required calls in a single command:

    python run_all_calls.py

Requires the server to already be running in another terminal:

    python -m patient_bot.server --serve

Each call runs to completion (hang-up) before the next begins, because we
only have one outbound line and want clean, separate recordings.
"""

import time

import requests

from scenarios import all_scenarios

SERVER = "http://localhost:7860"
# Seconds to wait after starting a call before starting the next one.
# Tune to your typical call length so calls don't overlap.
GAP_SECONDS = 150


def main():
    scenarios = all_scenarios()
    print(f"Running {len(scenarios)} scenarios:\n  " + "\n  ".join(scenarios))

    for i, scenario in enumerate(scenarios, 1):
        print(f"\n[{i}/{len(scenarios)}] Calling with scenario: {scenario}")
        resp = requests.post(f"{SERVER}/call", params={"scenario": scenario})
        print(f"  -> {resp.json()}")

        if i < len(scenarios):
            print(f"  waiting {GAP_SECONDS}s for call to finish...")
            time.sleep(GAP_SECONDS)

    print("\nDone. Check recordings/ and transcripts/.")


if __name__ == "__main__":
    main()
