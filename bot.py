import os
import asyncio
import logging
from decimal import Decimal

from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import database as db


# =========================================================
# ENV
# =========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").strip()
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@")


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID is required")

if not CHANNEL_USERNAME:
    raise RuntimeError("CHANNEL_USERNAME is required")


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

log = logging.getLogger(__name__)


# =========================================================
# CONVERSATION STATES
# =========================================================

SELL_WAITING = 1

DEPOSIT_AMOUNT = 2
DEPOSIT_DETAILS = 3

WITHDRAW_AMOUNT = 4
WITHDRAW_DETAILS = 5

BUY_QTY = 6

BROADCAST = 7
PRICE = 8
STOCK = 9


# =========================================================
# HELPERS
# =========================================================

def channel_name():
    if CHANNEL_USERNAME.startswith("@"):
        return CHANNEL_USERNAME

    return f"@{CHANNEL_USERNAME}"


async def is_member(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(
            chat_id=channel_name(),
            user_id=user_id,
        )

        return member.status in {
            "member",
            "administrator",
            "creator",
        }

    except Exception as e:
        log.warning("Membership check failed: %s", e)
        return False


def menu(user_id: int):

    rows = [
        [
            InlineKeyboardButton(
                "📧 Gmail Sell",
                callback_data="sell",
            ),
            InlineKeyboardButton(
                "🛒 Gmail Buy",
                callback_data="buy",
            ),
        ],

        [
            InlineKeyboardButton(
                "💳 Balance",
                callback_data="balance",
            ),
            InlineKeyboardButton(
                "💰 Deposit",
                callback_data="deposit",
            ),
        ],

        [
            InlineKeyboardButton(
                "💸 Withdraw",
                callback_data="withdraw",
            ),
            InlineKeyboardButton(
                "🎧 Support",
                callback_data="support",
            ),
        ],

        [
            InlineKeyboardButton(
                "📋 My Orders",
                callback_data="orders",
            ),
            InlineKeyboardButton(
                "📜 Transactions",
                callback_data="transactions",
            ),
        ],
    ]

    if user_id == ADMIN_ID:

        rows.append(
            [
                InlineKeyboardButton(
                    "⚙️ Admin Panel",
                    callback_data="admin",
                )
            ]
        )

    return InlineKeyboardMarkup(rows)


def admin_menu():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📊 Statistics",
                    callback_data="admin_stats",
                ),
                InlineKeyboardButton(
                    "💰 Change Price",
                    callback_data="admin_price",
                ),
            ],

            [
                InlineKeyboardButton(
                    "📦 Test Stock",
                    callback_data="admin_stock",
                ),
                InlineKeyboardButton(
                    "📥 Deposits",
                    callback_data="admin_deposits",
                ),
            ],

            [
                InlineKeyboardButton(
                    "📤 Withdrawals",
                    callback_data="admin_withdrawals",
                ),
                InlineKeyboardButton(
                    "📧 Sell Requests",
                    callback_data="admin_sells",
                ),
            ],

            [
                InlineKeyboardButton(
                    "🛒 Orders",
                    callback_data="admin_orders",
                ),
                InlineKeyboardButton(
                    "📢 Broadcast",
                    callback_data="admin_broadcast",
                ),
            ],
        ]
    )


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    user = update.effective_user

    db.ensure_user(
        user.id,
        user.username,
        user.full_name,
    )

    if not await is_member(
        context.bot,
        user.id,
    ):

        url = (
            f"https://t.me/"
            f"{CHANNEL_USERNAME.lstrip('@')}"
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📢 Join Channel",
                        url=url,
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔄 Verify Join",
                        callback_data="verify_join",
                    )
                ],
            ]
        )

        await update.message.reply_text(
            "🔐 আগে আমাদের official channel-এ "
            "join করুন, তারপর Verify Join চাপুন।",
            reply_markup=keyboard,
        )

        return

    await update.message.reply_text(
        "🏠 Main Menu",
        reply_markup=menu(user.id),
    )


# =========================================================
# VERIFY CHANNEL
# =========================================================

