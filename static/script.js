// static/user-script.js (v5 — guaranteed send + reply with clear logs)
(function () {
  const ready = (fn) => (document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', fn)
    : fn());

  ready(() => {
    const $ = (q) => document.querySelector(q);

    const fab = $('#chat-fab');
    const panel = $('#chat-panel');
    const closeBtn = $('#chat-close');
    const sendBtn = $('#chat-send');
    const input = $('#chat-text');
    const log = $('#chat-log');

    if (!fab || !panel || !sendBtn || !input || !log) {
      console.error('[Chat] Missing element(s):', {
        fab: !!fab, panel: !!panel, sendBtn: !!sendBtn, input: !!input, log: !!log
      });
      return;
    }

    const addMsg = (text, who = 'bot') => {
      const m = document.createElement('div');
      m.className = 'msg ' + (who === 'me' ? 'me' : 'bot');
      m.textContent = text || '…';
      log.appendChild(m);
      log.scrollTop = log.scrollHeight;
    };

    const openPanel = () => {
      panel.classList.remove('hidden');
      if (!log.dataset.greeted) {
        addMsg("Hi! I'm here to help with balance, last transactions, cards or loans.");
        log.dataset.greeted = '1';
      }
      input.focus();
    };
    const closePanel = () => panel.classList.add('hidden');

    fab.addEventListener('click', openPanel);
    if (closeBtn) closeBtn.addEventListener('click', closePanel);

    async function sendMsg() {
      const text = (input.value || '').trim();
      if (!text) return;
      addMsg(text, 'me');
      input.value = '';

      try {
        const res = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text }),
          credentials: 'same-origin'
        });

        // If session expired or server redirected to /login, we won't get JSON.
        const ct = res.headers.get('content-type') || '';
        if (!ct.includes('application/json')) {
          addMsg('Session expired or server error. Please sign in again.', 'bot');
          console.warn('[Chat] Non-JSON response (maybe redirect). HTTP', res.status);
          return;
        }

        const data = await res.json();
        addMsg(data.reply, 'bot');

        // UI hints
        if (data.action === 'show_balance') {
          const el = document.getElementById('balance-amount');
          if (el) {
            el.style.transition = 'transform .15s ease';
            el.style.transform = 'scale(1.05)';
            setTimeout(() => (el.style.transform = 'scale(1)'), 200);
          }
        } else if (data.action === 'show_last_txns') {
          const tb = document.getElementById('txn-body');
          if (tb) {
            tb.style.transition = 'background .2s ease';
            tb.style.background = 'rgba(86,97,255,.08)';
            setTimeout(() => (tb.style.background = 'transparent'), 300);
          }
        }
      } catch (err) {
        console.error('[Chat] fetch failed', err);
        addMsg('Network error. Please try again.', 'bot');
      }
    }

    sendBtn.addEventListener('click', sendMsg);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendMsg(); });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closePanel();
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') openPanel();
    });

    console.log('[Chat] initialized ✅');
  });
})();
