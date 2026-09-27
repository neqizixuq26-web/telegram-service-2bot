import os
import logging
from decimal import Decimal, InvalidOperation
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)

import database as db

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").strip()
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@")

if not BOT_TOKEN or not ADMIN_ID or not CHANNEL_USERNAME:
    raise RuntimeError("BOT_TOKEN, ADMIN_ID and CHANNEL_USERNAME are required in .env")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

SELL_WAITING = 1
DEPOSIT_AMOUNT = 2
DEPOSIT_DETAILS = 3
WITHDRAW_AMOUNT = 4
WITHDRAW_DETAILS = 5
BUY_QTY = 6
BROADCAST = 7
PRICE = 8
STOCK = 9
SUPPORT = 10


def channel_name():
    return CHANNEL_USERNAME if CHANNEL_USERNAME.startswith("@") else f"@{CHANNEL_USERNAME}"


async def is_member(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel_name(), user_id=user_id)
        return member.status in {"member", "administrator", "creator"}
    except Exception as e:
        log.warning("Membership check failed: %s", e)
        return False


def menu(user_id: int):
    rows = [
        [InlineKeyboardButton("📧 Gmail Sell", callback_data="sell"),
         InlineKeyboardButton("🛒 Gmail Buy", callback_data="buy")],
        [InlineKeyboardButton("💳 Balance", callback_data="balance"),
         InlineKeyboardButton("💰 Deposit", callback_data="deposit")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw"),
         InlineKeyboardButton("🎧 Support", callback_data="support")],
        [InlineKeyboardButton("📋 My Orders", callback_data="orders"),
         InlineKeyboardButton("📜 Transactions", callback_data="transactions")],
    ]
    if user_id == ADMIN_ID:
        rows.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin")])
    return InlineKeyboardMarkup(rows)


def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
         InlineKeyboardButton("💰 Change Price", callback_data="admin_price")],
        [InlineKeyboardButton("📦 Test Stock", callback_data="admin_stock"),
         InlineKeyboardButton("📥 Deposits", callback_data="admin_deposits")],
        [InlineKeyboardButton("📤 Withdrawals", callback_data="admin_withdrawals"),
         InlineKeyboardButton("📧 Sell Requests", callback_data="admin_sells")],
        [InlineKeyboardButton("🛒 Orders", callback_data="admin_orders"),
         InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.username, user.full_name)

    if not await is_member(context.bot, user.id):
        url = f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel", url=url)],
            [InlineKeyboardButton("🔄 Verify Join", callback_data="verify_join")]
        ])
        await update.message.reply_text(
            "🔐 আগে আমাদের official channel-এ join করুন, তারপর Verify Join চাপুন.",
            reply_markup=kb
        )
        return

    await update.message.reply_text("🏠 Main Menu", reply_markup=menu(user.id))


async def verify_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await is_member(context.bot, q.from_user.id):
        await q.answer("❌ এখনো channel join করা হয়নি।", show_alert=True)
        return
    await q.edit_message_text("✅ Verification successful.\n\n🏠 Main Menu", reply_markup=menu(q.from_user.id))


async def require_member(q, context):
    if not await is_member(context.bot, q.from_user.id):
        await q.answer("❌ আগে channel join করুন।", show_alert=True)
        return False
    return True


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_message.reply_text("❌ Cancelled.", reply_markup=menu(update.effective_user.id))
    return ConversationHandler.END


async def sell_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await require_member(q, context):
        return ConversationHandler.END
    await q.message.reply_text(
        "📧 Gmail Sell (TEST MODE)\n\n"
        "বাস্তব Gmail password/recovery পাঠাবেন না।\n"
        "Test inventory submit করুন:\n\n"
        "Format:\n"
        "demo@example.test | TEST_ITEM\n\n"
        "/cancel দিয়ে বন্ধ করতে পারবেন।"
    )
    return SELL_WAITING


async def sell_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    parts = [x.strip() for x in raw.split("|")]
    if len(parts) != 2 or not parts[0].endswith(".test"):
        await update.message.reply_text("❌ Format ভুল। উদাহরণ: demo@example.test | TEST_ITEM")
        return SELL_WAITING

    sell_id = db.create_sell(update.effective_user.id, parts[0], parts[1])
    price = db.get_price()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"approve_sell:{sell_id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"reject_sell:{sell_id}")]
    ])
    await context.bot.send_message(
        ADMIN_ID,
        f"📧 New TEST Sell #{sell_id}\n"
        f"User: {update.effective_user.id}\n"
        f"Item: {parts[0]}\n"
        f"Label: {parts[1]}\n"
        f"Price: ৳{price:.2f}\n\n"
        "⚠️ Test-only inventory; no real credentials.",
        reply_markup=kb
    )
    await update.message.reply_text("✅ Submitted. Admin review-এর অপেক্ষায় আছে।", reply_markup=menu(update.effective_user.id))
    return ConversationHandler.END


