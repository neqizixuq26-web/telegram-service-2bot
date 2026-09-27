
import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).with_name("bot.db")


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db():
    with closing(connect()) as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            balance REAL NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS sell_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            price REAL NOT NULL,
            description TEXT DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sell_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            price REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(task_id) REFERENCES sell_tasks(id)
        );

        CREATE TABLE IF NOT EXISTS buy_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            price REAL NOT NULL,
            description TEXT DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            price REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(service_id) REFERENCES buy_services(id)
        );

        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            details TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            details TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT
        );
        """)
        defaults = {
            "gmail_price": "20",
            "bkash_number": "",
            "nagad_number": "",
        }
        for k, v in defaults.items():
            con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        con.commit()


def upsert_user(user_id, username="", first_name=""):
    with closing(connect()) as con:
        con.execute("""
            INSERT INTO users(user_id, username, first_name)
            VALUES(?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                updated_at=CURRENT_TIMESTAMP
        """, (user_id, username, first_name))
        con.commit()


def all_user_ids():
    with closing(connect()) as con:
        return [r["user_id"] for r in con.execute("SELECT user_id FROM users").fetchall()]


def list_users(limit=30):
    with closing(connect()) as con:
        return con.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()


def get_balance(user_id):
    with closing(connect()) as con:
        row = con.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
        return float(row["balance"]) if row else 0.0


def adjust_balance(user_id, amount):
    with closing(connect()) as con:
        con.execute("UPDATE users SET balance=balance+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (amount, user_id))
        con.commit()


def get_setting(key, default=""):
    with closing(connect()) as con:
        row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with closing(connect()) as con:
        con.execute("""
            INSERT INTO settings(key,value) VALUES(?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """, (key, str(value)))
        con.commit()


def get_payment_info():
    return {
        "bkash": get_setting("bkash_number"),
        "nagad": get_setting("nagad_number"),
        "gmail_price": float(get_setting("gmail_price", "20") or 20),
    }


def add_sell_task(title, price, description=""):
    with closing(connect()) as con:
        cur = con.execute(
            "INSERT INTO sell_tasks(title,price,description) VALUES(?,?,?)",
            (title, price, description)
        )
        con.commit()
        return cur.lastrowid


def list_sell_tasks(active_only=True):
    with closing(connect()) as con:
        sql = "SELECT * FROM sell_tasks"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY id DESC"
        return con.execute(sql).fetchall()


def get_sell_task(task_id):
    with closing(connect()) as con:
        return con.execute("SELECT * FROM sell_tasks WHERE id=?", (task_id,)).fetchone()


def toggle_sell_task(task_id):
    with closing(connect()) as con:
        con.execute("UPDATE sell_tasks SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (task_id,))
        con.commit()


def create_sell_submission(user_id, task_id, email):
    task = get_sell_task(task_id)
    price = float(task["price"])
    with closing(connect()) as con:
        cur = con.execute(
            "INSERT INTO sell_submissions(user_id,task_id,email,price) VALUES(?,?,?,?)",
            (user_id, task_id, email, price)
        )
        con.commit()
        return cur.lastrowid


def pending_sell_submissions():
    with closing(connect()) as con:
        return con.execute("""
            SELECT ss.*, st.title
            FROM sell_submissions ss
            JOIN sell_tasks st ON st.id=ss.task_id
            WHERE ss.status='pending'
            ORDER BY ss.id DESC
        """).fetchall()


def review_sell(submission_id, approve):
    with closing(connect()) as con:
        row = con.execute("SELECT * FROM sell_submissions WHERE id=?", (submission_id,)).fetchone()
        if not row or row["status"] != "pending":
            return False
        new_status = "approved" if approve else "rejected"
        con.execute(
            "UPDATE sell_submissions SET status=?, reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
            (new_status, submission_id)
        )
        if approve:
            con.execute(
                "UPDATE users SET balance=balance+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                (row["price"], row["user_id"])
            )
        con.commit()
        return True


def add_buy_service(title, price, description=""):
    with closing(connect()) as con:
        cur = con.execute(
            "INSERT INTO buy_services(title,price,description) VALUES(?,?,?)",
            (title, price, description)
        )
        con.commit()
        return cur.lastrowid


def list_buy_services(active_only=True):
    with closing(connect()) as con:
        sql = "SELECT * FROM buy_services"
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY id DESC"
        return con.execute(sql).fetchall()


def get_buy_service(service_id):
    with closing(connect()) as con:
        return con.execute("SELECT * FROM buy_services WHERE id=?", (service_id,)).fetchone()


def toggle_buy_service(service_id):
    with closing(connect()) as con:
        con.execute("UPDATE buy_services SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (service_id,))
        con.commit()


def create_buy_order(user_id, service_id):
    with closing(connect()) as con:
        user = con.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
        service = con.execute("SELECT * FROM buy_services WHERE id=?", (service_id,)).fetchone()
        if not service or not service["active"]:
            return False, "Service available নেই।"
        if not user or float(user["balance"]) < float(service["price"]):
            return False, "আপনার balance পর্যাপ্ত নয়।"
        con.execute(
            "UPDATE users SET balance=balance-?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
            (service["price"], user_id)
        )
        cur = con.execute(
            "INSERT INTO orders(user_id,service_id,title,price) VALUES(?,?,?,?)",
            (user_id, service_id, service["title"], service["price"])
        )
        con.commit()
        return True, cur.lastrowid


def pending_orders():
    with closing(connect()) as con:
        return con.execute("SELECT * FROM orders WHERE status='pending' ORDER BY id DESC").fetchall()


def user_orders(user_id):
    with closing(connect()) as con:
        return con.execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()


def review_order(order_id, complete):
    with closing(connect()) as con:
        row = con.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row or row["status"] != "pending":
            return False
        if complete:
            status = "completed"
        else:
            status = "rejected"
            con.execute(
                "UPDATE users SET balance=balance+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                (row["price"], row["user_id"])
            )
        con.execute(
            "UPDATE orders SET status=?, reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, order_id)
        )
        con.commit()
        return True


def create_deposit(user_id, amount, details):
    with closing(connect()) as con:
        cur = con.execute(
            "INSERT INTO deposits(user_id,amount,details) VALUES(?,?,?)",
            (user_id, amount, details)
        )
        con.commit()
        return cur.lastrowid


def pending_deposits():
    with closing(connect()) as con:
        return con.execute("SELECT * FROM deposits WHERE status='pending' ORDER BY id DESC").fetchall()


def review_deposit(dep_id, approve):
    with closing(connect()) as con:
        row = con.execute("SELECT * FROM deposits WHERE id=?", (dep_id,)).fetchone()
        if not row or row["status"] != "pending":
            return False
        status = "approved" if approve else "rejected"
        con.execute("UPDATE deposits SET status=?, reviewed_at=CURRENT_TIMESTAMP WHERE id=?", (status, dep_id))
        if approve:
            con.execute(
                "UPDATE users SET balance=balance+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                (row["amount"], row["user_id"])
            )
        con.commit()
        return True


def create_withdrawal(user_id, amount, details):
    with closing(connect()) as con:
        row = con.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row or float(row["balance"]) < float(amount):
            return None
        con.execute(
            "UPDATE users SET balance=balance-?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
            (amount, user_id)
        )
        cur = con.execute(
            "INSERT INTO withdrawals(user_id,amount,details) VALUES(?,?,?)",
            (user_id, amount, details)
        )
        con.commit()
        return cur.lastrowid


def pending_withdrawals():
    with closing(connect()) as con:
        return con.execute("SELECT * FROM withdrawals WHERE status='pending' ORDER BY id DESC").fetchall()


def review_withdrawal(wid, approve):
    with closing(connect()) as con:
        row = con.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()
        if not row or row["status"] != "pending":
            return False
        status = "approved" if approve else "rejected"
        con.execute("UPDATE withdrawals SET status=?, reviewed_at=CURRENT_TIMESTAMP WHERE id=?", (status, wid))
        if not approve:
            con.execute(
                "UPDATE users SET balance=balance+?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
                (row["amount"], row["user_id"])
            )
        con.commit()
        return True


def stats():
    with closing(connect()) as con:
        users = con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        balance = con.execute("SELECT COALESCE(SUM(balance),0) s FROM users").fetchone()["s"]
        pending_sells = con.execute("SELECT COUNT(*) c FROM sell_submissions WHERE status='pending'").fetchone()["c"]
        pending_orders = con.execute("SELECT COUNT(*) c FROM orders WHERE status='pending'").fetchone()["c"]
        pending_deposits = con.execute("SELECT COUNT(*) c FROM deposits WHERE status='pending'").fetchone()["c"]
        pending_withdrawals = con.execute("SELECT COUNT(*) c FROM withdrawals WHERE status='pending'").fetchone()["c"]
        return {
            "users": users,
            "balance": float(balance),
            "pending_sells": pending_sells,
            "pending_orders": pending_orders,
            "pending_deposits": pending_deposits,
            "pending_withdrawals": pending_withdrawals,
        }
