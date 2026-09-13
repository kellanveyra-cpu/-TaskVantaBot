"""
TaskVanta - Admin-only handlers: task CRUD, user list, withdrawal management, stats.
Every entry point here checks config.is_admin() before doing anything.
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
from config import is_admin, DEFAULT_TASK_REWARD, DEMO_BANNER

logger = logging.getLogger(__name__)

# Conversation states for "add task"
ADD_TITLE, ADD_DESC, ADD_LINK, ADD_REWARD = range(4)
# Conversation state for "edit task field"
EDIT_VALUE = 10


async def _reject_non_admin(update: Update) -> bool:
    """Returns True (and notifies) if the caller is not an admin."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        if update.callback_query:
            await update.callback_query.answer("You are not authorized to use this.", show_alert=True)
        elif update.message:
            await update.message.reply_text("You are not authorized to use this command.")
        return True
    return False


# --------------------------------------------------------------------------
# Admin menu
# --------------------------------------------------------------------------

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    await update.message.reply_text(
        f"🛠 <b>{'Admin Panel'}</b>\n\n{DEMO_BANNER}",
        parse_mode="HTML",
        reply_markup=kb.admin_menu_kb(),
    )


async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        f"🛠 <b>Admin Panel</b>\n\n{DEMO_BANNER}", parse_mode="HTML", reply_markup=kb.admin_menu_kb()
    )


async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    query = update.callback_query
    await query.answer()
    s = db.get_platform_stats()
    text = (
        "📈 <b>Platform Stats</b>\n\n"
        f"👤 Users: <b>{s['total_users']}</b>\n"
        f"📋 Tasks: <b>{s['total_tasks']}</b> ({s['active_tasks']} active)\n"
        f"✅ Task completions: <b>{s['total_completions']}</b>\n"
        f"👥 Referrals: <b>{s['total_referrals']}</b> ({s['rewarded_referrals']} rewarded)\n"
        f"💰 Total rewards paid out: <b>${s['total_paid_out']:.2f}</b>\n"
        f"🏦 Total balance held (owed to users): <b>${s['total_balance_held']:.2f}</b>\n"
        f"⏳ Pending withdrawals: <b>{s['pending_withdrawal_count']}</b> "
        f"(${s['pending_withdrawal_sum']:.2f})\n"
        f"✅ Paid withdrawals: <b>{s['paid_withdrawal_count']}</b> "
        f"(${s['paid_withdrawal_sum']:.2f})\n\n"
        f"{DEMO_BANNER}"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb.admin_menu_kb())


# --------------------------------------------------------------------------
# Task management (list / view / toggle / delete)
# --------------------------------------------------------------------------

async def admin_tasks_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    query = update.callback_query
    await query.answer()
    tasks = db.get_all_tasks(active_only=False)
    if not tasks:
        await query.edit_message_text(
            "No tasks yet. Add your first one!",
            reply_markup=kb.admin_tasks_list_kb([]),
        )
        return
    await query.edit_message_text(
        "📋 <b>Manage Tasks</b>\n🟢 = active   🔴 = inactive",
        parse_mode="HTML",
        reply_markup=kb.admin_tasks_list_kb(tasks),
    )


def _task_detail_text(task) -> str:
    return (
        f"📌 <b>{html.escape(task['title'])}</b>  (ID #{task['task_id']})\n\n"
        f"{html.escape(task['description']) or '—'}\n\n"
        f"🔗 Link: {html.escape(task['link']) or '—'}\n"
        f"💰 Reward: <b>${task['reward']:.2f}</b>\n"
        f"Status: {'🟢 Active' if task['is_active'] else '🔴 Inactive'}\n"
        f"Qualifies referrals: {'✅ Yes' if task['is_qualifying'] else '➖ No'}"
    )


async def admin_task_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split(":")[-1])
    task = db.get_task(task_id)
    if not task:
        await query.edit_message_text("Task not found.", reply_markup=kb.admin_menu_kb())
        return
    await query.edit_message_text(
        _task_detail_text(task), parse_mode="HTML", reply_markup=kb.admin_task_detail_kb(task)
    )


async def admin_task_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    query = update.callback_query
    task_id = int(query.data.split(":")[-1])
    db.toggle_task_active(task_id)
    await query.answer("Status updated.")
    task = db.get_task(task_id)
    await query.edit_message_text(
        _task_detail_text(task), parse_mode="HTML", reply_markup=kb.admin_task_detail_kb(task)
    )


async def admin_task_qual_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    query = update.callback_query
    task_id = int(query.data.split(":")[-1])
    db.toggle_task_qualifying(task_id)
    await query.answer("Updated.")
    task = db.get_task(task_id)
    await query.edit_message_text(
        _task_detail_text(task), parse_mode="HTML", reply_markup=kb.admin_task_detail_kb(task)
    )


