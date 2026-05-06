const sessionList = document.querySelector("#sessionList");
const messagesEl = document.querySelector("#messages");
const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const newChatButton = document.querySelector("#newChatButton");
const openSidebar = document.querySelector("#openSidebar");
const closeSidebar = document.querySelector("#closeSidebar");
const sidebar = document.querySelector(".sidebar");
const deleteModal = document.querySelector("#deleteModal");
const deleteModalCancel = document.querySelector("#deleteModalCancel");
const deleteModalConfirm = document.querySelector("#deleteModalConfirm");

let currentSessionId = localStorage.getItem("cookwhat_session_id") || crypto.randomUUID();
let isSending = false;
let openSessionMenu = null;
let editingSessionId = null;
let pendingRenameSessionId = null;
let deleteTargetSession = null;

function setCurrentSession(sessionId) {
  currentSessionId = sessionId || crypto.randomUUID();
  localStorage.setItem("cookwhat_session_id", currentSessionId);
}

function pinIconSvg() {
  return `
    <svg class="session-pin-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M14 3l7 7-2 2-2-1-4 4v3l-2 2-3-3 2-2v-3l-4-4-2 1-2-2 7-7 2 2 1 1z"></path>
    </svg>
  `;
}

function closeSessionMenu() {
  if (openSessionMenu) {
    const menu = openSessionMenu.querySelector(".session-menu");
    if (menu) menu.hidden = true;
    openSessionMenu.removeAttribute("data-open");
    openSessionMenu = null;
  }
}

function toggleSessionMenu(item) {
  if (!item) return;

  if (openSessionMenu === item) {
    closeSessionMenu();
    return;
  }

  closeSessionMenu();
  item.setAttribute("data-open", "true");
  openSessionMenu = item;
}

function closeDeleteModal() {
  deleteTargetSession = null;
  deleteModal.hidden = true;
}

function openDeleteModal(session) {

  if (!session || !session.id) {
    console.warn("Invalid session, not opening modal");
    return;
  }
  closeSessionMenu();
  deleteTargetSession = session;
  deleteModal.hidden = false;
  deleteModalConfirm?.focus();
}

async function updateSession(sessionId, payload) {
  const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Không thể cập nhật lịch sử chat.");
  }

  return response.json();
}

function startRenameSession(session) {
  editingSessionId = session.id;
  pendingRenameSessionId = session.id;
  closeSessionMenu();
  loadSessions();
}

