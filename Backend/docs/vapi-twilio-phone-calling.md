# Vapi + Twilio Phone Calling

This project supports two call transports:

- `web`: candidate opens the browser assessment and uses the Vapi Web SDK.
- `phone`: admin/assessor enters the candidate phone number, and the backend asks Vapi to place an outbound phone call.

The phone flow still uses the same backend pipeline:

```text
Admin starts phone call
-> FastAPI POST /api/v1/sessions/{session_id}/start-call
-> Vapi outboundPhoneCall
-> candidate answers phone
-> Vapi sends webhooks
-> transcript is stored
-> Azure OpenAI report is generated
-> Resend email is sent
```

## Vapi Dashboard Setup

1. In Vapi, connect a phone number.
   - Use a Vapi-provisioned number if available for your region.
   - Or connect Twilio from Vapi's phone-number / BYO telephony setup.
2. Assign or allow the Riley assessment assistant for that number.
3. Copy the Vapi phone-number object ID. This is not the visible phone number; it is the Vapi ID for that number/trunk.
4. Keep the assistant server URL pointed at your public backend or Cloudflare Worker webhook:

```text
https://<your-public-api-domain>/api/v1/webhooks/vapi
```

For local demos through ngrok:

```text
https://<your-ngrok-domain>/api/v1/webhooks/vapi
```

## Backend Environment

Use web mode until the Vapi/Twilio phone number is ready:

```env
VAPI_CALL_MODE=web
VAPI_PHONE_NUMBER_ID=
```

Switch to phone mode when the Vapi phone-number ID is available:

```env
VAPI_CALL_MODE=phone
VAPI_PHONE_NUMBER_ID=replace-with-vapi-phone-number-id
```

The candidate phone number must be entered in E.164 format:

```text
+919766017525
+15551234567
```

## Frontend Flow

1. Sign in as admin or assessor.
2. Open `Candidates`.
3. Assign an assessment to the candidate if needed.
4. On a scheduled row, enter the candidate phone number in E.164 format.
5. Click `Call phone`.
6. The row will refresh with the Vapi call ID after Vapi accepts the outbound call.

## International Calling Note

Free Vapi-provisioned numbers may reject international outbound calls with:

```text
Couldn't start call. Free Vapi numbers do not support international calls.
```

For a demo that calls an Indian candidate number such as `+91...`, use one of these:

- a Twilio-connected number imported into Vapi,
- a paid/international-capable Vapi number,
- or a candidate number in a region supported by the current Vapi number.

After connecting Twilio in Vapi, copy the new Vapi phone-number object ID and replace `VAPI_PHONE_NUMBER_ID`.

If the backend is still in web mode, the API returns:

```json
{"detail":"phone_call_mode_not_enabled"}
```

That means the frontend is working, but the backend has not been switched to phone mode.

## Safety Rules

- The backend rejects duplicate call starts when a session already has a Vapi call ID.
- Completed sessions cannot be started again.
- Phone numbers are not stored on the candidate profile in this alpha/beta build; they are submitted only when starting the phone call.
- Web calling remains available from the candidate assessment page.
