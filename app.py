
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash, send_file
)
from pathlib import Path
import os, re, random, tempfile
from io import BytesIO
import datetime as dt


from db import (
    init_db,
    verify_user,
    get_last_transactions,
    get_balance,
    block_card_for_user,
    fetch_chat_logs,
    load_training_csv,
    save_training_csv,
    get_intent_stats,
    get_top_queries,
    log_chat_message,
    export_chat_logs_csv
)
from nlu_runtime import TinyNLU


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,  # set True when behind HTTPS
)
BANK_NAME = os.environ.get("BANK_NAME", "veridia Bank")

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


@app.context_processor
def inject_user():
    # Makes 'current_user' available inside Jinja templates
    return {"current_user": session.get("user")}


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
    try:
        resp_map = getattr(nlu, "responses", {}) or {}
        for k in keys:
            v = resp_map.get(k)
            if v:
                return random.choice(v)
    except Exception:
        pass
    return default_text

def format_entity_html(entity_name: str) -> str:
    """
    HTML fragment that renders the entity in the next line with your .entity-tag CSS.
    Example output:
      <div class="entity-tag">Entity : [transfer_help]</div>
    """
    safe_name = (entity_name or "").strip()
    return f'<div class="entity-tag">Entity : [{safe_name}]</div>'

def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login_page"))
        return fn(*args, **kwargs)
    return wrapper


def start_dialog(intent, slots=None):
    session["dialog"] = {"intent": intent, "slots": slots or {}, "fallbacks": 0}

def end_dialog(success=True):
    session.pop("dialog", None)


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


        role = user["role"]
        if role == "manager":
            return redirect(url_for("manager_page"))
        if role in ("employee", "admin"):
            return redirect(url_for("admin_page"))
        return redirect(url_for("user_dashboard"))
    return render_template("login.html", chosen_role=chosen_role)

@app.route("/logout")
def logout_page():
    session.clear()
    return redirect(url_for("role_select"))


@app.route("/manager")
@login_required
def manager_page():
    if session.get("user", {}).get("role") != "manager":
        flash("Access denied: managers only.", "error")
        return redirect(url_for("role_select"))
    return render_template("manager.html")


@app.route("/admin")
@login_required
def admin_page():
    if session.get("user", {}).get("role") not in ("admin", "employee", "manager"):
        flash("Access denied: admin only.", "error")
        return redirect(url_for("role_select"))


    logs = []
    training_data = ""
    intent_stats = []
    top_queries = []

    try:

        logs = fetch_chat_logs(limit=40)
    except Exception:
        logs = []

    try:
        training_data = load_training_csv()
    except Exception:
        training_data = ""

    try:
        intent_stats = get_intent_stats()
    except Exception:
        intent_stats = []

    try:
        top_queries = get_top_queries()
    except Exception:
        top_queries = []



    return render_template(
        "admin_dashboard.html",
        logs=logs,
        training_data=training_data,
        intent_stats=intent_stats,
        top_queries=top_queries
    )

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


@app.route("/update-training-data", methods=["POST"])
@login_required
def update_training_data():
    if session.get("user", {}).get("role") not in ("admin", "employee", "manager"):
        return jsonify({"ok": False, "error": "access denied"}), 403
    data = request.form.get("training_data", "")
    try:
        save_training_csv(data)
        return redirect(url_for("admin_page"))
    except Exception as e:
        flash("Failed to save training data: " + str(e), "error")
        return redirect(url_for("admin_page"))

@app.route("/retrain-model", methods=["GET"])
@login_required
def retrain_model():
    if session.get("user", {}).get("role") not in ("admin", "employee", "manager"):
        flash("Access denied: admin only.", "error")
        return redirect(url_for("role_select"))

    try:
        from nlu_train import train_and_save
        train_and_save()
        # reload nlu instance
        global nlu
        nlu = TinyNLU(MODEL_PATH)
        flash("Model retrained successfully.", "success")
    except Exception as e:
        flash(f"Retrain failed: {e}", "error")
    return redirect(url_for("admin_page"))

