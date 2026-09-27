
import asyncio
import logging
import os
import re
import threading
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters
)

import database as db

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").strip()
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "BD71NPC").strip()

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("task-bot")

# Conversation states
SELL_TASK, SELL_EMAIL = range(2)
BUY_SERVICE, BUY_CONFIRM = range(2, 4)
DEPOSIT_AMOUNT, DEPOSIT_DETAILS = range(4, 6)
WITHDRAW_AMOUNT, WITHDRAW_DETAILS = range(6, 8)
ADMIN_PRICE, ADMIN_BKASH = range(8, 10)
ADMIN_ADD_SELL_TITLE, ADMIN_ADD_SELL_PRICE, ADMIN_ADD_SELL_DESC = range(11, 14)
ADMIN_ADD_BUY_TITLE, ADMIN_ADD_BUY_PRICE, ADMIN_ADD_BUY_DESC = range(14, 17)
ADMIN_BROADCAST = 17


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def money(v) -> str:
    return f"{float(v):.2f}".rstrip("0").rstrip(".")


# ---------- Persistent Reply Keyboard (main menu) ----------

BTN_SELL = "📧 Gmail Sell"
BTN_BUY = "🛒 Gmail Buy "
BTN_DEPOSIT = "💰 Deposit"
BTN_WITHDRAW = "💸 Withdraw"
BTN_BALANCE = "💳 Balance"
BTN_ORDERS = "📦 My Orders"
BTN_HELP = "ℹ️ Help"
BTN_SUPPORT = "🎧 Support"
BTN_ADMIN = "⚙️ Admin Panel"
BTN_HOME = "🏠 Home"


def main_menu(user_id: int):
    """Persistent bottom keyboard shown after /start, 'Home', and 'Back'."""
    rows = [
        [BTN_SELL, BTN_BUY],
        [BTN_DEPOSIT, BTN_WITHDRAW],
        [BTN_BALANCE, BTN_ORDERS],
        [BTN_HELP, BTN_SUPPORT],
    ]
    if is_admin(user_id):
        rows.append([BTN_ADMIN])
    rows.append([BTN_HOME])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def get_uid(update: Update) -> int:
    """User id whether the update came from a button tap or a typed message."""
    q = update.callback_query
    return q.from_user.id if q else update.effective_user.id


async def ack(update: Update):
    """Answer the callback query if this update came from an inline button tap."""
    if update.callback_query:
        await update.callback_query.answer()


async def send_screen(update: Update, text: str, reply_markup=None, parse_mode=None):
    """Show a screen (with an INLINE keyboard, if any) whether triggered by an
    inline button tap or by a persistent reply-keyboard text message.
    Never pass a ReplyKeyboardMarkup here — edit_message_text can't carry one."""
    q = update.callback_query
    if q:
        await q.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = "🏠 মূল মেনু"):
    """Send the persistent main-menu keyboard as a fresh message. Used after an
    edit_message_text screen, since a ReplyKeyboardMarkup can't attach to an edit."""
    uid = get_uid(update)
    await context.bot.send_message(uid, text, reply_markup=main_menu(uid))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username or "", user.first_name or "")
    if CHANNEL_USERNAME:
        member = False
        try:
            chat = await context.bot.get_chat_member(CHANNEL_USERNAME, user.id)
            member = chat.status in ("member", "administrator", "creator")
        except Exception:
            member = False
        if not member:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")],
                [InlineKeyboardButton("✅ Verify", callback_data="verify_join")],
            ])
            await update.message.reply_text("বট ব্যবহার করতে আগে চ্যানেলে Join করুন।", reply_markup=kb)
            return
    await update.message.reply_text(
        "👋 স্বাগতম!\n\nনিচের মেনু থেকে একটি অপশন নির্বাচন করুন।",
        reply_markup=main_menu(user.id),
    )


