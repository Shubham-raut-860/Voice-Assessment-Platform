# Vapi Assistant Playbook

This playbook turns the Vapi assistant into a demo-ready assessment interviewer. The backend includes a repeatable provisioning script so the tuned assistant can be created or updated without hand-editing every field in the Vapi dashboard.

## Assistant Identity

Name: Riley - Voice Assessment Interviewer

Role: calm, professional AI voice assessor.

Tone:

- Warm and concise.
- No jokes during scoring-critical moments.
- Encourages the candidate without coaching them into the answer.
- Asks one question at a time.
- Uses short follow-ups when answers are vague.
- Does not reveal pass/fail or scoring thresholds during the call.

## Conversation Flow

1. Greeting and consent
   - Confirm the candidate is ready.
   - Explain that the session is recorded and analyzed for assessment purposes.
   - Tell the candidate they can ask to repeat a question.

2. Context setup
   - Briefly describe the role or assessment theme.
   - Confirm the candidate can hear clearly.

3. Core assessment
   - Ask 4-8 competency questions.
   - Mix behavioral, reasoning, communication, and role-specific questions.
   - Use one focused follow-up when the answer lacks evidence, outcome, or reasoning.

4. Calibration check
   - Ask one scenario question that requires tradeoffs.
   - Ask one concise self-reflection question.

5. Close
   - Thank the candidate.
   - Explain that the report will be generated after processing.
   - Do not reveal pass/fail in the call.

## Prompt Requirements

The source of truth for the assistant prompt is `scripts/provision_vapi_assistant.py`. It generates a tuned Riley prompt with:

- consent and readiness language
- one-question-at-a-time pacing
- evidence-seeking follow-up rules
- protected-class and secret-data guardrails
- no live pass/fail disclosure
- structured Vapi analysis prompts for backend report generation

Recommended default assessment context:

```text
Evaluate communication clarity, structured thinking, judgment, problem solving,
ownership, and ability to give evidence-backed examples.
```

## Recommended Questions

Default demo assessment:

1. Tell me about your background and the role you are preparing for.
2. Describe a challenging project or responsibility and how you handled it.
3. Give an example of a time you had to communicate a complex idea clearly.
4. Walk me through how you would solve an unfamiliar problem under time pressure.
5. Describe a mistake or setback and what changed afterward.
6. How do you decide what to prioritize when everything feels urgent?
7. Is there anything important about your skills or experience that we did not cover?

## Provision Or Update Riley

Create a new tuned assistant:

```powershell
cd "D:\Shubham\voice project\Backend"
C:\tmp\voice_backend_venv\Scripts\python.exe -B scripts\provision_vapi_assistant.py `
  --server-url "https://<public-api-host>" `
  --include-secret-header `
  --role-title "professional competency assessment" `
  --assessment-context "Evaluate communication clarity, structured thinking, judgment, problem solving, ownership, and ability to give evidence-backed examples." `
  --question-count 6
```

Update an existing Riley assistant:

```powershell
cd "D:\Shubham\voice project\Backend"
C:\tmp\voice_backend_venv\Scripts\python.exe -B scripts\provision_vapi_assistant.py `
  --server-url "https://<public-api-host>" `
  --assistant-id "<vapi-assistant-id>" `
  --include-secret-header `
  --role-title "professional competency assessment" `
  --assessment-context "Evaluate communication clarity, structured thinking, judgment, problem solving, ownership, and ability to give evidence-backed examples." `
  --question-count 6
```

Update only the conversation behavior while keeping the current Vapi dashboard server URL/header settings:

```powershell
cd "D:\Shubham\voice project\Backend"
C:\tmp\voice_backend_venv\Scripts\python.exe -B scripts\provision_vapi_assistant.py `
  --assistant-id "<vapi-assistant-id>" `
  --preserve-server-url `
  --role-title "professional competency assessment" `
  --assessment-context "Evaluate communication clarity, structured thinking, judgment, problem solving, ownership, and ability to give evidence-backed examples." `
  --question-count 6
```

