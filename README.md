Telegram Task Service Bot
This version removes the old TEST MODE concept.
It is designed for:
Gmail address task submissions (address only; no password/OTP/recovery data)
Admin-created Gmail task types and rewards
Admin-created Buy Services
User balance
bKash/Nagad payment settings
Deposit/withdrawal review
User/order/submission statistics
Admin user list with Telegram IDs
Broadcast
SQLite database
Render Worker deployment
Important
Do not collect or store passwords, OTPs, recovery codes, or other account secrets.
Deploy
Replace your old bot.py, database.py, requirements.txt, render.yaml, .env.example with these files.
Keep your Render environment variables:
BOT_TOKEN
ADMIN_ID
CHANNEL_USERNAME
SUPPORT_USERNAME
Commit/push to GitHub.
Redeploy the Render Worker.
Do not use asyncio.run() or updater.start_polling() separately. This project uses app.run_polling().
The database file bot.db is created automatically on first start.