async def verify_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = q.from_user
    if not CHANNEL_USERNAME:
        await q.edit_message_text("✅ Verification disabled.")
        return
    try:
        chat = await context.bot.get_chat_member(CHANNEL_USERNAME, user.id)
        if chat.status in ("member", "administrator", "creator"):
            await q.edit_message_text("✅ Verification successful.")
            await context.bot.send_message(user.id, "মূল মেনু:", reply_markup=main_menu(user.id))
        else:
            await q.answer("আগে Channel Join করুন।", show_alert=True)
    except Exception:
        await q.answer("Verification করা যাচ্ছে না। Channel username/permission চেক করুন।", show_alert=True)


# ---------- User: Gmail/address task ----------

async def sell_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ack(update)
    tasks = db.list_sell_tasks(active_only=True)
    if not tasks:
        await send_screen(update, "📧 বর্তমানে কোনো Gmail Task চালু নেই।")
        return ConversationHandler.END
    buttons = []
    for t in tasks:
        buttons.append([InlineKeyboardButton(
            f"{t['title']} — ৳{money(t['price'])}",
            callback_data=f"sell_task:{t['id']}"
        )])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="back")])
    await send_screen(
        update,
        "📧 Gmail Task\n\nএকটি Task নির্বাচন করুন:",
        InlineKeyboardMarkup(buttons),
    )
    return SELL_TASK


async def sell_task_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    task_id = int(q.data.split(":")[1])
    task = db.get_sell_task(task_id)
    if not task or not task["active"]:
        await q.edit_message_text("❌ এই Task আর চালু নেই।")
        return ConversationHandler.END
    context.user_data["sell_task_id"] = task_id
    await q.edit_message_text(
        f"📧 {task['title']}\n"
        f"💵 Reward: ৳{money(task['price'])}\n"
        f"📝 {task['description'] or 'কোনো অতিরিক্ত নির্দেশনা নেই।'}\n\n"
        "শুধু আপনার Gmail address পাঠান।\n"
        "⚠️ Password, এটা  botpass123@4 সেট করুন ।\n\n"
        "উদাহরণ: example@gmail.com"
    )
    return SELL_EMAIL


async def sell_email_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    if not re.fullmatch(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", email):
        await update.message.reply_text("❌ সঠিক Gmail address দিন। উদাহরণ: example@gmail.com")
        return SELL_EMAIL
    if not email.lower().endswith("@gmail.com"):
        await update.message.reply_text("❌ শুধু @gmail.com address দিন।")
        return SELL_EMAIL

    task_id = context.user_data.get("sell_task_id")
    task = db.get_sell_task(task_id) if task_id else None
    if not task:
        await update.message.reply_text("❌ Task পাওয়া যায়নি। আবার চেষ্টা করুন।")
        return ConversationHandler.END

    sub_id = db.create_sell_submission(update.effective_user.id, task_id, email)
    await update.message.reply_text(
        f"✅ Submission #{sub_id} নেওয়া হয়েছে।\n"
        "Admin review করার পর Task reward আপনার balance-এ যোগ হবে।",
        reply_markup=main_menu(update.effective_user.id),
    )
    await notify_admin(
        context,
        f"📧 নতুন Gmail Task Submission #{sub_id}\n\n"
        f"👤 User ID: {update.effective_user.id}\n"
        f"👤 Username: @{update.effective_user.username or 'N/A'}\n"
        f"📌 Task: {task['title']}\n"
        f"💵 Reward: ৳{money(task['price'])}\n"
        f"📧 Gmail: {email}",
        [
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_sell:{sub_id}")],
            [InlineKeyboardButton("❌ Reject", callback_data=f"reject_sell:{sub_id}")],
        ],
    )
    context.user_data.pop("sell_task_id", None)
    return ConversationHandler.END


# ---------- User: Buy services (no credential exchange) ----------

async def buy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ack(update)
    services = db.list_buy_services(active_only=True)
    if not services:
        await send_screen(update, "🛒 বর্তমানে কোনো Buy Service চালু নেই।")
        return ConversationHandler.END
    buttons = []
    for s in services:
        buttons.append([InlineKeyboardButton(
            f"{s['title']} — ৳{money(s['price'])}",
            callback_data=f"buy_service:{s['id']}"
        )])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="back")])
    await send_screen(update, "🛒 Gmail Buy নির্বাচন করুন:", InlineKeyboardMarkup(buttons))
    return BUY_SERSERVICEasync def buy_service_selselecteddate: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    service_id = int(q.data.split(":")[1])
    service = db.get_buy_service(service_id)
    if not service or not service["active"]:
        await q.edit_message_text("❌ Service আর available নেই।")
        return ConversationHandler.END

    context.user_data["buy_service_id"] = service_id
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm Order", callback_data="buy_confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="buy_cancel")],
    ])
    await q.edit_message_text(
        f"🛒 {service['title']}\n"
        f"💵 Price: ৳{money(service['price'])}\n"
        f"📝 {service['description'] or 'কোনো অতিরিক্ত তথ্য নেই।'}\n\n"
        "Confirm করলে আপনার balance থেকে টাকা কাটা হবে এবং Admin-এর কাছে order যাবে।",
        reply_markup=kb,
    )
    return BUY_CONFIRM