# ---------------- Admin CSV download---------------
@app.route("/admin/download-logs")
@login_required
def download_logs_csv():
    if session.get("user", {}).get("role") not in ("admin", "employee", "manager"):
        flash("Access denied: admin only.", "error")
        return redirect(url_for("role_select"))

    try:
        tmpfile = Path(tempfile.gettempdir()) / f"chat_logs_{dt.date.today().isoformat()}.csv"
        export_chat_logs_csv(tmpfile)
        return send_file(tmpfile, as_attachment=True, download_name=tmpfile.name, mimetype="text/csv")
    except Exception as e:
        flash(f"Download failed: {e}", "error")
        return redirect(url_for("admin_page"))

# ---------------- Chatbot API ----------------------
@app.route("/chat", methods=["POST"])
@login_required
def chat():
    if session.get("user", {}).get("role") != "user":
        return jsonify({"reply": "Chatbot available only to customers."}), 403

    payload = request.get_json(silent=True) or {}
    msg = (payload.get("message") or "").strip()
    if not msg:
        return jsonify({"reply": "Please type a message.", "intent": "fallback"}), 200

    user_id = session["user"]["id"]
    text = msg.strip()
    lower = text.lower()

    # Log user message
    try:
        log_chat_message(user_id, msg, "user_message")
    except Exception:
        pass

    # ---------------- Dialog handling & interruption ----------------
    dialog = session.get("dialog")

    # 🧠 If a dialog is active but user starts a new topic, end it gracefully
    if dialog:
        if re.search(r"\b(balance|transaction|transfer|loan|card|block|support)\b", lower):
            try:
                log_chat_message(user_id, f"[System] Dialog '{dialog.get('intent')}' interrupted by new query '{msg}'", "dialog_interrupt")
            except Exception:
                pass
            end_dialog(success=False)
            dialog = None

    # ---------------- Handle ongoing dialog ----------------
    if dialog:
        intent = dialog.get("intent")
        slots = dialog.get("slots", {})

        # Balance dialog — expects account number
        if intent == "balance_check":
            maybe = re.search(r'(\d{4,})', lower)
            if maybe:
                acct = maybe.group(1)
                slots["account_number"] = acct
                session["dialog"]["slots"] = slots
                total = get_balance(user_id)
                end_dialog(success=True)
                reply_text = f"💰 Balance for account {acct} is {fmt_rupees(total)}."
                reply_html = reply_text + "\n" + format_entity_html("balance_check")
                try:
                    log_chat_message(user_id, reply_text, "balance_check")
                except Exception:
                    pass
                return jsonify({
                    "reply": reply_text,
                    "reply_html": reply_html,
                    "intent": "balance_check",
                    "entity": "balance_check",
                    "action": "show_balance"
                }), 200
            else:
                dialog["fallbacks"] = dialog.get("fallbacks", 0) + 1
                session["dialog"] = dialog
                if dialog["fallbacks"] >= 3:
                    end_dialog(success=False)
                    return jsonify({
                        "reply": "I couldn't read the account number. Let's try again later.",
                        "intent": "fallback"
                    }), 200
                reply_text = "Please enter your account number (digits only)."
                reply_html = reply_text + "\n" + format_entity_html("balance_check")
                try:
                    log_chat_message(user_id, reply_text, "ask_account_number")
                except Exception:
                    pass
                return jsonify({
                    "reply": reply_text,
                    "reply_html": reply_html,
                    "intent": "ask_account_number"
                }), 200

        # Card dialog
        if intent == "card_flow":
            if re.search(r"\b(credit|debit|prepaid|pre-paid|pre paid)\b", lower):
                card_type = re.search(r"\b(credit|debit|prepaid|pre-paid|pre paid)\b", lower).group(1)
                card_type_clean = card_type.replace("-", "_").replace(" ", "_")
                slots["card_type"] = card_type_clean
                session["dialog"]["slots"] = slots
                reply_text = f"📋 Details for {card_type_clean.title()} Card. What would you like to do? (info / block)"
                reply_html = reply_text + "\n" + format_entity_html("card_info")
                try:
                    log_chat_message(user_id, reply_text, "card_info")
                except Exception:
                    pass
                return jsonify({
                    "reply": reply_text,
                    "reply_html": reply_html,
                    "intent": "card_info",
                    "entity": "card_info"
                }), 200

            if re.search(r"\b(block|disable|freeze)\b", lower):
                card_type = slots.get("card_type", "your card")
                try:
                    blocked = block_card_for_user(user_id, card_type)
                    success = bool(blocked)
                except Exception:
                    success = False
                if success:
                    end_dialog(success=True)
                    reply_text = f"✅ {card_type.title()} blocked successfully."
                else:
                    reply_text = "⚠️ I couldn’t block the card right now. Please contact support."
                reply_html = reply_text + "\n" + format_entity_html("block_card")
                try:
                    log_chat_message(user_id, reply_text, "block_card")
                except Exception:
                    pass
                return jsonify({
                    "reply": reply_text,
                    "reply_html": reply_html,
                    "intent": "block_card",
                    "entity": "block_card"
                }), 200

            dialog["fallbacks"] = dialog.get("fallbacks", 0) + 1
            session["dialog"] = dialog
            reply_text = "Please choose: credit, debit, prepaid, or say 'block' to block a card."
            reply_html = reply_text + "\n" + format_entity_html("card_flow")
            try:
                log_chat_message(user_id, reply_text, "card_flow")
            except Exception:
                pass
            if dialog["fallbacks"] >= 3:
                end_dialog(success=False)
                return jsonify({
                    "reply": "Let's start over. How can I help with cards?",
                    "intent": "fallback"
                }), 200
            return jsonify({
                "reply": reply_text,
                "reply_html": reply_html,
                "intent": "card_flow"
            }), 200

        # Loan dialog
        if intent == "loan_flow":
            found = re.search(r"\b(personal|home|car|education|educational)\b", lower)
            if found:
                typ = found.group(1)
                typ_clean = "education" if typ in ("education", "educational") else typ
                slots["loan_type"] = typ_clean
                session["dialog"]["slots"] = slots
                reply_text = f"🏦 Info for {typ_clean.title()} Loan: rates, EMI, eligibility. Want EMI or eligibility?"
                reply_html = reply_text + "\n" + format_entity_html("loan_info")
                try:
                    log_chat_message(user_id, reply_text, "loan_info")
                except Exception:
                    pass
                return jsonify({
                    "reply": reply_text,
                    "reply_html": reply_html,
                    "intent": "loan_info",
                    "entity": "loan_info"
                }), 200

            dialog["fallbacks"] = dialog.get("fallbacks", 0) + 1
            session["dialog"] = dialog
            reply_text = "Which loan type would you like? (personal, home, car, or education)"
            reply_html = reply_text + "\n" + format_entity_html("loan_flow")
            try:
                log_chat_message(user_id, reply_text, "loan_flow")
            except Exception:
                pass
            if dialog["fallbacks"] >= 3:
                end_dialog(success=False)
                return jsonify({
                    "reply": "I couldn't get the loan type. Try again later.",
                    "intent": "fallback"
                }), 200
            return jsonify({
                "reply": reply_text,
                "reply_html": reply_html,
                "intent": "loan_flow",
                "entity": "loan_flow"
            }), 200

    # ---------------- Handle new intents ----------------
    # Balance flow: Ask for account number first
    if re.search(r"\b(balance|check balance|account balance)\b", lower):
        start_dialog("balance_check", {})
        reply_text = "Sure! Please provide your account number to check the balance."
        reply_html = reply_text + "\n" + format_entity_html("balance_check_start")
        try:
            log_chat_message(user_id, reply_text, "balance_check_start")
        except Exception:
            pass
        return jsonify({
            "reply": reply_text,
            "reply_html": reply_html,
            "intent": "balance_check",
            "entity": "balance_check"
        }), 200

    # Transfers
    amount, recipient = parse_transfer(text)
    if amount is not None and recipient:
        end_dialog(success=True)
        reply_text = f"✅ Transfer initiated: {fmt_rupees(amount)} to {recipient}. You'll get an OTP to confirm."
        reply_html = reply_text + "\n" + format_entity_html("transfer_help")
        try:
            log_chat_message(user_id, reply_text, "transfer_help")
        except Exception:
            pass
        return jsonify({
            "reply": reply_text,
            "reply_html": reply_html,
            "intent": "transfer_help",
            "entity": "transfer_help"
        }), 200

    # Greetings
    if re.search(r"\b(hi|hello|hey|good morning|good evening)\b", lower):
        rep = reply_from_csv_or_default(["greet"], "👋 Hello! Ask me about balance, last transactions, loans, cards or transfers.")
        reply_html = rep + "\n" + format_entity_html("greet")
        try:
            log_chat_message(user_id, rep, "greet")
        except Exception:
            pass
        return jsonify({"reply": rep, "reply_html": reply_html, "intent": "greet", "entity": "greet"}), 200

    # Card flow
    if re.search(r"\b(card|cards|credit|debit|prepaid)\b", lower) and "transfer" not in lower:
        start_dialog("card_flow", {})
        reply_text = "Which card would you like details for? Credit, Debit, or Prepaid?"
        reply_html = reply_text + "\n" + format_entity_html("card_flow")
        try:
            log_chat_message(user_id, reply_text, "card_flow_start")
        except Exception:
            pass
        return jsonify({"reply": reply_text, "reply_html": reply_html, "intent": "card_flow", "entity": "card_flow"}), 200

    # Loan flow
    if re.search(r"\bloan(s)?\b", lower) or "emi" in lower or "interest" in lower:
        start_dialog("loan_flow", {})
        reply_text = "🏦 Available loan types: Personal Loan, Home Loan, Car Loan, and Education Loan. Which one would you like?"
        reply_html = reply_text + "\n" + format_entity_html("loan_flow")
        try:
            log_chat_message(user_id, reply_text, "loan_flow_start")
        except Exception:
            pass
        return jsonify({"reply": reply_text, "reply_html": reply_html, "intent": "loan_flow", "entity": "loan_flow"}), 200

    # ---------------- NLU fallback ----------------
    if nlu:
        try:
            predicted = nlu.parse(msg)
            if predicted == "last_transactions":
                txns = get_last_transactions(user_id, limit=5)
                reply_text = "📊 Here are your last transactions."
                reply_html = reply_text + "\n" + format_entity_html("last_transactions")
                try:
                    log_chat_message(user_id, reply_text, "last_transactions")
                except Exception:
                    pass
                return jsonify({
                    "reply": reply_text,
                    "reply_html": reply_html,
                    "transactions": txns,
                    "intent": "last_transactions",
                    "entity": "last_transactions",
                    "action": "show_last_txns"
                }), 200

            csv_reply = reply_from_csv_or_default([predicted], None)
            if csv_reply:
                reply_html = csv_reply + "\n" + format_entity_html(predicted)
                try:
                    log_chat_message(user_id, csv_reply, predicted)
                except Exception:
                    pass
                return jsonify({
                    "reply": csv_reply,
                    "reply_html": reply_html,
                    "intent": predicted,
                    "entity": predicted
                }), 200
        except Exception:
            pass

    # ---------------- Fallback ----------------
    reply_text = "I didn’t quite get that, but I’m here to help."
    reply_html = reply_text + "\n" + format_entity_html("fallback")
    try:
        log_chat_message(user_id, reply_text, "fallback")
    except Exception:
        pass
    return jsonify({"reply": reply_text, "reply_html": reply_html, "intent": "fallback", "entity": "fallback"}), 200

# ---------------- Main -----------------------------
if __name__ == "__main__":
    app.run(debug=True)