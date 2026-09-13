"""
TaskVanta - User-facing handlers: /start, dashboard, tasks, referrals, withdrawal flow.
"""

import html
import logging

from telegram import Update
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

import database as db
import keyboards as kb
from config import (
    is_admin,
    BOT_USERNAME,
    MIN_WITHDRAWAL,
    REFERRAL_REWARD,
    DEMO_BANNER,
    PROJECT_NAME,
)

logger = logging.getLogger(__name__)

# Conversation state for the withdrawal flow
ASK_WALLET = 1


def referral_link(user_id: int) -> str:
    if BOT_USERNAME:
        return f"https://t.me/{BOT_USERNAME}?start={user_id}"
    return f"(set BOT_USERNAME in your .env to generate a real link) start param: {user_id}"


# --------------------------------------------------------------------------
# /start
# --------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    referred_by = None
    if context.args:
        try:
            candidate = int(context.args[0])
            if candidate != user.id:
                referred_by = candidate
        except ValueError:
            pass

    _, is_new = db.get_or_create_user(user.id, user.username or "", user.first_name or "", referred_by)

    greeting = (
        f"👋 Welcome to <b>{PROJECT_NAME}</b>, {html.escape(user.first_name or 'there')}!\n\n"
        f"{DEMO_BANNER}\n\n"
        "Complete simple tasks to earn rewards, invite friends for bonuses, "
        "and track everything from your dashboard below."
    )
    if is_new and referred_by:
        greeting += "\n\n🎉 You joined using a referral link!"

    await update.message.reply_text(
        greeting,
        parse_mode="HTML",
        reply_markup=kb.main_menu_kb(is_admin(user.id)),
        disable_web_page_preview=True,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        help_text(),
        parse_mode="HTML",
        reply_markup=kb.main_menu_kb(is_admin(update.effective_user.id)),
    )


def help_text() -> str:
    return (
        f"{DEMO_BANNER}\n\n"
        "<b>How TaskVanta works</b>\n"
        "• Open <b>Tasks</b> and complete any active task to earn its reward.\n"
        "• Share your referral link from <b>Referral Program</b> — you earn "
        f"${REFERRAL_REWARD:.2f} once your invitee completes a qualifying task.\n"
        f"• Once your balance reaches ${MIN_WITHDRAWAL:.2f}, you can request a withdrawal "
        "to a USDT (TRC20) wallet address.\n\n"
        "Commands: /start /help"
    )


# --------------------------------------------------------------------------
# Main menu callback router
# --------------------------------------------------------------------------

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action = query.data.split(":", 1)[1]
    user_id = update.effective_user.id

    if action == "back":
        await query.edit_message_text(
            f"<b>{PROJECT_NAME} Main Menu</b>\n\n{DEMO_BANNER}",
            parse_mode="HTML",
            reply_markup=kb.main_menu_kb(is_admin(user_id)),
        )
    elif action == "dashboard":
        await show_dashboard(query, user_id)
    elif action == "tasks":
        await show_tasks(query)
    elif action == "referral":
        await show_referral(query, user_id)
    elif action == "help":
        await query.edit_message_text(
            help_text(), parse_mode="HTML", reply_markup=kb.back_to_menu_kb()
        )
    elif action == "withdraw":
        # Handled by the ConversationHandler entry point (withdraw_entry) below;
        # if it reaches here it means the amount check failed inline.
        await withdraw_entry(update, context)


async def show_dashboard(query, user_id: int) -> None:
    user = db.get_user(user_id)
    balance = user["balance"] if user else 0.0
    completed = db.count_user_completions(user_id)
    referrals = db.get_referral_count(user_id)
    qualified_refs = db.get_qualified_referral_count(user_id)

    text = (
        "📊 <b>Your Dashboard</b>\n\n"
        f"💰 Balance: <b>${balance:.2f}</b>\n"
        f"✅ Tasks Completed: <b>{completed}</b>\n"
        f"👥 Total Referrals: <b>{referrals}</b>\n"
        f"🏆 Rewarded Referrals: <b>{qualified_refs}</b>\n"
        f"🎯 Minimum Withdrawal: <b>${MIN_WITHDRAWAL:.2f}</b>\n\n"
        f"{DEMO_BANNER}"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb.back_to_menu_kb())