async def buy_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    service_id = context.user_data.get("buy_service_id")
    service = db.get_buy_service(service_id) if service_id else None
    if not service:
        await q.edit_message_text("❌ Service পাওয়া যায়নি।")
        return ConversationHandler.END

    ok, result = db.create_buy_order(update.effective_user.id, service_id)
    if not ok:
        await q.edit_message_text(f"❌ {result}")
        return ConversationHandler.END

    order_id = result
    await q.edit_message_text(
        f"✅ Order #{order_id} তৈরি হয়েছে।\n"
        "Admin আপনার order process করবে।"
    )
    await show_main_menu(update, context)
    await notify_admin(
        context,
        f"🛒 নতুন Buy Order #{order_id}\n\n"
        f"👤 User ID: {update.effective_user.id}\n"
        f"👤 Username: @{update.effective_user.username or 'N/A'}\n"
        f"📦 Service: {service['title']}\n"
        f"💵 Amount: ৳{money(service['price'])}",
        [
            [InlineKeyboardButton("✅ Complete", callback_data=f"complete_order:{order_id}")],
            [InlineKeyboardButton("❌ Reject + Refund", callback_data=f"reject_order:{order_id}")],
        ],
    )
    context.user_data.pop("buy_service_id", None)
    return ConversationHandler.END


async def buy_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data.pop("buy_service_id", None)
    await q.edit_message_text("❌ Order বাতিল করা হয়েছে।")
    await show_main_menu(update, context)
    return ConversationHandler.END


# ---------- Deposit / Withdraw ----------

async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ack(update)
    pay = db.get_payment_info()
    await send_screen(
        update,
        "💰 Deposit\n\n"
        f"bKash: {pay['bkash'] or 'Not set'}\n\n"
        "প্রথমে কত টাকা Deposit করবেন লিখুন:"
    )
    return DEPOSIT_AMOUNT


async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = Decimal(update.message.text.strip())
        if amount <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await update.message.reply_text("❌ সঠিক amount দিন।")
        return DEPOSIT_AMOUNT
    context.user_data["deposit_amount"] = float(amount)
    await update.message.reply_text("🧾 Payment transaction ID / reference পাঠান:")
    return DEPOSIT_DETAILS


async def deposit_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = context.user_data.get("deposit_amount")
    details = update.message.text.strip()
    dep_id = db.create_deposit(update.effective_user.id, amount, details)
    await update.message.reply_text(
        f"✅ Deposit request #{dep_id} পাঠানো হয়েছে। Admin approve করলে balance যোগ হবে।",
        reply_markup=main_menu(update.effective_user.id),
    )
    await notify_admin(
        context,
        f"💰 Deposit Request #{dep_id}\n\n"
        f"👤 User ID: {update.effective_user.id}\n"
        f"💵 Amount: ৳{money(amount)}\n"
        f"🧾 Reference: {details}",
        [
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_dep:{dep_id}")],
            [InlineKeyboardButton("❌ Reject", callback_data=f"reject_dep:{dep_id}")],
        ],
    )
    context.user_data.pop("deposit_amount", None)
    return ConversationHandler.END


async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ack(update)
    bal = db.get_balance(get_uid(update))
    await send_screen(update, f"💸 Withdraw\n\nCurrent balance: ৳{money(bal)}\n\nAmount লিখুন:")
    return WITHDRAW_AMOUNT