async def admin_task_delconfirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split(":")[-1])
    task = db.get_task(task_id)
    if not task:
        await query.edit_message_text("Task not found.", reply_markup=kb.admin_menu_kb())
        return
    await query.edit_message_text(
        f"Delete <b>{html.escape(task['title'])}</b> permanently?\n"
        "This also removes its completion history.",
        parse_mode="HTML",
        reply_markup=kb.admin_confirm_delete_kb(task_id),
    )


async def admin_task_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    query = update.callback_query
    task_id = int(query.data.split(":")[-1])
    db.delete_task(task_id)
    await query.answer("Task deleted.")
    tasks = db.get_all_tasks(active_only=False)
    await query.edit_message_text(
        "🗑 Task deleted.\n\n📋 <b>Manage Tasks</b>",
        parse_mode="HTML",
        reply_markup=kb.admin_tasks_list_kb(tasks),
    )


# --------------------------------------------------------------------------
# Add task conversation
# --------------------------------------------------------------------------

async def admin_add_task_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await _reject_non_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    context.user_data["new_task"] = {}
    await query.edit_message_text(
        "➕ <b>Add New Task</b>\n\nStep 1/4 — Send the task <b>title</b>.\n(/cancel to abort)",
        parse_mode="HTML",
    )
    return ADD_TITLE


async def admin_add_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_task"]["title"] = update.message.text.strip()[:200]
    await update.message.reply_text("Step 2/4 — Send the task <b>description</b>.", parse_mode="HTML")
    return ADD_DESC


async def admin_add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_task"]["description"] = update.message.text.strip()[:2000]
    await update.message.reply_text(
        "Step 3/4 — Send the task <b>link</b> (or send '-' for none).", parse_mode="HTML"
    )
    return ADD_LINK


async def admin_add_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    link = update.message.text.strip()
    context.user_data["new_task"]["link"] = "" if link == "-" else link[:500]
    await update.message.reply_text(
        f"Step 4/4 — Send the <b>reward amount</b> in USD (default is ${DEFAULT_TASK_REWARD:.2f}, "
        "send '-' to use the default).",
        parse_mode="HTML",
    )
    return ADD_REWARD


async def admin_add_reward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    if raw == "-":
        reward = DEFAULT_TASK_REWARD
    else:
        try:
            reward = round(float(raw), 2)
            if reward <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Please send a valid positive number, or '-' for the default.")
            return ADD_REWARD
    context.user_data["new_task"]["reward"] = reward
    await update.message.reply_text(
        "Should completing this task count toward a referral qualifying?",
        reply_markup=kb.admin_qualifying_choice_kb(),
    )
    return ConversationHandler.END  # finished by the callback below


async def admin_newtask_qual_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    query = update.callback_query
    await query.answer()
    is_qualifying = query.data.split(":")[-1] == "1"
    data = context.user_data.pop("new_task", None)
    if not data or "title" not in data:
        await query.edit_message_text("Session expired. Please start again from Admin Panel.")
        return

    task_id = db.create_task(
        title=data["title"],
        description=data.get("description", ""),
        link=data.get("link", ""),
        reward=data.get("reward", DEFAULT_TASK_REWARD),
        is_qualifying=is_qualifying,
    )
    task = db.get_task(task_id)
    await query.edit_message_text(
        f"✅ Task created!\n\n{_task_detail_text(task)}",
        parse_mode="HTML",
        reply_markup=kb.admin_task_detail_kb(task),
    )


async def admin_add_task_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("new_task", None)
    await update.message.reply_text("Cancelled.", reply_markup=kb.admin_menu_kb())
    return ConversationHandler.END


# --------------------------------------------------------------------------
# Edit task field conversation
# --------------------------------------------------------------------------

FIELD_LABELS = {
    "title": "title",
    "description": "description",
    "link": "link",
    "reward": "reward (USD, number only)",
}


async def admin_edit_field_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await _reject_non_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    _, _, _, field, task_id_str = query.data.split(":")
    task_id = int(task_id_str)
    task = db.get_task(task_id)
    if not task:
        await query.edit_message_text("Task not found.", reply_markup=kb.admin_menu_kb())
        return ConversationHandler.END

    context.user_data["edit_task_id"] = task_id
    context.user_data["edit_field"] = field
    await query.edit_message_text(
        f"Send the new <b>{FIELD_LABELS.get(field, field)}</b> for "
        f"'{html.escape(task['title'])}'.\n(/cancel to abort)",
        parse_mode="HTML",
    )
    return EDIT_VALUE


async def admin_edit_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    task_id = context.user_data.get("edit_task_id")
    field = context.user_data.get("edit_field")
    if task_id is None or field is None:
        await update.message.reply_text("Session expired. Please start again from Admin Panel.")
        return ConversationHandler.END

    raw = update.message.text.strip()
    if field == "reward":
        try:
            value = round(float(raw), 2)
            if value <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Please send a valid positive number.")
            return EDIT_VALUE
    else:
        value = raw[:2000]

    db.update_task_field(task_id, field, value)
    context.user_data.pop("edit_task_id", None)
    context.user_data.pop("edit_field", None)

    task = db.get_task(task_id)
    await update.message.reply_text(
        f"✅ Updated!\n\n{_task_detail_text(task)}",
        parse_mode="HTML",
        reply_markup=kb.admin_task_detail_kb(task),
    )
    return ConversationHandler.END