async function finishRenameSession(sessionId, inputEl, cancel = false) {
  if (cancel) {
    editingSessionId = null;
    pendingRenameSessionId = null;
    loadSessions();
    return;
  }

  const nextTitle = inputEl.value.trim();
  try {
    await updateSession(sessionId, { title: nextTitle || "New chat" });
    editingSessionId = null;
    pendingRenameSessionId = null;
    await loadSessions();
  } catch (error) {
    window.alert(error.message || "Không thể đổi tên đoạn chat.");
    window.requestAnimationFrame(() => {
      inputEl.focus();
      inputEl.select();
    });
  }
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

  if (safeRole === "assistant" && !options.loading) {
    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.className = "message-copy-button";
    copyButton.setAttribute("aria-label", "Sao chép câu trả lời");
    copyButton.textContent = "Copy";
    copyButton.addEventListener("click", async (event) => {
      event.stopPropagation();
      try {
        await navigator.clipboard.writeText(safeContent);
        const originalText = copyButton.textContent;
        copyButton.textContent = "Copied";
        copyButton.disabled = true;
        window.setTimeout(() => {
          copyButton.textContent = originalText;
          copyButton.disabled = false;
        }, 1200);
      } catch (error) {
        copyButton.textContent = "Lỗi";
        window.setTimeout(() => {
          copyButton.textContent = "Copy";
        }, 1200);
      }
    });
    bubble.appendChild(copyButton);
  }

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
    const item = document.createElement("div");
    const isActive = session.id === currentSessionId;
    const isEditing = session.id === editingSessionId;
    item.className = `session-item${isActive ? " active" : ""}${isEditing ? " editing" : ""}`;
    item.dataset.sessionId = session.id;
    item.innerHTML = `
      <button class="session-button${isActive ? " active" : ""}" type="button">
        <span class="session-main">
          <span class="session-title-row">
            ${session.pinned ? pinIconSvg() : ""}
            <span class="session-title-text${isEditing ? " hidden" : ""}">${escapeHtml(session.title || "New chat")}</span>
          </span>
          <span class="session-meta">${escapeHtml((session.ingredients || []).join(", ") || "CookWhat")}</span>
        </span>
      </button>
      <input
        class="session-rename-input"
        type="text"
        value="${escapeHtml(session.title || "New chat")}"
        aria-label="Sửa tên đoạn chat"
        ${isEditing ? "" : "hidden"}
      />
      <button class="session-menu-trigger" type="button" aria-label="Mở tùy chọn" aria-haspopup="menu">
        <span aria-hidden="true">⋯</span>
      </button>
      <div class="session-menu" role="menu" hidden>
        <button type="button" data-action="rename">Rename</button>
        <button type="button" data-action="pin">${session.pinned ? "Unpin" : "Pin to Top"}</button>
        <button type="button" data-action="delete">Delete Chat</button>
      </div>
    `;

    const button = item.querySelector(".session-button");
    const renameInput = item.querySelector(".session-rename-input");
    const menuTrigger = item.querySelector(".session-menu-trigger");
    const menu = item.querySelector(".session-menu");

    button.addEventListener("click", () => {
      if (editingSessionId === session.id) return;
      closeSessionMenu();
      setCurrentSession(session.id);
      loadMessages(session.id);
      loadSessions();
      sidebar.classList.remove("open");
    });

    menuTrigger.addEventListener("click", (event) => {
      event.stopPropagation();
      if (menu.hidden) {
        menu.hidden = false;
        toggleSessionMenu(item);
      } else {
        menu.hidden = true;
        closeSessionMenu();
      }
    });

    menu.addEventListener("click", async (event) => {
      const actionButton = event.target.closest("button[data-action]");
      if (!actionButton) return;

      const action = actionButton.dataset.action;
      if (action === "rename") {
        startRenameSession(session);
        return;
      }

      if (action === "pin") {
        await updateSession(session.id, { pinned: !session.pinned });
      }

      if (action === "delete") {
        openDeleteModal(session);
        return;
      }

      closeSessionMenu();
      await loadSessions();
    });

    renameInput?.addEventListener("keydown", async (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        await finishRenameSession(session.id, renameInput);
      }

      if (event.key === "Escape") {
        event.preventDefault();
        await finishRenameSession(session.id, renameInput, true);
      }
    });

    renameInput?.addEventListener("blur", async () => {
      if (editingSessionId !== session.id) return;
      await finishRenameSession(session.id, renameInput);
    });

    if (pendingRenameSessionId === session.id && renameInput) {
      window.requestAnimationFrame(() => {
        renameInput.focus();
        renameInput.select();
      });
    }

    sessionList.appendChild(item);
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

document.addEventListener("click", (event) => {
  if (!event.target.closest(".session-item")) {
    closeSessionMenu();
  }
});

document.addEventListener("scroll", () => {
  closeSessionMenu();
}, true);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (!deleteModal.hidden) {
      closeDeleteModal();
      return;
    }
    closeSessionMenu();
  }
});

deleteModal?.addEventListener("click", (event) => {
  if (event.target?.dataset?.dismiss === "true") {
    closeDeleteModal();
  }
});

deleteModalCancel?.addEventListener("click", () => {
  closeDeleteModal();
});

deleteModalConfirm?.addEventListener("click", async () => {
  if (!deleteTargetSession) return;

  const session = deleteTargetSession;

  closeDeleteModal();

  try {
    await fetch(`/api/sessions/${encodeURIComponent(session.id)}`, {
      method: "DELETE",
    });

    if (session.id === currentSessionId) {
      setCurrentSession(crypto.randomUUID());
      await loadMessages(currentSessionId);
    }
    const item = document.querySelector(`[data-session-id="${session.id}"]`);
    if (item) item.remove();

    closeSessionMenu();
    await loadSessions();
  } catch (error) {
    window.alert("Không thể xóa đoạn chat.");
  }
});

newChatButton.addEventListener("click", () => {
  closeSessionMenu();
  closeDeleteModal();
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
