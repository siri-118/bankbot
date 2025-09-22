# app.py  (Flask) — full, self-contained server that serves templates + /chat API
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from pathlib import Path
import json, re, random, os, pickle
from functools import wraps

# local imports if present
try:
    from db import init_db, verify_user, get_last_transactions, get_balance
except Exception:
    # simple stubs if db.py is missing (keeps app runnable)
    def init_db(seed=False): return None
    def verify_user(u,p):
        if (u,p) == ("user01","User01@123"):
            return {"id":1,"username":"user01","full_name":"Demo User","role":"user"}
        if (u,p) == ("manager01","Manager@123"):
            return {"id":2,"username":"manager01","full_name":"Manager","role":"manager"}
        return None
    def get_last_transactions(user_id, limit=5):
        return [{"date":"2025-09-01","desc":"Grocery","amount":"-₹ 500.00"}]
    def get_balance(user_id): return 10411.00

# attempt to import a proper nlu_runtime if available
try:
    from nlu_runtime import TinyNLU
    nlu = TinyNLU()
except Exception:
    # fallback tiny NLU
    class TinyNLU:
        def __init__(self): self.responses = {}
        def parse(self, text):
            t=text.lower()
            if any(x in t for x in ("hi","hello","hey")): return "greet"
            if "balance" in t or "how much" in t: return "balance_check"
            if "transfer" in t or "send" in t: return "transfer_help"
            if "loan" in t: return "loan"
            if "card" in t: return "card_info"
            return "fallback"
        def respond(self, intent):
            defaults = {
                "greet":"👋 Hello! Ask me about balance, last transactions, loans, cards or transfers.",
                "balance_check":"💰 Your balance is shown above.",
                "transfer_help":"💸 To transfer, go to Transfer page.",
                "loan":"🏦 We offer Personal, Home, Car and Education loans.",
                "card_info":"💳 Debit/Credit/Prepaid cards supported.",
                "fallback":"I didn’t quite get that, but I’m here to help."
            }
            return defaults.get(intent, defaults["fallback"])
    nlu = TinyNLU()

# Flask app
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

# init DB
init_db(seed=True)

# simple login_required decorator
def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("user"):
            return redirect(url_for("login_page"))
        return fn(*a, **kw)
    return wrapper

# ---------- Helpers ----------
def fmt_rupees(amount):
    try:
        return f"₹ {float(amount):,.2f}"
    except Exception:
        return str(amount)

def parse_transfer(text):
    m = re.search(r'(?i)\b(?:transfer|send)\s+(\d+(?:\.\d{1,2})?)\s*(?:₹|rs\.?|rupees)?\s*(?:to|for)\s+([A-Za-z0-9_]+)\b', text)
    if not m:
        return None, None
    return float(m.group(1)), m.group(2)

# ---------- Routes ----------
@app.context_processor
def inject_user():
    # makes current_user available in Jinja templates (fixes current_user undefined)
    return {"current_user": session.get("user")}

@app.route("/")
def index(): return redirect(url_for("role_select"))

@app.route("/role-select")
def role_select():
    return render_template("role_select.html")

@app.route("/login", methods=["GET","POST"])
def login_page():
    chosen = (request.args.get("role") or "").strip()
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        user = verify_user(username, password)
        if not user:
            flash("Invalid credentials", "error")
            return render_template("login.html", chosen_role=chosen)
        session["user"] = {"id": user["id"], "username": user["username"], "full_name": user.get("full_name", user["username"]), "role": user["role"]}
        # redirect based on role
        if user["role"] == "manager": return redirect(url_for("manager_page"))
        if user["role"] == "employee": return redirect(url_for("employee_page"))
        return redirect(url_for("user_dashboard"))
    return render_template("login.html", chosen_role=chosen)

@app.route("/logout")
def logout_page():
    session.clear()
    return redirect(url_for("role_select"))