async def show_tasks(query) -> None:
    tasks = db.get_all_tasks(active_only=True)
    if not tasks:
        await query.edit_message_text(
            "📋 No active tasks right now. Check back soon!",
            reply_markup=kb.back_to_menu_kb(),
        )
        return
    await query.edit_message_text(
        "📋 <b>Available Tasks</b>\nTap a task to view details and complete it.",
        parse_mode="HTML",
        reply_markup=kb.tasks_list_kb(tasks),
    )


async def show_referral(query, user_id: int) -> None:
    link = referral_link(user_id)
    referrals = db.get_referral_count(user_id)
    qualified = db.get_qualified_referral_count(user_id)
    text = (
        "👥 <b>Referral Program</b>\n\n"
        f"Earn <b>${REFERRAL_REWARD:.2f}</b> for every friend who joins with your link "
        "and completes at least one qualifying task.\n\n"
        f"🔗 Your link:\n<code>{html.escape(link)}</code>\n\n"
        f"👤 Total invited: <b>{referrals}</b>\n"
        f"💵 Rewarded so far: <b>{qualified}</b>"
    )
    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=kb.back_to_menu_kb(), disable_web_page_preview=True
    )


# --------------------------------------------------------------------------
# Task viewing & completion
# --------------------------------------------------------------------------

async def task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, task_id_str = query.data.split(":")
    task_id = int(task_id_str)
    user_id = update.effective_user.id

    task = db.get_task(task_id)
    if not task or not task["is_active"]:
        await query.edit_message_text(
            "This task is no longer available.", reply_markup=kb.back_to_menu_kb()
        )
        return

    if action == "view":
        already = db.has_completed_task(user_id, task_id)
        status_line = "\n\n✅ <i>You already completed this task.</i>" if already else ""
        text = (
            f"📌 <b>{html.escape(task['title'])}</b>\n\n"
            f"{html.escape(task['description'])}\n\n"
            f"🔗 Link: {html.escape(task['link']) if task['link'] else '—'}\n"
            f"💰 Reward: <b>${task['reward']:.2f}</b>"
            f"{status_line}"
        )
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=kb.task_detail_kb(task_id, already),
            disable_web_page_preview=True,
        )

    elif action == "complete":
        result = db.complete_task(user_id, task_id)
        if not result["ok"]:
            reasons = {
                "duplicate": "You've already completed this task and can't be rewarded twice.",
                "inactive": "This task was deactivated.",
                "not_found": "Task not found.",
            }
            await query.answer(reasons.get(result["reason"], "Could not complete task."), show_alert=True)
            already = db.has_completed_task(user_id, task_id)
            await query.edit_message_reply_markup(reply_markup=kb.task_detail_kb(task_id, already))
            return

        msg = f"🎉 Task completed! ${result['reward']:.2f} added to your balance."
        if result.get("referral_credited"):
            msg += "\n(Your referrer just earned their bonus too!)"
        await query.answer(msg, show_alert=True)
        await query.edit_message_text(
            f"📌 <b>{html.escape(task['title'])}</b>\n\n✅ Completed — ${task['reward']:.2f} credited!",
            parse_mode="HTML",
            reply_markup=kb.task_detail_kb(task_id, True),
        )


# --------------------------------------------------------------------------
# Withdrawal conversation
# --------------------------------------------------------------------------

