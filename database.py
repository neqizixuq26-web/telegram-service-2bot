import sqlite3
from decimal import Decimal

DB = "bot.db"

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            balance REAL NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sell_requests(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            test_email TEXT NOT NULL,
            test_label TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            amount REAL NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS stock(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'available'
        );
        CREATE TABLE IF NOT EXISTS deposits(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            details TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS withdrawals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            details TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            qty INTEGER,
            total REAL,
            status TEXT,
            items TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('gmail_price','20')")
        c.commit()

def ensure_user(uid, username, name):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO users(user_id,username,name) VALUES(?,?,?)", (uid,username,name))
        c.execute("UPDATE users SET username=?, name=? WHERE user_id=?", (username,name,uid))
        c.commit()

def get_balance(uid):
    with conn() as c:
        r = c.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        return Decimal(str(r["balance"] if r else 0))

def add_balance(uid, amount, note):
    with conn() as c:
        c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (float(amount),uid))
        c.execute("INSERT INTO transactions(user_id,type,amount,note) VALUES(?,?,?,?)",
                  (uid,"credit",float(amount),note))
        c.commit()

def deduct_balance(uid, amount, note):
    with conn() as c:
        r = c.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        if not r or Decimal(str(r["balance"])) < Decimal(str(amount)):
            return False
        c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (float(amount),uid))
        c.execute("INSERT INTO transactions(user_id,type,amount,note) VALUES(?,?,?,?)",
                  (uid,"debit",float(amount),note))
        c.commit()
        return True

def get_price():
    with conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key='gmail_price'").fetchone()
        return Decimal(str(r["value"]))

def set_price(p):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('gmail_price',?)", (str(p),))
        c.commit()

def create_sell(uid, email, label):
    price = get_price()
    with conn() as c:
        r = c.execute(
            "INSERT INTO sell_requests(user_id,test_email,test_label,amount) VALUES(?,?,?,?)",
            (uid,email,label,float(price))
        )
        c.commit()
        return r.lastrowid

def approve_sell(sid, approved):
    with conn() as c:
        r = c.execute("SELECT * FROM sell_requests WHERE id=?", (sid,)).fetchone()
        if not r or r["status"] != "Pending":
            return False, 0, Decimal("0")
        status = "Approved" if approved else "Rejected"
        c.execute("UPDATE sell_requests SET status=? WHERE id=?", (status,sid))
        if approved:
            c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (r["amount"],r["user_id"]))
            c.execute("INSERT INTO transactions(user_id,type,amount,note) VALUES(?,?,?,?)",
                      (r["user_id"],"credit",r["amount"],f"Test sell #{sid}"))
            c.execute("INSERT INTO stock(item) VALUES(?)", (r["test_email"],))
        c.commit()
        return True, r["user_id"], Decimal(str(r["amount"]))

def stock_count():
    with conn() as c:
        return c.execute("SELECT COUNT(*) n FROM stock WHERE status='available'").fetchone()["n"]

def add_test_stock(n):
    with conn() as c:
        for i in range(n):
            c.execute("INSERT INTO stock(item) VALUES(?)", (f"TEST-GMAIL-{os_random(i)}",))
        c.commit()

def os_random(i):
    import uuid
    return uuid.uuid4().hex[:10].upper()

def purchase(uid, qty, total):
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        r = c.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        if not r or Decimal(str(r["balance"])) < total:
            c.rollback(); return False, []
        rows = c.execute("SELECT id,item FROM stock WHERE status='available' LIMIT ?", (qty,)).fetchall()
        if len(rows) != qty:
            c.rollback(); return False, []
        c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (float(total),uid))
        ids = [r["id"] for r in rows]
        c.executemany("UPDATE stock SET status='sold' WHERE id=?", [(x,) for x in ids])
        items = [r["item"] for r in rows]
        c.execute("INSERT INTO orders(user_id,qty,total,status,items) VALUES(?,?,?,?,?)",
                  (uid,qty,float(total),"Completed",",".join(items)))
        c.execute("INSERT INTO transactions(user_id,type,amount,note) VALUES(?,?,?,?)",
                  (uid,"debit",float(total),f"Buy {qty} test items"))
        c.commit()
        return True, items

def create_deposit(uid, amount, details):
    with conn() as c:
        r=c.execute("INSERT INTO deposits(user_id,amount,details) VALUES(?,?,?)",(uid,float(amount),details))
        c.commit(); return r.lastrowid

def approve_deposit(did, approved):
    with conn() as c:
        r=c.execute("SELECT * FROM deposits WHERE id=?", (did,)).fetchone()
        if not r or r["status"]!="Pending": return False,0,Decimal("0")
        status="Approved" if approved else "Rejected"
        c.execute("UPDATE deposits SET status=? WHERE id=?", (status,did))
        if approved:
            c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (r["amount"],r["user_id"]))
            c.execute("INSERT INTO transactions(user_id,type,amount,note) VALUES(?,?,?,?)",
                      (r["user_id"],"credit",r["amount"],f"Deposit #{did}"))
        c.commit()
        return True,r["user_id"],Decimal(str(r["amount"]))

def create_withdrawal(uid, amount, details):
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        r=c.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        if not r or Decimal(str(r["balance"])) < amount:
            c.rollback(); raise ValueError("Insufficient balance")
        c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (float(amount),uid))
        c.execute("INSERT INTO withdrawals(user_id,amount,details) VALUES(?,?,?)",(uid,float(amount),details))
        c.execute("INSERT INTO transactions(user_id,type,amount,note) VALUES(?,?,?,?)",
                  (uid,"debit",float(amount),"Withdrawal locked"))
        wid=c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.commit(); return wid

def approve_withdrawal(wid, approved):
    with conn() as c:
        r=c.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()
        if not r or r["status"]!="Pending": return False,0,Decimal("0")
        status="Approved" if approved else "Rejected"
        c.execute("UPDATE withdrawals SET status=? WHERE id=?", (status,wid))
        if not approved:
            c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (r["amount"],r["user_id"]))
            c.execute("INSERT INTO transactions(user_id,type,amount,note) VALUES(?,?,?,?)",
                      (r["user_id"],"credit",r["amount"],f"Withdrawal refund #{wid}"))
        c.commit()
        return True,r["user_id"],Decimal(str(r["amount"]))

def all_users():
    with conn() as c:
        return [r["user_id"] for r in c.execute("SELECT user_id FROM users").fetchall()]

def user_orders(uid):
    with conn() as c:
        rows=c.execute("SELECT id,qty,total,status,created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 20",(uid,)).fetchall()
    return "\n".join(f"🛒 #{r['id']} | Qty {r['qty']} | ৳{r['total']:.2f} | {r['status']}" for r in rows)

def transactions(uid):
    with conn() as c:
        rows=c.execute("SELECT type,amount,note,created_at FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 20",(uid,)).fetchall()
    return "\n".join(f"📜 {r['type']} | ৳{r['amount']:.2f} | {r['note']}" for r in rows)

def stats():
    with conn() as c:
        users=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        orders=c.execute("SELECT COUNT(*) n FROM orders").fetchone()["n"]
        sells=c.execute("SELECT COUNT(*) n FROM sell_requests").fetchone()["n"]
    return f"📊 Stats\n\nUsers: {users}\nOrders: {orders}\nSell Requests: {sells}\nTest Stock: {stock_count()}"
