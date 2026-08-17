import sqlite3
from datetime import datetime
from config import DATABASE_PATH
import sqlite3


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        # Migration: tambah kolom string_session kalau belum ada
        try:
            conn.execute("ALTER TABLE accounts ADD COLUMN string_session TEXT DEFAULT ''")
        except Exception:
            pass
        # Migration: tambah kolom banned ke users
        try:
            conn.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
        except Exception:
            pass
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS targets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id     INTEGER UNIQUE NOT NULL,
                title       TEXT NOT NULL,
                username    TEXT,
                chat_type   TEXT,
                is_active   INTEGER DEFAULT 1,
                added_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS broadcasts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                message     TEXT NOT NULL,
                status      TEXT DEFAULT 'pending',
                test_mode   INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL,
                started_at  TEXT,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS broadcast_targets (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                broadcast_id INTEGER NOT NULL,
                target_id    INTEGER NOT NULL,
                status       TEXT DEFAULT 'pending',
                error        TEXT,
                sent_at      TEXT,
                FOREIGN KEY (broadcast_id) REFERENCES broadcasts(id),
                FOREIGN KEY (target_id)    REFERENCES targets(id)
            );

            CREATE TABLE IF NOT EXISTS logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                level      TEXT NOT NULL,
                message    TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS licenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER UNIQUE NOT NULL,
                paket       TEXT NOT NULL,
                max_grup    INTEGER NOT NULL,
                durasi_hari INTEGER NOT NULL,
                expired_at  TEXT NOT NULL,
                activated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                username    TEXT,
                first_name  TEXT,
                paket       TEXT NOT NULL,
                max_grup    INTEGER NOT NULL,
                durasi_hari INTEGER NOT NULL,
                harga       INTEGER NOT NULL,
                status      TEXT DEFAULT 'pending',
                created_at  TEXT NOT NULL,
                confirmed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS accounts (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                phone          TEXT UNIQUE NOT NULL,
                session_name   TEXT UNIQUE NOT NULL,
                name           TEXT,
                username       TEXT,
                string_session TEXT DEFAULT '',
                is_active      INTEGER DEFAULT 1,
                added_at       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER UNIQUE NOT NULL,
                username   TEXT,
                first_name TEXT,
                joined_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS visits (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                visited_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_accounts (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL,
                phone          TEXT NOT NULL,
                string_session TEXT NOT NULL,
                name           TEXT DEFAULT '',
                username       TEXT DEFAULT '',
                is_active      INTEGER DEFAULT 1,
                added_at       TEXT NOT NULL,
                UNIQUE(user_id, phone)
            );

            CREATE TABLE IF NOT EXISTS user_targets (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                chat_id   INTEGER NOT NULL,
                title     TEXT NOT NULL,
                username  TEXT DEFAULT '',
                chat_type TEXT DEFAULT 'supergroup',
                is_active INTEGER DEFAULT 1,
                added_at  TEXT NOT NULL,
                UNIQUE(user_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS user_messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                title      TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_broadcasts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                message     TEXT NOT NULL,
                status      TEXT DEFAULT 'pending',
                total       INTEGER DEFAULT 0,
                success     INTEGER DEFAULT 0,
                failed      INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL,
                finished_at TEXT
            );
        """)


# ── Targets ───────────────────────────────────────────────────────────────────

def add_target(chat_id: int, title: str, username: str | None, chat_type: str) -> bool:
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO targets (chat_id, title, username, chat_type, added_at) VALUES (?,?,?,?,?)",
                (chat_id, title, username, chat_type, datetime.now().isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_all_targets() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM targets ORDER BY added_at DESC").fetchall()


def get_active_targets() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM targets WHERE is_active = 1").fetchall()


def get_target_by_id(target_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM targets WHERE id = ?", (target_id,)).fetchone()


def get_target_by_chat_id(chat_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM targets WHERE chat_id = ?", (chat_id,)).fetchone()


def bulk_add_targets(targets: list[dict]) -> tuple[int, int]:
    """Tambah banyak target sekaligus. Return (added, skipped)."""
    added = skipped = 0
    for t in targets:
        ok = add_target(t["chat_id"], t["title"], t["username"], t["chat_type"])
        if ok:
            added += 1
        else:
            skipped += 1
    return added, skipped


def bulk_upsert_targets(targets: list[dict]) -> tuple[int, int, int]:
    """Tambah atau update target. Return (added, updated, skipped)."""
    added = updated = skipped = 0
    for t in targets:
        existing = get_target_by_chat_id(t["chat_id"])
        if existing is None:
            ok = add_target(t["chat_id"], t["title"], t["username"], t["chat_type"])
            if ok:
                added += 1
            else:
                skipped += 1
        else:
            # Update title, username, chat_type jika berubah
            if (existing["title"] != t["title"]
                    or existing["username"] != t["username"]
                    or existing["chat_type"] != t["chat_type"]):
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE targets SET title=?, username=?, chat_type=? WHERE chat_id=?",
                        (t["title"], t["username"], t["chat_type"], t["chat_id"]),
                    )
                updated += 1
            else:
                skipped += 1
    return added, updated, skipped


def remove_target(target_id: int) -> bool:
    with get_connection() as conn:
        conn.execute("DELETE FROM broadcast_targets WHERE target_id = ?", (target_id,))
        cur = conn.execute("DELETE FROM targets WHERE id = ?", (target_id,))
        return cur.rowcount > 0


def set_target_status(chat_id: int, is_active: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE targets SET is_active = ? WHERE chat_id = ?", (is_active, chat_id))


def activate_all_targets() -> int:
    """Set semua target jadi aktif. Return jumlah yang diupdate."""
    with get_connection() as conn:
        cur = conn.execute("UPDATE targets SET is_active = 1 WHERE is_active = 0")
        return cur.rowcount


# ── Broadcasts ────────────────────────────────────────────────────────────────

def create_broadcast(message: str, test_mode: bool = False) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO broadcasts (message, status, test_mode, created_at) VALUES (?,?,?,?)",
            (message, "running", int(test_mode), datetime.now().isoformat()),
        )
        return cur.lastrowid


def start_broadcast(broadcast_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE broadcasts SET status='running', started_at=? WHERE id=?",
            (datetime.now().isoformat(), broadcast_id),
        )


def finish_broadcast(broadcast_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE broadcasts SET status=?, finished_at=? WHERE id=?",
            (status, datetime.now().isoformat(), broadcast_id),
        )


def get_broadcasts(limit: int = 10) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM broadcasts ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()


# ── Broadcast Targets ─────────────────────────────────────────────────────────

def add_broadcast_target(broadcast_id: int, target_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO broadcast_targets (broadcast_id, target_id) VALUES (?,?)",
            (broadcast_id, target_id),
        )


def update_broadcast_target(broadcast_id: int, target_id: int, status: str, error: str | None = None) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE broadcast_targets SET status=?, error=?, sent_at=? WHERE broadcast_id=? AND target_id=?",
            (status, error, datetime.now().isoformat(), broadcast_id, target_id),
        )


def get_broadcast_results(broadcast_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("""
            SELECT bt.*, t.title, t.username
            FROM broadcast_targets bt
            JOIN targets t ON bt.target_id = t.id
            WHERE bt.broadcast_id = ?
        """, (broadcast_id,)).fetchall()


# ── Logs ──────────────────────────────────────────────────────────────────────

def add_log(level: str, message: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO logs (level, message, created_at) VALUES (?,?,?)",
            (level, message, datetime.now().isoformat()),
        )


def get_logs(limit: int = 30) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM logs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


# ── Users & Visits ───────────────────────────────────────────────────────────

def track_user(user_id: int, username: str | None, first_name: str | None) -> None:
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (user_id, username, first_name, joined_at) VALUES (?,?,?,?) ON CONFLICT(user_id) DO NOTHING",
            (user_id, username, first_name, now),
        )
        conn.execute("INSERT INTO visits (user_id, visited_at) VALUES (?,?)", (user_id, now))


def get_user_stats() -> dict:
    today = datetime.now().date().isoformat()
    with get_connection() as conn:
        total_users   = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        new_users     = conn.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{today}%",)).fetchone()[0]
        total_visits  = conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
        new_visits    = conn.execute("SELECT COUNT(*) FROM visits WHERE visited_at LIKE ?", (f"{today}%",)).fetchone()[0]
    return {
        "total_users":  total_users,
        "new_users":    new_users,
        "total_visits": total_visits,
        "new_visits":   new_visits,
    }


# ── Licenses ─────────────────────────────────────────────────────────────────

def get_license(user_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM licenses WHERE user_id = ?", (user_id,)).fetchone()


def is_license_active(user_id: int) -> bool:
    row = get_license(user_id)
    if not row:
        return False
    return datetime.now().isoformat() < row["expired_at"]


def activate_license(user_id: int, paket: str, max_grup: int, durasi_hari: int) -> None:
    from datetime import timedelta
    now = datetime.now()
    existing = get_license(user_id)

    if existing and datetime.fromisoformat(existing["expired_at"]) > now:
        # Perpanjang: tambah durasi dari expired sekarang + tambah grup
        base_expired = datetime.fromisoformat(existing["expired_at"])
        new_expired = (base_expired + timedelta(days=durasi_hari)).isoformat()
        new_max_grup = existing["max_grup"] + max_grup
    else:
        # Baru: mulai dari sekarang
        new_expired = (now + timedelta(days=durasi_hari)).isoformat()
        new_max_grup = max_grup

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO licenses (user_id, paket, max_grup, durasi_hari, expired_at, activated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
                paket=excluded.paket,
                max_grup=excluded.max_grup,
                durasi_hari=excluded.durasi_hari,
                expired_at=excluded.expired_at,
                activated_at=excluded.activated_at
        """, (user_id, paket, new_max_grup, durasi_hari, new_expired, now.isoformat()))


def revoke_license(user_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM licenses WHERE user_id = ?", (user_id,))


# ── Orders ────────────────────────────────────────────────────────────────────

def create_order(user_id: int, username: str | None, first_name: str | None,
                 paket: str, max_grup: int, durasi_hari: int, harga: int) -> int:
    with get_connection() as conn:
        cur = conn.execute("""
            INSERT INTO orders (user_id, username, first_name, paket, max_grup, durasi_hari, harga, status, created_at)
            VALUES (?,?,?,?,?,?,?,'pending',?)
        """, (user_id, username, first_name, paket, max_grup, durasi_hari, harga, datetime.now().isoformat()))
        return cur.lastrowid


def get_order(order_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def get_pending_orders() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM orders WHERE status='pending' ORDER BY created_at DESC"
        ).fetchall()


def confirm_order(order_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE orders SET status='confirmed', confirmed_at=? WHERE id=?",
            (datetime.now().isoformat(), order_id),
        )


def reject_order(order_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))


# ── Accounts ─────────────────────────────────────────────────────────────────

def add_account(phone: str, session_name: str, name: str = "", username: str = "", string_session: str = "") -> bool:
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO accounts (phone, session_name, name, username, string_session, added_at) VALUES (?,?,?,?,?,?)",
                (phone, session_name, name, username, string_session, datetime.now().isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_all_accounts() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM accounts ORDER BY added_at ASC").fetchall()


def get_active_accounts() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM accounts WHERE is_active=1").fetchall()


def get_account_by_phone(phone: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM accounts WHERE phone=?", (phone,)).fetchone()


def update_account_info(phone: str, name: str, username: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE accounts SET name=?, username=? WHERE phone=?",
            (name, username, phone),
        )


def set_account_active(phone: str, is_active: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE accounts SET is_active=? WHERE phone=?", (is_active, phone))


def delete_account(phone: str) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM accounts WHERE phone=?", (phone,))
        return cur.rowcount > 0


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    with get_connection() as conn:
        total    = conn.execute("SELECT COUNT(*) FROM targets").fetchone()[0]
        active   = conn.execute("SELECT COUNT(*) FROM targets WHERE is_active=1").fetchone()[0]
        total_bc = conn.execute("SELECT COUNT(*) FROM broadcasts").fetchone()[0]
        success  = conn.execute("SELECT COUNT(*) FROM broadcast_targets WHERE status='success'").fetchone()[0]
        failed   = conn.execute("SELECT COUNT(*) FROM broadcast_targets WHERE status='failed'").fetchone()[0]
    return {
        "total_targets":    total,
        "active_targets":   active,
        "inactive_targets": total - active,
        "total_broadcasts": total_bc,
        "total_success":    success,
        "total_failed":     failed,
    }


def get_userbot_stats_all() -> dict:
    """Total statistik broadcast semua userbot (untuk admin dashboard)."""
    with get_connection() as conn:
        success = conn.execute("SELECT COALESCE(SUM(success),0) FROM user_broadcasts WHERE status='completed'").fetchone()[0]
        failed  = conn.execute("SELECT COALESCE(SUM(failed),0)  FROM user_broadcasts WHERE status='completed'").fetchone()[0]
        total   = conn.execute("SELECT COUNT(*) FROM user_broadcasts WHERE status='completed'").fetchone()[0]
    return {"total_success": success, "total_failed": failed, "total_broadcasts": total}


def get_userbot_stats_user(user_id: int) -> dict:
    """Statistik broadcast userbot milik 1 user."""
    with get_connection() as conn:
        success = conn.execute("SELECT COALESCE(SUM(success),0) FROM user_broadcasts WHERE user_id=? AND status='completed'", (user_id,)).fetchone()[0]
        failed  = conn.execute("SELECT COALESCE(SUM(failed),0)  FROM user_broadcasts WHERE user_id=? AND status='completed'", (user_id,)).fetchone()[0]
        total   = conn.execute("SELECT COUNT(*) FROM user_broadcasts WHERE user_id=? AND status='completed'", (user_id,)).fetchone()[0]
    return {"total_success": success, "total_failed": failed, "total_broadcasts": total}


# ── User Accounts (per-user Telethon session) ─────────────────────────────────

def add_user_account(user_id: int, phone: str, string_session: str, name: str = "", username: str = "") -> bool:
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_accounts (user_id, phone, string_session, name, username, added_at) VALUES (?,?,?,?,?,?)",
                (user_id, phone, string_session, name, username, datetime.now().isoformat()),
            )
        return True
    except Exception:
        return False


def get_user_account(user_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM user_accounts WHERE user_id = ? AND is_active = 1", (user_id,)).fetchone()


def delete_user_account(user_id: int) -> bool:
    with get_connection() as conn:
        conn.execute("DELETE FROM user_accounts WHERE user_id = ?", (user_id,))
    return True


def update_user_account_session(user_id: int, string_session: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE user_accounts SET string_session = ? WHERE user_id = ?", (string_session, user_id))


# ── User Targets ──────────────────────────────────────────────────────────────

def add_user_target(user_id: int, chat_id: int, title: str, username: str, chat_type: str) -> bool:
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO user_targets (user_id, chat_id, title, username, chat_type, added_at) VALUES (?,?,?,?,?,?)",
                (user_id, chat_id, title, username, chat_type, datetime.now().isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_user_targets(user_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM user_targets WHERE user_id = ? ORDER BY added_at DESC", (user_id,)).fetchall()


def get_active_user_targets(user_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM user_targets WHERE user_id = ? AND is_active = 1", (user_id,)).fetchall()


def delete_user_target(user_id: int, target_id: int) -> bool:
    with get_connection() as conn:
        conn.execute("DELETE FROM user_targets WHERE id = ? AND user_id = ?", (target_id, user_id))
    return True


def clear_user_targets(user_id: int) -> int:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM user_targets WHERE user_id = ?", (user_id,))
        return cur.rowcount


def activate_all_user_targets(user_id: int) -> int:
    with get_connection() as conn:
        cur = conn.execute("UPDATE user_targets SET is_active = 1 WHERE user_id = ? AND is_active = 0", (user_id,))
        return cur.rowcount


def bulk_add_user_targets(user_id: int, targets: list[dict]) -> tuple[int, int]:
    added = skipped = 0
    for t in targets:
        ok = add_user_target(user_id, t["chat_id"], t["title"], t["username"], t["chat_type"])
        if ok:
            added += 1
        else:
            skipped += 1
    return added, skipped


# ── User Messages (template pesan) ───────────────────────────────────────────

def add_user_message(user_id: int, title: str, content: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO user_messages (user_id, title, content, created_at) VALUES (?,?,?,?)",
            (user_id, title, content, datetime.now().isoformat()),
        )
        return cur.lastrowid


def get_user_messages(user_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM user_messages WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()


def get_user_message_by_id(msg_id: int, user_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM user_messages WHERE id = ? AND user_id = ?", (msg_id, user_id)).fetchone()


def delete_user_message(msg_id: int, user_id: int) -> bool:
    with get_connection() as conn:
        conn.execute("DELETE FROM user_messages WHERE id = ? AND user_id = ?", (msg_id, user_id))
    return True


def clear_user_messages(user_id: int) -> int:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM user_messages WHERE user_id = ?", (user_id,))
        return cur.rowcount


# ── User Broadcasts ───────────────────────────────────────────────────────────

def create_user_broadcast(user_id: int, message: str, total: int) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO user_broadcasts (user_id, message, status, total, created_at) VALUES (?,?,?,?,?)",
            (user_id, message, "running", total, datetime.now().isoformat()),
        )
        return cur.lastrowid


def finish_user_broadcast(broadcast_id: int, success: int, failed: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE user_broadcasts SET status = 'completed', success = ?, failed = ?, finished_at = ? WHERE id = ?",
            (success, failed, datetime.now().isoformat(), broadcast_id),
        )


def get_user_broadcast_history(user_id: int, limit: int = 5) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM user_broadcasts WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()


# ── User Settings ─────────────────────────────────────────────────────────────

def get_user_setting(user_id: int, key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (f"user_{user_id}_{key}",)).fetchone()
        return row["value"] if row else default


def set_user_setting(user_id: int, key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
            (f"user_{user_id}_{key}", value),
        )


# ── Ban / Unban User ──────────────────────────────────────────────────────────

def ban_user(user_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))


def unban_user(user_id: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))


def is_user_banned(user_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return bool(row and row["is_banned"])


def get_banned_users() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM users WHERE is_banned = 1").fetchall()


def get_all_users() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM users ORDER BY joined_at DESC").fetchall()


def get_all_user_ids() -> list[int]:
    """Ambil semua user_id untuk broadcast pengumuman."""
    with get_connection() as conn:
        rows = conn.execute("SELECT user_id FROM users WHERE is_banned = 0").fetchall()
        return [r["user_id"] for r in rows]


# ── Paket Harga (bisa diubah admin) ──────────────────────────────────────────

_DEFAULT_PAKETS = {
    "spesial_7":    ("Spesial",   50, 7,  5000),
    "spesial_15":   ("Spesial",   50, 15, 8000),
    "spesial_30":   ("Spesial",   50, 30, 15000),
    "spesialpp_7":  ("Spesial++", 100, 7, 10000),
    "spesialpp_15": ("Spesial++", 100, 15, 15000),
    "spesialpp_30": ("Spesial++", 100, 30, 25000),
}

def get_paket_list() -> list[dict]:
    """Ambil daftar paket dari settings DB, fallback ke default."""
    result = []
    for key, (nama, max_grup, durasi, harga_default) in _DEFAULT_PAKETS.items():
        harga = int(get_setting(f"paket_harga_{key}", str(harga_default)))
        result.append({
            "key": key,
            "nama": nama,
            "max_grup": max_grup,
            "durasi_hari": durasi,
            "harga": harga,
        })
    return result


def set_paket_harga(key: str, harga: int) -> None:
    set_setting(f"paket_harga_{key}", str(harga))


def get_paket_by_key(key: str) -> dict | None:
    if key not in _DEFAULT_PAKETS:
        return None
    nama, max_grup, durasi, harga_default = _DEFAULT_PAKETS[key]
    harga = int(get_setting(f"paket_harga_{key}", str(harga_default)))
    return {"key": key, "nama": nama, "max_grup": max_grup, "durasi_hari": durasi, "harga": harga}


# ── Trial ─────────────────────────────────────────────────────────────────────

def has_used_trial(user_id: int) -> bool:
    """Cek apakah user sudah pernah trial."""
    with get_connection() as conn:
        row = conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return False
        val = get_setting(f"trial_used_{user_id}", "0")
        return val == "1"


def set_trial_used(user_id: int) -> None:
    """Tandai user sudah pakai trial."""
    set_setting(f"trial_used_{user_id}", "1")


def activate_trial(user_id: int) -> None:
    """Aktifkan lisensi trial 1 jam."""
    from datetime import timedelta
    now = datetime.now()
    expired = (now + timedelta(hours=1)).isoformat()
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO licenses (user_id, paket, max_grup, durasi_hari, expired_at, activated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
                paket=excluded.paket,
                max_grup=excluded.max_grup,
                durasi_hari=excluded.durasi_hari,
                expired_at=excluded.expired_at,
                activated_at=excluded.activated_at
        """, (user_id, "TRIAL", 10, 0, expired, now.isoformat()))
    set_trial_used(user_id)
