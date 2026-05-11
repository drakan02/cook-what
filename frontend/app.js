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
const micButton = document.querySelector("#micButton");

let currentSessionId = localStorage.getItem("cookwhat_session_id") || crypto.randomUUID();
let isSending = false;
let openSessionMenu = null;
let editingSessionId = null;
let pendingRenameSessionId = null;
let deleteTargetSession = null;
let currentAudio = null;
let currentSpeakButton = null;
let currentAudioUrl = null;

function setCurrentSession(sessionId) {
  currentSessionId = sessionId || crypto.randomUUID();
  localStorage.setItem("cookwhat_session_id", currentSessionId);
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function pinIconSvg() {
  return `
    <svg class="session-pin-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M14 3l7 7-2 2-2-1-4 4v3l-2 2-3-3 2-2v-3l-4-4-2 1-2-2 7-7 2 2 1 1z"></path>
    </svg>
  `;
}

function actionIcon(type) {
  if (type === "copy") {
    return `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="9" y="9" width="11" height="11" rx="2"></rect>
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
      </svg>
    `;
  }

  if (type === "pause") {
    return `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <rect x="6" y="4" width="4" height="16"></rect>
        <rect x="14" y="4" width="4" height="16"></rect>
      </svg>
    `;
  }

  return `
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
      <path d="M15.5 8.5a5 5 0 0 1 0 7"></path>
      <path d="M19 5a10 10 0 0 1 0 14"></path>
    </svg>
  `;
}

function flashAction(button, duration = 1200) {
  button.classList.add("is-active");
  window.setTimeout(() => {
    if (!button.classList.contains("is-speaking")) {
      button.classList.remove("is-active");
    }
  }, duration);
}

function stripMarkdown(content) {
  return String(content || "")
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

function stopSpeaking() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.src = "";
    currentAudio = null;
  }

  if (currentAudioUrl) {
    URL.revokeObjectURL(currentAudioUrl);
    currentAudioUrl = null;
  }

  if (currentSpeakButton) {
    currentSpeakButton.classList.remove("is-active", "is-speaking");
    currentSpeakButton.innerHTML = actionIcon("speak");
    currentSpeakButton.setAttribute("aria-label", "Đọc câu trả lời");
    currentSpeakButton = null;
  }
}

function finishSpeakingNaturally(audioUrl, button) {
  if (currentAudioUrl === audioUrl) {
    URL.revokeObjectURL(audioUrl);
    currentAudioUrl = null;
  }

  if (currentAudio && currentAudio.src === audioUrl) {
    currentAudio = null;
  }

  if (currentSpeakButton === button) {
    button.classList.remove("is-active", "is-speaking");
    button.innerHTML = actionIcon("speak");
    button.setAttribute("aria-label", "Đọc câu trả lời");
    button.title = "Đọc câu trả lời";
    currentSpeakButton = null;
  }
}

function showToast(message, duration = 3000) {
  let toast = document.querySelector("#cw-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "cw-toast";
    document.body.appendChild(toast);
  }

  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toast._hideTimer);
  toast._hideTimer = window.setTimeout(() => {
    toast.classList.remove("show");
  }, duration);
}

function closeSessionMenu() {
  if (!openSessionMenu) return;

  const menu = openSessionMenu.querySelector(".session-menu");
  if (menu) menu.hidden = true;
  openSessionMenu.removeAttribute("data-open");
  openSessionMenu = null;
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
  if (!deleteModal) return;
  deleteModal.hidden = true;
  deleteModal.setAttribute("aria-hidden", "true");
}

