"""
patient_bot/server.py
----------------------
FastAPI server with two jobs:

1. POST /call  -> initiates an OUTBOUND Twilio call to the PGAI test number.
                  Twilio answers, then opens a Media Stream WebSocket back to us.
2. WS  /ws     -> accepts that WebSocket and hands the audio to the Pipecat bot,
                  loaded with whichever scenario we picked for this call.

Run a single scenario from the command line:

    python -m patient_bot.server --scenario refill_basic

The scenario file selects the patient persona + goal (see scenarios/).
"""

import argparse
import json
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from loguru import logger
from twilio.rest import Client

from patient_bot.bot import run_bot
from scenarios import load_scenario

load_dotenv()

app = FastAPI()

TARGET_NUMBER = os.getenv("PGAI_TEST_NUMBER", "+18054398008")
FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")
PUBLIC_HOST = os.getenv("PUBLIC_HOST")  # e.g. your-name.ngrok.io  (no scheme)

twilio_client = Client(
    os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN")
)

# Active scenario for the next call, set by /call or CLI.
_pending_scenario = {"name": None}


@app.post("/call")
async def start_call(scenario: str = "refill_basic"):
    """Trigger an outbound call running the named scenario."""
    _pending_scenario["name"] = scenario

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://{PUBLIC_HOST}/ws">
      <Parameter name="scenario" value="{scenario}" />
    </Stream>
  </Connect>
</Response>"""

    try:
        call = twilio_client.calls.create(
            to=TARGET_NUMBER,
            from_=FROM_NUMBER,
            twiml=twiml,
            record=True,  # Twilio-side recording as a backstop
        )
    except Exception as e:
        logger.error(f"Twilio call failed: {e}")
        return {"error": str(e)}
    logger.info(f"Started call {call.sid} | scenario={scenario} -> {TARGET_NUMBER}")
    return {"call_sid": call.sid, "scenario": scenario}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Twilio sends two JSON messages first: "connected", then "start".
    await websocket.receive_text()                       # connected
    start_msg = json.loads(await websocket.receive_text())  # start

    start_data = start_msg["start"]
    stream_sid = start_data["streamSid"]
    call_sid = start_data["callSid"]

    # Pull scenario from custom parameter (falls back to pending).
    params = start_data.get("customParameters", {})
    scenario_name = params.get("scenario") or _pending_scenario["name"] or "refill_basic"

    scenario = load_scenario(scenario_name)
    logger.info(f"WebSocket connected | scenario={scenario_name}")

    await run_bot(
        websocket=websocket,
        stream_sid=stream_sid,
        call_sid=call_sid,
        system_prompt=scenario["system_prompt"],
        opening_line=scenario["opening_line"],
        scenario_name=scenario_name,
        patient_speaks_first=scenario.get("patient_speaks_first", False),
        voice_id=scenario.get("voice_id"),
    )


def _cli_call(scenario: str):
    """Place a single call from the CLI (server must already be running)."""
    import requests

    resp = requests.post("http://localhost:7860/call", params={"scenario": scenario})
    if resp.status_code != 200:
        print(f"Server returned {resp.status_code}. Response body:")
        print(resp.text)
        return
    try:
        print(resp.json())
    except Exception:
        print("Unexpected non-JSON response from server:")
        print(resp.text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true", help="Run the FastAPI server")
    parser.add_argument("--scenario", default="refill_basic", help="Scenario to call with")
    args = parser.parse_args()

    if args.serve:
        uvicorn.run(app, host="0.0.0.0", port=7860)
    else:
        _cli_call(args.scenario)
