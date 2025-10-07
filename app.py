# app.py - full drop-in replacement (includes admin analytics endpoints)
from flask import (
    Flask, render_template, request, redirect, url_for, session,
    jsonify, flash, send_file, abort
)
import os
from pathlib import Path
import re, io, csv, threading, time
from werkzeug.utils import secure_filename

# local db and nlu modules (your project should contain these)
# expected db helpers: init_db, verify_user, get_last_transactions, get_balance, optionally fetch_chat_logs, load_training_csv, save_training_csv, get_intent_stats, get_top_queries
try:
    from db import (
        init_db, verify_user, get_last_transactions, get_balance,
        fetch_chat_logs, load_training_csv, save_training_csv,
        get_intent_stats, get_top_queries, block_card_for_user
    )
except Exception as e:
    # import the minimal expected functions (fallbacks) if your db.py doesn't export analytics helpers
    from db import init_db, verify_user, get_last_transactions, get_balance, block_card_for_user
    fetch_chat_logs = None
    load_training_csv = None
    save_training_csv = None
    get_intent_stats = None
    get_top_queries = None

# NLU module (optional)
try:
    from nlu_runtime import TinyNLU
except Exception:
    TinyNLU = None

# ---------------- App config ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    MAX_CONTENT_LENGTH=5 * 1024 * 1024
)

PROJECT_DIR = Path(__file__).resolve().parent
MODEL_PATH = PROJECT_DIR / "models" / "nlu.pkl"
TRAINING_DATA_PATH = PROJECT_DIR / "data" / "training.csv"  # fallback
CHAT_LOG_CSV = PROJECT_DIR / "data" / "chat_logs.csv"       # fallback

# ---------------- Initialize DB & NLU ----------------
init_db(seed=True)

# Try to ensure data directory exists
(PROJECT_DIR / "data").mkdir(exist_ok=True)

nlu = None
if TinyNLU and MODEL_PATH.exists():
    try:
        nlu = TinyNLU(MODEL_PATH)
    except Exception as e:
        print("[WARN] TinyNLU init failed:", e)

# ---------------- Helpers ----------------
def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("user"):
            return redirect(url_for("login_page"))
        return fn(*a, **kw)
    return wrapper

def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*a, **kw):
        u = session.get("user")
        if not u or u.get("role") != "admin":
            flash("Access denied: admin only.", "error")
            return redirect(url_for("role_select"))
        return fn(*a, **kw)
    return wrapper

def fmt_rupees(amount: float) -> str:
    return f"₹ {amount:,.2f}"

# fallback versions for analytics helpers if db.py didn't provide them
def _fallback_fetch_chat_logs():
    # read simple CSV fallback with columns: timestamp,username,intent,message
    out = []
    if CHAT_LOG_CSV.exists():
        with CHAT_LOG_CSV.open("r", encoding="utf8") as fh:
            r = csv.DictReader(fh)
            for row in r:
                out.append({
                    "timestamp": row.get("timestamp"),
                    "username": row.get("username"),
                    "intent": row.get("intent"),
                    "message": row.get("message")
                })
    return out

def _fallback_load_training_csv():
    if TRAINING_DATA_PATH.exists():
        return TRAINING_DATA_PATH.read_text(encoding="utf8")
    return ""

def _fallback_save_training_csv(text):
    TRAINING_DATA_PATH.write_text(text, encoding="utf8")
    return True

def _fallback_intent_stats_and_top_queries():
    # produce tiny stats from chat logs fallback
    logs = (_fallback_fetch_chat_logs() if fetch_chat_logs is None else fetch_chat_logs())
    intents = {}
    queries = {}
    for r in logs:
        intent = (r.get("intent") or "unknown").strip()
        msg = (r.get("message") or "").strip()
        intents[intent] = intents.get(intent, 0) + 1
        if msg:
            queries[msg] = queries.get(msg, 0) + 1
    intent_stats = [{"intent": k, "count": v} for k, v in sorted(intents.items(), key=lambda x:-x[1])]
    top_queries = [{"query": k, "count": v} for k, v in sorted(queries.items(), key=lambda x:-x[1])][:10]
    return intent_stats, top_queries

# ---------------- Routes: auth & pages ---------------
@app.route("/")
def index():
    return redirect(url_for("role_select"))

@app.route("/role-select")
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
        # store minimal user info in session
        session["user"] = {
            "id": user["id"],
            "username": user["username"],
            "full_name": user.get("full_name", user["username"]),
            "role": user["role"]
        }
        # redirect by role
        if user["role"] == "manager":
            return redirect(url_for("manager_page"))
        if user["role"] == "admin":
            return redirect(url_for("admin_page"))
        return redirect(url_for("user_dashboard"))
    return render_template("login.html", chosen_role=chosen_role)

@app.route("/logout")
def logout_page():
    session.clear()
    return redirect(url_for("role_select"))

