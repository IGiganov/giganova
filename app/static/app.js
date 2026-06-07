const chat = document.getElementById("chat");
const form = document.getElementById("form");
const input = document.getElementById("input");
const send = document.getElementById("send");
const usageEl = document.getElementById("usage");

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function formatAssistant(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function addMessage(text, role) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  if (role === "assistant") {
    div.innerHTML = formatAssistant(text);
  } else {
    div.textContent = text;
  }
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

async function refreshUsage() {
  const res = await fetch("/api/usage");
  const data = await res.json();
  usageEl.textContent = `$${data.spent_usd.toFixed(2)} / $${data.monthly_budget_usd.toFixed(2)} this month · ${data.model}`;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;

  addMessage(message, "user");
  input.value = "";
  send.disabled = true;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    if (!res.ok) {
      addMessage(data.detail || "Request failed.", "error");
    } else {
      addMessage(data.answer, "assistant");
    }
  } catch (err) {
    addMessage("Network error. Is the server running?", "error");
  } finally {
    send.disabled = false;
    refreshUsage();
  }
});

addMessage(
  "Ask me about US stocks — quotes, recent moves, or headlines. Example: \"Summarize AAPL price action and news this month.\"",
  "assistant"
);
refreshUsage();
