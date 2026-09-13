"""
TaskVanta - Inline keyboard builders.
Keeping all callback_data strings centralized here avoids typos across handlers.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# --------------------------------------------------------------------------
# User-facing keyboards
# --------------------------------------------------------------------------

def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📊 Dashboard", callback_data="menu:dashboard")],
        [InlineKeyboardButton("📋 Tasks", callback_data="menu:tasks")],
        [InlineKeyboardButton("👥 Referral Program", callback_data="menu:referral")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="menu:withdraw")],
        [InlineKeyboardButton("❓ Help", callback_data="menu:help")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:back")]])


def tasks_list_kb(tasks) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"{t['title']}  •  ${t['reward']:.2f}", callback_data=f"task:view:{t['task_id']}")]
        for t in tasks
    ]
    rows.append([InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:back")])
    return InlineKeyboardMarkup(rows)


def task_detail_kb(task_id: int, already_completed: bool) -> InlineKeyboardMarkup:
    rows = []
    if not already_completed:
        rows.append([InlineKeyboardButton("✅ Mark as Completed", callback_data=f"task:complete:{task_id}")])
    rows.append([InlineKeyboardButton("⬅️ Back to Tasks", callback_data="menu:tasks")])
    return InlineKeyboardMarkup(rows)


def withdraw_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Confirm Withdrawal", callback_data="withdraw:confirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="withdraw:cancel")],
        ]
    )


def cancel_kb(target: str = "menu:back") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=target)]])


# --------------------------------------------------------------------------
# Admin keyboards
# --------------------------------------------------------------------------

def admin_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📋 Manage Tasks", callback_data="admin:tasks")],
        [InlineKeyboardButton("👥 Users", callback_data="admin:users:0")],
        [InlineKeyboardButton("💸 Withdrawals", callback_data="admin:withdrawals")],
        [InlineKeyboardButton("📈 Platform Stats", callback_data="admin:stats")],
        [InlineKeyboardButton("⬅️ Main Menu", callback_data="menu:back")],
    ]
    return InlineKeyboardMarkup(rows)


def admin_tasks_list_kb(tasks) -> InlineKeyboardMarkup:
    rows = []
    for t in tasks:
        dot = "🟢" if t["is_active"] else "🔴"
        rows.append([InlineKeyboardButton(f"{dot} {t['title']}", callback_data=f"admin:task:view:{t['task_id']}")])
    rows.append([InlineKeyboardButton("➕ Add New Task", callback_data="admin:task:add")])
    rows.append([InlineKeyboardButton("⬅️ Admin Menu", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


def admin_task_detail_kb(task) -> InlineKeyboardMarkup:
    active_label = "🔴 Deactivate" if task["is_active"] else "🟢 Activate"
    qual_label = "❌ Unmark Qualifying" if task["is_qualifying"] else "✅ Mark Qualifying"
    tid = task["task_id"]
    rows = [
        [InlineKeyboardButton("✏️ Title", callback_data=f"admin:task:edit:title:{tid}"),
         InlineKeyboardButton("✏️ Description", callback_data=f"admin:task:edit:description:{tid}")],
        [InlineKeyboardButton("✏️ Link", callback_data=f"admin:task:edit:link:{tid}"),
         InlineKeyboardButton("✏️ Reward", callback_data=f"admin:task:edit:reward:{tid}")],
        [InlineKeyboardButton(active_label, callback_data=f"admin:task:toggle:{tid}")],
        [InlineKeyboardButton(qual_label, callback_data=f"admin:task:qual:{tid}")],
        [InlineKeyboardButton("🗑 Delete Task", callback_data=f"admin:task:delconfirm:{tid}")],
        [InlineKeyboardButton("⬅️ Back to Tasks", callback_data="admin:tasks")],
    ]
    return InlineKeyboardMarkup(rows)


def admin_confirm_delete_kb(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Yes, delete permanently", callback_data=f"admin:task:delete:{task_id}")],
            [InlineKeyboardButton("❌ No, go back", callback_data=f"admin:task:view:{task_id}")],
        ]
    )


def admin_qualifying_choice_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Yes - counts toward referrals", callback_data="admin:newtask:qual:1")],
            [InlineKeyboardButton("➖ No - does not qualify referrals", callback_data="admin:newtask:qual:0")],
        ]
    )


def admin_withdrawals_kb(withdrawals) -> InlineKeyboardMarkup:
    rows = []
    for w in withdrawals:
        rows.append(
            [InlineKeyboardButton(
                f"#{w['withdrawal_id']} • ${w['amount']:.2f} • {w['status']}",
                callback_data=f"admin:withdrawal:view:{w['withdrawal_id']}",
            )]
        )
    rows.append([InlineKeyboardButton("⬅️ Admin Menu", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


def admin_withdrawal_detail_kb(w) -> InlineKeyboardMarkup:
    rows = []
    if w["status"] == "Pending":
        rows.append(
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"admin:withdrawal:approve:{w['withdrawal_id']}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"admin:withdrawal:reject:{w['withdrawal_id']}"),
            ]
        )
    elif w["status"] == "Approved":
        rows.append(
            [InlineKeyboardButton("💰 Mark as Paid", callback_data=f"admin:withdrawal:paid:{w['withdrawal_id']}")]
        )
    rows.append([InlineKeyboardButton("⬅️ Back to Withdrawals", callback_data="admin:withdrawals")])
    return InlineKeyboardMarkup(rows)


def admin_users_pagination_kb(offset: int, has_more: bool) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin:users:{max(0, offset - 10)}"))
    if has_more:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin:users:{offset + 10}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ Admin Menu", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)