# simple pages
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
    # keep this route name distinct (admin_page)
    if session.get("user", {}).get("role") != "admin":
        flash("Access denied: admin only.", "error")
        return redirect(url_for("role_select"))

    # fetch data for template (use db functions if present)
    logs = fetch_chat_logs() if callable(fetch_chat_logs) else _fallback_fetch_chat_logs()
    training_data = load_training_csv() if callable(load_training_csv) else _fallback_load_training_csv()
    if callable(get_intent_stats) and callable(get_top_queries):
        intent_stats = get_intent_stats()
        top_queries = get_top_queries()
    else:
        intent_stats, top_queries = _fallback_intent_stats_and_top_queries()

    return render_template(
        "admin.html",
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

# ---------------- Admin AJAX endpoints ----------------

@app.route("/admin/retrain", methods=["POST"])
@login_required
@admin_required
def retrain_model():
    # spawn background thread to train (non-blocking)
    def _train():
        try:
            # if there's a training script, call it (nlu_train.train_and_save)
            train_mod = None
            try:
                import importlib
                train_mod = importlib.import_module("nlu_train")
            except Exception:
                train_mod = None
            if train_mod and hasattr(train_mod, "train_and_save"):
                train_mod.train_and_save()
        except Exception as e:
            print("[admin] retrain error:", e)

    t = threading.Thread(target=_train, daemon=True)
    t.start()
    return jsonify({"message": "Retrain started"}), 200

@app.route("/admin/training", methods=["POST"])
@login_required
@admin_required
def update_training_data():
    # save posted training data; form field is "training_data"
    txt = request.form.get("training_data", "")
    if callable(save_training_csv):
        save_training_csv(txt)
    else:
        _fallback_save_training_csv(txt)
    flash("Training data saved.", "success")
    return redirect(url_for("admin_page"))

@app.route("/admin/logs/download")
@login_required
@admin_required
def download_logs_csv():
    # produce CSV from logs (either db helper or fallback)
    rows = fetch_chat_logs() if callable(fetch_chat_logs) else _fallback_fetch_chat_logs()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "username", "intent", "message"])
    for r in rows:
        writer.writerow([r.get("timestamp"), r.get("username"), r.get("intent"), r.get("message")])
    buf.seek(0)
    return send_file(io.BytesIO(buf.getvalue().encode("utf8")), mimetype="text/csv", as_attachment=True, download_name="chat_logs.csv")

@app.route("/admin/logs/clear", methods=["POST"])
@login_required
@admin_required
def clear_logs():
    # if db.py has a clear function you'd call it; here we clear fallback CSV
    try:
        # if fetch_chat_logs used DB clearing, try that
        # (we don't assume db provides clear; fallback: delete CSV)
        if CHAT_LOG_CSV.exists():
            CHAT_LOG_CSV.unlink()
        return jsonify({"ok": True}), 200
    except Exception as e:
        print("clear logs error:", e)
        return jsonify({"ok": False}), 500

# FAQ import/export stubs (implement as required)
@app.route("/admin/faq/import", methods=["POST"])
@login_required
@admin_required
def import_faqs():
    f = request.files.get("faqfile")
    if not f:
        flash("No file selected", "error")
        return redirect(url_for("admin_page"))
    # store file temporarily and return
    fname = secure_filename(f.filename)
    dest = PROJECT_DIR / "data" / fname
    f.save(dest)
    flash("FAQ file uploaded.", "success")
    return redirect(url_for("admin_page"))

@app.route("/admin/faq/export")
@login_required
@admin_required
def export_faqs():
    # stub: return empty JSON or return sample file if present
    sample = PROJECT_DIR / "data" / "faqs.json"
    if sample.exists():
        return send_file(str(sample), as_attachment=True, download_name="faqs.json", mimetype="application/json")
    return send_file(io.BytesIO(b"[]"), as_attachment=True, download_name="faqs.json", mimetype="application/json")

# ---------------- Chat API (your existing chatbot route) ---------------
@app.route("/chat", methods=["POST"])
@login_required
def chat():
    # only allow customers to chat
    if session.get("user", {}).get("role") != "user":
        return jsonify({"reply": "Chat is for customers only."}), 403

    payload = request.get_json(silent=True) or {}
    msg = (payload.get("message") or "").strip()
    if not msg:
        return jsonify({"reply": "Please type a message.", "intent": "fallback"}), 200

    text = msg.strip()
    lower = text.lower()

    # simple direct rules (balance/transfer/greet/cards/loans etc)
    # This block intentionally kept minimal; adapt to your existing code
    if re.search(r"\b(hi|hello|hey)\b", lower):
        return jsonify({"reply": "👋 Hello! Ask me about balance, last transactions, loans, cards or transfers.", "intent": "greet", "entity": "greet"}), 200

    # transfer detect
    m = re.search(r'(?i)\b(?:transfer|send)\s+(\d+(?:\.\d{1,2})?)\s*(?:to|for)\s+([A-Za-z0-9_]+)\b', text)
    if m:
        amount = float(m.group(1))
        recipient = m.group(2)
        return jsonify({"reply": f"✅ Transfer initiated: {fmt_rupees(amount)} to {recipient}.", "intent": "transfer_help", "entity": "transfer_help"}), 200

    # use NLU if available
    if nlu:
        try:
            pred = nlu.parse(text)
            # If predicted matches special intents, respond accordingly (example)
            if pred == "last_transactions":
                txns = get_last_transactions(session["user"]["id"], limit=5)
                return jsonify({"reply": "Here are your last transactions.", "transactions": txns, "intent": pred, "entity": pred}), 200
            # else fallback to canned response from NLU
            return jsonify({"reply": f"NLU predicted: {pred}", "intent": pred, "entity": pred}), 200
        except Exception as e:
            print("nlu parse error:", e)

    # fallback
    return jsonify({"reply": "I didn’t quite get that. Could you rephrase?", "intent": "fallback", "entity": "fallback"}), 200

# ---------------- Context processor ----------------
@app.context_processor
def inject_user():
    return {"current_user": session.get("user")}

# ---------------- Run ----------------
if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))