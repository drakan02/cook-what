const sessionList = document.querySelector("#sessionList");
const messagesEl = document.querySelector("#messages");
const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const newChatButton = document.querySelector("#newChatButton");
const openSidebar = document.querySelector("#openSidebar");
const closeSidebar = document.querySelector("#closeSidebar");
const sidebar = document.querySelector(".sidebar");
const micButton = document.querySelector("#micButton");

let currentSessionId = localStorage.getItem("cookwhat_session_id") || crypto.randomUUID();
let isSending = false;

// Speech-to-Text (STT)
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let isRecording = false;

if (SpeechRecognition) {
  recognition = new SpeechRecognition();
  recognition.lang = "vi-VN";
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.maxAlternatives = 1;

  let interimStart = 0; // cursor position where interim result begins

  recognition.addEventListener("start", () => {
    isRecording = true;
    micButton.classList.add("recording");
    micButton.title = "Đang nghe... (nhấn để dừng)";
  });

  recognition.addEventListener("result", (event) => {
    let interimText = "";
    let finalText = "";

    for (const result of event.results) {
      if (result.isFinal) {
        finalText += result[0].transcript;
      } else {
        interimText += result[0].transcript;
      }
    }

    // Replace interim portion and append final text
    const base = input.value.slice(0, interimStart);
    if (finalText) {
      input.value = base + finalText;
      interimStart = input.value.length;
    } else {
      input.value = base + interimText;
    }
    autoResizeInput();
  });

  recognition.addEventListener("end", () => {
    isRecording = false;
    micButton.classList.remove("recording");
    micButton.title = "Nhận dạng giọng nói";
    interimStart = input.value.length;
  });

  recognition.addEventListener("error", (event) => {
    isRecording = false;
    micButton.classList.remove("recording");
    micButton.title = "Nhận dạng giọng nói";
    if (event.error !== "aborted") {
      const msgs = {
        "not-allowed": "Vui lòng cấp quyền micro cho trang.",
        "no-speech": "Không nghe thấy giọng nói.",
        "network": "Lỗi mạng khi nhận dạng giọng nói.",
      };
      const msg = msgs[event.error] || `Lỗi nhận dạng: ${event.error}`;
      showToast(msg);
    }
  });

  micButton.addEventListener("click", () => {
    if (isRecording) {
      recognition.stop();
    } else {
      interimStart = input.value.length;
      try {
        recognition.start();
      } catch {
        // recognition already started – ignore
      }
    }
  });
} else {
  // Browser doesn't support STT – hide the button
  if (micButton) micButton.style.display = "none";
}

// Text-to-Speech — Backend API (gTTS tiếng Việt)
let currentAudio = null;
let currentSpeakBtn = null;

function stopSpeaking() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.src = "";
    currentAudio = null;
  }
  if (currentSpeakBtn) {
    currentSpeakBtn.classList.remove("speaking");
    currentSpeakBtn.innerHTML = speakButtonInner(false);
    currentSpeakBtn = null;
  }
}

function speakButtonInner(speaking) {
  const label = speaking ? "Dừng" : "Đọc";
  const icon = speaking
    ? `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>`;
  return `${icon}<span>${label}</span>`;
}

