// BankBot chat widget (v7) — guaranteed send + reply, with typing bubble and UX polish
(function () {
  function ready(fn) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  }

  ready(() => {
    // Grab elements
    const fab     = document.getElementById("chat-fab");
    const panel   = document.getElementById("chat-panel");
    const closeBt = document.getElementById("chat-close");
    const sendBt  = document.getElementById("chat-send");
    const input   = document.getElementById("chat-text");
    const log     = document.getElementById("chat-log");

    // Hard checks + console hints
    if (!fab || !panel || !sendBt || !input || !log) {
      console.error("[Chat] Missing elements", { fab:!!fab, panel:!!panel, sendBt:!!sendBt, input:!!input, log:!!log });
      return;
    }

    // Utils
    const addMsg = (text, who = "bot") => {
      const div = document.createElement("div");
      div.className = "msg " + (who === "me" ? "me" : "bot");
      div.textContent = text || "…";
      log.appendChild(div);
      log.scrollTop = log.scrollHeight;
      return div;
    };
    const showTyping = () => {
      const t = document.createElement("div");
      t.className = "msg bot typing";
      t.textContent = "typing…";
      log.appendChild(t);
      log.scrollTop = log.scrollHeight;
      return t;
    };

    // Open/close
    const openPanel = () => {
      panel.classList.remove("hidden");
      if (!log.dataset.greeted) {
        addMsg("👋 Hello! Ask me about balance, last transactions, loans, cards or transfers.");
        log.dataset.greeted = "1";
      }
      input.focus();
    };
    const closePanel = () => panel.classList.add("hidden");

    fab.addEventListener("click", openPanel);
    if (closeBt) closeBt.addEventListener("click", closePanel);

    // SEND
    async function sendMsg(e) {
      if (e) e.preventDefault(); // protect against form submits
      const text = (input.value || "").trim();
      if (!text) return;

      addMsg(text, "me");
      input.value = "";

      const typing = showTyping();

      try {
        const res = await fetch("/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
          credentials: "same-origin"
        });

        const ct = res.headers.get("content-type") || "";
        if (!ct.includes("application/json")) {
          typing.remove();
          addMsg("⚠️ Session expired or server error. Please sign in again.", "bot");
          console.warn("[Chat] Non-JSON response", res.status);
          return;
        }

        const data = await res.json();
        typing.remove();
        addMsg(data.reply, "bot");

        // Optional UI cues from backend
        if (data.action === "show_balance") {
          const el = document.getElementById("balance-amount");
          if (el) { el.classList.add("pulse"); setTimeout(()=>el.classList.remove("pulse"), 400); }
        } else if (data.action === "show_last_txns") {
          const tb = document.getElementById("txn-body");
          if (tb) { tb.classList.add("flash"); setTimeout(()=>tb.classList.remove("flash"), 400); }
        }
      } catch (err) {
        typing.remove();
        console.error("[Chat] fetch failed", err);
        addMsg("⚠️ Network error. Please try again.", "bot");
      }
    }

    // Bind send button and keys
    sendBt.addEventListener("click", sendMsg);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) sendMsg(e);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "enter") sendMsg(e);
    });

    // Shortcuts
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closePanel();
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") openPanel();
    });

    console.log("[Chat] initialized ✅");
  });
})();

