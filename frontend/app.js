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
const imageUploadButton = document.querySelector("#imageUploadButton");
const imageFileInput = document.querySelector("#imageFileInput");
const imagePreviewBar = document.querySelector("#imagePreviewBar");
const imagePreviewThumb = document.querySelector("#imagePreviewThumb");
const imagePreviewName = document.querySelector("#imagePreviewName");
const imageRemoveButton = document.querySelector("#imageRemoveButton");

let currentSessionId = localStorage.getItem("cookwhat_session_id") || crypto.randomUUID();
let isSending = false;
let openSessionMenu = null;
let editingSessionId = null;
let pendingRenameSessionId = null;
let deleteTargetSession = null;

// Pending image attachment state
let pendingImageFile = null;

// TTS state
let currentAudio = null;
let currentSpeakButton = null;
let currentAudioUrl = null;
let ttsAbortController = null;

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

// TTS helpers
function splitIntoChunks(text, maxLen = 200) {
  const sentences = text.match(/[^.!?\n]+[.!?\n]*/g) || [text];
  const chunks = [];
  let current = "";

  for (const sentence of sentences) {
    if ((current + sentence).length > maxLen && current) {
      chunks.push(current.trim());
      current = sentence;
    } else {
      current += sentence;
    }
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

async function fetchAudioChunk(text, signal) {
  const response = await fetch("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, lang: "vi" }),
    signal,
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${response.status}`);
  }
  const blob = await response.blob();
  return URL.createObjectURL(blob);
}

function prefetchFirstChunk(text) {
  const chunks = splitIntoChunks(stripMarkdown(text));
  if (!chunks.length) return null;
 
  const abortController = new AbortController();
  const audioUrlPromise = fetchAudioChunk(chunks[0], abortController.signal).catch(() => null);
 
  return {
    audioUrlPromise, // Promise<string|null>
    abortController,
    chunks,
    cancel() {
      abortController.abort();
      audioUrlPromise.then((url) => { if (url) URL.revokeObjectURL(url); }).catch(() => {});
    },
  };
}

function playAudioUrl(audioUrl) {
  return new Promise((resolve) => {
    const audio = new Audio(audioUrl);
    currentAudio = audio;
    currentAudioUrl = audioUrl;

    audio.addEventListener("ended", () => {
      URL.revokeObjectURL(audioUrl);
      if (currentAudioUrl === audioUrl) {
        currentAudio = null;
        currentAudioUrl = null;
      }
      resolve();
    });
    audio.addEventListener("error", () => {
      URL.revokeObjectURL(audioUrl);
      if (currentAudioUrl === audioUrl) {
        currentAudio = null;
        currentAudioUrl = null;
      }
      resolve();
    });

    audio.play().catch(() => resolve());
  });
}

function stopSpeaking() {
  if (ttsAbortController) {
    ttsAbortController.abort();
    ttsAbortController = null;
  }

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
    currentSpeakButton.title = "Đọc câu trả lời";
    currentSpeakButton.disabled = false;
    currentSpeakButton = null;
  }
}

// TTS pipeline streaming
// Fetch chunk N+1 while playing chunk N
async function startStreamingTTS(text, speakButton, prefetch = null) {
  const PREFETCH = 2;
  
  stopSpeaking();
 
  speakButton.classList.add("is-active", "is-speaking");
  speakButton.innerHTML = actionIcon("pause");
  speakButton.setAttribute("aria-label", "Dừng đọc câu trả lời");
  speakButton.title = "Dừng đọc";
  currentSpeakButton = speakButton;

  const chunks = prefetch?.chunks ?? splitIntoChunks(stripMarkdown(text));
  const abortController = new AbortController();
  ttsAbortController = abortController;
  const { signal } = abortController;

  const fetchSlots = new Array(chunks.length).fill(null);
  let nextFetchIndex = 0;

  function scheduleFetch(index) {
    if (index >= chunks.length) return;
    if (fetchSlots[index] !== null) return;
    fetchSlots[index] = fetchAudioChunk(chunks[index], signal).catch(() => null);
  }

  if (prefetch?.audioUrlPromise && !prefetch.abortController.signal.aborted) {
    fetchSlots[0] = prefetch.audioUrlPromise;
    nextFetchIndex = 1;
  }

  for (let i = nextFetchIndex; i < Math.min(PREFETCH, chunks.length); i++) {
    scheduleFetch(i);
    nextFetchIndex = i + 1;
  }
 
  let fetchError = null;
 
  for (let playIndex = 0; playIndex < chunks.length; playIndex++) {
    if (signal.aborted) break;
 
    // Trigger fetch next chunk
    if (nextFetchIndex < chunks.length) {
      scheduleFetch(nextFetchIndex);
      nextFetchIndex++;
    }

    let audioUrl = null;
    try {
      audioUrl = await fetchSlots[playIndex];
    } catch (err) {
      if (!signal.aborted) fetchError = err;
      break;
    }
 
    if (signal.aborted) {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      break;
    }
 
    if (!audioUrl) continue; 
 
    await playAudioUrl(audioUrl);
 
    if (signal.aborted) break;
  }

  if (signal.aborted) {
    for (let i = 0; i < fetchSlots.length; i++) {
      if (fetchSlots[i]) {
        fetchSlots[i].then((url) => { if (url) URL.revokeObjectURL(url); }).catch(() => {});
      }
    }
  }
 
  if (currentSpeakButton === speakButton && !signal.aborted) {
    speakButton.classList.remove("is-active", "is-speaking");
    speakButton.innerHTML = actionIcon("speak");
    speakButton.setAttribute("aria-label", "Đọc câu trả lời");
    speakButton.title = "Đọc câu trả lời";
    speakButton.disabled = false;
    currentSpeakButton = null;
    ttsAbortController = null;
 
    if (fetchError) {
      showToast(`Lỗi TTS: ${fetchError.message}`);
    }
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
    /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  output = output.replace(
    /(^|[^"'>])(https?:\/\/[^\s<]+)/g,
    '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>'
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

function isMarkdownTableRow(line) {
  const trimmed = line.trim();
  return trimmed.startsWith("|") && trimmed.endsWith("|") && trimmed.includes("|", 1);
}

function isMarkdownTableSeparator(line) {
  if (!isMarkdownTableRow(line)) return false;
  return line
    .trim()
    .slice(1, -1)
    .split("|")
    .every((cell) => /^:?-{3,}:?$/.test(cell.trim()));
}

function parseMarkdownTableRow(line) {
  return line
    .trim()
    .slice(1, -1)
    .split("|")
    .map((cell) => cell.trim());
}

function renderTable(rows) {
  if (rows.length < 2) return "";

  const headers = parseMarkdownTableRow(rows[0]);
  const bodyRows = rows.slice(2).map(parseMarkdownTableRow);
  const head = headers.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("");
  const body = bodyRows
    .map((row) => `<tr>${row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join("")}</tr>`)
    .join("");

  return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function renderMarkdown(content) {
  const lines = String(content || "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  let listItems = [];
  let orderedList = false;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(`<p>${paragraph.map(renderInlineMarkdown).join("<br>")}</p>`);
    paragraph = [];
  };

  const flushCurrentList = () => {
    if (!listItems.length) return;
    blocks.push(flushList(listItems, orderedList));
    listItems = [];
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      flushParagraph();
      flushCurrentList();
      continue;
    }

    if (/^---+$/.test(trimmed)) {
      flushParagraph();
      flushCurrentList();
      blocks.push("<hr>");
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushCurrentList();
      const level = Math.min(headingMatch[1].length + 2, 6);
      blocks.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
      continue;
    }

    if (
      isMarkdownTableRow(trimmed) &&
      index + 1 < lines.length &&
      isMarkdownTableSeparator(lines[index + 1])
    ) {
      flushParagraph();
      flushCurrentList();

      const tableRows = [trimmed, lines[index + 1].trim()];
      index += 2;
      while (index < lines.length && isMarkdownTableRow(lines[index])) {
        tableRows.push(lines[index].trim());
        index += 1;
      }
      index -= 1;
      blocks.push(renderTable(tableRows));
      continue;
    }

    const orderedMatch = trimmed.match(/^\d+\.\s+(.+)$/);
    if (orderedMatch) {
      flushParagraph();
      if (listItems.length && !orderedList) flushCurrentList();
      orderedList = true;
      listItems.push(orderedMatch[1]);
      continue;
    }

    const bulletMatch = trimmed.match(/^[-*]\s+(.+)$/);
    if (bulletMatch) {
      flushParagraph();
      if (listItems.length && orderedList) flushCurrentList();
      orderedList = false;
      listItems.push(bulletMatch[1]);
      continue;
    }

    flushCurrentList();
    paragraph.push(trimmed);
  }

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

function createAnswerActions(content, prefetch = null) {
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

  let pendingPrefetch = prefetch;

  speakButton.addEventListener("click", (event) => {
    event.stopPropagation();

    if (currentSpeakButton === speakButton) {
      stopSpeaking();
      pendingPrefetch = null;
      return;
    }

    const usedPrefetch = pendingPrefetch;
    pendingPrefetch = null;

    startStreamingTTS(content, speakButton, usedPrefetch);
  });

  actions.append(copyButton, speakButton);
  return actions;
}

/**
 * Parse a stored user message that may contain the VLM-combined format:
 *   "[Mô tả ảnh]: <description>\n\n[Câu hỏi của bạn]: <text>"
 * Returns { hasImageContext, displayText }.
 */
function parseUserMessage(content) {
  // Format: combined image description + question
  const combined = content.match(
    /^\[Mô tả ảnh\]:[\s\S]*?\n\n\[Câu hỏi của bạn\]:\s*([\s\S]*)$/
  );
  if (combined) return { hasImageContext: true, displayText: combined[1].trim() };
  // Format: image description only (no typed question)
  if (content.startsWith("[Mô tả ảnh]:"))
    return { hasImageContext: true, displayText: "" };
  return { hasImageContext: false, displayText: content };
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

  if (safeRole === "assistant") {
    if (options.loading) {
      bubble.innerHTML = `
        <div class="loading-bubble-inner">
          <div class="typing-indicator" aria-label="Đang xử lý">
            <span></span><span></span><span></span>
          </div>
          <span class="loading-label"></span>
        </div>`;
    } else {
      bubble.innerHTML = renderMarkdown(safeContent);
    }
  } else {
    // ── User bubble ──────────────────────────────────────────────────────────
    // 1. If we have a live image data URL (just uploaded), show thumbnail
    if (options.imageDataUrl) {
      const imgWrap = document.createElement("div");
      imgWrap.className = "user-bubble-image";
      const img = document.createElement("img");
      img.src = options.imageDataUrl;
      img.alt = "Ảnh đính kèm";
      imgWrap.appendChild(img);
      bubble.appendChild(imgWrap);
    } else {
      // 2. Loaded from history: detect [Mô tả ảnh]: prefix and clean it up
      const parsed = parseUserMessage(safeContent);
      if (parsed.hasImageContext) {
        const badge = document.createElement("div");
        badge.className = "user-image-badge";
        badge.textContent = "📷 Hình ảnh";
        bubble.appendChild(badge);
        if (parsed.displayText) {
          const textNode = document.createElement("span");
          textNode.textContent = parsed.displayText;
          bubble.appendChild(textNode);
        }
        row.appendChild(bubble);
        messagesEl.appendChild(row);
        scrollToBottom();
        return;
      }
    }

    // Plain text (no image context)
    const textNode = document.createTextNode(safeContent);
    bubble.appendChild(textNode);
  }

  if (safeRole === "assistant" && !options.loading) {
    const prefetch = prefetchFirstChunk(safeContent);
    bubble.appendChild(createAnswerActions(safeContent, prefetch));
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
  if (imageUploadButton) imageUploadButton.disabled = enabled;
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
  // Capture the image data URL BEFORE clearing the pending state
  const imageDataUrl =
    pendingImageFile && imagePreviewThumb && imagePreviewThumb.src
      ? imagePreviewThumb.src
      : null;

  // Show the user bubble with image thumbnail + text immediately
  addMessage("user", content, { imageDataUrl });
  addMessage("assistant", "Đang suy nghĩ...", { id: "loadingMessage", loading: true });
  setLoading(true);

  // Capture and clear pending image before any async work
  const imageFile = pendingImageFile;
  clearPendingImage();

  let finalMessage = content;

  // ── VLM preprocessing layer ──────────────────────────────────────────────
  if (imageFile) {
    try {
      const loadingEl = document.querySelector("#loadingMessage .loading-label");
      if (loadingEl) loadingEl.textContent = "Đang phân tích hình ảnh...";

      const formData = new FormData();
      formData.append("image", imageFile);
      formData.append("query", content);

      const vlmResponse = await fetch("/api/analyze-image", {
        method: "POST",
        body: formData,
      });

      const vlmData = await vlmResponse.json().catch(() => ({}));

      if (!vlmResponse.ok) {
        const loading = document.querySelector("#loadingMessage");
        if (loading) loading.remove();
        addMessage("assistant", vlmData.error || `Lỗi phân tích ảnh (HTTP ${vlmResponse.status}).`);
        setLoading(false);
        input.focus();
        return;
      }

      const description = (vlmData.description || "").trim();
      if (description) {
        finalMessage = content
          ? `[Mô tả ảnh]: ${description}\n\n[Câu hỏi của bạn]: ${content}`
          : `[Mô tả ảnh]: ${description}`;
      }

      if (loadingEl) loadingEl.textContent = "";
    } catch (err) {
      const loading = document.querySelector("#loadingMessage");
      if (loading) loading.remove();
      addMessage("assistant", `Không kết nối được dịch vụ phân tích ảnh: ${err.message}`);
      setLoading(false);
      input.focus();
      return;
    }
  }
  // ── end VLM layer ─────────────────────────────────────────────────────────

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: finalMessage,
        session_id: currentSessionId,
        top_k: 5,
      }),
    });

    const data = await response.json().catch(() => ({}));
    const loading = document.querySelector("#loadingMessage");
    if (loading) loading.remove();

    if (!response.ok) {
      addMessage("assistant", data.detail || data.error || `Backend trả về lỗi HTTP ${response.status}.`);
      return;
    }

    setCurrentSession(data.session_id || currentSessionId);
    addMessage("assistant", data.response || "Mình chưa có phản hồi phù hợp.");
    await loadSessions();
  } catch {
    const loading = document.querySelector("#loadingMessage");
    if (loading) loading.remove();
    addMessage(
      "assistant",
      "Không kết nối được backend. Kiểm tra server FastAPI và PostgreSQL nếu bạn đang bật lưu lịch sử."
    );
  } finally {
    setLoading(false);
    input.focus();
  }
}

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let isRecording = false;

// ── Image attachment helpers ─────────────────────────────────────────────────

function clearPendingImage() {
  pendingImageFile = null;
  if (imagePreviewBar) imagePreviewBar.hidden = true;
  if (imagePreviewThumb) imagePreviewThumb.src = "";
  if (imagePreviewName) imagePreviewName.textContent = "";
  if (imageFileInput) imageFileInput.value = "";
  if (imageUploadButton) imageUploadButton.classList.remove("has-image");
}

function attachPendingImage(file) {
  if (!file) return;
  pendingImageFile = file;

  // Show thumbnail preview
  const reader = new FileReader();
  reader.onload = (e) => {
    if (imagePreviewThumb) imagePreviewThumb.src = e.target.result;
  };
  reader.readAsDataURL(file);

  if (imagePreviewName) {
    const shortName = file.name.length > 28 ? file.name.slice(0, 25) + "…" : file.name;
    imagePreviewName.textContent = shortName;
  }
  if (imagePreviewBar) imagePreviewBar.hidden = false;
  if (imageUploadButton) imageUploadButton.classList.add("has-image");
}

if (imageUploadButton && imageFileInput) {
  imageUploadButton.addEventListener("click", () => {
    if (!isSending) imageFileInput.click();
  });

  imageFileInput.addEventListener("change", () => {
    const file = imageFileInput.files?.[0];
    if (file) attachPendingImage(file);
  });
}

if (imageRemoveButton) {
  imageRemoveButton.addEventListener("click", () => {
    clearPendingImage();
    input.focus();
  });
}

// ── Drag-and-drop onto the composer ──────────────────────────────────────────
// Use a counter to avoid flickering when pointer moves over child elements.
let dragEnterCount = 0;

form.addEventListener("dragenter", (e) => {
  if (!e.dataTransfer?.types?.includes("Files")) return;
  e.preventDefault();
  dragEnterCount++;
  form.classList.add("drag-over");
});

form.addEventListener("dragover", (e) => {
  if (!e.dataTransfer?.types?.includes("Files")) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = "copy";
});

form.addEventListener("dragleave", () => {
  dragEnterCount--;
  if (dragEnterCount <= 0) {
    dragEnterCount = 0;
    form.classList.remove("drag-over");
  }
});

form.addEventListener("drop", (e) => {
  e.preventDefault();
  dragEnterCount = 0;
  form.classList.remove("drag-over");
  if (isSending) return;

  const file = Array.from(e.dataTransfer?.files || []).find((f) =>
    f.type.startsWith("image/")
  );
  if (file) {
    attachPendingImage(file);
    input.focus();
  }
});

// ── Paste image from clipboard ────────────────────────────────────────────────
document.addEventListener("paste", (e) => {
  if (isSending) return;

  const items = Array.from(e.clipboardData?.items || []);
  const imageItem = items.find((item) => item.type.startsWith("image/"));
  if (!imageItem) return;

  // Only intercept if the paste isn't inside a text field that has text selected
  // (allow normal text paste to work unaffected)
  const activeEl = document.activeElement;
  const isTextInput =
    activeEl &&
    (activeEl.tagName === "INPUT" || activeEl.tagName === "TEXTAREA") &&
    activeEl !== input;
  if (isTextInput) return;

  e.preventDefault();
  const file = imageItem.getAsFile();
  if (file) {
    attachPendingImage(file);
    showToast("Đã dán ảnh từ clipboard 📋", 2000);
    input.focus();
  }
});

// ── end image attachment helpers ─────────────────────────────────────────────


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
        network: "Lỗi mạng khi nhận dạng giọng nói.",
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

  // Require either text content or a pending image (or both)
  if (!content && !pendingImageFile) return;

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

// ── Dark mode ───────────────────────────────────────────────────────────
const themeToggleButton = document.querySelector("#themeToggleButton");
const themeIcon = document.querySelector("#themeIcon");

const SUN_PATH = `<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>`;
const MOON_PATH = `<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>`;

function applyTheme(dark) {
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  if (themeIcon) themeIcon.innerHTML = dark ? SUN_PATH : MOON_PATH;
  if (themeToggleButton) {
    themeToggleButton.title = dark ? "Chuyển sang Light mode" : "Chuyển sang Dark mode";
    themeToggleButton.setAttribute("aria-label", themeToggleButton.title);
  }
  localStorage.setItem("cookwhat_theme", dark ? "dark" : "light");
}

// Init from saved preference or system preference
(function initTheme() {
  const saved = localStorage.getItem("cookwhat_theme");
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(saved ? saved === "dark" : prefersDark);
})();

themeToggleButton?.addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme !== "dark");
});

// ── Sidebar collapse ─────────────────────────────────────────────────
const sidebarCollapseButton = document.querySelector("#sidebarCollapseButton");
const appShell = document.querySelector(".app-shell");

function setSidebarCollapsed(collapsed) {
  appShell?.classList.toggle("sidebar-collapsed", collapsed);
  if (sidebarCollapseButton) {
    sidebarCollapseButton.title = collapsed ? "Mở rộng sidebar" : "Thu gọn sidebar";
    sidebarCollapseButton.setAttribute("aria-label", sidebarCollapseButton.title);
  }
  localStorage.setItem("cookwhat_sidebar_collapsed", collapsed ? "1" : "0");
}

// Init collapsed state from localStorage
(function initSidebar() {
  const saved = localStorage.getItem("cookwhat_sidebar_collapsed");
  if (saved === "1") setSidebarCollapsed(true);
})();

sidebarCollapseButton?.addEventListener("click", () => {
  const isCollapsed = appShell?.classList.contains("sidebar-collapsed");
  setSidebarCollapsed(!isCollapsed);
});