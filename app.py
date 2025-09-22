# app.py - Streamlit BankBot with Role-select, Login, Dashboard & Chat
import streamlit as st
from pathlib import Path
import re, random, html, pickle, os, json
from typing import Tuple

# Try to import your db and NLU runtime; if missing, use simple stubs so app still runs
try:
    from db import init_db, verify_user, get_last_transactions, get_balance
except Exception:
    def init_db(seed=False): pass
    def verify_user(u, p):
        if u == "user01" and p == "User01@123":
            return {"id": 1, "username": "user01", "full_name": "Demo User", "role": "user"}
        if u == "manager01" and p == "Manager@123":
            return {"id": 2, "username": "manager01", "full_name": "Manager", "role": "manager"}
        return None
    def get_last_transactions(user_id, limit=5):
        return [{"date":"2025-09-01","desc":"Grocery","amount":"-₹ 500.00"},
                {"date":"2025-08-28","desc":"Salary","amount":"+₹ 50,000.00"}][:limit]
    def get_balance(user_id):
        return 10411.00

# Try to load your TinyNLU runtime
nlu = None
try:
    from nlu_runtime import TinyNLU
    MODEL_PATH = Path("models") / "nlu.pkl"
    if MODEL_PATH.exists():
        try:
            nlu = TinyNLU(MODEL_PATH)
        except Exception as e:
            st.warning(f"Could not load NLU model: {e}")
            nlu = None
    else:
        nlu = None
except Exception:
    nlu = None

# Initialize DB (no-op if stub)
init_db(seed=True)

# ------------------ Helpers ------------------
def fmt_rupees(amount: float) -> str:
    return f"₹ {amount:,.2f}"

def parse_transfer(text: str) -> Tuple[float, str]:
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

# create or reset session keys we'll use
if "user" not in st.session_state:
    st.session_state.user = None
if "dialog" not in st.session_state:
    st.session_state.dialog = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # list of (role, text, entity)

# ------------------ Chat / Dialog logic ------------------
def start_dialog(intent):
    st.session_state.dialog = {"intent": intent, "slots": {}, "fallbacks": 0}

def end_dialog():
    st.session_state.dialog = None

def handle_balance_slot_fill(text: str):
    # expect digits for account number
    m = re.search(r'(\d{4,})', text)
    if m:
        acct = m.group(1)
        # In real app you would verify acct belongs to user; here we just show balance
        total = get_balance(st.session_state.user["id"])
        end_dialog()
        reply = f"💰 Balance for account {acct} is {fmt_rupees(total)}."
        return reply, "balance_check"
    else:
        st.session_state.dialog["fallbacks"] += 1
        if st.session_state.dialog["fallbacks"] >= 3:
            end_dialog()
            return "I couldn't read the account number. Please try later.", "fallback"
        return "Please provide your account number (digits only).", "balance_check"

def chatbot_response(message: str):
    text = (message or "").strip()
    # If dialog active
    if st.session_state.dialog:
        if st.session_state.dialog["intent"] == "balance_check":
            return handle_balance_slot_fill(text)

    # quick rules
    low = text.lower()
    if any(w in low for w in ("hi","hello","hey")):
        rep = reply_from_csv_or_default(["greet"], "👋 Hello! Ask me about balance, last transactions, loans, cards or transfers.")
        return rep, "greet"

    if re.search(r"\btransfer\b|\bsend\b", low):
        amount, rec = parse_transfer(text)
        if amount and rec:
            rep = f"✅ Transfer {fmt_rupees(amount)} to {rec}. You'll get an OTP to confirm."
            return rep, "transfer_help"
        return "To transfer: say 'transfer 200 to user02' or use the Transfer page.", "transfer_help"

    if re.search(r"\bbalance\b|\baccount balance\b|\bhow much\b", low):
        start_dialog("balance_check")
        return "Sure — please provide your account number (digits only).", "balance_check"

    if re.search(r"\bloan(s)?\b|\bemi\b|\binterest\b", low):
        rep = reply_from_csv_or_default(["loan","loan_info"], "🏦 Available loan types: Personal Loan, Home Loan, Car Loan, Education Loan.")
        return rep, "loan_info"

    if re.search(r"\b(card|cards|credit|debit)\b", low):
        rep = reply_from_csv_or_default(["card_info","cards"], "💳 Available card types: Debit Card, Credit Card, Prepaid Card.")
        return rep, "card_info"

    if "transaction" in low or "transactions" in low:
        txns = get_last_transactions(st.session_state.user["id"], limit=5)
        return f"📊 Here are your recent transactions (top {len(txns)}).", "last_transactions"

    # fallback to NLU if available
    if nlu:
        try:
            predicted = nlu.parse(message)
            # if parse returns dict: get intent
            if isinstance(predicted, dict):
                intent = predicted.get("intent") or predicted.get("label")
            else:
                intent = predicted
            # choose a CSV reply if NLU responses available
            if hasattr(nlu, "responses") and isinstance(nlu.responses, dict):
                opts = nlu.responses.get(intent)
                if opts:
                    return random.choice(opts), intent
            return "I didn’t quite get that, but I’m here to help.", intent or "fallback"
        except Exception:
            pass

    return "I didn’t quite get that, but I’m here to help.", "fallback"

