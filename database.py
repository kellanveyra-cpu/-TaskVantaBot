"""
TaskVanta - Database layer (SQLite)

All persistence lives here. Every public function opens its own short-lived
connection via get_db(), which commits on success and rolls back on error.
This keeps writes atomic per-call, which is what prevents duplicate task
rewards and duplicate referral rewards (see complete_task()).
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from config import DB_PATH, REFERRAL_REWARD


# --------------------------------------------------------------------------
# Connection helper
# --------------------------------------------------------------------------

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables if they do not already exist. Safe to call every boot."""
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id      INTEGER PRIMARY KEY,
                username     TEXT,
                first_name   TEXT,
                balance      REAL NOT NULL DEFAULT 0,
                referred_by  INTEGER,
                joined_at    TEXT NOT NULL,
                FOREIGN KEY (referred_by) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS tasks (
                task_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                title         TEXT NOT NULL,
                description   TEXT NOT NULL DEFAULT '',
                link          TEXT NOT NULL DEFAULT '',
                reward        REAL NOT NULL DEFAULT 1.0,
                is_active     INTEGER NOT NULL DEFAULT 1,
                is_qualifying INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_completions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                task_id      INTEGER NOT NULL,
                reward       REAL NOT NULL,
                completed_at TEXT NOT NULL,
                UNIQUE(user_id, task_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            );

            CREATE TABLE IF NOT EXISTS referrals (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id  INTEGER NOT NULL,
                referred_id  INTEGER NOT NULL UNIQUE,
                reward_given INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT NOT NULL,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS withdrawals (
                withdrawal_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL,
                amount         REAL NOT NULL,
                wallet_address TEXT NOT NULL,
                status         TEXT NOT NULL DEFAULT 'Pending',
                created_at     TEXT NOT NULL,
                processed_at   TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                type        TEXT NOT NULL,
                amount      REAL NOT NULL,
                description TEXT,
                created_at  TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_tc_user ON task_completions(user_id);
            CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id);
            CREATE INDEX IF NOT EXISTS idx_wd_user ON withdrawals(user_id);
            CREATE INDEX IF NOT EXISTS idx_wd_status ON withdrawals(status);
            """
        )


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------

def get_user(user_id: int):
    with get_db() as db:
        return db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def get_or_create_user(user_id: int, username: str, first_name: str, referred_by: int = None):
    """
    Ensures a user row exists. If this is a brand-new user and a valid
    referrer was passed (from a /start deep link), records the referral.
    Returns (user_row, is_new_user).
    """
    with get_db() as db:
        existing = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if existing:
            db.execute(
                "UPDATE users SET username=?, first_name=? WHERE user_id=?",
                (username, first_name, user_id),
            )
            row = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            return row, False

        valid_referrer = None
        if referred_by and referred_by != user_id:
            ref_row = db.execute("SELECT user_id FROM users WHERE user_id=?", (referred_by,)).fetchone()
            if ref_row:
                valid_referrer = referred_by

        db.execute(
            "INSERT INTO users (user_id, username, first_name, balance, referred_by, joined_at) "
            "VALUES (?, ?, ?, 0, ?, ?)",
            (user_id, username, first_name, valid_referrer, _now()),
        )

        if valid_referrer:
            db.execute(
                "INSERT INTO referrals (referrer_id, referred_id, reward_given, created_at) "
                "VALUES (?, ?, 0, ?)",
                (valid_referrer, user_id, _now()),
            )

        row = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row, True


def get_balance(user_id: int) -> float:
    row = get_user(user_id)
    return row["balance"] if row else 0.0


def get_all_users(limit: int = 50, offset: int = 0):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM users ORDER BY joined_at DESC LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()


def count_users() -> int:
    with get_db() as db:
        return db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]


# --------------------------------------------------------------------------
# Tasks (admin CRUD)
# --------------------------------------------------------------------------

def create_task(title: str, description: str, link: str, reward: float, is_qualifying: bool = True) -> int:
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO tasks (title, description, link, reward, is_active, is_qualifying, created_at) "
            "VALUES (?, ?, ?, ?, 1, ?, ?)",
            (title, description, link, reward, int(is_qualifying), _now()),
        )
        return cur.lastrowid


def get_task(task_id: int):
    with get_db() as db:
        return db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()


def get_all_tasks(active_only: bool = False):
    with get_db() as db:
        if active_only:
            return db.execute(
                "SELECT * FROM tasks WHERE is_active=1 ORDER BY created_at DESC"
            ).fetchall()
        return db.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()


def update_task_field(task_id: int, field: str, value) -> None:
    allowed = {"title", "description", "link", "reward"}
    if field not in allowed:
        raise ValueError(f"Field '{field}' cannot be edited directly")
    with get_db() as db:
        db.execute(f"UPDATE tasks SET {field}=? WHERE task_id=?", (value, task_id))


def toggle_task_active(task_id: int) -> bool:
    """Flips is_active and returns the new value."""
    with get_db() as db:
        row = db.execute("SELECT is_active FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            raise ValueError("Task not found")
        new_val = 0 if row["is_active"] else 1
        db.execute("UPDATE tasks SET is_active=? WHERE task_id=?", (new_val, task_id))
        return bool(new_val)


def toggle_task_qualifying(task_id: int) -> bool:
    with get_db() as db:
        row = db.execute("SELECT is_qualifying FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            raise ValueError("Task not found")
        new_val = 0 if row["is_qualifying"] else 1
        db.execute("UPDATE tasks SET is_qualifying=? WHERE task_id=?", (new_val, task_id))
        return bool(new_val)


def delete_task(task_id: int) -> None:
    with get_db() as db:
        db.execute("DELETE FROM task_completions WHERE task_id=?", (task_id,))
        db.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))


# --------------------------------------------------------------------------
# Task completion + reward engine
# --------------------------------------------------------------------------

def has_completed_task(user_id: int, task_id: int) -> bool:
    with get_db() as db:
        row = db.execute(
            "SELECT 1 FROM task_completions WHERE user_id=? AND task_id=?", (user_id, task_id)
        ).fetchone()
        return row is not None


def complete_task(user_id: int, task_id: int) -> dict:
    """
    Credits the task reward exactly once per (user, task) pair.
    If this is the user's first *qualifying* task completion and they were
    referred, also credits the referral bonus exactly once.

    Returns a dict:
      {"ok": False, "reason": "not_found" | "inactive" | "duplicate"}
      {"ok": True, "reward": float, "referral_credited": int|None}
    """
    with get_db() as db:
        task = db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not task:
            return {"ok": False, "reason": "not_found"}
        if not task["is_active"]:
            return {"ok": False, "reason": "inactive"}

        dup = db.execute(
            "SELECT 1 FROM task_completions WHERE user_id=? AND task_id=?", (user_id, task_id)
        ).fetchone()
        if dup:
            return {"ok": False, "reason": "duplicate"}

        db.execute(
            "INSERT INTO task_completions (user_id, task_id, reward, completed_at) VALUES (?, ?, ?, ?)",
            (user_id, task_id, task["reward"], _now()),
        )
        db.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (task["reward"], user_id))
        db.execute(
            "INSERT INTO transactions (user_id, type, amount, description, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, "task_reward", task["reward"], f"Task reward: {task['title']}", _now()),
        )

        referral_credited = None
        if task["is_qualifying"]:
            qual_count = db.execute(
                """
                SELECT COUNT(*) c FROM task_completions tc
                JOIN tasks t ON t.task_id = tc.task_id
                WHERE tc.user_id = ? AND t.is_qualifying = 1
                """,
                (user_id,),
            ).fetchone()["c"]

            if qual_count == 1:  # this completion was the first qualifying one
                ref = db.execute(
                    "SELECT * FROM referrals WHERE referred_id=? AND reward_given=0", (user_id,)
                ).fetchone()
                if ref:
                    db.execute("UPDATE referrals SET reward_given=1 WHERE id=?", (ref["id"],))
                    db.execute(
                        "UPDATE users SET balance = balance + ? WHERE user_id=?",
                        (REFERRAL_REWARD, ref["referrer_id"]),
                    )
                    db.execute(
                        "INSERT INTO transactions (user_id, type, amount, description, created_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            ref["referrer_id"],
                            "referral_reward",
                            REFERRAL_REWARD,
                            f"Referral bonus (user {user_id} qualified)",
                            _now(),
                        ),
                    )
                    referral_credited = ref["referrer_id"]

        return {"ok": True, "reward": task["reward"], "referral_credited": referral_credited}


def get_user_completions(user_id: int):
    with get_db() as db:
        return db.execute(
            """
            SELECT tc.*, t.title FROM task_completions tc
            JOIN tasks t ON t.task_id = tc.task_id
            WHERE tc.user_id=? ORDER BY tc.completed_at DESC
            """,
            (user_id,),
        ).fetchall()


def count_user_completions(user_id: int) -> int:
    with get_db() as db:
        return db.execute(
            "SELECT COUNT(*) c FROM task_completions WHERE user_id=?", (user_id,)
        ).fetchone()["c"]


# --------------------------------------------------------------------------
# Referrals
# --------------------------------------------------------------------------

def get_referral_count(user_id: int) -> int:
    with get_db() as db:
        return db.execute(
            "SELECT COUNT(*) c FROM referrals WHERE referrer_id=?", (user_id,)
        ).fetchone()["c"]


def get_qualified_referral_count(user_id: int) -> int:
    with get_db() as db:
        return db.execute(
            "SELECT COUNT(*) c FROM referrals WHERE referrer_id=? AND reward_given=1", (user_id,)
        ).fetchone()["c"]


# --------------------------------------------------------------------------
# Withdrawals
# --------------------------------------------------------------------------

def create_withdrawal(user_id: int, amount: float, wallet_address: str) -> int:
    """
    Deducts the amount from balance immediately (funds are held pending
    admin review) and creates a Pending withdrawal record.
    Raises ValueError if the user does not have sufficient balance.
    """
    with get_db() as db:
        user = db.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not user or user["balance"] < amount:
            raise ValueError("Insufficient balance")

        db.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id))
        cur = db.execute(
            "INSERT INTO withdrawals (user_id, amount, wallet_address, status, created_at) "
            "VALUES (?, ?, ?, 'Pending', ?)",
            (user_id, amount, wallet_address, _now()),
        )
        db.execute(
            "INSERT INTO transactions (user_id, type, amount, description, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, "withdrawal_request", -amount, f"Withdrawal request #{cur.lastrowid}", _now()),
        )
        return cur.lastrowid


def get_withdrawal(withdrawal_id: int):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM withdrawals WHERE withdrawal_id=?", (withdrawal_id,)
        ).fetchone()


def get_user_withdrawals(user_id: int):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM withdrawals WHERE user_id=? ORDER BY created_at DESC", (user_id,)
        ).fetchall()


def get_all_withdrawals(status: str = None, limit: int = 50):
    with get_db() as db:
        if status:
            return db.execute(
                "SELECT * FROM withdrawals WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        return db.execute(
            "SELECT * FROM withdrawals ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()


def set_withdrawal_status(withdrawal_id: int, status: str) -> None:
    """
    status: 'Approved' | 'Paid' | 'Rejected'
    Rejecting refunds the held balance back to the user.
    """
    with get_db() as db:
        w = db.execute("SELECT * FROM withdrawals WHERE withdrawal_id=?", (withdrawal_id,)).fetchone()
        if not w:
            raise ValueError("Withdrawal not found")
        if w["status"] != "Pending":
            raise ValueError(f"Withdrawal already {w['status']}")

        db.execute(
            "UPDATE withdrawals SET status=?, processed_at=? WHERE withdrawal_id=?",
            (status, _now(), withdrawal_id),
        )

        if status == "Rejected":
            db.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id=?", (w["amount"], w["user_id"])
            )
            db.execute(
                "INSERT INTO transactions (user_id, type, amount, description, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    w["user_id"],
                    "withdrawal_refund",
                    w["amount"],
                    f"Withdrawal #{withdrawal_id} rejected - refunded",
                    _now(),
                ),
            )
        elif status in ("Approved", "Paid"):
            db.execute(
                "INSERT INTO transactions (user_id, type, amount, description, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    w["user_id"],
                    "withdrawal_" + status.lower(),
                    0,
                    f"Withdrawal #{withdrawal_id} marked {status}",
                    _now(),
                ),
            )


# --------------------------------------------------------------------------
# Transactions / stats
# --------------------------------------------------------------------------

def get_user_transactions(user_id: int, limit: int = 10):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


def get_platform_stats() -> dict:
    with get_db() as db:
        total_users = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        total_tasks = db.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"]
        active_tasks = db.execute("SELECT COUNT(*) c FROM tasks WHERE is_active=1").fetchone()["c"]
        total_completions = db.execute("SELECT COUNT(*) c FROM task_completions").fetchone()["c"]
        total_referrals = db.execute("SELECT COUNT(*) c FROM referrals").fetchone()["c"]
        rewarded_referrals = db.execute(
            "SELECT COUNT(*) c FROM referrals WHERE reward_given=1"
        ).fetchone()["c"]
        total_paid_out = db.execute(
            "SELECT COALESCE(SUM(amount),0) s FROM transactions "
            "WHERE type IN ('task_reward','referral_reward')"
        ).fetchone()["s"]
        pending_withdrawals = db.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM withdrawals WHERE status='Pending'"
        ).fetchone()
        paid_withdrawals = db.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM withdrawals WHERE status='Paid'"
        ).fetchone()
        total_balance_held = db.execute(
            "SELECT COALESCE(SUM(balance),0) s FROM users"
        ).fetchone()["s"]

        return {
            "total_users": total_users,
            "total_tasks": total_tasks,
            "active_tasks": active_tasks,
            "total_completions": total_completions,
            "total_referrals": total_referrals,
            "rewarded_referrals": rewarded_referrals,
            "total_paid_out": total_paid_out,
            "pending_withdrawal_count": pending_withdrawals["c"],
            "pending_withdrawal_sum": pending_withdrawals["s"],
            "paid_withdrawal_count": paid_withdrawals["c"],
            "paid_withdrawal_sum": paid_withdrawals["s"],
            "total_balance_held": total_balance_held,
        }
