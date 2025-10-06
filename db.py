# db.py
import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash
from typing import Optional, Tuple, List, Dict, Any
import json

DB_PATH = Path(__file__).resolve().parent / "bank.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(seed=True):
    conn = get_conn()
    cur = conn.cursor()

    # Create schema (preserve existing tables + add chat_logs + blocked_cards)
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT CHECK(role IN ('user','manager','employee','admin')) NOT NULL,
        password_hash TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        account_number TEXT UNIQUE NOT NULL,
        balance REAL NOT NULL DEFAULT 0.0,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        txn_time TEXT NOT NULL,
        description TEXT NOT NULL,
        amount REAL NOT NULL,
        type TEXT CHECK(type IN ('debit','credit')) NOT NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
    );

    -- Chat logs table for admin viewing
    CREATE TABLE IF NOT EXISTS chat_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        message TEXT,
        intent TEXT,
        meta TEXT,            -- optional JSON string for additional info
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Blocked cards records (fallback if no cards table)
    CREATE TABLE IF NOT EXISTS blocked_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        card_identifier TEXT,
        reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.commit()

    if seed:
        # Only seed once
        row = cur.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        if row["c"] == 0:
            samples = [
                ("manager01", "Priya Manager", "manager", "Manager@123"),
                ("employee01", "Ravi Employee", "employee", "Employee@123"),
            ]
            # 8 customer users
            for i in range(1, 9):
                samples.append((f"user{i:02d}", f"User {i:02d}", "user", f"User{i:02d}@123"))

            for username, full_name, role, pw in samples:
                cur.execute(
                    "INSERT INTO users (username, full_name, role, password_hash) VALUES (?,?,?,?)",
                    (username, full_name, role, generate_password_hash(pw)),
                )
            conn.commit()

            # Make an account for each customer user
            users = cur.execute("SELECT id, username FROM users WHERE role='user'").fetchall()
            for u in users:
                acct = f"SB{u['id']:04d}{u['username'][-2:]}"
                balance = 10000 + (u["id"] * 137) % 5000
                cur.execute(
                    "INSERT INTO accounts (user_id, account_number, balance) VALUES (?,?,?)",
                    (u["id"], acct, balance)
                )
            conn.commit()

            # Seed 10 transactions per account
            import random, datetime as dt
            accts = cur.execute("SELECT id FROM accounts").fetchall()
            for a in accts:
                for j in range(10):
                    t = dt.datetime.now() - dt.timedelta(days=j, hours=random.randint(0,23))
                    amt = round(random.uniform(100, 2000), 2)
                    typ = random.choice(["debit", "credit"])
                    desc = random.choice([
                        "UPI Payment", "ATM Withdrawal", "POS Purchase",
                        "Salary Credit", "Bill Payment", "NEFT Transfer"
                    ])
                    cur.execute(
                        "INSERT INTO transactions (account_id, txn_time, description, amount, type) VALUES (?,?,?,?,?)",
                        (a["id"], t.isoformat(timespec="seconds"), desc, amt, typ)
                    )
            conn.commit()

    conn.close()

def verify_user(username, password):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if row and check_password_hash(row["password_hash"], password):
        return dict(row)
    return None