async def buy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not await require_member(q, context):
        return ConversationHandler.END
    price = db.get_price()
    stock = db.stock_count()
    await q.message.reply_text(
        f"🛒 Test Gmail Buy\n\n"
        f"Unit Price: ৳{price:.2f}\n"
        f"Available Test Stock: {stock}\n\n"
        "কতটি নিতে চান? শুধু quantity লিখুন।\n/cancel"
    )
    return BUY_QTY


async def buy_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        qty = int(update.message.text.strip())
        if qty <= 0 or qty > 1000:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Valid quantity দিন, যেমন: 5")
        return BUY_QTY

    price = db.get_price()
    total = price * qty
    balance = db.get_balance(update.effective_user.id)
    stock = db.stock_count()

    if qty > stock:
        await update.message.reply_text(f"❌ পর্যাপ্ত test stock নেই। Available: {stock}")
        return ConversationHandler.END
    if balance < total:
        await update.message.reply_text(
            f"❌ Balance কম।\nRequired: ৳{total:.2f}\nBalance: ৳{balance:.2f}\n\n"
            "💰 Deposit করে আবার চেষ্টা করুন।",
            reply_markup=menu(update.effective_user.id)
        )
        return ConversationHandler.END

    context.user_data["buy_qty"] = qty
    context.user_data["buy_total"] = total
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, Confirm", callback_data="confirm_buy"),
         InlineKeyboardButton("❌ No, Cancel", callback_data="cancel_buy")]
    ])
    await update.message.reply_text(
        f"🛒 Confirm Order\nQuantity: {qty}\nTotal: ৳{total:.2f}",
        reply_markup=kb
    )
    return ConversationHandler.END


async def confirm_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    qty = int(context.user_data.pop("buy_qty", 0))
    total = Decimal(str(context.user_data.pop("buy_total", "0")))
    if not qty:
        await q.edit_message_text("❌ Order session expired.")
        return
    ok, items = db.purchase(q.from_user.id, qty, total)
    if not ok:
        await q.edit_message_text("❌ Order failed. Balance/stock আবার check করুন।")
        return
    text = "\n".join(f"• {x}" for x in items)
    await q.edit_message_text(
        f"✅ Order completed\nQuantity: {qty}\nPaid: ৳{total:.2f}\n\n"
        f"TEST ITEMS:\n{text}\n\n⚠️ এগুলো dummy test items."
    )


async def cancel_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data.clear()
    await q.edit_message_text("❌ Order cancelled.")


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    b = db.get_balance(q.from_user.id)
    await q.message.reply_text(f"💳 Balance: ৳{b:.2f}", reply_markup=menu(q.from_user.id))


async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("💰 Deposit amount লিখুন।\n/cancel")
    return DEPOSIT_AMOUNT


async def deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = Decimal(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except Exception:
        await update.message.reply_text("❌ Valid amount দিন।")
        return DEPOSIT_AMOUNT
    context.user_data["deposit_amount"] = str(amount)
    await update.message.reply_text("bKash/Nagad number + TrxID দিন।\nউদাহরণ: 01XXXXXXXXX | TRX123\n/cancel")
    return DEPOSIT_DETAILS


async def deposit_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = Decimal(context.user_data.pop("deposit_amount"))
    details = update.message.text.strip()
    dep_id = db.create_deposit(update.effective_user.id, amount, details)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"approve_dep:{dep_id}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"reject_dep:{dep_id}")]
    ])
    await context.bot.send_message(
        ADMIN_ID, f"💰 Deposit #{dep_id}\nUser: {update.effective_user.id}\nAmount: ৳{amount}\nDetails: {details}",
        reply_markup=kb
    )
    await update.message.reply_text("✅ Deposit submitted for admin review.", reply_markup=menu(update.effective_user.id))
    return ConversationHandler.END


async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("💸 Withdrawal amount লিখুন।\n/cancel")
    return WITHDRAW_AMOUNT


async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = Decimal(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except Exception:
        await update.message.reply_text("❌ Valid amount দিন।")
        return WITHDRAW_AMOUNT
    if db.get_balance(update.effective_user.id) < amount:
        await update.message.reply_text("❌ আপনার balance যথেষ্ট নয়।")
        return ConversationHandler.END
    context.user_data["withdraw_amount"] = str(amount)
    await update.message.reply_text("Payment method + number দিন।\n/cancel")
    return WITHDRAW_DETAILS


async def withdraw_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = Decimal(context.user_data.pop("withdraw_amount"))
    details = update.message.text.strip()
    wid = db.create_withdrawal(update.effective_user.id, amount, details)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve", callback_data=f"approve_wd:{wid}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"reject_wd:{wid}")]
    ])
    await context.bot.send_message(
        ADMIN_ID, f"💸 Withdrawal #{wid}\nUser: {update.effective_user.id}\nAmount: ৳{amount}\nDetails: {details}",
        reply_markup=kb
    )
    await update.message.reply_text("✅ Withdrawal submitted for review.", reply_markup=menu(update.effective_user.id))
    return ConversationHandler.END


async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if SUPPORT_USERNAME:
        await q.message.reply_text(
            "🎧 Support\n\nযেকোনো সমস্যায় যোগাযোগ করুন:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👨‍💻 Contact Support", url=f"https://t.me/{SUPPORT_USERNAME}")]
            ])
        )
    else:
        await q.message.reply_text("🎧 Support username .env-এ সেট করা হয়নি।")
    return ConversationHandler.END


