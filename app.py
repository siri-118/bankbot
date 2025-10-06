# app.py — milestone-4 full version
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash, send_from_directory
)
from pathlib import Path
import os, re, random, subprocess, json

# Local modules
from db import (
    init_db, verify_user, get_last_transactions, get_balance, block_card_for_user,
    log_chat_message, fetch_chat_logs, load_training_csv, save_training_csv,
    get_intent_stats, get_top_queries
)
# add alongside your existing db imports
from db import (
    fetch_chat_logs,
    load_training_csv,
    save_training_csv,
    get_intent_stats,
    get_top_queries
)

from nlu_runtime import TinyNLU

# ---------------- App config ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
)

# ---------------- Bootstrap DB & NLU ----------------
init_db(seed=True)
MODEL_PATH = Path(__file__).resolve().parent / "models" / "nlu.pkl"
try:
    nlu = TinyNLU(MODEL_PATH)
except Exception as e:
    print("[WARN] Could not initialize NLU:", e)
    nlu = None

# ---------------- Helpers -------------------------
def fmt_rupees(amount: float) -> str:
    return f"₹ {amount:,.2f}"

def parse_transfer(text: str):
    m = re.search(r'(?i)\b(?:transfer|send)\s+(\d+(?:\.\d{1,2})?)\s*(?:₹|rs\.?|rupees)?\s*(?:to|for)\s+([A-Za-z0-9_]+)\b', text)
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

def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user") or session["user"].get("role") != "admin":
            flash("Admin access required", "error")
            return redirect(url_for("role_select"))
        return fn(*args, **kwargs)
    return wrapper

def start_dialog(intent, slots=None):
    session["dialog"] = {"intent": intent, "slots": slots or {}, "fallbacks": 0}

def end_dialog(success=True):
    session.pop("dialog", None)

@app.context_processor
def inject_user():
    return {"current_user": session.get("user")}

# ---------------- Auth & Pages ----------------------
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

        # Store user info in session
        session["user"] = {
            "id": user["id"],
            "username": user["username"],
            "full_name": user.get("full_name", user["username"]),
            "role": user["role"],
        }

        # Role-based redirects
        role = user["role"]
        if role == "manager":
            return redirect(url_for("manager_page"))
        elif role == "admin":
            return redirect(url_for("admin_page"))
        elif role == "user":
            return redirect(url_for("user_dashboard"))
        else:
            flash("Unknown role. Please contact support.", "error")
            return redirect(url_for("role_select"))

    # Default render for GET request
    return render_template("login.html", chosen_role=chosen_role)

# ---------------- Admin routes (Milestone 4) ----------------

@app.route("/admin")
@login_required
def admin_page():
    """Admin dashboard page: logs, training data, analytics"""
    user = session.get("user")
    if user.get("role") != "admin":
        flash("Access denied: admin only.", "error")
        return redirect(url_for("role_select"))

    logs = fetch_chat_logs(limit=30)
    training_data = load_training_csv()
    intent_stats = get_intent_stats()
    top_queries = get_top_queries()

    return render_template(
        "admin.html",
        logs=logs,
        training_data=training_data,
        intent_stats=intent_stats,
        top_queries=top_queries
    )


@app.route("/update-training-data", methods=["POST"])
@login_required
def update_training_data():
    """Admin saves updated training data"""
    user = session.get("user")
    if user.get("role") != "admin":
        flash("Access denied: admin only.", "error")
        return redirect(url_for("role_select"))

    new_data = request.form.get("training_data", "")
    save_training_csv(new_data)
    flash("✅ Training data saved successfully.", "success")
    return redirect(url_for("admin_page"))


@app.route("/retrain-model")
@login_required
def retrain_model():
    """Trigger NLU model retraining from the Admin UI"""
    user = session.get("user")
    if user.get("role") != "admin":
        flash("Access denied: admin only.", "error")
        return redirect(url_for("role_select"))

    try:
        from nlu_train import train_and_save
        train_and_save()
        flash("✅ Model retrained successfully!", "success")
    except Exception as e:
        flash(f"❌ Model retraining failed: {e}", "error")

    return redirect(url_for("admin_page"))


