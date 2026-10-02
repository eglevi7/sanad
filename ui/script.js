const chat = document.getElementById("chat");
const input = document.getElementById("input");
const send = document.getElementById("send");
const status = document.getElementById("status");
const newChat = document.getElementById("new-chat");
const toggleSidebar = document.getElementById("toggle-sidebar");
const sidebar = document.getElementById("sidebar");
const chatList = document.getElementById("chat-list");
const loginBtn = document.getElementById("login-btn");
const loginModal = document.getElementById("login-modal");
const closeModal = document.getElementById("close-modal");
const welcome = document.getElementById("welcome");
const welcomeTagline = document.getElementById("welcome-tagline");
const suggestionsBox = document.getElementById("suggestions");

let isWaiting = false;
let currentAbortController = null;

// ============== إعدادات marked ==============
marked.setOptions({
    breaks: true,
    gfm: true
});

// ============== العبارات ==============
const MAIN_TAGLINE = "سندك في رحلتك";

const SECONDARY_TAGLINES = [
    "معاك أينما كنت",
    "معاك تفهم، مش تحفظ",
    "رفيقك في كل خطوة",
    "خطوة بخطوة نوصل",
    "اسأل، وافهم، واتفوق",
    "التعلم يبدأ بسؤال",
    "معاك في كل درس",
    "بسيط، ذكي، معاك",
    "طريقك للتفوق يبدأ هنا",
    "كل سؤال خطوة للأمام"
];

function getRandomTagline() {
    if (Math.random() < 0.65) {
        return MAIN_TAGLINE;
    } else {
        const idx = Math.floor(Math.random() * SECONDARY_TAGLINES.length);
        return SECONDARY_TAGLINES[idx];
    }
}

function setRandomTagline() {
    welcomeTagline.textContent = getRandomTagline();
}

setRandomTagline();

// ============== Sidebar toggle ==============
toggleSidebar.addEventListener("click", () => {
    sidebar.classList.toggle("hidden");
});

// ============== Login Modal ==============
loginBtn.addEventListener("click", () => {
    loginModal.classList.add("active");
});

closeModal.addEventListener("click", () => {
    loginModal.classList.remove("active");
});

loginModal.addEventListener("click", (e) => {
    if (e.target === loginModal) {
        loginModal.classList.remove("active");
    }
});

document.querySelectorAll(".login-option").forEach(btn => {
    btn.addEventListener("click", () => {
        const method = btn.classList.contains("google") ? "Google" : "Phone";
        alert(`تسجيل الدخول بـ ${method} هيتم إضافته قريباً 🚀`);
    });
});

// ============== شاشة الترحيب ==============
function hideWelcome() {
    welcome.classList.add("hidden");
    chat.classList.remove("hidden");
}

// ============== الأزرار المقترحة ==============
function clearSuggestions() {
    suggestionsBox.innerHTML = "";
}

function showSuggestions(suggestions) {
    clearSuggestions();

    if (!suggestions || suggestions.length === 0) {
        return;
    }

    suggestions.forEach(text => {
        const btn = document.createElement("button");
        btn.className = "suggestion-btn";
        btn.textContent = text;
        btn.onclick = () => {
            clearSuggestions();
            sendSuggestion(text);
        };
        suggestionsBox.appendChild(btn);
    });
}

// ============== إضافة رسالة ==============
function addMessage(text, role) {
    const msg = document.createElement("div");
    msg.className = `message ${role}`;

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    if (role === "ai") {
        bubble.innerHTML = marked.parse(text);

        const copyBtn = document.createElement("button");
        copyBtn.className = "copy-btn";
        copyBtn.textContent = "📋 نسخ";
        copyBtn.onclick = async () => {
            try {
                await navigator.clipboard.writeText(text);
                copyBtn.textContent = "✓ اتمسخ";
                copyBtn.classList.add("copied");
                setTimeout(() => {
                    copyBtn.textContent = "📋 نسخ";
                    copyBtn.classList.remove("copied");
                }, 1500);
            } catch (e) {
                console.error(e);
            }
        };
        bubble.appendChild(copyBtn);
    } else {
        bubble.textContent = text;
    }

    msg.appendChild(bubble);
    chat.appendChild(msg);
    scrollDown();
}

// ============== مؤشر الكتابة ==============
function showTyping() {
    const msg = document.createElement("div");
    msg.className = "message ai";
    msg.id = "typing-msg";

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = `
        <div class="typing">
            <span></span><span></span><span></span>
        </div>
    `;

    msg.appendChild(bubble);
    chat.appendChild(msg);
    scrollDown();
}

function hideTyping() {
    const el = document.getElementById("typing-msg");
    if (el) el.remove();
}

// ============== Scroll ==============
function scrollDown() {
    chat.scrollTop = chat.scrollHeight;
}

function updateSendButton() {
    if (isWaiting) {
        // ⏹ إيقاف
        send.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2"/>
            </svg>
        `;
        send.classList.add("stop-mode");
    } else {
        // ⬆ إرسال
        send.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="19" x2="12" y2="5"></line>
                <polyline points="5 12 12 5 19 12"></polyline>
            </svg>
        `;
        send.classList.remove("stop-mode");
    }
}

