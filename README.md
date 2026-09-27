# Telegram Task Service Bot

This version removes the old TEST MODE concept.

It is designed for:
- Gmail address task submissions (address only; no password/OTP/recovery data)
- Admin-created Gmail task types and rewards
- Admin-created Buy Services
- User balance
- bKash/Nagad payment settings
- Deposit/withdrawal review
- User/order/submission statistics
- Admin user list with Telegram IDs
- Broadcast
- SQLite database
- Render Worker deployment

## Important
Do not collect or store passwords, OTPs, recovery codes, or other account secrets.

## Deploy
1. Replace **all** files in your repo with the files in this package (`bot.py`, `database.py`, `requirements.txt`, `runtime.txt`, `render.yaml`, `.env.example`, `.gitignore`).
2. Keep your Render environment variables:
   - BOT_TOKEN
   - ADMIN_ID
   - CHANNEL_USERNAME
   - SUPPORT_USERNAME
3. Commit/push to GitHub.
4. Redeploy on Render (Manual Deploy → Deploy latest commit, or wait for auto-deploy).
5. Do not use `asyncio.run()` or `updater.start_polling()` separately. This project uses `app.run_polling()`.

The database file `bot.db` is created automatically on first start.

### Fixes included in this package
- `requirements.txt` now pins `python-telegram-bot==21.11` (the previous `21.4` pin crashed on
  newer Python with `RuntimeError: There is no current event loop in thread 'MainThread'`).
- `runtime.txt` pins Render's Python to `3.11.9`, a version this PTB release is well-tested on.
- `bot.py` now starts a tiny built-in HTTP server on `$PORT` in a background thread. This means
  the bot works correctly **whether your Render service is set to "Web Service" or "Background
  Worker"** — if `PORT` isn't set (Worker type), this step is simply skipped.
- Recommended: set the service type to **Background Worker** on Render, since this bot only does
  Telegram polling and never needs to receive HTTP traffic. `render.yaml` is already configured
  this way for Blueprint deploys.
