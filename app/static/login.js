const form = document.getElementById("login-form");
const errorEl = document.getElementById("login-error");
const loginBtn = document.getElementById("login-btn");

async function redirectIfAuthed() {
  try {
    const res = await fetch("/api/me");
    if (res.ok) {
      window.location.href = "/";
    }
  } catch (err) {
    /* stay on login page */
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorEl.hidden = true;
  loginBtn.disabled = true;

  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;

  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      errorEl.textContent = data.detail || "Sign in failed.";
      errorEl.hidden = false;
      loginBtn.disabled = false;
      return;
    }
    window.location.href = "/";
  } catch (err) {
    errorEl.textContent = "Network error. Is the server running?";
    errorEl.hidden = false;
    loginBtn.disabled = false;
  }
});

redirectIfAuthed();