# ------------------ Streamlit UI ------------------
st.set_page_config(page_title="BankBot — AI Banking", layout="centered")

# Header
st.markdown("<h1 style='text-align:center'>🏦 BankBot — AI Banking Assistant</h1>", unsafe_allow_html=True)
st.write("---")

# Role select / login flow (left column)
col1, col2 = st.columns([1,3])

with col1:
    st.subheader("Access")
    if st.session_state.user is None:
        role = st.selectbox("Choose role", ["user","employee","manager"], index=0)
        st.write("Sample accounts: user01 / User01@123")
        username = st.text_input("Username", value="")
        password = st.text_input("Password", value="", type="password")
        if st.button("Login"):
            u = verify_user(username.strip(), password.strip())
            if u:
                st.session_state.user = u
                st.success(f"Logged in as {u.get('full_name') or u.get('username')} ({u.get('role')})")
            else:
                st.error("Invalid credentials")
    else:
        st.markdown(f"**Signed in:** {st.session_state.user.get('full_name') or st.session_state.user.get('username')}")
        if st.button("Logout"):
            st.session_state.user = None
            st.session_state.chat_history = []
            st.session_state.dialog = None
            st.experimental_rerun()

    # quick actions (buttons)
    if st.session_state.user:
        if st.session_state.user.get("role") == "user":
            if st.button("Go to Chat"):
                st.experimental_rerun()
        else:
            st.info("Manager/Employee UI is not implemented in Streamlit demo.")

with col2:
    # If not logged in, show a friendly message
    if st.session_state.user is None:
        st.markdown("Please select a role and login on the left to access the chat. Use the demo credentials if needed.")
    else:
        st.subheader("Chat")
        # Chat area
        chat_box = st.container()

        # show previous chat history
        for role, text, ent in st.session_state.chat_history:
            if role == "user":
                st.markdown(f"<div style='text-align:right; background:#e8f5e9; padding:10px; border-radius:8px; display:inline-block;'>{html.escape(text)}</div>", unsafe_allow_html=True)
            else:
                # reply plus entity on next line, formatted
                reply_html = html.escape(text).replace("\n", "<br/>")
                ent_html = f"<div style='font-family:Courier New, monospace; display:inline-block; margin-top:6px; color:#1a237e; background:#e8eaf6; padding:6px 10px; border-radius:6px;'>Entity: [{html.escape(ent)}]</div>"
                st.markdown(f"<div style='background:#f7f9fb; padding:10px; border-radius:8px; display:inline-block;'>{reply_html}<br/>{ent_html}</div>", unsafe_allow_html=True)

        # input
        msg = st.text_input("Type your message", key="input_message")
        if st.button("Send"):
            if not msg.strip():
                st.error("Please type a message.")
            else:
                # save user msg
                st.session_state.chat_history.append(("user", msg, ""))
                # compute bot response
                bot_reply, bot_ent = chatbot_response(msg)
                st.session_state.chat_history.append(("bot", bot_reply, bot_ent))
                # clear input
                st.session_state.input_message = ""
                st.experimental_rerun()

        # quick UI buttons for some actions
        cols = st.columns(4)
        if cols[0].button("Check Balance"):
            st.session_state.chat_history.append(("user", "check balance", ""))
            bot_reply, bot_ent = chatbot_response("balance")
            st.session_state.chat_history.append(("bot", bot_reply, bot_ent))
            st.experimental_rerun()
        if cols[1].button("Last Transactions"):
            st.session_state.chat_history.append(("user", "last transactions", ""))
            bot_reply, bot_ent = chatbot_response("last transactions")
            st.session_state.chat_history.append(("bot", bot_reply, bot_ent))
            st.experimental_rerun()
        if cols[2].button("Loans"):
            st.session_state.chat_history.append(("user", "loan", ""))
            bot_reply, bot_ent = chatbot_response("loan")
            st.session_state.chat_history.append(("bot", bot_reply, bot_ent))
            st.experimental_rerun()
        if cols[3].button("Transfer"):
            st.session_state.chat_history.append(("user", "transfer 200 to user02", ""))
            bot_reply, bot_ent = chatbot_response("transfer 200 to user02")
            st.session_state.chat_history.append(("bot", bot_reply, bot_ent))
            st.experimental_rerun()

# Footer / info
st.write("---")
st.markdown("**Note:** This Streamlit demo keeps session state in-memory. For production you should persist sessions & use secure authentication.")