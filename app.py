# app.py
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash
)
from pathlib import Path
import os, re, random

# Local modules that must exist in your project (leave as-is)
from db import init_db, verify_user, get_last_transactions, get_balance
from nlu_runtime import TinyNLU

# ---------------- App config ----------------
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,  # set True when behind HTTPS
)

# ---------------- Bootstrap DB & NLU ----------------
init_db(seed=True)

MODEL_PATH = Path(__file__).resolve().parent / "models" / "nlu.pkl"
if not MODEL_PATH.exists():
    try:
        from nlu_train import train_and_save
        train_and_save()
    except Exception as e:
        print("[WARN] NLU model missing / auto-train failed:", e)

try:
    nlu = TinyNLU(MODEL_PATH)
except Exception as e:
    print("[WARN] Could not initialize NLU:", e)
    nlu = None

# ---------------- Context processor ----------------
@app.context_processor
def inject_user():
    # Makes 'current_user' available inside Jinja templates
    return {"current_user": session.get("user")}

# ---------------- Helpers -------------------------
def fmt_rupees(amount: float) -> str:
    return f"₹ {amount:,.2f}"

def parse_transfer(text: str):
    """
    Simple parser for: 'transfer 200 to user02' or 'send 99.5 to alice'
    """
    m = re.search(
        r'(?i)\b(?:transfer|send)\s+(\d+(?:\.\d{1,2})?)\s*(?:₹|rs\.?|rupees)?\s*(?:to|for)\s+([A-Za-z0-9_]+)\b',
        text
    )
    if not m:
        return None, None
    try:
        return float(m.group(1)), m.group(2)
    except:
        return None, None

def reply_from_csv_or_default(keys, default_text):
    """
    Try to pick a response from the NLU responses map (if present).
    `nlu.responses` is expected to be a dict of lists.
    """
    try:
        resp_map = getattr(nlu, "responses", {}) or {}
        for k in keys:
            v = resp_map.get(k)
            if v:
                return random.choice(v)
    except Exception:
        pass
    return default_text

# ---------------- Dialog helpers ------------------
def start_dialog(intent, slots=None):
    session["dialog"] = {"intent": intent, "slots": slots or {}, "fallbacks": 0}

def end_dialog(success=True):
    session.pop("dialog", None)

# ---------------- Decorators ----------------------
def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login_page"))
        return fn(*args, **kwargs)
    return wrapper

# ---------------- Routes: Auth & Pages -------------
@app.route("/", methods=["GET"])
def index():
    return redirect(url_for("role_select"))

@app.route("/role-select", methods=["GET"])
def role_select():
    return render_template("role_select.html")

@app.route("/login", methods=["GET", "POST"])
def login_page():
    chosen_role = (request.args.get("role") or "").strip().lower()
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        user = verify_user(username, password)
        if not user:
            flash("Invalid credentials", "error")
            return render_template("login.html", chosen_role=chosen_role)

        session["user"] = {
            "id": user["id"],
            "username": user["username"],
            "full_name": user.get("full_name", user["username"]),
            "role": user["role"],
        }

        if user["role"] == "manager":
            return redirect(url_for("manager_page"))
        if user["role"] == "employee":
            return redirect(url_for("employee_page"))
        return redirect(url_for("user_dashboard"))
    return render_template("login.html", chosen_role=chosen_role)

@app.route("/logout")
def logout_page():
    session.clear()
    return redirect(url_for("role_select"))

# ---------------- Portal pages --------------------
@app.route("/manager")
@login_required
def manager_page():
    if session.get("user", {}).get("role") != "manager":
        flash("Access denied: managers only.", "error")
        return redirect(url_for("role_select"))
    return render_template("manager.html")

@app.route("/employee")
@login_required
def employee_page():
    if session.get("user", {}).get("role") != "employee":
        flash("Access denied: employees only.", "error")
        return redirect(url_for("role_select"))
    return render_template("employee.html")

@app.route("/user-dashboard")
@login_required
def user_dashboard():
    if session.get("user", {}).get("role") != "user":
        flash("Access denied: users only.", "error")
        return redirect(url_for("role_select"))
    last5 = get_last_transactions(session["user"]["id"], limit=5)
    balance = get_balance(session["user"]["id"])
    return render_template("user_dashboard.html", last5=last5, balance=balance)

