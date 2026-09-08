/**
 * RAG Chat Widget – zero-dependency embeddable chat UI with SSE streaming.
 *
 * Usage:
 *   <script src="https://YOUR-API/public/widget.js"
 *           data-chatbot-id="my-bot"
 *           data-api-url="https://YOUR-API"></script>
 */
(function () {
  "use strict";

  // ── Configuration ──────────────────────────────────────────
  var scriptEl = document.currentScript;
  var API_URL = scriptEl?.getAttribute("data-api-url") || "";
  var CHATBOT_ID = scriptEl?.getAttribute("data-chatbot-id") || "default";
  var STORAGE_KEY = "rag_widget_" + CHATBOT_ID;
  var CSS_URL = API_URL + "/public/widget.css";

  // ── Session persistence ────────────────────────────────────
  function getSessionId() {
    var stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        var parsed = JSON.parse(stored);
        if (parsed.session_id) return parsed.session_id;
      } catch (_) {}
    }
    var id = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ session_id: id }));
    return id;
  }

  var sessionId = getSessionId();

  // ── Load CSS ───────────────────────────────────────────────
  if (!document.querySelector('link[href="' + CSS_URL + '"]')) {
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = CSS_URL;
    document.head.appendChild(link);
  }

  // ── SVG Icons ──────────────────────────────────────────────
  var ICON_CHAT =
    '<svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
  var ICON_CLOSE =
    '<svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
  var ICON_SEND =
    '<svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
  var ICON_BOT =
    '<svg viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="9" cy="16" r="1"/><circle cx="15" cy="16" r="1"/><path d="M12 11V7"/></svg>';

  // ── Build DOM ──────────────────────────────────────────────
  var host = document.createElement("div");
  host.className = "rag-widget-host";
  host.attachShadow({ mode: "open" });

  host.shadowRoot.innerHTML =
    '<style>@import url("' + CSS_URL + '");</style>' +
    '<div class="rag-widget-window" id="rag-window">' +
    '  <div class="rag-widget-header">' +
    '    <div class="rag-widget-header-avatar">' + ICON_BOT + "</div>" +
    '    <div class="rag-widget-header-text">' +
    '      <div class="rag-widget-header-title">Chat Assistant</div>' +
    '      <div class="rag-widget-header-subtitle">Powered by RAG</div>' +
    "    </div>" +
    "  </div>" +
    '  <div class="rag-widget-messages" id="rag-messages"></div>' +
    '  <div class="rag-widget-input-area">' +
    '    <input class="rag-widget-input" id="rag-input" placeholder="Type a message..." autocomplete="off" />' +
    '    <button class="rag-widget-send" id="rag-send" title="Send">' + ICON_SEND + "</button>" +
    "  </div>" +
    '  <div class="rag-widget-badge">Powered by <a href="#">RAG Platform</a></div>' +
    "</div>" +
    '<button class="rag-widget-toggle" id="rag-toggle">' + ICON_CHAT + "</button>";

  document.body.appendChild(host);

  // ── References ─────────────────────────────────────────────
  var shadow = host.shadowRoot;
  var window_ = shadow.getElementById("rag-window");
  var messagesEl = shadow.getElementById("rag-messages");
  var inputEl = shadow.getElementById("rag-input");
  var sendBtn = shadow.getElementById("rag-send");
  var toggleBtn = shadow.getElementById("rag-toggle");

  // ── State ──────────────────────────────────────────────────
  var isOpen = false;
  var isLoading = false;
  var abortController = null;

  // ── Helpers ────────────────────────────────────────────────
  function addBubble(text, role) {
    var div = document.createElement("div");
    div.className = "rag-widget-bubble rag-widget-bubble-" + role;
    div.textContent = text;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return div;
  }

  function addError(text) {
    return addBubble(text, "error");
  }

  function showTyping() {
    var div = document.createElement("div");
    div.className = "rag-widget-typing";
    div.id = "rag-typing";
    div.innerHTML =
      '<span class="rag-widget-typing-dot"></span>' +
      '<span class="rag-widget-typing-dot"></span>' +
      '<span class="rag-widget-typing-dot"></span>';
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function removeTyping() {
    var el = shadow.getElementById("rag-typing");
    if (el) el.remove();
  }

  function setLoading(state) {
    isLoading = state;
    sendBtn.disabled = state;
    inputEl.disabled = state;
    if (!state) inputEl.focus();
  }

  function toggleWindow() {
    isOpen = !isOpen;
    window_.classList.toggle("rag-widget-visible", isOpen);
    toggleBtn.classList.toggle("rag-widget-open", isOpen);
    toggleBtn.innerHTML = isOpen ? ICON_CLOSE : ICON_CHAT;
    if (isOpen) inputEl.focus();
  }

  // ── SSE Stream Parser ──────────────────────────────────────
  async function sendMessage() {
    var text = inputEl.value.trim();
    if (!text || isLoading) return;

    inputEl.value = "";
    addBubble(text, "user");
    setLoading(true);
    showTyping();

    // Abort any prior in-flight stream
    if (abortController) {
      try { abortController.abort(); } catch (_) {}
    }
    abortController = new AbortController();

    try {
      var resp = await fetch(API_URL + "/api/v1/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: text,
          chatbot_id: CHATBOT_ID,
          session_id: sessionId,
        }),
        signal: abortController.signal,
      });

      if (!resp.ok) {
        removeTyping();
        var errBody;
        try { errBody = await resp.json(); } catch (_) { errBody = {}; }
        addError(errBody.detail || "Something went wrong. Please try again.");
        setLoading(false);
        return;
      }

      // Switch from typing dots to an empty assistant bubble that we fill token-by-token
      removeTyping();
      var assistantBubble = addBubble("", "assistant");

      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";

      while (true) {
        var { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Process complete SSE lines from the buffer
        var lines = buffer.split("\n");
        // Keep the last (potentially incomplete) line in the buffer
        buffer = lines.pop() || "";

        for (var i = 0; i < lines.length; i++) {
          var line = lines[i].trim();
          if (!line.startsWith("data: ")) continue;

          var payload = line.slice(6); // strip "data: "

          // End-of-stream sentinel
          if (payload === "[DONE]") {
            setLoading(false);
            return;
          }

          try {
            var parsed = JSON.parse(payload);

            // Session metadata event (first event)
            if (parsed && parsed.session_id) {
              sessionId = parsed.session_id;
              continue;
            }

            // Error event
            if (parsed && parsed.error) {
              addError(parsed.error);
              setLoading(false);
              return;
            }

            // Token string
            if (typeof parsed === "string") {
              assistantBubble.textContent += parsed;
              messagesEl.scrollTop = messagesEl.scrollHeight;
            }
          } catch (_) {
            // Non-JSON payload — append raw text
            if (payload !== "[DONE]") {
              assistantBubble.textContent += payload;
              messagesEl.scrollTop = messagesEl.scrollHeight;
            }
          }
        }
      }

      // Stream ended without [DONE] sentinel (network interruption)
      setLoading(false);
    } catch (err) {
      removeTyping();
      if (err.name === "AbortError") {
        // User triggered a new message — don't show error
        return;
      }
      addError("Network error. Please check your connection and try again.");
      setLoading(false);
    }
  }

  // ── Event Listeners ────────────────────────────────────────
  toggleBtn.addEventListener("click", toggleWindow);
  sendBtn.addEventListener("click", sendMessage);
  inputEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // ── Welcome message ────────────────────────────────────────
  addBubble("Hi! How can I help you today?", "assistant");
})();