async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = Decimal(update.message.text.strip())
        if amount <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await update.message.reply_text("❌ সঠিক amount দিন।")
        return WITHDRAW_AMOUNT
    bal = db.get_balance(update.effective_user.id)
    if float(amount) > bal:
        await update.message.reply_text("❌ পর্যাপ্ত balance নেই।")
        return WITHDRAW_AMOUNT
    context.user_data["withdraw_amount"] = float(amount)
    await update.message.reply_text("📱 বিকাশ নম্বর লিখুন:")
    return WITHDRAW_DETAILS


async def withdraw_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = context.user_data.get("withdraw_amount")
    details = update.message.text.strip()
    wid = db.create_withdrawal(update.effective_user.id, amount, details)
    if not wid:
        await update.message.reply_text("❌ Balance পরিবর্তন করা যায়নি। আবার চেষ্টা করুন।")
        return ConversationHandler.END
    await update.message.reply_text(
        f"✅ Withdraw request #{wid} পাঠানো হয়েছে। Admin review করবে।",
        reply_markup=main_menu(update.effective_user.id),
    )
    await notify_admin(
        context,
        f"💸 Withdraw Request #{wid}\n\n"
        f"👤 User ID: {update.effective_user.id}\n"
        f"💵 Amount: ৳{money(amount)}\n"
        f"📱 Payment info: {details}",
        [
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_wd:{wid}")],
            [InlineKeyboardButton("❌ Reject + Refund", callback_data=f"reject_wd:{wid}")],
        ],
    )
    context.user_data.pop("withdraw_amount", None)
    return ConversationHandler.END


# ---------- Admin ----------

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q:
        await q.answer()
    uid = get_uid(update)
    if not is_admin(uid):
        if q:
            await q.answer("Admin only.", show_alert=True)
        else:
            await update.message.reply_text("Admin only.")
        return
    stats = db.stats()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
         InlineKeyboardButton("👥 Users", callback_data="admin_users")],
        [InlineKeyboardButton("📧 Gmail Tasks", callback_data="admin_sell_tasks"),
         InlineKeyboardButton("🛒 Buy Services", callback_data="admin_buy_services")],
        [InlineKeyboardButton("💳 Payment Settings", callback_data="admin_payment")],
        [InlineKeyboardButton("💰 Deposits", callback_data="admin_deposits"),
         InlineKeyboardButton("💸 Withdrawals", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("📋 Gmail Submissions", callback_data="admin_sells"),
         InlineKeyboardButton("📦 Orders", callback_data="admin_orders")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
    ])
    await send_screen(
        update,
        f"⚙️ Admin Panel\n\n"
        f"👥 Users: {stats['users']}\n"
        f"💰 Total balance: ৳{money(stats['balance'])}\n"
        f"📧 Pending submissions: {stats['pending_sells']}\n"
        f"📦 Pending orders: {stats['pending_orders']}",
        kb,
    )


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    s = db.stats()
    await q.edit_message_text(
        f"📊 Statistics\n\n"
        f"👥 Users: {s['users']}\n"
        f"💰 Total balance: ৳{money(s['balance'])}\n"
        f"📧 Pending Gmail submissions: {s['pending_sells']}\n"
        f"📦 Pending orders: {s['pending_orders']}\n"
        f"💳 Pending deposits: {s['pending_deposits']}\n"
        f"💸 Pending withdrawals: {s['pending_withdrawals']}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin")]]),
    )


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    users = db.list_users(limit=30)
    if not users:
        text = "👥 কোনো user নেই।"
    else:
        lines = ["👥 Recent Users:\n"]
        for u in users:
            lines.append(
                f"• ID: `{u['user_id']}` | @{u['username'] or 'N/A'} | "
                f"{u['first_name'] or 'N/A'} | ৳{money(u['balance'])}"
            )
        text = "\n".join(lines)
    await q.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin")]])
    )