@app.route("/balance")
@login_required
def balance_page():
    if session.get("user", {}).get("role") != "user":
        flash("Access denied: users only.", "error")
        return redirect(url_for("role_select"))
    total = get_balance(session["user"]["id"])
    return render_template("balance.html", total=total)

@app.route("/loan")
@login_required
def loan_page():
    if session.get("user", {}).get("role") != "user":
        flash("Access denied: users only.", "error")
        return redirect(url_for("role_select"))
    return render_template("loan.html")

@app.route("/cards")
@login_required
def cards_page():
    if session.get("user", {}).get("role") != "user":
        flash("Access denied: users only.", "error")
        return redirect(url_for("role_select"))
    return render_template("cards.html")

@app.route("/transfer")
@login_required
def transfer_page():
    if session.get("user", {}).get("role") != "user":
        flash("Access denied: users only.", "error")
        return redirect(url_for("role_select"))
    return render_template("transfer.html")

@app.route("/support")
@login_required
def support_page():
    if session.get("user", {}).get("role") != "user":
        flash("Access denied: users only.", "error")
        return redirect(url_for("role_select"))
    return render_template("support.html")

# ---------------- Chatbot API ----------------------
def make_reply_html(message_text: str, entity_name: str | None) -> str:
    """
    Build an HTML version of the reply where the entity is rendered on the next line
    inside a span with class 'entity-tag' so you can style it via CSS.
    """
    safe_msg = message_text or ""
    if entity_name:
        ent_html = f"<div class='entity-line'>Entity: <span class='entity-tag'>{entity_name}</span></div>"
        return f"{safe_msg}<br/>{ent_html}"
    return safe_msg

@app.route("/chat", methods=["POST"])
@login_required
def chat():
    if session.get("user", {}).get("role") != "user":
        return jsonify({"reply": "Chatbot available only to customers.", "intent": "fallback"}), 403

    payload = request.get_json(silent=True) or {}
    msg = (payload.get("message") or "").strip()
    if not msg:
        return jsonify({"reply": "Please type a message.", "intent": "fallback"}), 200

    text = msg.lower()

    # 0) Continue dialog if active
    dialog = session.get("dialog")
    if dialog:
        intent = dialog.get("intent")
        slots = dialog.get("slots", {})
        if intent == "balance_check":
            maybe = re.search(r'(\d{4,})', text)
            if maybe:
                acct = maybe.group(1)
                slots["account_number"] = acct
                session["dialog"]["slots"] = slots
                total = get_balance(session["user"]["id"])
                end_dialog(success=True)

                plain = f"💰 Balance for account {acct} is {fmt_rupees(total)}."
                # Build HTML with Entity line
                html = make_reply_html(plain, "balance_check")
                return jsonify({
                    "reply": plain,
                    "reply_html": html,
                    "intent": "balance_check",
                    "entity": "balance_check",
                    "action": "show_balance"
                }), 200
            else:
                dialog["fallbacks"] = dialog.get("fallbacks", 0) + 1
                session["dialog"] = dialog
                if dialog["fallbacks"] >= 3:
                    end_dialog(success=False)
                    return jsonify({"reply": "I couldn't read the account number. Please try later.", "intent": "fallback", "entity": None}), 200
                plain = "Please provide your account number (digits only)."
                html = make_reply_html(plain, "balance_check")
                return jsonify({"reply": plain, "reply_html": html, "intent": "ask_account_number", "entity": "balance_check"}), 200

    # 1) Quick replies for common phrases
    if re.search(r"\bloan(s)?\b", text) or "emi" in text or "interest" in text:
        rep = reply_from_csv_or_default(["loan", "loan_info"], "🏦 Available loan types: Personal Loan, Home Loan, Car Loan, and Education Loan.")
        plain = rep
        html = make_reply_html(plain, "loan_info")
        return jsonify({"reply": plain, "reply_html": html, "intent": "loan_info", "entity": "loan_info"}), 200

    if re.search(r"\b(card|cards|credit|debit)\b", text):
        rep = reply_from_csv_or_default(["card_info", "cards"], "💳 Which card would you like details for? Credit Card, Debit Card, or Prepaid Card?")
        plain = rep
        html = make_reply_html(plain, "card_info")
        return jsonify({"reply": plain, "reply_html": html, "intent": "card_info", "entity": "card_info"}), 200

    amount, recipient = parse_transfer(msg)
    if amount is not None and recipient:
        plain = f"✅ Transfer initiated: {fmt_rupees(amount)} to {recipient}. You'll get an OTP to confirm."
        html = make_reply_html(plain, "transfer_help")
        return jsonify({
            "reply": plain,
            "reply_html": html,
            "intent": "transfer_help",
            "entity": "transfer_help"
        }), 200

    if any(w in text for w in ("hi", "hello", "hey")):
        rep = reply_from_csv_or_default(["greet"], "👋 Hello! Ask me about balance, last transactions, loans, cards or transfers.")
        plain = rep
        html = make_reply_html(plain, "greet")
        return jsonify({"reply": plain, "reply_html": html, "intent": "greet", "entity": "greet"}), 200

    # 2) Start balance dialog
    if "balance" in text or "account balance" in text or "how much" in text:
        start_dialog("balance_check")
        plain = "Sure — please provide your account number (digits only)."
        html = make_reply_html(plain, "balance_check")
        return jsonify({"reply": plain, "reply_html": html, "intent": "balance_check", "entity": "balance_check"}), 200

    # 3) Use NLU for other inputs (if available)
    if nlu:
        try:
            predicted = nlu.parse(msg)
            # allow nlu.parse to return an entity or an intent string depending on implementation
            # assume parse returns an intent string name
            if predicted == "last_transactions":
                txns = get_last_transactions(session["user"]["id"], limit=5)
                plain = "📊 Here are your last transactions."
                html = make_reply_html(plain, "last_transactions")
                return jsonify({"reply": plain, "reply_html": html, "transactions": txns, "intent": "last_transactions", "entity": "last_transactions", "action": "show_last_txns"}), 200

            csv_reply = reply_from_csv_or_default([predicted], None)
            if csv_reply:
                plain = csv_reply
                html = make_reply_html(plain, predicted)
                return jsonify({"reply": plain, "reply_html": html, "intent": predicted, "entity": predicted}), 200
        except Exception as e:
            # don't crash - fallback below
            print("[NLU ERROR]", e)

    # 4) Fallback
    plain = "I didn’t quite get that, but I’m here to help."
    html = make_reply_html(plain, "fallback")
    return jsonify({"reply": plain, "reply_html": html, "intent": "fallback", "entity": "fallback"}), 200