@app.route("/logout")
def logout_page():
    session.clear()
    return redirect(url_for("role_select"))

# ---------------- Pages -----------------------------
@app.route("/manager")
@login_required
def manager_page():
    if session["user"]["role"] != "manager":
        flash("Access denied.", "error")
        return redirect(url_for("role_select"))
    return render_template("manager.html")

@app.route("/admin")
@admin_required
def admin_page():
    return render_template("admin.html")

@app.route("/user-dashboard")
@login_required
def user_dashboard():
    if session["user"]["role"] != "user":
        flash("Access denied.", "error")
        return redirect(url_for("role_select"))
    last5 = get_last_transactions(session["user"]["id"], limit=5)
    balance = get_balance(session["user"]["id"])
    return render_template("user_dashboard.html", last5=last5, balance=balance)

@app.route("/balance")
@login_required
def balance_page():
    total = get_balance(session["user"]["id"])
    return render_template("balance.html", total=total)

@app.route("/loan")
@login_required
def loan_page():
    return render_template("loan.html")

@app.route("/cards")
@login_required
def cards_page():
    return render_template("cards.html")

@app.route("/transfer")
@login_required
def transfer_page():
    return render_template("transfer.html")

@app.route("/support")
@login_required
def support_page():
    return render_template("support.html")

# ---------------- Admin API (for admin.html) ----------------
@app.route("/admin/api/logs", methods=["GET"])
@login_required
def admin_api_logs():
    # Only admin or manager can access logs
    role = session.get("user", {}).get("role")
    if role not in ("admin", "manager"):
        return jsonify({"error": "Forbidden"}), 403
    logs = fetch_chat_logs(limit=200)
    return jsonify(logs), 200


@app.route("/admin/api/training", methods=["GET", "POST"])
@login_required
def admin_api_training():
    # Only admin or manager can edit training data
    role = session.get("user", {}).get("role")
    if role not in ("admin", "manager"):
        return jsonify({"error": "Forbidden"}), 403

    if request.method == "GET":
        # Return training rows as list of dicts
        rows = load_training_csv()
        # If CSV empty, return an example list with text+intent placeholders
        if not rows:
            return jsonify([{"text": "hi", "intent": "greet"}, {"text": "what is my balance", "intent": "balance_check"}]), 200
        return jsonify(rows), 200

    # POST -> accept JSON array of rows, save CSV and retrain model
    data = request.get_json(silent=True)
    if not isinstance(data, list):
        return "Expected JSON array of rows (list of objects)", 400

    # Normalize rows: ensure each item is a dict and has at least text + intent
    cleaned = []
    for r in data:
        if not isinstance(r, dict):
            continue
        text = (r.get("text") or r.get("utterance") or "").strip()
        intent = (r.get("intent") or r.get("label") or "").strip()
        # optional response column (if present)
        resp = r.get("response") if "response" in r else r.get("answer") if "answer" in r else None
        if not text or not intent:
            continue
        # build canonical dict: keep response if present
        row = {"text": text, "intent": intent}
        if resp is not None:
            row["response"] = resp
        cleaned.append(row)

    if not cleaned:
        return "No valid rows provided (each row needs 'text' and 'intent')", 400

    # Save training CSV
    try:
        save_training_csv(cleaned)
    except Exception as e:
        return f"Failed to save training CSV: {e}", 500

    # Trigger retrain (import inside function to avoid top-level heavy import)
    try:
        # try common trainer name; if different replace with your trainer call
        from nlu_train import train_and_save
        train_and_save()  # should write models/nlu.pkl
    except Exception as e:
        # If retrain fails, still return success for save but show warning
        return f"Saved training data but retrain failed: {e}", 200

    return "Training data saved and model retrained successfully.", 200


@app.route("/admin/api/intent-stats", methods=["GET"])
@login_required
def admin_api_intent_stats():
    role = session.get("user", {}).get("role")
    if role not in ("admin", "manager"):
        return jsonify({"error": "Forbidden"}), 403
    stats = get_intent_stats()
    # return list of {intent, c}
    return jsonify(stats), 200


