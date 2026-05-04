const sessionList = document.querySelector("#sessionList");
const messagesEl = document.querySelector("#messages");
const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const newChatButton = document.querySelector("#newChatButton");
const openSidebar = document.querySelector("#openSidebar");
const closeSidebar = document.querySelector("#closeSidebar");
const sidebar = document.querySelector(".sidebar");

let currentSessionId = localStorage.getItem("cookwhat_session_id") || crypto.randomUUID();
let isSending = false;

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
  scrollToBottom();
}

function setLoading(enabled) {
  isSending = enabled;
  sendButton.disabled = enabled;
  input.disabled = enabled;
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
    addMessage("assistant", data.response || "Mình chưa có phản hồi phù hợp.");
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
