import sqlite3
from datetime import datetime
from config import DATABASE_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
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


def remove_target(target_id: int) -> bool:
    with get_connection() as conn:
        conn.execute("DELETE FROM broadcast_targets WHERE target_id = ?", (target_id,))
        cur = conn.execute("DELETE FROM targets WHERE id = ?", (target_id,))
        return cur.rowcount > 0


def set_target_status(chat_id: int, is_active: int) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE targets SET is_active = ? WHERE chat_id = ?", (is_active, chat_id))


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
    expired = (now + timedelta(days=durasi_hari)).isoformat()
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
        """, (user_id, paket, max_grup, durasi_hari, expired, now.isoformat()))


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