# Anonymous chat endpoint (for testing w/o login)
@app.route("/chat_anon", methods=["POST"])
def chat_anon():
    payload = request.get_json(silent=True) or {}
    msg = (payload.get("message") or "").strip()
    if not msg:
        return jsonify({"reply": "Please type a message.", "intent": "fallback"}), 200
    # reuse the same logic but without login/session specifics (simple)
    # For brevity call the /chat handler logic by simulating minimal session
    # We'll implement a lightweight local handling here:
    text = msg.lower()
    if any(w in text for w in ("hi", "hello", "hey")):
        plain = "👋 Hello! Ask me about balance, last transactions, loans, cards or transfers."
        html = make_reply_html(plain, "greet")
        return jsonify({"reply": plain, "reply_html": html, "intent": "greet", "entity": "greet"}), 200

    amount, recipient = parse_transfer(msg)
    if amount is not None and recipient:
        plain = f"✅ Transfer {fmt_rupees(amount)} to {recipient}. You'll get an OTP to confirm."
        html = make_reply_html(plain, "transfer_help")
        return jsonify({"reply": plain, "reply_html": html, "intent": "transfer_help", "entity": "transfer_help"}), 200

    if "balance" in text:
        plain = "Sure — please provide your account number (digits only)."
        html = make_reply_html(plain, "balance_check")
        return jsonify({"reply": plain, "reply_html": html, "intent": "balance_check", "entity": "balance_check"}), 200

    if nlu:
        try:
            predicted = nlu.parse(msg)
            csv_reply = reply_from_csv_or_default([predicted], None)
            if csv_reply:
                plain = csv_reply
                html = make_reply_html(plain, predicted)
                return jsonify({"reply": plain, "reply_html": html, "intent": predicted, "entity": predicted}), 200
        except Exception:
            pass

    plain = "I didn’t quite get that, but I’m here to help."
    html = make_reply_html(plain, "fallback")
    return jsonify({"reply": plain, "reply_html": html, "intent": "fallback", "entity": "fallback"}), 200

# ---------------- Main -----------------------------
if __name__ == "__main__":
    app.run(debug=True)