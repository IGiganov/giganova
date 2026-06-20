const form = document.getElementById("setup-form");
const errorEl = document.getElementById("setup-error");
const setupBtn = document.getElementById("setup-btn");

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
  setupBtn.disabled = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorEl.hidden = true;
  setupBtn.disabled = true;

  const first_name = document.getElementById("first_name").value.trim();
  const last_name = document.getElementById("last_name").value.trim();
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  const confirm = document.getElementById("confirm").value;

  if (password.length < 8) {
    showError("Password must be at least 8 characters.");
    return;
  }
  if (password !== confirm) {
    showError("Passwords do not match.");
    return;
  }

  try {
    const res = await fetch("/api/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ first_name, last_name, username, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      showError(data.detail || "Setup failed.");
      return;
    }
    window.location.href = "/";
  } catch (err) {
    showError("Network error. Is the server running?");
  }
});
