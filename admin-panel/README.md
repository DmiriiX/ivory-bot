# IVORY-ART Telegram Admin + Mini App

A private Telegram control panel for the **existing** painting and facts publishers.

## Features
- Telegram commands `/start`, `/menu`, `/status`.
- Responsive Mini App: painting photos, previews, full queue, history, status, last-publication time.
- Edit captions; choose next post; exclude/restore entries; pause/resume schedules.
- Trigger a real GitHub Actions post (with a confirmation dialog). Delivery is verified by subsequent state, not the dispatch response.
- Existing post history is read from `state.json` (`used_ids` and historic `used_indices`), avoiding repeat posts.
- Server verifies Telegram Mini App HMAC signature and restricts every request to allowlisted Telegram IDs.
- No passwords or bot tokens in GitHub files or front-end code.

## Deployment
1. Create a **new Telegram bot** using @BotFather; copy its token privately to your host.
2. Deploy `admin-panel/` to an always-on HTTPS Python/Docker host with the values from `.env.example`.
3. Create a **fine-grained GitHub PAT** for the two repos with Contents read/write and Actions write permissions. Put it only in server-side `GITHUB_TOKEN`. Never put it in GitHub commits or web UI.
4. Get your numeric Telegram user ID (e.g. from a trusted `/start` update or a Telegram ID bot) and set `ADMIN_TELEGRAM_IDS`. Only allow your own Telegram account.
5. Set a long random `TELEGRAM_WEBHOOK_SECRET` (letters, digits, underscore, hyphen; length 1..256).
6. Set `PUBLIC_BASE_URL` to your real HTTPS URL, **without** a final slash.
7. Set Telegram webhook with:
   `curl -X POST https://api.telegram.org/bot<TOKEN>/setWebhook -d url=https://YOURDOMAIN/telegram/webhook -d secret_token=YOUR_SECRET`
   **Do not paste tokens into chats, commits or screenshots.**
8. In BotFather: **Bot Settings → Menu Button → Configure menu button**, set your `PUBLIC_BASE_URL` for Mini App.
9. Send `/start` to the new bot in a private chat and open the panel.

## Data
Current repo files remain canonical:
- `posts.json` catalog and captions
- `state.json` publication history and partial-send status
- `control.json` pause, skip, selected next post

The Mini App only reads/writes through its server. It cannot access tokens. The existing publishing workflows continue independently. GitHub Actions normally runs on schedule; manual posting uses `workflow_dispatch` and can take time. Partial/uncertain send state prevents automatic duplicate delivery.

## Security / important notes
- Host must use HTTPS; Telegram Mini App initData expires after 1 hour.
- Restrict GitHub token to only the two project repositories. Never share webhook secrets.
- Only trusted admin IDs are allowed to see or mutate private data.
- Never use GitHub Pages for this backend: it needs a running server to securely verify Telegram signatures.
- Photo URLs are loaded from the painting catalog. The browser is not allowed to execute post HTML.
- For actual launch, perform a private test with test channels before scheduling any real sends.
- A GitHub Actions run marked "success" does not prove that Telegram and MAX both received the message. Inspect per-platform delivery state.
- Avoid editing a post while a partial publication of that post is pending.

## Development
`pip install -r requirements.txt`
`uvicorn app:app --reload`
`python -m compileall -q app.py`

There are no background jobs in the Mini App host: GitHub Actions performs publishing.


## Instagram via Buffer
- Render keeps `BUFFER_API_KEY` privately in Environment. Never copy it to GitHub Actions.
- `/api/integrations/instagram` is available only after Telegram Mini App signature verification.
- The connected Buffer channel is resolved by name `ivoryartgallery`; the backend refuses ambiguous or missing channels.
- `.github/workflows/instagram-sync.yml` runs hourly (Moscow daytime), obtains a short-lived **GitHub OIDC** token and calls the Render backend securely without any static credential.
- The backend checks GitHub's token signature, issuer, audience, repository ID, workflow identity and main branch.
- Instagram uses `mode: shareNow` and `schedulingType: automatic`, with the artwork's public HTTPS image.
- `instagram_state.json` has a baseline of the four artworks already published before Instagram was integrated. It tracks separate Instagram acceptance, delivery, and ambiguous results without affecting Telegram/MAX state.
- Initially `instagram_state.json.enabled` is `false`. Set it to `true` **only after** verifying that the Buffer API key and Instagram channel are valid. This intentionally prevents a live post during installation.
- A successful Buffer `createPost` only means Buffer accepted the post; the job subsequently checks `post.status` to confirm it was sent.
- Any network ambiguity is saved as `uncertain` and blocks duplicate resubmission until manually investigated in Buffer.
- Buffer has plan and Instagram posting limits; the synchronization does not override them.