async def simple_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = db.user_orders(uid) if q.data == "orders" else db.transactions(uid)
    await q.message.reply_text(data or "কোনো record নেই.", reply_markup=menu(uid))


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return
    await q.message.reply_text("⚙️ Admin Panel", reply_markup=admin_menu())


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id == ADMIN_ID:
        await q.message.reply_text(db.stats(), reply_markup=admin_menu())


async def admin_price_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return ConversationHandler.END
    await q.message.reply_text(f"Current price: ৳{db.get_price():.2f}\nনতুন price লিখুন.\n/cancel")
    return PRICE


async def admin_price_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        p = Decimal(update.message.text.strip())
        if p <= 0: raise ValueError
    except Exception:
        await update.message.reply_text("❌ Valid price দিন.")
        return PRICE
    db.set_price(p)
    await update.message.reply_text(f"✅ Price updated: ৳{p:.2f}", reply_markup=admin_menu())
    return ConversationHandler.END


async def admin_stock_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return ConversationHandler.END
    await q.message.reply_text("কতটি dummy test item add করবেন?\n/cancel")
    return STOCK


async def admin_stock_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        n = int(update.message.text.strip())
        if n <= 0 or n > 10000: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Valid quantity দিন.")
        return STOCK
    db.add_test_stock(n)
    await update.message.reply_text(f"✅ Added {n} test items.\nStock: {db.stock_count()}", reply_markup=admin_menu())
    return ConversationHandler.END


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return ConversationHandler.END
    await q.message.reply_text("📢 Broadcast message লিখুন.\n/cancel")
    return BROADCAST


async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = db.all_users()
    ok = 0
    for uid in users:
        try:
            await context.bot.send_message(uid, update.message.text)
            ok += 1
        except Exception:
            pass
    await update.message.reply_text(f"📢 Broadcast complete: {ok}/{len(users)}", reply_markup=admin_menu())
    return ConversationHandler.END


async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return
    action, sid = q.data.split(":")
    sid = int(sid)
    if action == "approve_sell":
        ok, uid, amount = db.approve_sell(sid, True)
        text = "Approved" if ok else "Already processed"
    elif action == "reject_sell":
        ok, uid, amount = db.approve_sell(sid, False)
        text = "Rejected" if ok else "Already processed"
    elif action == "approve_dep":
        ok, uid, amount = db.approve_deposit(sid, True)
        text = "Approved" if ok else "Already processed"
    elif action == "reject_dep":
        ok, uid, amount = db.approve_deposit(sid, False)
        text = "Rejected" if ok else "Already processed"
    elif action == "approve_wd":
        ok, uid, amount = db.approve_withdrawal(sid, True)
        text = "Approved" if ok else "Already processed"
    else:
        ok, uid, amount = db.approve_withdrawal(sid, False)
        text = "Rejected" if ok else "Already processed"

    await q.edit_message_text(f"#{sid}: {text}")
    if ok:
        await context.bot.send_message(uid, f"📌 Request #{sid}: {text}\nAmount: ৳{amount:.2f}")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Help\n\n"
        "এই botটি TEST/learning environment-এর জন্য।\n"
        "Real Gmail password/recovery কখনো পাঠাবেন না।\n"
        "/start দিয়ে main menu খুলুন."
    )


def main():
    db.init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    sell_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(sell_start, "^sell$")],
        states={SELL_WAITING: [MessageHandler(filters.TEXT & ~filters.COMMAND, sell_receive)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    buy_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_start, "^buy$")],
        states={BUY_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_quantity)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    dep_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_start, "^deposit$")],
        states={
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount)],
            DEPOSIT_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_details)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    wd_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(withdraw_start, "^withdraw$")],
        states={
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount)],
            WITHDRAW_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_details)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    price_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_price_start, "^admin_price$")],
        states={PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_price_set)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    stock_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_stock_start, "^admin_stock$")],
        states={STOCK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_stock_add)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_start, "^admin_broadcast$")],
        states={BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(sell_conv); app.add_handler(buy_conv); app.add_handler(dep_conv); app.add_handler(wd_conv)
    app.add_handler(price_conv); app.add_handler(stock_conv); app.add_handler(broadcast_conv)

    app.add_handler(CallbackQueryHandler(verify_join, "^verify_join$"))
    app.add_handler(CallbackQueryHandler(confirm_buy, "^confirm_buy$"))
    app.add_handler(CallbackQueryHandler(cancel_buy, "^cancel_buy$"))
    app.add_handler(CallbackQueryHandler(balance, "^balance$"))
    app.add_handler(CallbackQueryHandler(support_start, "^support$"))
    app.add_handler(CallbackQueryHandler(simple_info, "^(orders|transactions)$"))
    app.add_handler(CallbackQueryHandler(admin_panel, "^admin$"))
    app.add_handler(CallbackQueryHandler(admin_stats, "^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_action, "^(approve_sell|reject_sell|approve_dep|reject_dep|approve_wd|reject_wd):\\d+$"))

    log.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