function openDeleteModal(session) {
  if (!session?.id || !deleteModal) return;

  closeSessionMenu();
  deleteTargetSession = session;
  deleteModal.hidden = false;
  deleteModal.setAttribute("aria-hidden", "false");
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

  try {
    await updateSession(sessionId, { title: inputEl.value.trim() || "New chat" });
    editingSessionId = null;
    pendingRenameSessionId = null;
    await loadSessions();
  } catch (error) {
    showToast(error.message || "Không thể đổi tên đoạn chat.");
    window.requestAnimationFrame(() => {
      inputEl.focus();
      inputEl.select();
    });
  }
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
  const lines = String(content || "").replace(/\r\n/g, "\n").split("\n");
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

function createAnswerActions(content) {
  const actions = document.createElement("div");
  actions.className = "message-actions";

  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "message-action-button";
  copyButton.setAttribute("aria-label", "Sao chép câu trả lời");
  copyButton.title = "Sao chép";
  copyButton.innerHTML = actionIcon("copy");
  copyButton.addEventListener("click", async (event) => {
    event.stopPropagation();
    try {
      await navigator.clipboard.writeText(content);
      flashAction(copyButton);
      showToast("Đã sao chép câu trả lời.", 1200);
    } catch {
      showToast("Không thể sao chép câu trả lời.");
    }
  });

  const speakButton = document.createElement("button");
  speakButton.type = "button";
  speakButton.className = "message-action-button";
  speakButton.setAttribute("aria-label", "Đọc câu trả lời");
  speakButton.title = "Đọc câu trả lời";
  speakButton.innerHTML = actionIcon("speak");
  speakButton.addEventListener("click", async (event) => {
    event.stopPropagation();

    if (currentSpeakButton === speakButton) {
      stopSpeaking();
      return;
    }

    stopSpeaking();
    speakButton.disabled = true;
    speakButton.classList.add("is-active");

    try {
      const response = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: stripMarkdown(content), lang: "vi" }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${response.status}`);
      }

      const blob = await response.blob();
      const audioUrl = URL.createObjectURL(blob);
      currentAudioUrl = audioUrl;
      currentAudio = new Audio(audioUrl);
      currentSpeakButton = speakButton;

      speakButton.classList.add("is-speaking");
      speakButton.innerHTML = actionIcon("pause");
      speakButton.setAttribute("aria-label", "Dừng đọc câu trả lời");
      speakButton.title = "Dừng đọc";

      currentAudio.addEventListener("ended", () => {
        finishSpeakingNaturally(audioUrl, speakButton);
      });
      currentAudio.addEventListener("error", () => {
        const shouldReport = currentAudio !== null;
        stopSpeaking();
        if (shouldReport) {
          showToast("Lỗi phát audio.");
        }
      });
      await currentAudio.play();
    } catch (error) {
      speakButton.classList.remove("is-active", "is-speaking");
      speakButton.innerHTML = actionIcon("speak");
      showToast(`Lỗi đọc câu trả lời: ${error.message}`);
    } finally {
      speakButton.disabled = false;
    }
  });

  actions.append(copyButton, speakButton);
  return actions;
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
    bubble.appendChild(createAnswerActions(safeContent));
  }

  row.appendChild(bubble);
  messagesEl.appendChild(row);
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
        <button type="button" data-action="rename">Sửa tên</button>
        <button type="button" data-action="pin">${session.pinned ? "Bỏ ghim" : "Ghim lên đầu"}</button>
        <button type="button" data-action="delete">Xóa đoạn chat</button>
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
  } catch {
    const loading = document.querySelector("#loadingMessage");
    if (loading) loading.remove();
    addMessage("assistant", "Không kết nối được backend. Kiểm tra server FastAPI và PostgreSQL nếu bạn đang bật lưu lịch sử.");
  } finally {
    setLoading(false);
    input.focus();
  }
}

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let isRecording = false;

if (SpeechRecognition && micButton) {
  recognition = new SpeechRecognition();
  recognition.lang = "vi-VN";
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.maxAlternatives = 1;

  let interimStart = 0;

  recognition.addEventListener("start", () => {
    isRecording = true;
    micButton.classList.add("recording");
    micButton.title = "Đang nghe... nhấn để dừng";
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
      const messages = {
        "not-allowed": "Vui lòng cấp quyền micro cho trang.",
        "no-speech": "Không nghe thấy giọng nói.",
        "network": "Lỗi mạng khi nhận dạng giọng nói.",
      };
      showToast(messages[event.error] || `Lỗi nhận dạng: ${event.error}`);
    }
  });

  micButton.addEventListener("click", () => {
    if (isRecording) {
      recognition.stop();
      return;
    }

    interimStart = input.value.length;
    try {
      recognition.start();
    } catch {
      // Ignore repeated starts from quick double-clicks.
    }
  });
} else if (micButton) {
  micButton.style.display = "none";
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

document.addEventListener("scroll", closeSessionMenu, true);

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;

  if (deleteModal && !deleteModal.hidden) {
    closeDeleteModal();
    return;
  }

  closeSessionMenu();
});

deleteModal?.addEventListener("click", (event) => {
  if (event.target?.dataset?.dismiss === "true") {
    closeDeleteModal();
  }
});

deleteModalCancel?.addEventListener("click", closeDeleteModal);

deleteModalConfirm?.addEventListener("click", async () => {
  if (!deleteTargetSession) return;

  const session = deleteTargetSession;
  closeDeleteModal();
  closeSessionMenu();

  try {
    await fetch(`/api/sessions/${encodeURIComponent(session.id)}`, {
      method: "DELETE",
    });

    if (session.id === currentSessionId) {
      setCurrentSession(crypto.randomUUID());
      await loadMessages(currentSessionId);
    }

    document.querySelector(`[data-session-id="${session.id}"]`)?.remove();
    await loadSessions();
  } catch {
    showToast("Không thể xóa đoạn chat.");
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