async def admin_sell_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tasks = db.list_sell_tasks(active_only=False)
    lines = ["📧 Gmail Tasks"]
    for t in tasks:
        lines.append(f"\n#{t['id']} — {t['title']} — ৳{money(t['price'])} — {'ON' if t['active'] else 'OFF'}")
    if not tasks:
        lines.append("\nNo tasks.")
    kb = [[InlineKeyboardButton("➕ Add Gmail Task", callback_data="add_sell_task")]]
    for t in tasks:
        kb.append([InlineKeyboardButton(
            f"{'🔴' if t['active'] else '🟢'} Toggle #{t['id']}",
            callback_data=f"toggle_sell:{t['id']}"
        )])
    kb.append([InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin")])
    await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))


async def admin_buy_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    services = db.list_buy_services(active_only=False)
    lines = ["🛒 Buy Services"]
    for s in services:
        lines.append(f"\n#{s['id']} — {s['title']} — ৳{money(s['price'])} — {'ON' if s['active'] else 'OFF'}")
    if not services:
        lines.append("\nNo services.")
    kb = [[InlineKeyboardButton("➕ Add Buy Service", callback_data="add_buy_service")]]
    for s in services:
        kb.append([InlineKeyboardButton(
            f"{'🔴' if s['active'] else '🟢'} Toggle #{s['id']}",
            callback_data=f"toggle_buy:{s['id']}"
        )])
    kb.append([InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin")])
    await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))


async def admin_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    p = db.get_payment_info()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Set bKash", callback_data="set_bkash")],
        [InlineKeyboardButton("💵 Set Gmail Task Default Price", callback_data="set_price")],
        [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin")],
    ])
    await q.edit_message_text(
        f"💳 Payment / Price Settings\n\n"
        f"bKash: {p['bkash'] or 'Not set'}\n"
        f"Default task price: ৳{money(p['gmail_price'])}",
        reply_markup=kb,
    )


async def admin_deposits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = db.pending_deposits()
    if not rows:
        text = "💰 কোনো pending deposit নেই।"
    else:
        text = "💰 Pending Deposits:\n\n" + "\n".join(
            f"#{r['id']} | User {r['user_id']} | ৳{money(r['amount'])} | {r['details']}"
            for r in rows[:20]
        )
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin")]]))


async def admin_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = db.pending_withdrawals()
    if not rows:
        text = "💸 কোনো pending withdrawal নেই।"
    else:
        text = "💸 Pending Withdrawals:\n\n" + "\n".join(
            f"#{r['id']} | User {r['user_id']} | ৳{money(r['amount'])} | {r['details']}"
            for r in rows[:20]
        )
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin")]]))


async def admin_sells(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = db.pending_sell_submissions()
    if not rows:
        text = "📋 কোনো pending Gmail submission নেই।"
    else:
        text = "📋 Pending Gmail Submissions:\n\n" + "\n".join(
            f"#{r['id']} | User {r['user_id']} | {r['email']} | ৳{money(r['price'])}"
            for r in rows[:30]
        )
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin")]]))


async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = db.pending_orders()
    if not rows:
        text = "📦 কোনো pending order নেই।"
    else:
        text = "📦 Pending Orders:\n\n" + "\n".join(
            f"#{r['id']} | User {r['user_id']} | {r['title']} | ৳{money(r['price'])}"
            for r in rows[:30]
        )
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin")]]))


async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    action, raw_id = q.data.split(":")
    item_id = int(raw_id)

    if action == "approve_sell":
        result = db.review_sell(item_id, True)
        msg = "Submission approved." if result else "Submission already processed/not found."
    elif action == "reject_sell":
        result = db.review_sell(item_id, False)
        msg = "Submission rejected." if result else "Submission already processed/not found."
    elif action == "approve_dep":
        result = db.review_deposit(item_id, True)
        msg = "Deposit approved." if result else "Deposit already processed/not found."
    elif action == "reject_dep":
        result = db.review_deposit(item_id, False)
        msg = "Deposit rejected." if result else "Deposit already processed/not found."
    elif action == "approve_wd":
        result = db.review_withdrawal(item_id, True)
        msg = "Withdrawal approved." if result else "Withdrawal already processed/not found."
    elif action == "reject_wd":
        result = db.review_withdrawal(item_id, False)
        msg = "Withdrawal rejected/refunded." if result else "Withdrawal already processed/not found."
    elif action == "complete_order":
        result = db.review_order(item_id, True)
        msg = "Order completed." if result else "Order already processed/not found."
    elif action == "reject_order":
        result = db.review_order(item_id, False)
        msg = "Order rejected/refunded." if result else "Order already processed/not found."
    else:
        msg = "Unknown action."

    await q.edit_message_text(f"✅ {msg}", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Admin Panel", callback_data="admin")]
    ]))