@app.route("/user-dashboard")
@login_required
def user_dashboard():
    if session["user"]["role"] != "user":
        flash("Access denied", "error")
        return redirect(url_for("role_select"))
    last5 = get_last_transactions(session["user"]["id"], limit=5)
    balance = get_balance(session["user"]["id"])
    return render_template("user_dashboard.html", last5=last5, balance=balance)

@app.route("/balance")
@login_required
def balance_page():
    if session["user"]["role"] != "user":
        flash("Access denied", "error")
        return redirect(url_for("role_select"))
    total = get_balance(session["user"]["id"])
    return render_template("balance.html", total=total)

@app.route("/loan")
@login_required
def loan_page():
    if session["user"]["role"] != "user":
        flash("Access denied", "error")
        return redirect(url_for("role_select"))
    return render_template("loan.html")

@app.route("/cards")
@login_required
def cards_page():
    if session["user"]["role"] != "user":
        flash("Access denied", "error")
        return redirect(url_for("role_select"))
    return render_template("cards.html")

@app.route("/transfer")
@login_required
def transfer_page():
    if session["user"]["role"] != "user":
        flash("Access denied", "error")
        return redirect(url_for("role_select"))
    return render_template("transfer.html")

@app.route("/support")
@login_required
def support_page():
    if session["user"]["role"] != "user":
        flash("Access denied", "error")
        return redirect(url_for("role_select"))
    return render_template("support.html")


# ---------- Chat API ----------
@app.route("/chat", methods=["POST"])
def chat():
    """
    Accepts JSON: { message: "text" }
    Returns JSON: { reply: "...", intent: "...", entity: "...", action: "show_balance" }
    """
    # if user not logged-in, return a helpful message or allow an anon API endpoint if you want
    user = session.get("user")
    payload = request.get_json(silent=True) or {}
    msg = (payload.get("message") or "").strip()
    if not msg:
        return jsonify({"reply":"Please type a message.", "intent":"fallback", "entity":""}), 200

    # free-form transfer regex handling
    amount, recipient = parse_transfer(msg)
    if amount is not None and recipient:
        # example: do not actually debit anything — just a demo reply
        reply = f"✅ Transfer {fmt_rupees(amount)} to {recipient}. You'll get an OTP to confirm."
        return jsonify({"reply": reply, "intent": "transfer_help", "entity":"transfer_help"}), 200

    # simple rule-based dialog for balance that asks for account number
    low = msg.lower()
    # if user provided account number in a previous message? keep a dialog state in session
    dialog = session.get("dialog") or {}
    if dialog.get("intent") == "balance_check":
        maybe = re.search(r'(\d{4,})', msg)
        if maybe:
            acct = maybe.group(1)
            total = get_balance(user["id"]) if user else 0.0
            session.pop("dialog", None)
            return jsonify({"reply": f"💰 Balance for account {acct} is {fmt_rupees(total)}.", "intent":"balance_check", "entity":"balance_check", "action":"show_balance"}), 200
        else:
            # ask again
            return jsonify({"reply":"Please provide your account number (digits only).", "intent":"ask_account_number", "entity":"balance_check"}), 200

    # if message asks balance, start dialog
    if "balance" in low or "account balance" in low or "how much" in low:
        session["dialog"] = {"intent": "balance_check"}
        return jsonify({"reply":"Sure — please provide your account number (digits only).", "intent":"balance_check", "entity":"balance_check"}), 200

    # simple intents: loan, card, last_transactions
    if re.search(r"\bloan(s)?\b|\bemi\b|\binterest\b", low):
        resp = nlu.respond("loan")
        return jsonify({"reply": resp, "intent":"loan", "entity":"loan"}), 200

    if re.search(r"\b(card|cards|credit|debit)\b", low):
        resp = nlu.respond("card_info")
        return jsonify({"reply": resp, "intent":"card_info", "entity":"card_info"}), 200

    if re.search(r"\blast\b.*\btxn|transactions|recent\b", low) or "last transactions" in low:
        txns = get_last_transactions(user["id"]) if user else []
        return jsonify