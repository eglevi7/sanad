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

// ============== إرسال رسالة للسيرفر ==============
async function sendToServer(text) {
    isWaiting = true;
    send.disabled = true;

    showTyping();
    status.textContent = "بيكتب...";

    try {
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text })
        });

        const data = await response.json();
        hideTyping();

        if (data && data.ok) {
            addMessage(data.text, "ai");
            showSuggestions(data.suggestions);
        } else {
            const err = data && data.error ? data.error : "حصل خطأ";
            addMessage("⚠️ " + err, "ai");
        }
    } catch (e) {
        hideTyping();
        addMessage("⚠️ حصل خطأ في الاتصال: " + e.message, "ai");
    }

    isWaiting = false;
    send.disabled = false;
    status.textContent = "جاهز";
    input.focus();
}

// ============== إرسال الرسالة العادية ==============
async function sendMessage() {
    const text = input.value.trim();
    if (!text || isWaiting) return;

    hideWelcome();
    clearSuggestions();

    addMessage(text, "user");
    input.value = "";
    input.style.height = "auto";

    await sendToServer(text);
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

// ============== لما الصفحة تحمّل ==============
window.addEventListener("load", () => {
    status.textContent = "جاهز";
    input.focus();
});
