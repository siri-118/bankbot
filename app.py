# app.py - Streamlit version of BankBot
import streamlit as st
import re, random, pickle
from pathlib import Path
import pandas as pd
from db import get_balance, get_last_transactions  # keep your db.py functions
from nlu_runtime import TinyNLU

# ----------------- Load NLU model -----------------
MODEL_PATH = Path("models") / "nlu.pkl"
nlu = None
if MODEL_PATH.exists():
    try:
        nlu = TinyNLU(MODEL_PATH)
    except Exception as e:
        st.warning(f"⚠️ Could not load NLU: {e}")

# ----------------- Helpers -----------------
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

# ----------------- Chat Logic -----------------
def chat_response(msg: str, user_id="user01"):
    text = msg.lower().strip()

    # Greeting
    if any(w in text for w in ("hi", "hello", "hey")):
        rep = reply_from_csv_or_default(["greet"], "👋 Hello! Ask me about balance, loans, cards, or transfers.")
        return rep, "greet"

    # Balance check
    if "balance" in text:
        return "Sure — please provide your account number (digits only).", "balance_check"

    # Loans
    if "loan" in text or "emi" in text:
        rep = reply_from_csv_or_default(["loan", "loan_info"], "🏦 Available loan types: Personal Loan, Home Loan, Car Loan, Education Loan.")
        return rep, "loan_info"

    # Cards
    if "card" in text or "credit" in text or "debit" in text:
        rep = reply_from_csv_or_default(["card_info"], "💳 Available cards: Debit, Credit, Prepaid.")
        return rep, "card_info"

    # Transfers
    amount, recipient = parse_transfer(text)
    if amount and recipient:
        return f"✅ Transfer {fmt_rupees(amount)} to {recipient}. You'll get an OTP to confirm.", "transfer_help"

    # Last transactions
    if "transactions" in text:
        txns = get_last_transactions(user_id, limit=5)
        return f"📊 Last {len(txns)} transactions: {txns}", "last_transactions"

    # Fallback to NLU
    if nlu:
        try:
            intent = nlu.parse(msg)
            return f"(NLU) Detected intent: {intent}", intent
        except Exception:
            pass

    return "I didn’t quite get that, but I’m here to help.", "fallback"

# ----------------- Streamlit UI -----------------
st.set_page_config(page_title="BankBot", page_icon="🏦")

st.title("🏦 BankBot — AI Banking Assistant")

if "history" not in st.session_state:
    st.session_state.history = []

user_input = st.chat_input("Type your message...")

if user_input:
    # user message
    st.session_state.history.append(("user", user_input))

    # bot response
    reply, intent = chat_response(user_input)
    bot_msg = f"{reply}\n\n**Entity: [{intent}]**"
    st.session_state.history.append(("bot", bot_msg))

# render chat
for role, msg in st.session_state.history:
    if role == "user":
        st.chat_message("user").markdown(msg)
    else:
        st.chat_message("assistant").markdown(msg)
