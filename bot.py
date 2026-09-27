import os
import logging
from decimal import Decimal, InvalidOperation

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
# ENVIRONMENT
# =========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "").strip()
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@")

try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0").strip())
except ValueError:
    ADMIN_ID = 0


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID is missing or invalid")

if not CHANNEL_USERNAME:
    raise RuntimeError("CHANNEL_USERNAME is missing")


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

PAYMENT_BKASH = 10
PAYMENT_NAGAD = 11


# =========================================================
# HELPERS
# =========================================================

def channel_name():
    username = CHANNEL_USERNAME.strip()

    if username.startswith("@"):
        return username

    return f"@{username}"


def support_url():
    if not SUPPORT_USERNAME:
        return None

    return f"https://t.me/{SUPPORT_USERNAME}"


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

    except Exception as error:
        log.warning(
            "Channel membership check failed: %s",
            error,
        )
        return False


async def require_member(query, context) -> bool:
    if await is_member(
        context.bot,
        query.from_user.id,
    ):
        return True

    try:
        await query.answer(
            "❌ আগে আমাদের channel join করুন।",
            show_alert=True,
        )
    except Exception:
        pass

    return False


def main_menu(user_id: int):

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
                    "💳 Payment Settings",
                    callback_data="admin_payment",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📥 Deposits",
                    callback_data="admin_deposits",
                ),
                InlineKeyboardButton(
                    "📤 Withdrawals",
                    callback_data="admin_withdrawals",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📧 Sell Requests",
                    callback_data="admin_sells",
                ),
                InlineKeyboardButton(
                    "🛒 Orders",
                    callback_data="admin_orders",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📢 Broadcast",
                    callback_data="admin_broadcast",
                )
            ],
        ]
    )


def back_admin_markup():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⬅️ Admin Panel",
                    callback_data="admin",
                )
            ]
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

        channel_url = (
            f"https://t.me/"
            f"{CHANNEL_USERNAME.lstrip('@')}"
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📢 Join Channel",
                        url=channel_url,
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
            "🔐 আগে আমাদের official channel-এ join করুন।\n\n"
            "Channel join করার পর নিচের "
            "Verify Join button চাপুন।",
            reply_markup=keyboard,
        )

        return

    await update.message.reply_text(
        "🏠 Main Menu",
        reply_markup=main_menu(user.id),
    )


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
        reply_markup=main_menu(
            query.from_user.id
        ),
    )


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
        reply_markup=main_menu(
            update.effective_user.id
        ),
    )

    return ConversationHandler.END


# =========================================================
# GMAIL SELL - TEST MODE
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
        "📧 Gmail Sell — TEST MODE\n\n"
        "⚠️ বাস্তব Gmail password/recovery "
        "পাঠাবেন না।\n\n"
        "শুধু dummy test item ব্যবহার করুন:\n\n"
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
            "সঠিক উদাহরণ:\n"
            "demo@example.test | TEST_ITEM"
        )

        return SELL_WAITING

    test_email = parts[0]
    label = parts[1]

    sell_id = db.create_sell(
        update.effective_user.id,
        test_email,
        label,
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
        (
            f"📧 New TEST Sell #{sell_id}\n\n"
            f"User ID: {update.effective_user.id}\n"
            f"Item: {test_email}\n"
            f"Label: {label}\n"
            f"Price: ৳{price:.2f}\n\n"
            "⚠️ Test-only inventory.\n"
            "No real credentials."
        ),
        reply_markup=keyboard,
    )

    await update.message.reply_text(
        "✅ Sell request submitted.\n\n"
        "Admin review-এর অপেক্ষায় আছে।",
        reply_markup=main_menu(
            update.effective_user.id
        ),
    )

    return ConversationHandler.END


# =========================================================
# GMAIL BUY - TEST MODE
#