async def verify_join(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    if not await is_member(
        context.bot,
        query.from_user.id,
    ):

        await query.answer(
            "❌ এখনো channel join করা হয়নি।",
            show_alert=True,
        )

        return

    await query.edit_message_text(
        "✅ Verification successful.\n\n"
        "🏠 Main Menu",
        reply_markup=menu(query.from_user.id),
    )


async def require_member(
    query,
    context,
):

    if not await is_member(
        context.bot,
        query.from_user.id,
    ):

        await query.answer(
            "❌ আগে channel join করুন।",
            show_alert=True,
        )

        return False

    return True


# =========================================================
# CANCEL
# =========================================================

async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    context.user_data.clear()

    await update.effective_message.reply_text(
        "❌ Cancelled.",
        reply_markup=menu(
            update.effective_user.id
        ),
    )

    return ConversationHandler.END


# =========================================================
# SELL
# =========================================================

async def sell_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    if not await require_member(
        query,
        context,
    ):

        return ConversationHandler.END

    await query.message.reply_text(
        "📧 Gmail Sell (TEST MODE)\n\n"
        "বাস্তব Gmail password/recovery পাঠাবেন না।\n\n"
        "Test inventory submit করুন:\n\n"
        "Format:\n"
        "demo@example.test | TEST_ITEM\n\n"
        "/cancel দিয়ে বন্ধ করতে পারবেন।"
    )

    return SELL_WAITING


async def sell_receive(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    raw = update.message.text.strip()

    parts = [
        item.strip()
        for item in raw.split("|")
    ]

    if (
        len(parts) != 2
        or not parts[0].endswith(".test")
    ):

        await update.message.reply_text(
            "❌ Format ভুল।\n\n"
            "উদাহরণ:\n"
            "demo@example.test | TEST_ITEM"
        )

        return SELL_WAITING

    sell_id = db.create_sell(
        update.effective_user.id,
        parts[0],
        parts[1],
    )

    price = db.get_price()

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=f"approve_sell:{sell_id}",
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"reject_sell:{sell_id}",
                ),
            ]
        ]
    )

    await context.bot.send_message(
        ADMIN_ID,

        f"📧 New TEST Sell #{sell_id}\n"
        f"User: {update.effective_user.id}\n"
        f"Item: {parts[0]}\n"
        f"Label: {parts[1]}\n"
        f"Price: ৳{price:.2f}\n\n"
        "⚠️ Test-only inventory; "
        "no real credentials.",

        reply_markup=keyboard,
    )

    await update.message.reply_text(
        "✅ Submitted.\n"
        "Admin review-এর অপেক্ষায় আছে।",

        reply_markup=menu(
            update.effective_user.id
        ),
    )

    return ConversationHandler.END


# =========================================================
# BUY
# =========================================================

async def buy_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    if not await require_member(
        query,
        context,
    ):

        return ConversationHandler.END

    price = db.get_price()

    stock = db.stock_count()

    await query.message.reply_text(
        f"🛒 Test Gmail Buy\n\n"
        f"Unit Price: ৳{price:.2f}\n"
        f"Available Test Stock: {stock}\n\n"
        "কতটি নিতে চান?\n"
        "শুধু quantity লিখুন।\n\n"
        "/cancel"
    )

    return BUY_QTY


async def buy_quantity(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        qty = int(
            update.message.text.strip()
        )

        if qty <= 0 or qty > 1000:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ Valid quantity দিন।\n"
            "যেমন: 5"
        )

        return BUY_QTY

    price = db.get_price()

    total = price * qty

    balance = db.get_balance(
        update.effective_user.id
    )

    stock = db.stock_count()

    if qty > stock:

        await update.message.reply_text(
            f"❌ পর্যাপ্ত test stock নেই।\n"
            f"Available: {stock}"
        )

        return ConversationHandler.END

    if balance < total:

        await update.message.reply_text(
            f"❌ Balance কম।\n\n"
            f"Required: ৳{total:.2f}\n"
            f"Balance: ৳{balance:.2f}\n\n"
            "💰 Deposit করে আবার চেষ্টা করুন।",

            reply_markup=menu(
                update.effective_user.id
            ),
        )

        return ConversationHandler.END

    context.user_data["buy_qty"] = qty

    context.user_data["buy_total"] = str(
        total
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Yes, Confirm",
                    callback_data="confirm_buy",
                ),
                InlineKeyboardButton(
                    "❌ No, Cancel",
                    callback_data="cancel_buy",
                ),
            ]
        ]
    )

    await update.message.reply_text(
        f"🛒 Confirm Order\n\n"
        f"Quantity: {qty}\n"
        f"Total: ৳{total:.2f}",

        reply_markup=keyboard,
    )

    return ConversationHandler.END


