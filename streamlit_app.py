# streamlit_app.py
import streamlit as st
import requests

st.set_page_config(page_title="💬 BankBot", page_icon="🏦", layout="centered")
st.title("🏦 BankBot")

BACKEND_URL = "http://127.0.0.1:5000/chat"

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "bot", "content": "👋 Hello! Ask me about balance, last transactions, loans, cards or transfers."}
    ]

# Display chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
user_input = st.chat_input("Type your message...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})

    try:
        response = requests.post(BACKEND_URL, json={"message": user_input}, timeout=10)
        data = response.json()

        bot_msg = data.get("reply", "⚠️ No reply from backend.")
        entity = data.get("entity", "unknown")
        bot_msg = f"{bot_msg}\n\n**Entity:** `{entity}`"

    except requests.exceptions.ConnectionError:
        bot_msg = "⚠️ Backend not reachable. Start Flask (`python app.py`) first."
    except ValueError:
        bot_msg = "⚠️ Backend returned invalid response."
    except Exception as e:
        bot_msg = f"⚠️ Unexpected error: {str(e)}"

    st