// ============== إرسال رسالة للسيرفر ==============
async function sendToServer(text) {
    isWaiting = true;
    send.disabled = false;
    updateSendButton();

    showTyping();
    status.textContent = "بيكتب...";

    // نعمل abort controller للإلغاء
    currentAbortController = new AbortController();

    // نضيف رسالة AI فاضية عشان نكتب فيها
    const aiMsg = document.createElement("div");
    aiMsg.className = "message ai";
    aiMsg.id = "streaming-msg";

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.id = "streaming-bubble";

    aiMsg.appendChild(bubble);
    hideTyping();
    chat.appendChild(aiMsg);
    scrollDown();

    let fullText = "";

    try {
        const response = await fetch("/api/chat/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text }),
            signal: currentAbortController.signal
        });

        if (!response.ok) {
            throw new Error("Network error: " + response.status);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n\n");
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith("data: ")) continue;
                const data = JSON.parse(line.slice(6));

                if (data.error) {
                    throw new Error(data.error);
                }

                if (data.chunk) {
                    fullText += data.chunk;
                    bubble.innerHTML = marked.parse(fullText);
                    scrollDown();
                }

                if (data.done) {
                    // نضيف زرار النسخ
                    const copyBtn = document.createElement("button");
                    copyBtn.className = "copy-btn";
                    copyBtn.textContent = "📋 نسخ";
                    copyBtn.onclick = async () => {
                        try {
                            await navigator.clipboard.writeText(fullText);
                            copyBtn.textContent = "✓ اتمسخ";
                            copyBtn.classList.add("copied");
                            setTimeout(() => {
                                copyBtn.textContent = "📋 نسخ";
                                copyBtn.classList.remove("copied");
                            }, 1500);
                        } catch (e) {
                            console.error(e);
                        }
                    };
                    bubble.appendChild(copyBtn);
                }
            }
        }

    } catch (e) {
        if (e.name === "AbortError") {
            // المستخدم وقف الرد
            bubble.innerHTML += "\n\n<i style='color:var(--text-muted);font-size:13px'>⏹ تم إيقاف الرد</i>";
        } else {
            // خطأ في الشبكة
            if (bubble) {
                bubble.innerHTML = `
                    <div style="color:var(--text-primary);margin-bottom:10px">⚠️ مش قادر أوصل للسيرفر</div>
                    <div style="color:var(--text-muted);font-size:13px;margin-bottom:12px">اتأكد من الإنترنت وحاول تاني</div>
                    <button onclick="retryLastMessage()" style="background:var(--accent);color:var(--accent-text);border:none;padding:8px 20px;border-radius:20px;font-family:inherit;font-size:14px;font-weight:600;cursor:pointer">🔄 إعادة المحاولة</button>
                `;
            }
        }
    }

    // نظّف
    currentAbortController = null;
    isWaiting = false;
    send.disabled = false;
    updateSendButton();
    status.textContent = "جاهز";
    input.focus();

    // احفظ آخر رسالة عشان الـ retry
    window.lastMessage = text;
}

// ============== إرسال الرسالة العادية ==============
async function sendMessage() {
    // لو في انتظار → نوقف
    if (isWaiting) {
        if (currentAbortController) {
            currentAbortController.abort();
        }
        return;
    }

    const text = input.value.trim();
    if (!text) return;

    hideWelcome();
    clearSuggestions();

    addMessage(text, "user");
    input.value = "";
    input.style.height = "auto";

    await sendToServer(text);
}

function retryLastMessage() {
    if (window.lastMessage) {
        // امسح الرسالة الفاشلة
        const lastMsg = chat.lastElementChild;
        if (lastMsg) lastMsg.remove();

        sendToServer(window.lastMessage);
    }
}

// ============== إرسال رسالة من زرار ==============
async function sendSuggestion(text) {
    if (isWaiting) return;

    hideWelcome();

    addMessage(text, "user");

    await sendToServer(text);
}

// ============== محادثة جديدة ==============
async function startNewChat() {
    if (isWaiting) return;

    try {
        await fetch("/api/clear", { method: "POST" });
    } catch (e) {
        console.error("فشل مسح الذاكرة:", e);
    }

    chat.innerHTML = "";
    chat.classList.add("hidden");
    welcome.classList.remove("hidden");
    clearSuggestions();
    setRandomTagline();

    chatList.innerHTML = `
        <div class="chat-item active">
            <span class="chat-icon">💬</span>
            <span class="chat-title">محادثة جديدة</span>
        </div>
    `;

    status.textContent = "جاهز";
    input.focus();
}

// ============== Events ==============
send.addEventListener("click", sendMessage);
newChat.addEventListener("click", startNewChat);

input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 200) + "px";
});

window.addEventListener("load", () => {
    status.textContent = "جاهز";
    input.focus();

    // نخفي الـ sidebar افتراضيًا على الموبايل
    if (window.innerWidth <= 768) {
        sidebar.classList.add("hidden");
    }
});

// ============== PWA Service Worker ==============
if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
        navigator.serviceWorker.register("/ui/service-worker.js")
            .then((reg) => console.log("✅ SW registered:", reg.scope))
            .catch((err) => console.log("❌ SW failed:", err));
    });
}