async def confirm_buy(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    qty = int(
        context.user_data.pop(
            "buy_qty",
            0,
        )
    )

    total = Decimal(
        str(
            context.user_data.pop(
                "buy_total",
                "0",
            )
        )
    )

    if not qty:

        await query.edit_message_text(
            "❌ Order session expired."
        )

        return

    ok, items = db.purchase(
        query.from_user.id,
        qty,
        total,
    )

    if not ok:

        await query.edit_message_text(
            "❌ Order failed.\n"
            "Balance/stock আবার check করুন।"
        )

        return

    text = "\n".join(
        f"• {item}"
        for item in items
    )

    await query.edit_message_text(
        f"✅ Order completed\n\n"
        f"Quantity: {qty}\n"
        f"Paid: ৳{total:.2f}\n\n"
        f"TEST ITEMS:\n{text}\n\n"
        "⚠️ এগুলো dummy test items."
    )


async def cancel_buy(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    context.user_data.clear()

    await query.edit_message_text(
        "❌ Order cancelled."
    )


# =========================================================
# BALANCE
# =========================================================

async def balance(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    amount = db.get_balance(
        query.from_user.id
    )

    await query.message.reply_text(
        f"💳 Balance: ৳{amount:.2f}",

        reply_markup=menu(
            query.from_user.id
        ),
    )


# =========================================================
# DEPOSIT
# =========================================================

async def deposit_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    await query.message.reply_text(
        "💰 Deposit amount লিখুন।\n\n"
        "/cancel"
    )

    return DEPOSIT_AMOUNT


async def deposit_amount(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        amount = Decimal(
            update.message.text.strip()
        )

        if amount <= 0:
            raise ValueError

    except Exception:

        await update.message.reply_text(
            "❌ Valid amount দিন।"
        )

        return DEPOSIT_AMOUNT

    context.user_data["deposit_amount"] = str(
        amount
    )

    await update.message.reply_text(
        "bKash/Nagad number + TrxID দিন।\n\n"
        "উদাহরণ:\n"
        "01XXXXXXXXX | TRX123\n\n"
        "/cancel"
    )

    return DEPOSIT_DETAILS


async def deposit_details(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    amount = Decimal(
        context.user_data.pop(
            "deposit_amount"
        )
    )

    details = update.message.text.strip()

    deposit_id = db.create_deposit(
        update.effective_user.id,
        amount,
        details,
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=f"approve_dep:{deposit_id}",
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"reject_dep:{deposit_id}",
                ),
            ]
        ]
    )

    await context.bot.send_message(
        ADMIN_ID,

        f"💰 Deposit #{deposit_id}\n"
        f"User: {update.effective_user.id}\n"
        f"Amount: ৳{amount:.2f}\n"
        f"Details: {details}",

        reply_markup=keyboard,
    )

    await update.message.reply_text(
        "✅ Deposit submitted for review.",

        reply_markup=menu(
            update.effective_user.id
        ),
    )

    return ConversationHandler.END


# =========================================================
# WITHDRAW
# =========================================================

async def withdraw_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    await query.message.reply_text(
        "💸 Withdrawal amount লিখুন।\n\n"
        "/cancel"
    )

    return WITHDRAW_AMOUNT


async def withdraw_amount(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        amount = Decimal(
            update.message.text.strip()
        )

        if amount <= 0:
            raise ValueError

    except Exception:

        await update.message.reply_text(
            "❌ Valid amount দিন।"
        )

        return WITHDRAW_AMOUNT

    balance_amount = db.get_balance(
        update.effective_user.id
    )

    if balance_amount < amount:

        await update.message.reply_text(
            "❌ আপনার balance যথেষ্ট নয়।"
        )

        return ConversationHandler.END

    context.user_data["withdraw_amount"] = str(
        amount
    )

    await update.message.reply_text(
        "Payment method + number দিন।\n\n"
        "উদাহরণ:\n"
        "bKash | 01XXXXXXXXX\n\n"
        "/cancel"
    )

    return WITHDRAW_DETAILS


async def withdraw_details(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    amount = Decimal(
        context.user_data.pop(
            "withdraw_amount"
        )
    )

    details = update.message.text.strip()

    withdrawal_id = db.create_withdrawal(
        update.effective_user.id,
        amount,
        details,
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Approve",
                    callback_data=f"approve_wd:{withdrawal_id}",
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"reject_wd:{withdrawal_id}",
                ),
            ]
        ]
    )

    await context.bot.send_message(
        ADMIN_ID,

        f"💸 Withdrawal #{withdrawal_id}\n"
        f"User: {update.effective_user.id}\n"
        f"Amount: ৳{amount:.2f}\n"
        f"Details: {details}",

        reply_markup=keyboard,
    )

    await update.message.reply_text(
        "✅ Withdrawal submitted for review.",

        reply_markup=menu(
            update.effective_user.id
        ),
    )

    return ConversationHandler.END


# =========================================================
# SUPPORT
# =========================================================

async def support_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    if SUPPORT_USERNAME:

        await query.message.reply_text(
            "🎧 Support\n\n"
            "যেকোনো সমস্যায় যোগাযোগ করুন:",

            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "👨‍💻 Contact Support",
                            url=(
                                "https://t.me/"
                                f"{SUPPORT_USERNAME}"
                            ),
                        )
                    ]
                ]
            ),
        )

    else:

        await query.message.reply_text(
            "🎧 Support username "
            ".env-এ সেট করা হয়নি।"
        )


