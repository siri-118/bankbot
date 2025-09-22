// static/script.js (patched same as user-script.js)
(function () {
  const ready = (fn) => (document.readyState === "loading"
    ? document.addEventListener("DOMContentLoaded", fn)
    : fn());

  ready(() => {
    const fab = document.getElementById("chat-fab");
    const panel = document.getElementById("chat-panel");
    const closeBtn = document.getElementById("chat-close");
    const sendBtn = document.getElementById("chat-send");
    const input = document.getElementById("chat-text");
    const log = document.getElementById("chat-log");

    if (!fab || !panel || !sendBtn || !input || !log) {
      console.error("[Chat] Missing elements:", { fab, panel, sendBtn, input, log });
      return;
    }

    // Add message
    const addMsg = (text, who = "bot") => {
      const m = document.createElement("div");
      m.className = "msg " + (who === "me" ? "me" : "bot");

      if (who === "me") {
        m.textContent = text || "…";   // user plain text
      } else {
        m.innerHTML = text || "…";     // bot can use HTML (for Entity line)
      }

      log.appendChild(m);
      log.scrollTop = log.scrollHeight;
    };

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
    if (closeBtn) closeBtn.addEventListener("click", closePanel);

    async function sendMsg() {
      const text = (input.value || "").trim();
      if (!text) return;

      addMsg(text, "me");
      input.value = "";

      try {
        const res = await fetch("/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
          credentials: "same-origin"
        });

        const ct = res.headers.get("content-type") || "";
        if (!ct.includes("application/json")) {
          addMsg("⚠️ Session expired or server error. Please sign in again.", "bot");
          return;
        }

        const data = await res.json();
        const botHtml = data.reply_html || data.reply || "";
        addMsg(botHtml, "bot");

      } catch (err) {
        console.error("[Chat] fetch failed", err);
        addMsg("⚠️ Network error. Please try again.", "bot");
      }
    }

    sendBtn.addEventListener("click", sendMsg);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") sendMsg(); });

    console.log("[Chat] initialized ✅");
  });
})();