function attachSpeakButton(row, plainText) {
  const bubble = row.querySelector(".bubble");
  if (!bubble) return;

  const btn = document.createElement("button");
  btn.className = "speak-button";
  btn.setAttribute("aria-label", "Đọc phản hồi");
  btn.innerHTML = speakButtonInner(false);

  btn.addEventListener("click", async () => {
    if (btn.classList.contains("speaking")) {
      stopSpeaking();
      return;
    }
    stopSpeaking();

    // Hiển thị trạng thái đang tải
    btn.disabled = true;
    btn.style.opacity = "0.6";

    try {
      const response = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: plainText, lang: "vi" }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${response.status}`);
      }

      const blob = await response.blob();
      const audioUrl = URL.createObjectURL(blob);
      const audio = new Audio(audioUrl);

      currentAudio = audio;
      currentSpeakBtn = btn;
      btn.classList.add("speaking");
      btn.innerHTML = speakButtonInner(true);

      const onEnd = () => {
        if (currentSpeakBtn === btn) {
          btn.classList.remove("speaking");
          btn.innerHTML = speakButtonInner(false);
          currentSpeakBtn = null;
          currentAudio = null;
        }
        URL.revokeObjectURL(audioUrl);
      };
      audio.addEventListener("ended", onEnd);
      audio.addEventListener("error", () => {
        onEnd();
        showToast("Lỗi phát audio.");
      });

      audio.play();
    } catch (error) {
      showToast(`Lỗi TTS: ${error.message}`);
    } finally {
      btn.disabled = false;
      btn.style.opacity = "";
    }
  });

  bubble.appendChild(btn);
}


// Helper: strip markdown to plain text for TTS
function stripMarkdown(md) {
  return md
    .replace(/#{1,6}\s*/g, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*\n]+)\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/[-*]\s+/g, "")
    .replace(/\d+\.\s+/g, "")
    .replace(/---+/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

// ─── Toast helper ────────────────────────────────────────────────────────────
function showToast(message, duration = 3500) {
  let toast = document.getElementById("cw-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "cw-toast";
    Object.assign(toast.style, {
      position: "fixed",
      bottom: "90px",
      left: "50%",
      transform: "translateX(-50%)",
      background: "#1f2328",
      color: "#f8fafc",
      padding: "10px 18px",
      borderRadius: "8px",
      fontSize: "14px",
      fontWeight: "500",
      zIndex: "9999",
      boxShadow: "0 4px 24px rgba(0,0,0,0.18)",
      transition: "opacity 0.3s",
      pointerEvents: "none",
    });
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.style.opacity = "1";
  clearTimeout(toast._hideTimer);
  toast._hideTimer = setTimeout(() => { toast.style.opacity = "0"; }, duration);
}

function setCurrentSession(sessionId) {
  currentSessionId = sessionId || crypto.randomUUID();
  localStorage.setItem("cookwhat_session_id", currentSessionId);
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderInlineMarkdown(value) {
  let output = escapeHtml(value);
  output = output.replace(
    /(https?:\/\/[^\s<]+)/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  output = output.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  output = output.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  output = output.replace(/`([^`]+)`/g, "<code>$1</code>");
  return output;
}

function flushList(listItems, ordered) {
  if (!listItems.length) return "";

  const tag = ordered ? "ol" : "ul";
  const items = listItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("");
  return `<${tag}>${items}</${tag}>`;
}

function renderMarkdown(content) {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  let listItems = [];
  let orderedList = false;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  const flushCurrentList = () => {
    if (!listItems.length) return;
    blocks.push(flushList(listItems, orderedList));
    listItems = [];
  };

  lines.forEach((line) => {
    const trimmed = line.trim();

    if (!trimmed) {
      flushParagraph();
      flushCurrentList();
      return;
    }

    if (/^---+$/.test(trimmed)) {
      flushParagraph();
      flushCurrentList();
      blocks.push("<hr>");
      return;
    }

    const headingMatch = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushCurrentList();
      const level = Math.min(headingMatch[1].length + 2, 4);
      blocks.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
      return;
    }

    const orderedMatch = trimmed.match(/^\d+\.\s+(.+)$/);
    if (orderedMatch) {
      flushParagraph();
      if (listItems.length && !orderedList) flushCurrentList();
      orderedList = true;
      listItems.push(orderedMatch[1]);
      return;
    }

    const bulletMatch = trimmed.match(/^[-*]\s+(.+)$/);
    if (bulletMatch) {
      flushParagraph();
      if (listItems.length && orderedList) flushCurrentList();
      orderedList = false;
      listItems.push(bulletMatch[1]);
      return;
    }

    flushCurrentList();
    paragraph.push(trimmed);
  });

  flushParagraph();
  flushCurrentList();

  return blocks.join("");
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderEmpty() {
  messagesEl.innerHTML = `
    <div class="empty-state">
      <h2>Hôm nay nấu gì?</h2>
      <p>Gõ nguyên liệu đang có trong tủ lạnh. CookWhat sẽ tìm món phù hợp và bạn có thể hỏi tiếp như một cuộc trò chuyện.</p>
    </div>
  `;
}

function addMessage(role, content, options = {}) {
  const empty = messagesEl.querySelector(".empty-state");
  if (empty) empty.remove();

  const normalizedRole = String(role || "").trim().toLowerCase();
  const safeRole = normalizedRole === "assistant" ? "assistant" : "user";
  const safeContent = String(content || "");

  const row = document.createElement("div");
  row.className = `message-row ${safeRole}${options.loading ? " loading" : ""}`;
  if (options.id) row.id = options.id;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = safeRole === "assistant" ? renderMarkdown(safeContent) : escapeHtml(safeContent);

  row.appendChild(bubble);
  messagesEl.appendChild(row);

  // Attach TTS button to non-loading assistant messages
  if (safeRole === "assistant" && !options.loading) {
    attachSpeakButton(row, stripMarkdown(safeContent));
  }

  scrollToBottom();
}

function setLoading(enabled) {
  isSending = enabled;
  sendButton.disabled = enabled;
  input.disabled = enabled;
  if (micButton) micButton.disabled = enabled;
}

function autoResizeInput() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
}

async function loadSessions() {
  const response = await fetch("/api/sessions");
  const sessions = await response.json();

  sessionList.innerHTML = "";
  sessions.forEach((session) => {
    const button = document.createElement("button");
    button.className = `session-button${session.id === currentSessionId ? " active" : ""}`;
    button.type = "button";
    button.dataset.sessionId = session.id;
    button.innerHTML = `
      <span class="session-title">${escapeHtml(session.title || "New chat")}</span>
      <span class="session-meta">${escapeHtml((session.ingredients || []).join(", ") || "CookWhat")}</span>
    `;
    button.addEventListener("click", () => {
      setCurrentSession(session.id);
      loadMessages(session.id);
      loadSessions();
      sidebar.classList.remove("open");
    });
    sessionList.appendChild(button);
  });
}

async function loadMessages(sessionId) {
  const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/messages`);
  const messages = await response.json();

  messagesEl.innerHTML = "";
  if (!messages.length) {
    renderEmpty();
    return;
  }

  messages.forEach((message) => addMessage(message.role, message.content));
}

async function sendMessage(content) {
  addMessage("user", content);
  addMessage("assistant", "Đang suy nghĩ...", { id: "loadingMessage", loading: true });
  setLoading(true);

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: content,
        session_id: currentSessionId,
        top_k: 5,
      }),
    });

    const data = await response.json();
    const loading = document.querySelector("#loadingMessage");
    if (loading) loading.remove();

    if (!response.ok) {
      addMessage("assistant", data.detail || "Có lỗi xảy ra khi gửi tin nhắn.");
      return;
    }

    setCurrentSession(data.session_id || currentSessionId);
    const assistantText = data.response || "Mình chưa có phản hồi phù hợp.";
    addMessage("assistant", assistantText);
    await loadSessions();
  } catch (error) {
    const loading = document.querySelector("#loadingMessage");
    if (loading) loading.remove();
    addMessage("assistant", "Không kết nối được backend. Kiểm tra server FastAPI và PostgreSQL nếu bạn đang bật lưu lịch sử.");
  } finally {
    setLoading(false);
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  if (isSending) return;

  const content = input.value.trim();
  if (!content) return;

  input.value = "";
  autoResizeInput();
  sendMessage(content);
});

input.addEventListener("input", autoResizeInput);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

newChatButton.addEventListener("click", () => {
  setCurrentSession(crypto.randomUUID());
  renderEmpty();
  loadSessions();
  sidebar.classList.remove("open");
  input.focus();
});

openSidebar.addEventListener("click", () => sidebar.classList.add("open"));
closeSidebar.addEventListener("click", () => sidebar.classList.remove("open"));

setCurrentSession(currentSessionId);
renderEmpty();
loadMessages(currentSessionId);
loadSessions();
