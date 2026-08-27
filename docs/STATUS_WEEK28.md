# Week 28 status report — WhatsApp Cloud API wired into the delivery channel

Full context: `sms_delivery.py`'s own docstring (updated this week with the same detail below).

## Step 1 — real constraint check, done before building anything

Checked live via the Graph API (`GET /{WABA_ID}/message_templates`), not assumed: only
**`hello_world`** (Meta's default) plus its standard `jaspers_market_*` demo samples were
`APPROVED` on this real account. No custom hazard-alert template existed. `hello_world` itself
was read directly (not assumed static) — confirmed **zero parameters**: its header/body/footer
are fixed text with no `{{n}}` placeholders anywhere.

## Step 2 — functional end-to-end send, done first with hello_world

Since only the generic default template was available, proved the whole pipeline
(trigger → formatted record → real WhatsApp delivery) with it first, exactly as scoped — content
is Meta's placeholder text, not yet the real hazard-alert wording.

## Step 3 — real custom template submitted

Submitted `hazard_alert` (category `UTILITY`, positional placeholders for hazard/district/
confidence) via `POST /{WABA_ID}/message_templates`. **Real submission id: `1732666884606981`,
status: `PENDING`.** Approval is not instant and is out of this project's control — not waited
on before calling Step 2 done, per direction.

## Steps 4-6 — built

- `sms_delivery.py` swapped from Twilio (never had real credentials configured the whole
  project — Week 15 confirmed signup never resolved) to the real WhatsApp Cloud API, same
  env-var STUB-gating discipline (`WHATSAPP_PHONE_NUMBER_ID`/`WHATSAPP_ACCESS_TOKEN`/
  `WHATSAPP_TEST_TO_NUMBER` all required or it stays in `STUB_NO_CREDENTIALS`). Twilio's client
  path kept intact, unused, not deleted speculatively.
- **Template-aware formatting**: checks the *live* approval status of `hazard_alert` at runtime
  (not assumed from the submission payload) — sends the real hazard-specific bilingual content
  once approved, automatically falls back to the zero-parameter `hello_world` until then, and
  every delivery record states plainly which template was actually used and why.
- **Delivery-status scope, deliberately limited**: records the real message id the API returns
  on acceptance. Full delivered/read receipts need a webhook with a public callback URL — this
  project's real infrastructure (a personal Windows machine, the same constraint Track H's live
  loop already carries) doesn't have one, and building one isn't cheap — so this module reports
  "API accepted the send," not a confirmed-delivered/read status, and says so explicitly in
  every record rather than implying more than was verified.
- Credentials stored in a local `.env` (confirmed gitignored via `git check-ignore -v`, not
  committed).

## Step 7 — real device test

Could not discover WhatsApp's verified test-recipient numbers via any API (Meta only exposes
this list through WhatsApp Manager's UI) — asked you directly rather than guessing a number.
You provided a real verified recipient (+923335133592). Sent one real message:

- **Mode**: `LIVE (real WhatsApp Cloud API)`
- **Template used**: `hello_world` (real, only-approved template)
- **Real message id**: `wamid.HBgMOTIzMzM1MTMzNTkyFQIAERgSOTgwNDlFRjMzMUUwODgzOUNEAA==`
- **API response**: `message_status: "accepted"`
- **Real device confirmation**: you confirmed the message arrived on the real device — not just
  that the API call returned success.

## Real current status

WhatsApp is now a genuinely working delivery channel: `STUB_NO_CREDENTIALS` → `SENT_REAL_WHATSAPP_MESSAGE`,
confirmed to reach a real device. Content is currently generic (`hello_world`) until
`hazard_alert` clears Meta's approval — check `GET /{WABA_ID}/message_templates?name=hazard_alert`
for its real current status; `sms_delivery.py` will pick it up automatically the next time it
runs, no code change needed.