async def withdraw_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    balance = db.get_balance(user_id)

    if balance < MIN_WITHDRAWAL:
        await query.edit_message_text(
            "💸 <b>Withdraw</b>\n\n"
            f"Your balance: <b>${balance:.2f}</b>\n"
            f"Minimum withdrawal: <b>${MIN_WITHDRAWAL:.2f}</b>\n\n"
            "Keep completing tasks and inviting friends to reach the minimum!",
            parse_mode="HTML",
            reply_markup=kb.back_to_menu_kb(),
        )
        return ConversationHandler.END

    context.user_data["withdraw_balance"] = balance
    await query.edit_message_text(
        "💸 <b>Withdraw Funds</b>\n\n"
        f"Available balance: <b>${balance:.2f}</b>\n\n"
        "Please send your <b>USDT (TRC20)</b> wallet address to withdraw your "
        "<u>full available balance</u>.\n\n"
        f"{DEMO_BANNER}",
        parse_mode="HTML",
        reply_markup=kb.cancel_kb("menu:back"),
    )
    return ASK_WALLET


def _looks_like_trc20(address: str) -> bool:
    # TRC20 (TRON) addresses start with 'T' and are 34 characters, base58.
    return address.startswith("T") and 30 <= len(address) <= 40 and address.isalnum()


async def withdraw_wallet_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    address = update.message.text.strip()
    user_id = update.effective_user.id

    if not _looks_like_trc20(address):
        await update.message.reply_text(
            "⚠️ That doesn't look like a valid USDT TRC20 address (should start with "
            "'T' and be ~34 characters). Please try again, or press Cancel below.",
            reply_markup=kb.cancel_kb("menu:back"),
        )
        return ASK_WALLET

    balance = db.get_balance(user_id)
    if balance < MIN_WITHDRAWAL:
        await update.message.reply_text(
            "Your balance dropped below the minimum withdrawal before you finished this "
            "request. Please try again later.",
            reply_markup=kb.back_to_menu_kb(),
        )
        return ConversationHandler.END

    context.user_data["withdraw_address"] = address
    context.user_data["withdraw_amount"] = balance
    await update.message.reply_text(
        "Please confirm your withdrawal request:\n\n"
        f"💰 Amount: <b>${balance:.2f}</b>\n"
        f"👛 Wallet (TRC20): <code>{html.escape(address)}</code>\n\n"
        f"{DEMO_BANNER}",
        parse_mode="HTML",
        reply_markup=kb.withdraw_confirm_kb(),
    )
    return ConversationHandler.END  # confirmation is handled by a plain CallbackQueryHandler below


async def withdraw_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if query.data == "withdraw:cancel":
        context.user_data.pop("withdraw_address", None)
        context.user_data.pop("withdraw_amount", None)
        await query.edit_message_text(
            "Withdrawal cancelled.", reply_markup=kb.back_to_menu_kb()
        )
        return

    address = context.user_data.pop("withdraw_address", None)
    amount = context.user_data.pop("withdraw_amount", None)
    if not address or not amount:
        await query.edit_message_text(
            "This withdrawal request expired. Please start again from the menu.",
            reply_markup=kb.back_to_menu_kb(),
        )
        return

    try:
        wid = db.create_withdrawal(user_id, amount, address)
    except ValueError:
        await query.edit_message_text(
            "Insufficient balance to complete this withdrawal.",
            reply_markup=kb.back_to_menu_kb(),
        )
        return

    await query.edit_message_text(
        f"✅ Withdrawal request <b>#{wid}</b> submitted for <b>${amount:.2f}</b>.\n"
        "Status: <b>Pending</b>\n\n"
        "An admin will review this request. You'll see the updated status on your dashboard.\n\n"
        f"{DEMO_BANNER}",
        parse_mode="HTML",
        reply_markup=kb.back_to_menu_kb(),
    )


async def withdraw_cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Cancelled.", reply_markup=kb.main_menu_kb(is_admin(update.effective_user.id))
    )
    return ConversationHandler.END


# --------------------------------------------------------------------------
# Handler registration helpers (imported by main.py)
# --------------------------------------------------------------------------

def get_withdraw_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(withdraw_entry, pattern="^menu:withdraw$")],
        states={
            ASK_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_wallet_received)],
        },
        fallbacks=[CommandHandler("cancel", withdraw_cancel_command)],
        name="withdraw_conversation",
        persistent=False,
    )