async def toggle_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    kind, raw_id = q.data.split(":")
    item_id = int(raw_id)
    if kind == "toggle_sell":
        db.toggle_sell_task(item_id)
        await admin_sell_tasks(update, context)
    else:
        db.toggle_buy_service(item_id)
        await admin_buy_services(update, context)


# ---------- Admin conversations ----------

async def add_sell_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return ConversationHandler.END
    await q.edit_message_text("📧 নতুন Gmail Task-এর নাম লিখুন:")
    return ADMIN_ADD_SELL_TITLE


async def add_sell_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_sell_title"] = update.message.text.strip()[:100]
    await update.message.reply_text("💵 Reward/price লিখুন:")
    return ADMIN_ADD_SELL_PRICE


async def add_sell_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(Decimal(update.message.text.strip()))
        if price <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await update.message.reply_text("❌ সঠিক price দিন।")
        return ADMIN_ADD_SELL_PRICE
    context.user_data["new_sell_price"] = price
    await update.message.reply_text("📝 Description/instructions লিখুন:")
    return ADMIN_ADD_SELL_DESC


async def add_sell_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = context.user_data.pop("new_sell_title")
    price = context.user_data.pop("new_sell_price")
    desc = update.message.text.strip()[:500]
    db.add_sell_task(title, price, desc)
    await update.message.reply_text("✅ Gmail Task added.", reply_markup=main_menu(update.effective_user.id))
    return ConversationHandler.END


async def add_buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return ConversationHandler.END
    await q.edit_message_text("🛒 নতুন Buy Service-এর নাম লিখুন:")
    return ADMIN_ADD_BUY_TITLE


async def add_buy_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_buy_title"] = update.message.text.strip()[:100]
    await update.message.reply_text("💵 Price লিখুন:")
    return ADMIN_ADD_BUY_PRICE


async def add_buy_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(Decimal(update.message.text.strip()))
        if price <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await update.message.reply_text("❌ সঠিক price দিন।")
        return ADMIN_ADD_BUY_PRICE
    context.user_data["new_buy_price"] = price
    await update.message.reply_text("📝 Description লিখুন:")
    return ADMIN_ADD_BUY_DESC


async def add_buy_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = context.user_data.pop("new_buy_title")
    price = context.user_data.pop("new_buy_price")
    desc = update.message.text.strip()[:500]
    db.add_buy_service(title, price, desc)
    await update.message.reply_text("✅ Buy Service added.", reply_markup=main_menu(update.effective_user.id))
    return ConversationHandler.END


async def set_price_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return ConversationHandler.END
    await q.edit_message_text("💵 Default Gmail Task reward লিখুন:")
    return ADMIN_PRICE


async def set_price_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(Decimal(update.message.text.strip()))
        if price <= 0:
            raise InvalidOperation
    except InvalidOperation:
        await update.message.reply_text("❌ সঠিক price দিন।")
        return ADMIN_PRICE
    db.set_setting("gmail_price", str(price))
    await update.message.reply_text("✅ Default price updated.")
    return ConversationHandler.END


async def set_bkash_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return ConversationHandler.END
    await q.edit_message_text("📱 নতুন bKash number লিখুন:")
    return ADMIN_BKASH


async def set_bkash_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.set_setting("bkash_number", update.message.text.strip())
    await update.message.reply_text("✅ bKash updated.")
    return ConversationHandler.END


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return ConversationHandler.END
    await q.edit_message_text("📢 Broadcast message লিখুন:")
    return ADMIN_BROADCAST


async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    users = db.all_user_ids()
    sent = 0
    for uid in users:
        try:
            await context.bot.send_message(uid, update.message.text)
            sent += 1
        except Exception:
            pass
    await update.message.reply_text(f"📢 Broadcast completed. Sent: {sent}")
    return ConversationHandler.END