@app.route("/admin/api/top-queries", methods=["GET"])
@login_required
def admin_api_top_queries():
    role = session.get("user", {}).get("role")
    if role not in ("admin", "manager"):
        return jsonify({"error": "Forbidden"}), 403
    top = get_top_queries(limit=10)
    return jsonify(top), 200


# ---------------- Chatbot ---------------------------
@app.route("/chat", methods=["POST"])
@login_required
def chat():
    if session["user"]["role"] != "user":
        return jsonify({"reply": "Chatbot available only to customers."}), 403

    payload = request.get_json(silent=True) or {}
    msg = (payload.get("message") or "").strip()
    if not msg:
        return jsonify({"reply": "Please type a message.", "intent": "fallback"}), 200
    lower = msg.lower()

    # Greetings
    if re.search(r"\b(hi|hello|hey|good morning|good evening)\b", lower):
        reply = "👋 Hello! Ask me about balance, last transactions, loans, cards or transfers."
        log_chat_message(session["user"]["id"], msg, "greet")
        return jsonify({"reply": reply, "reply_html": reply + "\n" + format_entity_html("greet")})

    # Balance flow
    if "balance" in lower:
        total = get_balance(session["user"]["id"])
        reply = f"💰 Your balance is {fmt_rupees(total)}."
        log_chat_message(session["user"]["id"], msg, "balance_check")
        return jsonify({"reply": reply, "reply_html": reply + "\n" + format_entity_html("balance_check")})

    # Loan flow
    if "loan" in lower:
        reply = "🏦 We offer Personal, Home, Car, and Education loans. Which one would you like details for?"
        log_chat_message(session["user"]["id"], msg, "loan_flow")
        return jsonify({"reply": reply, "reply_html": reply + "\n" + format_entity_html("loan_flow")})

    # Cards flow
    if re.search(r"\bcard(s)?\b", lower):
        reply = "💳 We offer Credit, Debit, and Prepaid cards. You can also say 'block my credit card'."
        log_chat_message(session["user"]["id"], msg, "card_flow")
        return jsonify({"reply": reply, "reply_html": reply + "\n" + format_entity_html("card_flow")})

    # Transfer
    amount, recipient = parse_transfer(msg)
    if amount and recipient:
        reply = f"✅ Transfer initiated: {fmt_rupees(amount)} to {recipient}."
        log_chat_message(session["user"]["id"], msg, "transfer_help")
        return jsonify({"reply": reply, "reply_html": reply + "\n" + format_entity_html("transfer_help")})

    # Fallback
    reply = "I didn’t quite get that, but I’m here to help."
    log_chat_message(session["user"]["id"], msg, "fallback")
    return jsonify({"reply": reply, "reply_html": reply + "\n" + format_entity_html("fallback")})

# ---------------- Admin APIs ------------------------
@app.route("/admin/api/logs")
@admin_required
def admin_logs():
    logs = fetch_chat_logs(limit=100)
    return jsonify({"ok": True, "logs": logs})

@app.route("/admin/api/training", methods=["GET"])
@admin_required
def admin_training():
    rows = load_training_csv()
    return jsonify({"ok": True, "rows": rows})

@app.route("/admin/api/training/save", methods=["POST"])
@admin_required
def admin_save_training():
    data = request.get_json(silent=True) or {}
    rows = data.get("rows", [])
    save_training_csv(rows)
    return jsonify({"ok": True})

@app.route("/admin/api/retrain", methods=["POST"])
@admin_required
def admin_retrain():
    py = os.environ.get("PYTHON_BIN", "python")
    proc = subprocess.run([py, "nlu_train.py"], capture_output=True, text=True)
    return jsonify({"ok": proc.returncode == 0, "log": proc.stdout + proc.stderr})

@app.route("/admin/api/analytics")
@admin_required
def admin_analytics():
    return jsonify({
        "ok": True,
        "intents": get_intent_stats(),
        "top_queries": get_top_queries()
    })

# ---------------- Static ----------------------------
@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

# ---------------- Main -----------------------------
if __name__ == "__main__":
    app.run(debug=True)
