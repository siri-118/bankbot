import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = Path(__file__).resolve().parent / "bank.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(seed=True):
    conn = get_conn()
    cur = conn.cursor()

    # Create schema
    cur.executescript("""
    PRAGMA foreign_keys = ON;
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT CHECK(role IN ('user','manager','employee')) NOT NULL,
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
