"""
TaskVanta - Telegram Task & Rewards Bot (DEMO/TEST environment)

Entry point. Run with: python main.py
Requires BOT_TOKEN set in the environment (see .env.example).
"""

import logging
import sys

from telegram.ext import Application, CommandHandler, CallbackQueryHandler

import database as db
from config import BOT_TOKEN
import handlers_user as user_h
import handlers_admin as admin_h

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("taskvanta")


def build_application() -> Application:
    application = Application.builder().token(BOT_TOKEN).build()

    # --- Core commands ---
    application.add_handler(CommandHandler("start", user_h.start))
    application.add_handler(CommandHandler("help", user_h.help_command))
    application.add_handler(CommandHandler("admin", admin_h.admin_command))

    # --- Conversations (must be added before the generic callback catch-alls) ---
    application.add_handler(user_h.get_withdraw_conversation_handler())
    application.add_handler(admin_h.get_add_task_conversation_handler())
    application.add_handler(admin_h.get_edit_task_conversation_handler())

    # --- Withdrawal confirmation (plain callback, outside the conversation) ---
    application.add_handler(
        CallbackQueryHandler(user_h.withdraw_confirm_callback, pattern="^withdraw:(confirm|cancel)$")
    )

    # --- User menu / task callbacks ---
    application.add_handler(CallbackQueryHandler(user_h.menu_callback, pattern="^menu:"))
    application.add_handler(CallbackQueryHandler(user_h.task_callback, pattern="^task:"))

    # --- Admin callbacks ---
    application.add_handler(CallbackQueryHandler(admin_h.admin_menu_callback, pattern="^admin:menu$"))
    application.add_handler(CallbackQueryHandler(admin_h.admin_stats_callback, pattern="^admin:stats$"))
    application.add_handler(CallbackQueryHandler(admin_h.admin_tasks_list_callback, pattern="^admin:tasks$"))
    application.add_handler(CallbackQueryHandler(admin_h.admin_task_view_callback, pattern=r"^admin:task:view:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_h.admin_task_toggle_callback, pattern=r"^admin:task:toggle:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_h.admin_task_qual_callback, pattern=r"^admin:task:qual:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_h.admin_task_delconfirm_callback, pattern=r"^admin:task:delconfirm:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_h.admin_task_delete_callback, pattern=r"^admin:task:delete:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_h.admin_newtask_qual_callback, pattern=r"^admin:newtask:qual:(0|1)$"))
    application.add_handler(CallbackQueryHandler(admin_h.admin_users_callback, pattern=r"^admin:users:\d+$"))
    application.add_handler(CallbackQueryHandler(admin_h.admin_withdrawals_callback, pattern="^admin:withdrawals$"))
    application.add_handler(CallbackQueryHandler(admin_h.admin_withdrawal_view_callback, pattern=r"^admin:withdrawal:view:\d+$"))
    application.add_handler(
        CallbackQueryHandler(
            admin_h.admin_withdrawal_action_callback,
            pattern=r"^admin:withdrawal:(approve|reject|paid):\d+$",
        )
    )

    return application


def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")
        sys.exit(1)

    logger.info("Initializing database...")
    db.init_db()

    logger.info("Starting TaskVanta bot (polling mode)...")
    application = build_application()
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
