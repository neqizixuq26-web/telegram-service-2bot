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
        f"🛒 Gmail Buy — TEST MODE\n\n"
        f"💰 Unit Price: ৳{price:.2f}\n"
        f"📦 Available Test Stock: {stock}\n\n"
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

        quantity = int(
            update.message.text.strip()
        )

        if quantity <= 0 or quantity > 1000:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ Valid quantity দিন।\n\n"
            "উদাহরণ: 5"
        )

        return BUY_QTY

    price = db.get_price()

    total = price * quantity

    balance = db.get_balance(
        update.effective_user.id
    )

    stock = db.stock_count()

    if quantity > stock:

        await update.message.reply_text(
            f"❌ পর্যাপ্ত test stock নেই।\n\n"
            f"Available: {stock}"
        )

        return ConversationHandler.END

    if balance < total:

        await update.message.reply_text(
            f"❌ আপনার balance কম।\n\n"
            f"Required: ৳{total:.2f}\n"
            f"Balance: ৳{balance:.2f}\n\n"
            "💰 Deposit করে আবার চেষ্টা করুন।",
            reply_markup=main_menu(
                update.effective_user.id
            ),
        )

        return ConversationHandler.END

    context.user_data["buy_qty"] = quantity
    context.user_data["buy_total"] = str(total)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Confirm",
                    callback_data="confirm_buy",
                ),
                InlineKeyboardButton(
                    "❌ Cancel",
                    callback_data="cancel_buy",
                ),
            ]
        ]
    )

    await update.message.reply_text(
        "🛒 Confirm Order\n\n"
        f"Quantity: {quantity}\n"
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

    quantity = int(
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

    if not quantity:

        await query.edit_message_text(
            "❌ Order session expired."
        )

        return

    success, items = db.purchase(
        query.from_user.id,
        quantity,
        total,
    )

    if not success:

        await query.edit_message_text(
            "❌ Order failed.\n\n"
            "Balance অথবা stock আবার check করুন।"
        )

        return

    item_text = "\n".join(
        f"• {item}"
        for item in items
    )

    await query.edit_message_text(
        "✅ Order completed\n\n"
        f"Quantity: {quantity}\n"
        f"Paid: ৳{total:.2f}\n\n"
        "TEST ITEMS:\n"
        f"{item_text}\n\n"
        "⚠️ এগুলো dummy test items।"
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

    current_balance = db.get_balance(
        query.from_user.id
    )

    await query.message.reply_text(
        f"💳 Balance: ৳{current_balance:.2f}",
        reply_markup=main_menu(
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

    payment = db.get_payment_info()

    lines = [
        "💰 Deposit",
        "",
        "Admin-এর payment number-এ payment করুন।",
        "",
    ]

    if payment["bkash"]:
        lines.append(
            f"🟣 bKash: {payment['bkash']}"
        )

    if payment["nagad"]:
        lines.append(
            f"🟠 Nagad: {payment['nagad']}"
        )

    if (
        not payment["bkash"]
        and not payment["nagad"]
    ):
        lines.append(
            "⚠️ এখনো কোনো payment number "
            "set করা হয়নি।"
        )

    lines.extend(
        [
            "",
            "কত টাকা deposit করবেন লিখুন।",
            "/cancel",
        ]
    )

    await query.message.reply_text(
        "\n".join(lines)
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

    except (InvalidOperation, ValueError):

        await update.message.reply_text(
            "❌ Valid amount দিন।"
        )

        return DEPOSIT_AMOUNT

    context.user_data[
        "deposit_amount"
    ] = str(amount)

    await update.message.reply_text(
        "Payment method + number + TrxID দিন।\n\n"
        "উদাহরণ:\n"
        "bKash | 01XXXXXXXXX | TRX123\n\n"
        "/cancel"
    )

    return DEPOSIT_DETAILS


async def deposit_details(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    amount_text = context.user_data.pop(
        "deposit_amount",
        None,
    )

    if not amount_text:

        await update.message.reply_text(
            "❌ Deposit session expired।"
        )

        return ConversationHandler.END

    amount = Decimal(amount_text)

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
        (
            f"💰 New Deposit #{deposit_id}\n\n"
            f"User ID: {update.effective_user.id}\n"
            f"Amount: ৳{amount:.2f}\n"
            f"Details: {details}"
        ),
        reply_markup=keyboard,
    )

    await update.message.reply_text(
        "✅ Deposit submitted.\n\n"
        "Admin review-এর অপেক্ষায় আছে।",
        reply_markup=main_menu(
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

    except (InvalidOperation, ValueError):

        await update.message.reply_text(
            "❌ Valid amount দিন।"
        )

        return WITHDRAW_AMOUNT

    current_balance = db.get_balance(
        update.effective_user.id
    )

    if current_balance < amount:

        await update.message.reply_text(
            "❌ আপনার balance যথেষ্ট নয়।"
        )

        return ConversationHandler.END

    context.user_data[
        "withdraw_amount"
    ] = str(amount)

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

    amount_text = context.user_data.pop(
        "withdraw_amount",
        None,
    )

    if not amount_text:

        await update.message.reply_text(
            "❌ Withdrawal session expired।"
        )

        return ConversationHandler.END

    amount = Decimal(amount_text)

    details = update.message.text.strip()

    try:

        withdrawal_id = db.create_withdrawal(
            update.effective_user.id,
            amount,
            details,
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Balance আর যথেষ্ট নেই।"
        )

        return ConversationHandler.END

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
        (
            f"💸 New Withdrawal #{withdrawal_id}\n\n"
            f"User ID: {update.effective_user.id}\n"
            f"Amount: ৳{amount:.2f}\n"
            f"Details: {details}"
        ),
        reply_markup=keyboard,
    )

    await update.message.reply_text(
        "✅ Withdrawal submitted.\n\n"
        "Admin review-এর অপেক্ষায় আছে।",
        reply_markup=main_menu(
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

    url = support_url()

    if url:

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "👨‍💻 Contact Support",
                        url=url,
                    )
                ]
            ]
        )

        await query.message.reply_text(
            "🎧 Support\n\n"
            "যেকোনো সমস্যায় যোগাযোগ করুন।",
            reply_markup=keyboard,
        )

    else:

        await query.message.reply_text(
            "🎧 Support username .env-এ "
            "set করা হয়নি।"
        )


# =========================================================
# USER ORDERS / TRANSACTIONS
# =========================================================

async def simple_info(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    user_id = query.from_user.id

    if query.data == "orders":
        data = db.user_orders(user_id)
    else:
        data = db.transactions(user_id)

    await query.message.reply_text(
        data or "কোনো record নেই।",
        reply_markup=main_menu(user_id),
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

    if query.from_user.id != ADMIN_ID:
        return

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
        f"💰 Current Price: ৳{db.get_price():.2f}\n\n"
        "নতুন price লিখুন।\n\n"
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

    except (InvalidOperation, ValueError):

        await update.message.reply_text(
            "❌ Valid price দিন।"
        )

        return PRICE

    db.set_price(price)

    await update.message.reply_text(
        f"✅ Price updated.\n\n"
        f"New Price: ৳{price:.2f}",
        reply_markup=admin_menu(),
    )

    return ConversationHandler.END


# =========================================================
# ADMIN TEST STOCK
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
        "📦 কতটি dummy test item add করবেন?\n\n"
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
        f"✅ Added: {quantity} test items\n\n"
        f"📦 Current Stock: {db.stock_count()}",
        reply_markup=admin_menu(),
    )

    return ConversationHandler.END


# =========================================================
# ADMIN PAYMENT SETTINGS
# =========================================================

async def admin_payment_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return ConversationHandler.END

    payment = db.get_payment_info()

    await query.message.reply_text(
        "💳 Payment Settings\n\n"
        f"🟣 Current bKash: "
        f"{payment['bkash'] or 'Not set'}\n"
        f"🟠 Current Nagad: "
        f"{payment['nagad'] or 'Not set'}\n\n"
        "নতুন bKash number লিখুন।\n"
        "Number remove করতে NONE লিখুন।\n\n"
        "/cancel"
    )

    return PAYMENT_BKASH


async def admin_payment_bkash(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    value = update.message.text.strip()

    if value.upper() == "NONE":
        value = ""

    db.set_setting(
        "bkash_number",
        value,
    )

    await update.message.reply_text(
        "🟠 এখন Nagad number লিখুন।\n\n"
        "Number remove করতে NONE লিখুন।\n\n"
        "/cancel"
    )

    return PAYMENT_NAGAD


async def admin_payment_nagad(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    value = update.message.text.strip()

    if value.upper() == "NONE":
        value = ""

    db.set_setting(
        "nagad_number",
        value,
    )

    payment = db.get_payment_info()

    await update.message.reply_text(
        "✅ Payment settings saved.\n\n"
        f"🟣 bKash: "
        f"{payment['bkash'] or 'Not set'}\n"
        f"🟠 Nagad: "
        f"{payment['nagad'] or 'Not set'}",
        reply_markup=admin_menu(),
    )

    return ConversationHandler.END


# =========================================================
# ADMIN LISTS
# =========================================================

async def admin_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    kind = query.data

    if kind == "admin_deposits":

        rows = db.pending_list("deposits")

        if not rows:

            text = "📥 No pending deposits."

        else:

            text = (
                "📥 Pending Deposits\n\n"
                +
                "\n\n".join(
                    (
                        f"#{row['id']}\n"
                        f"User: {row['user_id']}\n"
                        f"Amount: ৳{row['amount']:.2f}\n"
                        f"Details: {row['details']}"
                    )
                    for row in rows
                )
            )

    elif kind == "admin_withdrawals":

        rows = db.pending_list("withdrawals")

        if not rows:

            text = "📤 No pending withdrawals."

        else:

            text = (
                "📤 Pending Withdrawals\n\n"
                +
                "\n\n".join(
                    (
                        f"#{row['id']}\n"
                        f"User: {row['user_id']}\n"
                        f"Amount: ৳{row['amount']:.2f}\n"
                        f"Details: {row['details']}"
                    )
                    for row in rows
                )
            )

    elif kind == "admin_sells":

        rows = db.pending_list("sell_requests")

        if not rows:

            text = "📧 No pending sell requests."

        else:

            text = (
                "📧 Pending Sell Requests\n\n"
                +
                "\n\n".join(
                    (
                        f"#{row['id']}\n"
                        f"User: {row['user_id']}\n"
                        f"Item: {row['test_email']}\n"
                        f"Amount: ৳{row['amount']:.2f}"
                    )
                    for row in rows
                )
            )

    else:

        rows = db.recent_orders()

        if not rows:

            text = "🛒 No orders yet."

        else:

            text = (
                "🛒 Recent Orders\n\n"
                +
                "\n\n".join(
                    (
                        f"#{row['id']}\n"
                        f"User: {row['user_id']}\n"
                        f"Quantity: {row['qty']}\n"
                        f"Total: ৳{row['total']:.2f}\n"
                        f"Status: {row['status']}"
                    )
                    for row in rows
                )
            )

    await query.message.reply_text(
        text,
        reply_markup=back_admin_markup(),
    )


# =========================================================
# ADMIN BROADCAST
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
        "📢 Broadcast message লিখুন।\n\n"
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
                chat_id=user_id,
                text=update.message.text,
            )

            success += 1

        except Exception as error:

            log.warning(
                "Broadcast failed for %s: %s",
                user_id,
                error,
            )

    await update.message.reply_text(
        f"📢 Broadcast complete.\n\n"
        f"Success: {success}\n"
        f"Total: {len(users)}",
        reply_markup=admin_menu(),
    )

    return ConversationHandler.END


# =========================================================
# ADMIN APPROVE / REJECT
# =========================================================

async def admin_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    try:

        action, request_id = query.data.split(":")

        request_id = int(request_id)

    except Exception:

        await query.edit_message_text(
            "❌ Invalid admin action."
        )

        return

    success = False
    user_id = None
    amount = Decimal("0")
    result_text = "Unknown"

    if action == "approve_sell":

        success, user_id, amount = db.approve_sell(
            request_id,
            True,
        )

        result_text = (
            "✅ Approved"
            if success
            else "⚠️ Already processed"
        )

    elif action == "reject_sell":

        success, user_id, amount = db.approve_sell(
            request_id,
            False,
        )

        result_text = (
            "❌ Rejected"
            if success
            else "⚠️ Already processed"
        )

    elif action == "approve_dep":

        success, user_id, amount = db.approve_deposit(
            request_id,
            True,
        )

        result_text = (
            "✅ Approved"
            if success
            else "⚠️ Already processed"
        )

    elif action == "reject_dep":

        success, user_id, amount = db.approve_deposit(
            request_id,
            False,
        )

        result_text = (
            "❌ Rejected"
            if success
            else "⚠️ Already processed"
        )

    elif action == "approve_wd":

        success, user_id, amount = db.approve_withdrawal(
            request_id,
            True,
        )

        result_text = (
            "✅ Approved"
            if success
            else "⚠️ Already processed"
        )

    elif action == "reject_wd":

        success, user_id, amount = db.approve_withdrawal(
            request_id,
            False,
        )

        result_text = (
            "❌ Rejected"
            if success
            else "⚠️ Already processed"
        )

    else:

        await query.edit_message_text(
            "❌ Unknown action."
        )

        return

    await query.edit_message_text(
        f"Request #{request_id}\n\n"
        f"{result_text}"
    )

    if success and user_id:

        try:

            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"📌 Request #{request_id}\n\n"
                    f"{result_text}\n"
                    f"Amount: ৳{amount:.2f}"
                ),
            )

        except Exception as error:

            log.warning(
                "User notification failed: %s",
                error,
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
        "এই botটি TEST/learning environment-এর জন্য।\n\n"
        "⚠️ Real Gmail password বা recovery "
        "কখনো পাঠাবেন না।\n\n"
        "/start দিয়ে Main Menu খুলুন।"
    )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    log.error(
        "Unhandled exception while processing update:",
        exc_info=context.error,
    )


# =========================================================
# MAIN APPLICATION
# =========================================================

def main():

    log.info("Initializing database...")

    db.init_db()

    log.info("Creating Telegram application...")

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # -----------------------------------------------------
    # SELL
    # -----------------------------------------------------

    sell_conversation = ConversationHandler(
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

    buy_conversation = ConversationHandler(
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

    deposit_conversation = ConversationHandler(
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

    withdraw_conversation = ConversationHandler(
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
    # ADMIN PRICE
    # -----------------------------------------------------

    price_conversation = ConversationHandler(
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
    # ADMIN STOCK
    # -----------------------------------------------------

    stock_conversation = ConversationHandler(
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
    # ADMIN PAYMENT SETTINGS
    # -----------------------------------------------------

    payment_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                admin_payment_start,
                "^admin_payment$",
            )
        ],
        states={
            PAYMENT_BKASH: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    admin_payment_bkash,
                )
            ],
            PAYMENT_NAGAD: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    admin_payment_nagad,
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
    # BROADCAST
    # -----------------------------------------------------

    broadcast_conversation = ConversationHandler(
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

    application.add_handler(
        sell_conversation
    )

    application.add_handler(
        buy_conversation
    )

    application.add_handler(
        deposit_conversation
    )

    application.add_handler(
        withdraw_conversation
    )

    application.add_handler(
        price_conversation
    )

    application.add_handler(
        stock_conversation
    )

    application.add_handler(
        payment_conversation
    )

    application.add_handler(
        broadcast_conversation
    )

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
            admin_list,
            "^(admin_deposits|admin_withdrawals|admin_sells|admin_orders)$",
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            admin_action,
            r"^(approve_sell|reject_sell|approve_dep|reject_dep|approve_wd|reject_wd):\d+$",
        )
    )

    # =====================================================
    # ERROR HANDLER
    # =====================================================

    application.add_error_handler(
        error_handler
    )

    # =====================================================
    # START BOT
    # =====================================================

    log.info(
        "========================================"
    )

    log.info(
        "Telegram bot starting..."
    )

    log.info(
        "python-telegram-bot polling mode enabled."
    )

    log.info(
        "========================================"
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":
    main()
