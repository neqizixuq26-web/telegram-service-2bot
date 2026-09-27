# Telegram Test Service Bot

Python Telegram bot using python-telegram-bot 21.4 + SQLite.

## Important
This project is intentionally a TEST/learning implementation.
It does not collect or store real Gmail passwords or recovery codes.
Only `.test` dummy inventory is accepted by Gmail Sell.

## 1. Install

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Termux:
source .venv/bin/activate

pip install -r requirements.txt
```

## 2. Configure

Copy `.env.example` to `.env` and set:

```env
BOT_TOKEN=...
ADMIN_ID=...
CHANNEL_USERNAME=@your_channel
SUPPORT_USERNAME=your_support_username
```

The bot must be an administrator of the channel so Telegram can reliably answer membership checks.

## 3. Run

```bash
python bot.py
```

SQLite creates `bot.db` automatically.

## 4. Test flow

1. User joins the channel.
2. `/start`
3. Admin adds test stock from Admin Panel.
4. User submits:
   `demo@example.test | TEST_ITEM`
5. Admin approves.
6. User receives the configured unit price in balance.
7. User can deposit, withdraw, or buy dummy test items.

## 5. Render

Create a Render Worker and use:

Build:
`pip install -r requirements.txt`

Start:
`python bot.py`

Set the four environment variables in Render.

### SQLite on Render
Render worker filesystems are not a permanent database solution. For learning/testing this SQLite setup is fine, but for a serious production deployment use PostgreSQL or another persistent database.