async def admin_edit_field_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("edit_task_id", None)
    context.user_data.pop("edit_field", None)
    await update.message.reply_text("Cancelled.", reply_markup=kb.admin_menu_kb())
    return ConversationHandler.END


# --------------------------------------------------------------------------
# Users list
# --------------------------------------------------------------------------

async def admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    query = update.callback_query
    await query.answer()
    offset = int(query.data.split(":")[-1])
    page_size = 10
    users = db.get_all_users(limit=page_size, offset=offset)
    total = db.count_users()

    if not users:
        await query.edit_message_text("No users found.", reply_markup=kb.admin_menu_kb())
        return

    lines = [f"👥 <b>Users</b> ({total} total)\n"]
    for u in users:
        uname = f"@{u['username']}" if u["username"] else "(no username)"
        lines.append(
            f"• <code>{u['user_id']}</code> {html.escape(uname)} — "
            f"${u['balance']:.2f} — completed {db.count_user_completions(u['user_id'])}"
        )
    has_more = offset + page_size < total
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=kb.admin_users_pagination_kb(offset, has_more),
    )


# --------------------------------------------------------------------------
# Withdrawals management
# --------------------------------------------------------------------------

async def admin_withdrawals_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    query = update.callback_query
    await query.answer()
    withdrawals = db.get_all_withdrawals(limit=50)
    if not withdrawals:
        await query.edit_message_text("No withdrawal requests yet.", reply_markup=kb.admin_menu_kb())
        return
    await query.edit_message_text(
        "💸 <b>Withdrawal Requests</b>",
        parse_mode="HTML",
        reply_markup=kb.admin_withdrawals_kb(withdrawals),
    )


def _withdrawal_detail_text(w, user) -> str:
    uname = f"@{user['username']}" if user and user["username"] else "(no username)"
    return (
        f"💸 <b>Withdrawal #{w['withdrawal_id']}</b>\n\n"
        f"User: <code>{w['user_id']}</code> {html.escape(uname)}\n"
        f"Amount: <b>${w['amount']:.2f}</b>\n"
        f"Wallet (TRC20): <code>{html.escape(w['wallet_address'])}</code>\n"
        f"Status: <b>{w['status']}</b>\n"
        f"Requested: {w['created_at']}\n"
        f"Processed: {w['processed_at'] or '—'}\n\n"
        f"{DEMO_BANNER}"
    )


async def admin_withdrawal_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    query = update.callback_query
    await query.answer()
    wid = int(query.data.split(":")[-1])
    w = db.get_withdrawal(wid)
    if not w:
        await query.edit_message_text("Withdrawal not found.", reply_markup=kb.admin_menu_kb())
        return
    user = db.get_user(w["user_id"])
    await query.edit_message_text(
        _withdrawal_detail_text(w, user), parse_mode="HTML", reply_markup=kb.admin_withdrawal_detail_kb(w)
    )


async def admin_withdrawal_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _reject_non_admin(update):
        return
    query = update.callback_query
    parts = query.data.split(":")  # admin:withdrawal:approve:<id>
    action = parts[2]
    wid = int(parts[3])

    status_map = {"approve": "Approved", "reject": "Rejected", "paid": "Paid"}
    new_status = status_map.get(action)
    try:
        db.set_withdrawal_status(wid, new_status)
        await query.answer(f"Marked as {new_status}.")
    except ValueError as e:
        await query.answer(str(e), show_alert=True)

    w = db.get_withdrawal(wid)
    user = db.get_user(w["user_id"])
    await query.edit_message_text(
        _withdrawal_detail_text(w, user), parse_mode="HTML", reply_markup=kb.admin_withdrawal_detail_kb(w)
    )


# --------------------------------------------------------------------------
# Handler registration helpers (imported by main.py)
# --------------------------------------------------------------------------

def get_add_task_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_task_entry, pattern="^admin:task:add$")],
        states={
            ADD_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_title)],
            ADD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_desc)],
            ADD_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_link)],
            ADD_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_reward)],
        },
        fallbacks=[CommandHandler("cancel", admin_add_task_cancel)],
        name="admin_add_task_conversation",
        persistent=False,
    )


def get_edit_task_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_edit_field_entry, pattern=r"^admin:task:edit:(title|description|link|reward):\d+$")
        ],
        states={
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_field_value)],
        },
        fallbacks=[CommandHandler("cancel", admin_edit_field_cancel)],
        name="admin_edit_task_conversation",
        persistent=False,
    )
