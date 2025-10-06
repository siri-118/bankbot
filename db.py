import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash
import csv, os
from collections import Counter

DB_PATH = Path(__file__).resolve().parent / "bank.db"
TRAINING_DATA = Path(__file__).resolve().parent / "data" / "kaggle_training_data.csv"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ------------------ INIT DB ---------------------
def init_db(seed=True):
    conn = get_conn()
    cur = conn.cursor()

    cur.executescript("""
    PRAGMA foreign_keys = ON;

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

    CREATE TABLE IF NOT EXISTS chat_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        intent TEXT,
        ts DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    conn.commit()

    if seed:
        row = cur.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        if row["c"] == 0:
            samples = [
                ("manager01", "Priya Manager", "manager", "Manager@123"),
                ("admin01", "Ravi Admin", "admin", "Admin@123"),

            ]
            for i in range(1, 9):
                samples.append((f"user{i:02d}", f"User {i:02d}", "user", f"User{i:02d}@123"))
            for username, full_name, role, pw in samples:
                cur.execute(
                    "INSERT INTO users (username, full_name, role, password_hash) VALUES (?,?,?,?)",
                    (username, full_name, role, generate_password_hash(pw)),
                )
            conn.commit()

            # Create accounts for users
            users = cur.execute("SELECT id, username FROM users WHERE role='user'").fetchall()
            for u in users:
                acct = f"SB{u['id']:04d}{u['username'][-2:]}"
                balance = 10000 + (u["id"] * 137) % 5000
                cur.execute(
                    "INSERT INTO accounts (user_id, account_number, balance) VALUES (?,?,?)",
                    (u["id"], acct, balance),
                )
            conn.commit()

            # Seed transactions
            import random, datetime as dt
            accts = cur.execute("SELECT id FROM accounts").fetchall()
            for a in accts:
                for j in range(10):
                    t = dt.datetime.now() - dt.timedelta(days=j, hours=random.randint(0, 23))
                    amt = round(random.uniform(100, 2000), 2)
                    typ = random.choice(["debit", "credit"])
                    desc = random.choice([
                        "UPI Payment", "ATM Withdrawal", "POS Purchase",
                        "Salary Credit", "Bill Payment", "NEFT Transfer"
                    ])
                    cur.execute(
                        "INSERT INTO transactions (account_id, txn_time, description, amount, type) VALUES (?,?,?,?,?)",
                        (a["id"], t.isoformat(timespec="seconds"), desc, amt, typ),
                    )
            conn.commit()

    conn.close()

# ------------------ AUTH ---------------------
def verify_user(username, password):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if row and check_password_hash(row["password_hash"], password):
        return dict(row)
    return None

# ------------------ ACCOUNTS ---------------------
def get_user_accounts(user_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM accounts WHERE user_id=?", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_balance(user_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT SUM(balance) AS total FROM accounts WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    return (row["total"] or 0.0)

def get_last_transactions(user_id, limit=5):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT t.* FROM transactions t
        JOIN accounts a ON a.id = t.account_id
        WHERE a.user_id = ?
        ORDER BY datetime(t.txn_time) DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ------------------ CHAT LOGGING ---------------------
def log_chat_message(user_id, message, intent):
    conn = get_conn()
    conn.execute(
        "INSERT INTO chat_logs (user_id, message, intent) VALUES (?,?,?)",
        (user_id, message, intent),
    )
    conn.commit()
    conn.close()

def fetch_chat_logs(limit=100):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT c.id, u.username, c.message, c.intent, c.ts
        FROM chat_logs c
        JOIN users u ON u.id = c.user_id
        ORDER BY datetime(c.ts) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ------------------ TRAINING DATA ---------------------
def load_training_csv():
    rows = []
    if not TRAINING_DATA.exists():
        return rows
    with open(TRAINING_DATA, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows

def save_training_csv(rows):
    os.makedirs(TRAINING_DATA.parent, exist_ok=True)
    with open(TRAINING_DATA, "w", newline="", encoding="utf-8") as f:
        if not rows:
            return
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

# ------------------ ANALYTICS ---------------------
def get_intent_stats():
    conn = get_conn()
    rows = conn.execute("SELECT intent, COUNT(*) AS c FROM chat_logs GROUP BY intent").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_top_queries(limit=10):
    conn = get_conn()
    rows = conn.execute(
        "SELECT message, COUNT(*) AS c FROM chat_logs GROUP BY message ORDER BY c DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ------------------ BLOCK CARD ---------------------
def block_card_for_user(user_id, card_type):
    """
    Simulates blocking a card by logging action. 
    Real banking API would go here.
    """
    conn = get_conn()
    conn.execute(
        "INSERT INTO chat_logs (user_id, message, intent) VALUES (?,?,?)",
        (user_id, f"Blocked {card_type} card", "block_card"),
    )
    conn.commit()
    conn.close()
    return True