# ---------- Informational ----------

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ack(update)
    uid = get_uid(update)
    await send_screen(
        update,
        f"💳 Your Balance: ৳{money(db.get_balance(uid))}",
        InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
    )


async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ack(update)
    uid = get_uid(update)
    rows = db.user_orders(uid)
    if not rows:
        text = "📦 আপনার কোনো order নেই।"
    else:
        text = "📦 আপনার Orders:\n\n" + "\n".join(
            f"#{r['id']} — {r['title']} — ৳{money(r['price'])} — {r['status']}"
            for r in rows[:20]
        )
    await send_screen(update, text, InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]]))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Help\n\n"
        "📧 Gmail Task: শুধু Gmail address জমা দিন।\n"
        "🛒 Buy Services: balance দিয়ে service order করুন।\n"
        "💰 Deposit: Admin approval-এর মাধ্যমে balance যোগ হবে।\n"
        "💸 Withdraw: balance থেকে withdrawal request দিন।\n\n"
        "⚠️ Password, OTP, recovery code বা অন্য কোনো secret তথ্য কখনো পাঠাবেন না।",
        reply_markup=main_menu(update.effective_user.id),
    )


async def simple_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "ℹ️ Help\n\nশুধু Gmail address submit করুন। Password/OTP/recovery code নেওয়া হয় না।",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back")]])
    )


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ack(update)
    username = SUPPORT_USERNAME.lstrip("@")
    await send_screen(
        update,
        f"🎧 Support: @{username}",
        InlineKeyboardMarkup([[InlineKeyboardButton("💬 Contact Support", url=f"https://t.me/{username}")]])
    )


async def back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("🏠 মূল মেনু")
    await show_main_menu(update, context, "নিচের মেনু থেকে অপশন বেছে নিন:")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.", reply_markup=main_menu(update.effective_user.id))
    return ConversationHandler.END


