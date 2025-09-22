# app.py
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash
)
from pathlib import Path
import os, re, random

# Local modules (must exist in your repo)
from db import init_db, verify_user, get_last_transactions, get_balance
from nlu_runtime import TinyNLU

# ---------------- App config ----------------
app = Flask(__name__)
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
    Utility: attempt to get canned reply from NLU / response map (if available)
    Fallback to default_text if nothing found.
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

def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login_page"))
        return fn(*args, **kwargs)
    return wrapper

# ---------------- Dialog helpers ------------------
def start_dialog(intent, slots=None):
    session["dialog"] = {"intent": intent, "slots": slots or {}, "fallbacks": 0}

def end_dialog(success=True):
    session.pop("dialog", None)

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
@app.route("/chat", methods=["POST"])
@login_required
def chat():
    # Chat only available for logged-in users with role 'user'
    if session.get("user", {}).get("role") != "user":
        return jsonify({"reply": "Chatbot available only to customers."}), 403

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

        # Balance followup (ask for account number)
        if intent == "balance_check":
            maybe = re.search(r'(\d{4,})', text)
            if maybe:
                acct = maybe.group(1)
                slots["account_number"] = acct
                session["dialog"]["slots"] = slots
                total = get_balance(session["user"]["id"])
                end_dialog(success=True)
                reply_html = (
                    f"💰 Balance for account {acct} is {fmt_rupees(total)}."
                    f"<div class='entity-tag'>Entity: [balance_check]</div>"
                )
                return jsonify({
                    "reply": f"💰 Balance for account {acct} is {fmt_rupees(total)}. balance_check",
                    "reply_html": reply_html,
                    "intent": "balance_check",
                    "action": "show_balance"
                }), 200
            else:
                dialog["fallbacks"] = dialog.get("fallbacks", 0) + 1
                session["dialog"] = dialog
                if dialog["fallbacks"] >= 3:
                    end_dialog(success=False)
                    return jsonify({"reply": "I couldn't read the account number. Please try later.", "intent": "fallback"}), 200
                return jsonify({"reply": "Please provide your account number (digits only). balance_check", "intent": "ask_account_number"}), 200

        # Card followup: detect type and respond with subtype info
        if intent == "card_info":
            if any(w in text for w in ("credit", "credit card", "cc")):
                slots["card_type"] = "credit"
            elif any(w in text for w in ("debit", "debit card")):
                slots["card_type"] = "debit"
            elif any(w in text for w in ("prepaid", "pre-paid", "prepaid card")):
                slots["card_type"] = "prepaid"

            if slots.get("card_type"):
                ctype = slots["card_type"]
                session["dialog"]["slots"] = slots
                end_dialog(success=True)

                if ctype == "credit":
                    text_reply = "💳 Credit Card — features: High credit limit, EMI options, rewards on spend."
                elif ctype == "debit":
                    text_reply = "💳 Debit Card — features: Direct account spends, ATM withdrawals, POS payments."
                else:
                    text_reply = "💳 Prepaid Card — features: Reloadable, safe for online shopping, no bank account required."

                reply_html = f"{text_reply}<div class='entity-tag'>Entity: [card_info - {ctype}]</div>"
                return jsonify({
                    "reply": f"{text_reply} card_info",
                    "reply_html": reply_html,
                    "intent": "card_info"
                }), 200
            else:
                dialog["fallbacks"] = dialog.get("fallbacks", 0) + 1
                session["dialog"] = dialog
                if dialog["fallbacks"] >= 3:
                    end_dialog(success=False)
                    return jsonify({"reply": "I couldn't detect card type. Please try again later.", "intent": "fallback"}), 200
                return jsonify({"reply": "Which card would you like details for? Credit Card, Debit Card, or Prepaid Card? card_info", "intent": "ask_card_type"}), 200

        # Loan followup: detect which loan and respond
        if intent == "loan_info":
            if "personal" in text:
                slots["loan_type"] = "personal"
            elif "home" in text or "house" in text:
                slots["loan_type"] = "home"
            elif "car" in text:
                slots["loan_type"] = "car"
            elif "education" in text or "student" in text:
                slots["loan_type"] = "education"

            if slots.get("loan_type"):
                ltype = slots["loan_type"]
                session["dialog"]["slots"] = slots
                end_dialog(success=True)

                if ltype == "personal":
                    text_reply = "🏦 Personal Loan — unsecured, quick disbursal, suitable for short-term needs."
                elif ltype == "home":
                    text_reply = "🏠 Home Loan — lower interest, long tenure, requires property as collateral."
                elif ltype == "car":
                    text_reply = "🚗 Car Loan — financing for vehicle purchase with competitive EMI plans."
                else:
                    text_reply = "🎓 Education Loan — funds for tuition, competitive interest with moratorium options."

                reply_html = f"{text_reply}<div class='entity-tag'>Entity: [loan_info - {ltype}]</div>"
                return jsonify({
                    "reply": f"{text_reply} loan_info",
                    "reply_html": reply_html,
                    "intent": "loan_info"
                }), 200
            else:
                dialog["fallbacks"] = dialog.get("fallbacks", 0) + 1
                session["dialog"] = dialog
                if dialog["fallbacks"] >= 3:
                    end_dialog(success=False)
                    return jsonify({"reply": "I couldn't detect loan type. Please try again later.", "intent": "fallback"}), 200
                return jsonify({"reply": "Which loan type? Personal, Home, Car, or Education? loan_info", "intent": "ask_loan_type"}), 200

        # Generic fallback for active dialog
        dialog["fallbacks"] = dialog.get("fallbacks", 0) + 1
        session["dialog"] = dialog
        if dialog["fallbacks"] >= 3:
            end_dialog(success=False)
            return jsonify({"reply": "I couldn't handle that follow-up. Let's start over.", "intent": "fallback"}), 200
        return jsonify({"reply": "I didn't understand that follow-up. Could you rephrase?", "intent": "fallback"}), 200

    # ------- 1) Quick replies for common phrases -------
    if re.search(r"\bloan(s)?\b", text) or "emi" in text or "interest" in text:
        # Start loan dialog
        start_dialog("loan_info", slots={})
        return jsonify({"reply": "🏦 Available loan types: Personal Loan, Home Loan, Car Loan, and Education Loan. Which one would you like? loan_info", "intent": "loan_info"}), 200

    if re.search(r"\b(card|cards|credit|debit|prepaid)\b", text):
        # Start card dialog
        start_dialog("card_info", slots={})
        return jsonify({"reply": "💳 Which card would you like details for? Credit Card, Debit Card, or Prepaid Card? card_info", "intent": "card_info"}), 200

    amount, recipient = parse_transfer(msg)
    if amount is not None and recipient:
        reply_text = f"✅ Transfer initiated: {fmt_rupees(amount)} to {recipient}. You'll get an OTP to confirm."
        reply_html = f"{reply_text}<div class='entity-tag'>Entity: [transfer_help]</div>"
        return jsonify({"reply": f"{reply_text} transfer_help", "reply_html": reply_html, "intent": "transfer_help"}), 200

    if any(w in text for w in ("hi", "hello", "hey")):
        rep = reply_from_csv_or_default(["greet"], "👋 Hello! Ask me about balance, last transactions, loans, cards or transfers.")
        reply_html = f"{rep}<div class='entity-tag'>Entity: [greet]</div>"
        return jsonify({"reply": f"{rep} greet", "reply_html": reply_html, "intent": "greet"}), 200

    # Start balance dialog
    if "balance" in text or "account balance" in text or "how much" in text:
        start_dialog("balance_check")
        return jsonify({"reply": "Sure — please provide your account number (digits only). balance_check", "intent": "balance_check"}), 200

    # Use NLU if available
    if nlu:
        try:
            predicted = nlu.parse(msg)
            if predicted == "last_transactions":
                txns = get_last_transactions(session["user"]["id"], limit=5)
                reply_html = f"📊 Here are your last transactions.<div class='entity-tag'>Entity: [last_transactions]</div>"
                return jsonify({"reply": "📊 Here are your last transactions. last_transactions", "transactions": txns, "reply_html": reply_html, "intent": "last_transactions"}), 200
            csv_reply = reply_from_csv_or_default([predicted], None)
            if csv_reply:
                reply_html = f"{csv_reply}<div class='entity-tag'>Entity: [{predicted}]</div>"
                return jsonify({"reply": f"{csv_reply} {predicted}", "reply_html": reply_html, "intent": predicted}), 200
        except Exception:
            pass

    # Final fallback
    return jsonify({"reply": "I didn’t quite get that, but I’m here to help. fallback", "intent": "fallback"}), 200

# ---------------- Main -----------------------------
if __name__ == "__main__":
    app.run(debug=True)