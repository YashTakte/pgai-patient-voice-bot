# PGAI Patient Voice Bot

This is a bot I built that calls the Pretty Good AI test line and pretends to be a patient. It books appointments, asks for refills, asks about hours and insurance, and pokes at edge cases to see where the receptionist agent breaks. Every call is recorded and written out as a timestamped transcript so I can review the conversations afterward.

## How it works

There are two bots in this story. Theirs is the receptionist that answers the phone, role playing a clinic called Pivot Point Orthopedics. Mine is the patient that calls in and gives it a hard time.

For my patient to hold a real phone conversation, it has to do four things in a loop: hear the receptionist, decide what a patient would say back, say it out loud, and do all of that fast enough that the call does not feel laggy or awkward. Here is how those four jobs are split up.

Twilio places the actual phone call to the test number and carries the audio both ways. Deepgram listens to the receptionist and turns its speech into text. GPT-4o is the patient's brain. It reads what the receptionist said and writes back what a patient would say, using a persona and a goal that live in the scenario files. Cartesia takes the brain's reply and speaks it out loud in a natural voice.

The piece holding all of this together is Pipecat. It handles the timing, knowing when the receptionist has stopped talking, jumping in at the right moment, and backing off gracefully if the receptionist talks over my patient. That timing is the hardest part of any voice bot, so leaning on Pipecat instead of building the audio plumbing by hand was the main design decision here. It is what makes the calls sound like two people talking.

One detail worth calling out: most Twilio voice tutorials are about answering calls. This bot does the opposite. It makes outbound calls. So the server uses Twilio to dial out, and Twilio opens a live audio connection back to the bot for the conversation.

The flow, start to finish:

```
Twilio dials the number, receptionist answers
        |
        v
receptionist speaks  ->  Deepgram (hear)  ->  GPT-4o (think)  ->  Cartesia (speak)  ->  back to Twilio
        ^                                                                                      |
        |______________________________________________________________________________________|
                              (repeats until someone hangs up)
```

## Project structure

```
pgai-voicebot/
  patient_bot/
    __init__.py
    bot.py              the Pipecat pipeline (the patient's voice loop)
    server.py           dials out via Twilio, accepts the audio websocket
  scenarios/
    __init__.py         the 10 patient personas (name, goal, fake identity)
  recordings/           call audio lands here (.wav, then .mp3)
  transcripts/          both sides of each call, timestamped (.txt)
  run_all_calls.py      places every scenario back to back
  convert_to_mp3.py     converts recordings to mp3 after the calls
  requirements.txt      Python dependencies
  README.md             this file
  ARCHITECTURE.docx     the architecture write-up
  BUG_REPORT.md         issues found while testing
  .env.example          template for the keys you need
  .gitignore            keeps .env and raw .wav out of git
```

## What you need

Accounts and keys from four places: Twilio (a funded account with a phone number that can make calls), OpenAI (funded), Deepgram, and Cartesia. Each one gives you a secret key. Those go in a file called `.env`, which stays on your machine and never gets committed.

You also need ngrok, which is a small tool that gives Twilio a way to reach the bot running on your laptop.

## Setup

Install the dependencies:

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Copy the example env file and fill in your keys:

```
copy .env.example .env
```

Open `.env` and paste in your four service keys plus your Twilio number. Use the same Twilio number for every call.

Start ngrok so Twilio can reach you. If you have a reserved ngrok domain, use it so the address stays the same between runs:

```
ngrok http --url=YOUR-DOMAIN.ngrok-free.dev 7860
```

Take the address ngrok shows (without the https in front) and put it in `.env` as `PUBLIC_HOST`.

## Running it

The bot runs across three terminals, all open at the same time.

In the first terminal, start ngrok and leave it running. Confirm its forwarding line points to localhost:7860.

```
ngrok http --url=YOUR-DOMAIN.ngrok-free.dev 7860
```

In the second terminal, start the server and leave it running. This is the window to watch during a call, both sides of the conversation print here as [AGENT] and [PATIENT] with timestamps.

```
venv\Scripts\activate
python -m patient_bot.server --serve
```

In the third terminal, place a call. For a single scenario:

```
venv\Scripts\activate
python -m patient_bot.server --scenario refill_basic
```

Or run every scenario back to back, one at a time over the same number:

```
venv\Scripts\activate
python run_all_calls.py
```

Each call saves a recording to `recordings/` and a transcript to `transcripts/`.

## The scenarios

These live in `scenarios/__init__.py`. Some are normal patient calls and some are deliberately built to trip the receptionist up. Each patient has a full fake identity (name, date of birth, phone, and so on) so it answers questions confidently, the way a real patient would.

| Scenario | What it tests |
|----------|---------------|
| schedule_basic | A plain appointment booking, does it confirm a real date and time |
| refill_basic | A medication refill, does it get the pharmacy and timing right |
| reschedule | Moving an appointment, does it cancel the old one without double booking |
| hours_insurance | Office hours, insurance, and location questions |
| weekend_trap | Asking for a Sunday slot, does it wrongly confirm a closed day |
| ambiguous_med | A vague medication request, does it make up a drug name |
| interruption | Changing your mind mid sentence, does it recover |
| multi_intent | Three requests at once, does it drop any of them |
| wrong_practice | Asking for a doctor who probably is not there |
| cancel_then_silence | Canceling, then going quiet, does it handle dead air |

To add your own, drop another entry into the SCENARIOS dictionary with a persona, a goal, and an opening line.

## After the calls

The calls save as `.wav`. To get them as mp3, run:

```
python convert_to_mp3.py
```

From there you can listen back to each recording and read the matching transcript to see how the receptionist handled the call. Anything it got wrong, a booking it never confirmed, a question it dodged, a detail it dropped, is worth noting down. `BUG_REPORT.md` is where those findings live, with the call and timestamp so you can jump straight to the moment.

## A few notes

The whole run usually costs only a few dollars in API and telephony charges. Do not commit your `.env`, it is already in `.gitignore` along with the raw wav files. And only ever call the test number, +1-805-439-8008.