async def go_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the persistent '🏠 Home' reply-keyboard button — works even
    mid-conversation, cancelling whatever step the user was on."""
    context.user_data.clear()
    await update.message.reply_text("🏠 মূল মেনু", reply_markup=main_menu(update.effective_user.id))
    return ConversationHandler.END


async def notify_admin(context, text, buttons=None):
    if not ADMIN_ID:
        return
    try:
        await context.bot.send_message(ADMIN_ID, text, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
    except Exception as e:
        log.error("Admin notification failed: %s", e)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Unhandled error", exc_info=context.error)


def build_application():
    app = Application.builder().token(BOT_TOKEN).concurrent_updates(False).build()

    def btn(label: str):
        """Exact-match filter for a persistent reply-keyboard button label."""
        return filters.Regex(f"^{re.escape(label)}$")

    home_guard = MessageHandler(btn(BTN_HOME), go_home)

    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(sell_menu, "^sell_menu$"),
            MessageHandler(btn(BTN_SELL), sell_menu),
            CallbackQueryHandler(buy_menu, "^buy_menu$"),
            MessageHandler(btn(BTN_BUY), buy_menu),
            CallbackQueryHandler(deposit_start, "^deposit$"),
            MessageHandler(btn(BTN_DEPOSIT), deposit_start),
            CallbackQueryHandler(withdraw_start, "^withdraw$"),
            MessageHandler(btn(BTN_WITHDRAW), withdraw_start),
            CallbackQueryHandler(add_sell_task_start, "^add_sell_task$"),
            CallbackQueryHandler(add_buy_start, "^add_buy_service$"),
            CallbackQueryHandler(set_price_start, "^set_price$"),
            CallbackQueryHandler(set_bkash_start, "^set_bkash$"),
            CallbackQueryHandler(broadcast_start, "^admin_broadcast$"),
        ],
        states={
            SELL_TASK: [CallbackQueryHandler(sell_task_selected, r"^sell_task:\d+$")],
            SELL_EMAIL: [home_guard, MessageHandler(filters.TEXT & ~filters.COMMAND, sell_email_received)],
            BUY_SERVICE: [CallbackQueryHandler(buy_service_selected, r"^buy_service:\d+$")],
            BUY_CONFIRM: [
                CallbackQueryHandler(buy_confirm, "^buy_confirm$"),
                CallbackQueryHandler(buy_cancel, "^buy_cancel$"),
            ],
            DEPOSIT_AMOUNT: [home_guard, MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
            DEPOSIT_DETAILS: [home_guard, MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_details)],
            WITHDRAW_AMOUNT: [home_guard, MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_DETAILS: [home_guard, MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_details)],
            ADMIN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_price_value)],
            ADMIN_BKASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_bkash_value)],
            ADMIN_ADD_SELL_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_sell_title)],
            ADMIN_ADD_SELL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_sell_price)],
            ADMIN_ADD_SELL_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_sell_desc)],
            ADMIN_ADD_BUY_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_buy_title)],
            ADMIN_ADD_BUY_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_buy_price)],
            ADMIN_ADD_BUY_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_buy_desc)],
            ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(back, "^back$"),
            home_guard,
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(conv)

    # Persistent reply-keyboard buttons that don't start a multi-step flow
    app.add_handler(MessageHandler(btn(BTN_HOME), go_home))
    app.add_handler(MessageHandler(btn(BTN_BALANCE), balance))
    app.add_handler(MessageHandler(btn(BTN_ORDERS), my_orders))
    app.add_handler(MessageHandler(btn(BTN_HELP), help_cmd))
    app.add_handler(MessageHandler(btn(BTN_SUPPORT), support))
    app.add_handler(MessageHandler(btn(BTN_ADMIN), admin_panel))

    app.add_handler(CallbackQueryHandler(verify_join, "^verify_join$"))
    app.add_handler(CallbackQueryHandler(admin_panel, "^admin$"))
    app.add_handler(CallbackQueryHandler(admin_stats, "^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_users, "^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_sell_tasks, "^admin_sell_tasks$"))
    app.add_handler(CallbackQueryHandler(admin_buy_services, "^admin_buy_services$"))
    app.add_handler(CallbackQueryHandler(admin_payment, "^admin_payment$"))
    app.add_handler(CallbackQueryHandler(admin_deposits, "^admin_deposits$"))
    app.add_handler(CallbackQueryHandler(admin_withdrawals, "^admin_withdrawals$"))
    app.add_handler(CallbackQueryHandler(admin_sells, "^admin_sells$"))
    app.add_handler(CallbackQueryHandler(admin_orders, "^admin_orders$"))
    app.add_handler(CallbackQueryHandler(toggle_item, r"^toggle_(sell|buy):\d+$"))
    app.add_handler(CallbackQueryHandler(admin_action, r"^(approve_sell|reject_sell|approve_dep|reject_dep|approve_wd|reject_wd|complete_order|reject_order):\d+$"))
    app.add_handler(CallbackQueryHandler(balance, "^balance$"))
    app.add_handler(CallbackQueryHandler(my_orders, "^my_orders$"))
    app.add_handler(CallbackQueryHandler(simple_help, "^help$"))
    app.add_handler(CallbackQueryHandler(support, "^support$"))
    app.add_handler(CallbackQueryHandler(back, "^back$"))

    app.add_error_handler(error_handler)
    return app


class _HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running.")

    def log_message(self, format, *args):
        return  # silence default request logging


def start_keep_alive_server():
    """Binds a dummy HTTP server to $PORT.

    Render's "Web Service" type expects something listening on $PORT,
    while this bot itself only does Telegram long-polling. Running this
    in a background thread lets the same code work correctly whether the
    service is configured as a Web Service or a Background Worker on
    Render (if PORT isn't set, this is skipped)."""
    port = os.getenv("PORT")
    if not port:
        return
    try:
        server = HTTPServer(("0.0.0.0", int(port)), _HealthCheckHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        log.info("Keep-alive HTTP server listening on port %s", port)
    except Exception as e:
        log.warning("Could not start keep-alive server: %s", e)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    if not ADMIN_ID:
        raise RuntimeError("ADMIN_ID is missing")

    # Some hosting environments start Python without a current event loop
    # in the main thread; make sure one exists before PTB needs it.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    start_keep_alive_server()

    db.init_db()
    app = build_application()
    log.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