# =========================================================
# ORDERS / TRANSACTIONS
# =========================================================

async def simple_info(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    if query.data == "orders":

        data = db.user_orders(
            user_id
        )

    else:

        data = db.transactions(
            user_id
        )

    await query.message.reply_text(
        data or "কোনো record নেই।",

        reply_markup=menu(user_id),
    )


# =========================================================
# ADMIN PANEL
# =========================================================

async def admin_panel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    await query.message.reply_text(
        "⚙️ Admin Panel",
        reply_markup=admin_menu(),
    )


async def admin_stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id == ADMIN_ID:

        await query.message.reply_text(
            db.stats(),
            reply_markup=admin_menu(),
        )


# =========================================================
# ADMIN PRICE
# =========================================================

async def admin_price_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:

        return ConversationHandler.END

    await query.message.reply_text(
        f"Current price: "
        f"৳{db.get_price():.2f}\n\n"
        "নতুন price লিখুন।\n"
        "/cancel"
    )

    return PRICE


async def admin_price_set(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        price = Decimal(
            update.message.text.strip()
        )

        if price <= 0:
            raise ValueError

    except Exception:

        await update.message.reply_text(
            "❌ Valid price দিন।"
        )

        return PRICE

    db.set_price(price)

    await update.message.reply_text(
        f"✅ Price updated: ৳{price:.2f}",

        reply_markup=admin_menu(),
    )

    return ConversationHandler.END


# =========================================================
# ADMIN STOCK
# =========================================================

async def admin_stock_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:

        return ConversationHandler.END

    await query.message.reply_text(
        "কতটি dummy test item add করবেন?\n"
        "/cancel"
    )

    return STOCK


async def admin_stock_add(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        quantity = int(
            update.message.text.strip()
        )

        if quantity <= 0 or quantity > 10000:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ Valid quantity দিন।"
        )

        return STOCK

    db.add_test_stock(quantity)

    await update.message.reply_text(
        f"✅ Added {quantity} test items.\n"
        f"Stock: {db.stock_count()}",

        reply_markup=admin_menu(),
    )

    return ConversationHandler.END


# =========================================================
# BROADCAST
# =========================================================

async def broadcast_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:

        return ConversationHandler.END

    await query.message.reply_text(
        "📢 Broadcast message লিখুন.\n"
        "/cancel"
    )

    return BROADCAST


async def broadcast_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    users = db.all_users()

    success = 0

    for user_id in users:

        try:

            await context.bot.send_message(
                user_id,
                update.message.text,
            )

            success += 1

        except Exception:

            pass

    await update.message.reply_text(
        f"📢 Broadcast complete: "
        f"{success}/{len(users)}",

        reply_markup=admin_menu(),
    )

    return ConversationHandler.END


# =========================================================
# ADMIN ACTIONS
# =========================================================

async def admin_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    action, request_id = query.data.split(":")

    request_id = int(request_id)

    if action == "approve_sell":

        ok, user_id, amount = db.approve_sell(
            request_id,
            True,
        )

        text = (
            "Approved"
            if ok
            else "Already processed"
        )

    elif action == "reject_sell":

        ok, user_id, amount = db.approve_sell(
            request_id,
            False,
        )

        text = (
            "Rejected"
            if ok
            else "Already processed"
        )

    elif action == "approve_dep":

        ok, user_id, amount = db.approve_deposit(
            request_id,
            True,
        )

        text = (
            "Approved"
            if ok
            else "Already processed"
        )

    elif action == "reject_dep":

        ok, user_id, amount = db.approve_deposit(
            request_id,
            False,
        )

        text = (
            "Rejected"
            if ok
            else "Already processed"
        )

    elif action == "approve_wd":

        ok, user_id, amount = db.approve_withdrawal(
            request_id,
            True,
        )

        text = (
            "Approved"
            if ok
            else "Already processed"
        )

    else:

        ok, user_id, amount = db.approve_withdrawal(
            request_id,
            False,
        )

        text = (
            "Rejected"
            if ok
            else "Already processed"
        )

    await query.edit_message_text(
        f"#{request_id}: {text}"
    )

    if ok:

        await context.bot.send_message(
            user_id,

            f"📌 Request #{request_id}: "
            f"{text}\n"
            f"Amount: ৳{amount:.2f}",
        )


# =========================================================
# HELP
# =========================================================

async def help_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await update.message.reply_text(
        "ℹ️ Help\n\n"
        "এই botটি TEST/learning "
        "environment-এর জন্য।\n\n"
        "Real Gmail password/recovery "
        "কখনো পাঠাবেন না।\n\n"
        "/start দিয়ে main menu খুলুন।"
    )


# =========================================================
# APPLICATION BUILD
# =========================================================

def build_application():

    db.init_db()

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # -----------------------------------------------------
    # SELL
    # -----------------------------------------------------

    sell_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                sell_start,
                "^sell$",
            )
        ],

        states={
            SELL_WAITING: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    sell_receive,
                )
            ]
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel,
            )
        ],
    )

    # -----------------------------------------------------
    # BUY
    # -----------------------------------------------------

    buy_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                buy_start,
                "^buy$",
            )
        ],

        states={
            BUY_QTY: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    buy_quantity,
                )
            ]
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel,
            )
        ],
    )

    # -----------------------------------------------------
    # DEPOSIT
    # -----------------------------------------------------

    deposit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                deposit_start,
                "^deposit$",
            )
        ],

        states={

            DEPOSIT_AMOUNT: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    deposit_amount,
                )
            ],

            DEPOSIT_DETAILS: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    deposit_details,
                )
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel,
            )
        ],
    )

    # -----------------------------------------------------
    # WITHDRAW
    # -----------------------------------------------------

    withdraw_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                withdraw_start,
                "^withdraw$",
            )
        ],

        states={

            WITHDRAW_AMOUNT: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    withdraw_amount,
                )
            ],

            WITHDRAW_DETAILS: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    withdraw_details,
                )
            ],
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel,
            )
        ],
    )

    # -----------------------------------------------------
    # PRICE
    # -----------------------------------------------------

    price_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                admin_price_start,
                "^admin_price$",
            )
        ],

        states={
            PRICE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    admin_price_set,
                )
            ]
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel,
            )
        ],
    )

    # -----------------------------------------------------
    # STOCK
    # -----------------------------------------------------

    stock_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                admin_stock_start,
                "^admin_stock$",
            )
        ],

        states={
            STOCK: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    admin_stock_add,
                )
            ]
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel,
            )
        ],
    )

    # -----------------------------------------------------
    # BROADCAST
    # -----------------------------------------------------

    broadcast_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                broadcast_start,
                "^admin_broadcast$",
            )
        ],

        states={
            BROADCAST: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    broadcast_send,
                )
            ]
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel,
            )
        ],
    )

    # =====================================================
    # COMMAND HANDLERS
    # =====================================================

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_cmd,
        )
    )

    # =====================================================
    # CONVERSATION HANDLERS
    # =====================================================

    application.add_handler(sell_conv)
    application.add_handler(buy_conv)
    application.add_handler(deposit_conv)
    application.add_handler(withdraw_conv)

    application.add_handler(price_conv)
    application.add_handler(stock_conv)
    application.add_handler(broadcast_conv)

    # =====================================================
    # CALLBACK HANDLERS
    # =====================================================

    application.add_handler(
        CallbackQueryHandler(
            verify_join,
            "^verify_join$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            confirm_buy,
            "^confirm_buy$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            cancel_buy,
            "^cancel_buy$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            balance,
            "^balance$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            support_start,
            "^support$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            simple_info,
            "^(orders|transactions)$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_panel,
            "^admin$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_stats,
            "^admin_stats$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_action,
            r"^(approve_sell|reject_sell|approve_dep|reject_dep|approve_wd|reject_wd):\d+$",
        )
    )

    return application


# =========================================================
# ASYNC RUNNER
# =========================================================

async def run_bot():

    application = build_application()

    log.info("Initializing Telegram application...")

    await application.initialize()

    await application.start()

    log.info("Starting Telegram polling...")

    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES
    )

    log.info("Bot is running successfully.")

    try:

        await asyncio.Event().wait()

    finally:

        log.info("Stopping Telegram polling...")

        await application.updater.stop()

        log.info("Stopping application...")

        await application.stop()

        log.info("Shutting down application...")

        await application.shutdown()


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            run_bot()
        )

    except KeyboardInterrupt:

        log.info(
            "Bot stopped by user."
        )

    except Exception:

        log.exception(
            "Bot crashed."
        )

        raiseraise