def get_user_accounts(user_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM accounts WHERE user_id=?", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_last_transactions(user_id, limit=5):
    conn = get_conn()
    rows = conn.execute(
        "SELECT t.* FROM transactions t "
        "JOIN accounts a ON a.id = t.account_id "
        "WHERE a.user_id = ? "
        "ORDER BY datetime(t.txn_time) DESC "
        "LIMIT ?",
        (user_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_balance(user_id):
    conn = get_conn()
    row = conn.execute("SELECT SUM(balance) AS total FROM accounts WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return (row["total"] or 0.0)

# -----------------------------
# Chat log helpers (for admin)
# -----------------------------
def log_chat_message(user_id: Optional[int], message: str, intent: Optional[str] = None, meta: Optional[Dict[str,Any]] = None) -> None:
    """
    Record a chat message to chat_logs.
    meta (optional) will be JSON-dumped and stored in meta column.
    """
    conn = get_conn()
    cur = conn.cursor()
    username = None
    if user_id:
        r = cur.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
        username = r["username"] if r else None
    meta_json = json.dumps(meta) if meta else None
    cur.execute(
        "INSERT INTO chat_logs (user_id, username, message, intent, meta) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, message, intent, meta_json)
    )
    conn.commit()
    conn.close()

def fetch_chat_logs(limit: int = 100, offset: int = 0) -> List[Dict[str,Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, user_id, username, message, intent, meta, created_at FROM chat_logs ORDER BY datetime(created_at) DESC LIMIT ? OFFSET ?",
        (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def clear_chat_logs() -> None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM chat_logs")
    conn.commit()
    conn.close()

# -----------------------------
# Analytics helpers
# -----------------------------
def get_intent_stats() -> Dict[str,int]:
    """
    Returns a dict mapping intent -> count from chat_logs.
    """
    conn = get_conn()
    rows = conn.execute("SELECT intent, COUNT(*) AS c FROM chat_logs WHERE intent IS NOT NULL GROUP BY intent").fetchall()
    conn.close()
    return {r["intent"]: r["c"] for r in rows}

def get_top_queries(limit: int = 20) -> List[Tuple[str,int]]:
    """
    Returns list of (message, count) tuples ordered by frequency.
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT message, COUNT(*) AS c FROM chat_logs GROUP BY message ORDER BY c DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [(r["message"], r["c"]) for r in rows]

# -----------------------------
# Block card helper (defensive)
# -----------------------------
def block_card_for_user(user_id: int, card_identifier: str, reason: Optional[str] = None) -> Tuple[bool, str]:
    """
    Block a card for a given user.
    - Attempts to update a 'cards' table if present (set blocked = 1).
    - If no cards table or no matching rows, records the request in blocked_cards table.
    Returns (success, message).
    """
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()

        # Try updating existing 'cards' table (if exists and has columns)
        updated = 0
        try:
            # This SQL assumes cards table may have columns: user_id, card_id, last4, card_type, blocked, blocked_reason
            cur.execute(
                """
                UPDATE cards
                SET blocked = 1, blocked_reason = COALESCE(blocked_reason, ?)
                WHERE user_id = ? AND (card_id = ? OR last4 = ? OR card_type = ?)
                """,
                (reason or "blocked via web UI", user_id, card_identifier, card_identifier, card_identifier)
            )
            updated = cur.rowcount
        except sqlite3.OperationalError:
            updated = 0

        if updated > 0:
            conn.commit()
            return True, f"Blocked {updated} card(s) for user {user_id}."

        # Otherwise insert a record in blocked_cards (this table is created by init_db)
        cur.execute(
            "INSERT INTO blocked_cards (user_id, card_identifier, reason) VALUES (?, ?, ?)",
            (user_id, str(card_identifier), reason or "blocked via web UI")
        )
        conn.commit()
        return True, "Recorded card block request."

    except Exception as e:
        return False, f"Error while blocking card: {str(e)}"
    finally:
        if conn:
            conn.close()

# -----------------------------
# Simple CSV helpers (optional)
# -----------------------------
def load_training_csv(path: Optional[Path] = None) -> List[Dict[str,str]]:
    """
    Load training CSV as list of dicts.
    Expects default path data/kaggle_training_data.csv if path is None.
    """
    import csv
    p = Path(path) if path else Path(__file__).resolve().parent / "data" / "kaggle_training_data.csv"
    if not p.exists():
        return []
    out = []
    with p.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            out.append(dict(r))
    return out

def save_training_csv(rows: List[Dict[str,str]], path: Optional[Path] = None) -> None:
    """
    Save list-of-dicts to CSV. Overwrites file.
    Caller should ensure rows is non-empty and dict keys consistent.
    """
    import csv
    p = Path(path) if path else Path(__file__).resolve().parent / "data" / "kaggle_training_data.csv"
    if not rows:
        return
    keys = list(rows[0].keys())
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

# -----------------------------
# end of db.py
# -----------------------------