Preview the payload without calling Vapi:

```powershell
C:\tmp\voice_backend_venv\Scripts\python.exe -B scripts\provision_vapi_assistant.py `
  --server-url "https://example.ngrok-free.app" `
  --dry-run
```

## Verify Riley Before A Demo

Run the assistant readiness checker against the exact public Worker/API URL Vapi will call:

```powershell
cd "D:\Shubham\voice project\Backend"
C:\tmp\voice_backend_venv\Scripts\python.exe -B scripts\verify_vapi_assistant_readiness.py `
  --assistant-id "<vapi-assistant-id>" `
  --server-url "https://<public-worker-or-api-host>"
```

The checker validates:

- assistant identity
- first and final messages
- max duration and silence timeout
- webhook URL
- `X-Vapi-Secret` header alignment with backend `.env`
- required server messages
- model and transcriber settings
- prompt guardrails
- Vapi analysis prompts

Expected result:

```text
vapi_assistant_readiness: ok
```

## Vapi Settings

Server URL:

```text
https://<public-api-host>/api/v1/webhooks/vapi
```

Required server messages:

```text
status-update
transcript
end-of-call-report
```

Recommended demo mode:

```text
webCall
```

Use phone mode only after a working phone number or SIP trunk is available in the target country.

Recommended runtime settings:

- `maxDurationSeconds`: 900 for demos, 1800 for longer production assessments.
- `silenceTimeoutSeconds`: 35.
- `responseDelaySeconds`: 0.35.
- `firstMessageMode`: `assistant-speaks-first`.
- `backgroundSound`: `off`.
- Transcriber: Deepgram `nova-3`, English.
- Model: OpenAI `gpt-4o-mini` in Vapi for the live interviewer. Azure OpenAI remains the backend report generator.

## Quality Tuning Checklist

Run at least five trial calls before a final demo:

- Candidate can interrupt naturally.
- Assistant does not speak in long paragraphs.
- Assistant does not ask multiple questions at once.
- Transcript contains enough evidence for scoring.
- End-of-call report webhook arrives.
- The backend session has `status=completed`.
- The generated report cites transcript-specific evidence.
- Resend email is delivered to the intended test recipient.

## Trial Call Scorecard

Score every rehearsal call from 1-5:

| Area | Passing Standard |
| --- | --- |
| Opening clarity | Candidate understands this is an assessment and gives consent/readiness. |
| Turn discipline | Riley asks one question at a time and avoids long monologues. |
| Evidence depth | Candidate gives concrete examples, context, actions, and outcomes. |
| Follow-up quality | Riley asks one focused follow-up when an answer is vague. |
| Transcript quality | Transcript captures both Riley and candidate with enough detail for scoring. |
| Close behavior | Riley ends without revealing pass/fail. |
| Backend chain | Session completes, transcript persists, report generates, email attempt is logged. |

Demo-ready threshold:

```text
No area below 4/5 across two consecutive live calls.
```

## Demo Acceptance Criteria

For a company demo, the assistant is good enough only if:

- The opening asks for readiness and mentions recording/analysis.
- The candidate speaks for at least 90 seconds total.
- Riley asks no more than one question per turn.
- Riley asks at least two evidence-seeking follow-ups when answers are vague.
- The transcript contains candidate examples, not only yes/no answers.
- The backend report is not inconclusive unless the candidate did not answer.
- The report's strengths and weaknesses quote or paraphrase real transcript moments.

## Review Rubric

Each trial call should be reviewed against:

- Question clarity.
- Candidate comfort.
- Transcript completeness.
- Score calibration.
- Weakness quality.
- Recommendation usefulness.
- No accidental pass/fail disclosure during the call.

If scores feel inflated, adjust the report prompt first. If transcripts lack evidence, adjust Riley's follow-up behavior.
