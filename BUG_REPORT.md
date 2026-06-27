# Bug Report - Pretty Good AI Receptionist (Pivot Point Orthopedics test line)

Tested by calling +1-805-439-8008 with an automated patient bot across ten
scenarios. Each entry points to the transcript and timestamp so you can jump
straight to the moment in the recording.

I've ordered these by how much they'd hurt a real patient, not by how many
times they happened. A few of these showed up on almost every call, which to
me makes them the most important ones to look at.

---

## High severity

### 1. The agent collects everything, then can't actually do anything
Every task-based call ended the same way: the agent gathered the patient's
name, date of birth, and phone number, confirmed it all, and then said some
version of "I can't proceed further right now, but I'll have our clinic support
team follow up." Not one appointment was booked, rescheduled, cancelled, or
refilled across ten calls.

- Where: `refill_basic` at 01:51, `schedule_basic` at 02:14, `reschedule` at
  01:56, `cancel_then_silence` at 02:08, `multi_intent` at 02:10.
- Why it matters: this is the core job of the line. A patient spends two
  minutes handing over all their details and leaves with nothing done and no
  timeframe. If the live product behaves like this, every call is a dead end.
- Note: this is a test line, so it's possible task completion is intentionally
  stubbed. Worth confirming, but from the patient's side it reads as a total
  failure to complete the request.

### 2. The "transfer to a representative" goes nowhere and hangs up mid-sentence
After punting the task, the agent says it's connecting you to the patient
support team, then the transfer immediately lands on "Hello. You've reached the
Pretty Good AI test line. Goodbye." and the call ends, often while the patient
is still talking.

- Where: `refill_basic` at 02:02, `reschedule` at 02:09, `multi_intent` at
  02:22, `interruption` at 02:08, `cancel_then_silence` at 02:17.
- Why it matters: the patient is promised a human and gets a dial tone instead.
  In `cancel_then_silence` the patient was still asking "can you confirm my
  appointment is cancelled?" as the line dropped. Abrupt termination during an
  open question is jarring and leaves the request unresolved.

### 3. The agent confirms a cancellation it never actually performed
In the cancel scenario, very early on the agent's confirmation flow produced
"We have successfully canceled your appointment for tomorrow, Ms. Foster" —
but later in the same call it said "I can't cancel the appointment right now"
and transferred her. So it claimed success, then contradicted itself.

- Where: `cancel_then_silence` at 00:32 versus 02:08.
- Why it matters: telling a patient their appointment is cancelled when it
  isn't is dangerous. They'd stop expecting the visit, miss it, and the slot
  stays booked. A false confirmation is worse than a plain "I can't do that."

---

## Medium severity

### 4. The agent gets stuck in a phone-number loop and can't move on
Several calls had the agent ask for the phone number, hear it correctly, and
then immediately ask for it again, over and over. In the cancel call the
patient gave the same number cleanly seven times before the agent accepted it.

- Where: `cancel_then_silence` 01:06–01:48 (asked ~7 times), `ambiguous_med`
  01:02–01:38 (asked ~6 times), `schedule_basic` 01:16–01:57.
- Why it matters: it's the single biggest reason the calls dragged toward the
  two-minute mark without resolving anything. A real patient would give up.

### 5. The agent never addresses the actual medication question
In both refill calls the patient repeatedly asked "when will it be ready?" and
"which pharmacy?" and the agent never answered either, it only collected
identity details and transferred. In `ambiguous_med`, the patient deliberately
couldn't name the drug ("the white one, my heart pill"); the agent neither
asked clarifying questions nor flagged that it couldn't safely refill an
unidentified medication. It just moved on to the transfer.

- Where: `refill_basic` 01:02 and 02:02, `ambiguous_med` 01:43.
- Why it matters: for the ambiguous case especially, safe handling would be to
  insist on identifying the medication. Silently ignoring it is a safety gap.

### 6. The agent forgets it's an orthopedics clinic and over-promises on insurance
In the hours/insurance call the patient asked if they take Aetna PPO. The agent
answered "Pivot Point Orthopaedics accepts most insurance plans, including
Aetna PPO." Stating it accepts "most plans" is a confident claim the agent
likely can't actually verify, the kind of thing that should be checked, not
asserted.

- Where: `hours_insurance` at 00:36.
- Why it matters: an over-broad insurance promise can mislead a patient into a
  visit their plan doesn't cover.

### 7. Multi-request calls collapse to one generic transfer
In `multi_intent` the patient clearly listed three things up front (book an
appointment, refill metformin, ask about a bill). The agent never tracked them
as separate items; it spent the whole call on identity verification and then
gave the same generic "support team will follow up" with no acknowledgement of
the three distinct requests.

- Where: `multi_intent` at 00:11 (requests stated) and 02:10 (generic punt).
- Why it matters: dropping intents means the patient has to call back and start
  over for each one.

---

## Low severity

### 8. Garbled greeting and a wrong phone number read back
The agent's opening line is consistently clipped ("Corded for quality and
training purposes" instead of "This call may be recorded..."). More notably, in
`refill_basic` at 01:13 the agent read back a phone number the patient never
gave ("four seven two, two three eight, seven eight eight three"), seemingly a
leftover from a previous caller's record tied to the same number.

- Where: greeting clip on nearly every call; phantom number at
  `refill_basic` 01:13.
- Why it matters: minor, but the phantom number suggests records may be bleeding
  between callers on the same line.

### 9. Name mismatch from a stale profile
The agent greeted nearly every caller as "Robert" regardless of who was calling,
because the test number had an existing "Robert" profile. The patients corrected
it and the agent did update (e.g. "I have your name as Rosa Chen"), so it
recovered, but the wrong-name greeting is a rough first impression.

- Where: the "Am I speaking with Robert?" line on most calls.
- Why it matters: low impact since it self-corrects, but worth noting the
  profile lookup keys on the phone number in a way that surfaces the wrong name.

---

## What worked well

Credit where due, a few things were handled correctly:

- The `wrong_practice` call was the best. Asked about a Dr. Hammond who doesn't
  work there, the agent correctly said he isn't a listed provider and offered
  the real provider list, no hallucinated confirmation. That's the right
  behavior. (`wrong_practice` at 00:26.)
- The `weekend_trap` was handled correctly too: the agent did NOT book a Sunday
  slot, it stated the clinic is open Monday–Friday and offered a weekday
  instead. (`weekend_trap` at 02:21.) This was the specific failure I was
  hunting for, and the agent passed.
- The hours and location answers were direct and correct.
