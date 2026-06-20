const chat = document.getElementById("chat");
const form = document.getElementById("form");
const input = document.getElementById("input");
const send = document.getElementById("send");
const usageEl = document.getElementById("usage");

const DISCLAIMER = /informational only, not investment advice\.?/gi;

const SECTION_HEADERS = {
  summary: "executive summary",
  factors: "key factors",
  watch: "what to watch",
};

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function stripDisclaimer(text) {
  return text
    .replace(DISCLAIMER, "")
    .replace(/^---\s*$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function parseSectionHeader(line) {
  const normalized = line.replace(/^##\s*/, "").trim().toLowerCase();
  if (normalized === SECTION_HEADERS.summary) return "summary";
  if (normalized === SECTION_HEADERS.factors) return "factors";
  if (normalized === SECTION_HEADERS.watch) return "watch";
  return null;
}

const PUBLISHER =
  /^(?:Yahoo Finance|Barron's|Reuters|IBD|Fortune|WSJ|The Wall Street Journal|Motley Fool|Investor's Business Daily|Wall Street Journal)(?:,\s*(?:Yahoo Finance|Barron's|Reuters|IBD|Fortune|WSJ|The Wall Street Journal|Motley Fool|Investor's Business Daily|Wall Street Journal))*\.?$/i;

const UP_WORDS =
  /\b(up|gained?|gains|rose|risen|jumped?|climbed?|higher|surged?|rallied|advanced|added|soared|popped)(\s+)<span class="num">/gi;
const DOWN_WORDS =
  /\b(down|fell|fall|dropped?|lower|declined?|slid|slipped?|sank|lost|losses|loss|tumbled?|plunged?|sank|shed|slumped?)(\s+)<span class="num">/gi;

function colorNumbers(html) {
  html = html.replace(/(\$\d[\d,]*(?:\.\d+)?)/g, '<span class="num">$1</span>');
  html = html.replace(/\b(\d{1,3}(?:,\d{3})+(?:\.\d+)?)\b/g, '<span class="num">$1</span>');
  html = html.replace(/([+-]?\d[\d,]*(?:\.\d+)?\s*%)/g, (match) => {
    const trimmed = match.trim();
    const cls = trimmed.startsWith("+")
      ? "num up"
      : trimmed.startsWith("-")
      ? "num down"
      : "num";
    return `<span class="${cls}">${match}</span>`;
  });
  html = html.replace(UP_WORDS, '$1$2<span class="num up">');
  html = html.replace(DOWN_WORDS, '$1$2<span class="num down">');
  return html;
}

function formatInline(text) {
  let html = escapeHtml(text);
  html = html.replace(/^([A-Z][^.]{2,60}\.)\s/, "<strong>$1</strong> ");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*\(([^)]+)\)\*/g, (match, group) =>
    PUBLISHER.test(group.trim()) ? ` <span class="sources">${group.trim()}</span>` : match
  );
  html = html.replace(/\s—\s([A-Za-z0-9 .,'&]+)$/, (match, group) =>
    PUBLISHER.test(group.trim()) ? ` <span class="sources">${group.trim()}</span>` : match
  );
  html = html.replace(
    /\s((?:Yahoo Finance|Barron's|Reuters|IBD|Fortune|WSJ|The Wall Street Journal|Motley Fool|Investor's Business Daily|Wall Street Journal)(?:,\s*(?:Yahoo Finance|Barron's|Reuters|IBD|Fortune|WSJ|The Wall Street Journal|Motley Fool|Investor's Business Daily|Wall Street Journal))*)\.?\s*$/,
    ' <span class="sources">$1</span>'
  );
  html = colorNumbers(html);
  return html;
}

function closeWatchList(state) {
  if (state.watchOpen) {
    state.html += "</div>";
    state.watchOpen = false;
    state.watchIndex = 0;
  }
}

function closeBulletList(state) {
  if (state.listType) {
    state.html += state.listType === "ol" ? "</ol>" : "</ul>";
    state.listType = null;
  }
}

function closeList(state) {
  closeWatchList(state);
  closeBulletList(state);
}

function openList(state, type) {
  if (state.listType !== type) {
    closeBulletList(state);
    closeWatchList(state);
    state.html += type === "ol" ? '<ol class="note-list">' : '<ul class="note-list">';
    state.listType = type;
  }
}

function addListItem(state, type, text) {
  openList(state, type);
  state.html += `<li>${formatInline(text)}</li>`;
}

function addWatchItem(state, text) {
  closeBulletList(state);
  const body = text.replace(/^\d+\.\s+/, "").trim();
  if (!body) {
    return;
  }
  if (!state.watchOpen) {
    state.html += '<div class="watch-list">';
    state.watchOpen = true;
    state.watchIndex = 0;
  }
  state.watchIndex += 1;
  state.html += `<div class="watch-item"><span class="watch-num">${state.watchIndex}.</span><div class="watch-body">${formatInline(body)}</div></div>`;
}

function formatAssistant(text) {
  const cleaned = stripDisclaimer(text);
  const state = {
    html: "",
    listType: null,
    section: null,
    watchOpen: false,
    watchIndex: 0,
    pendingWatchLine: false,
  };

  for (const rawLine of cleaned.split("\n")) {
    const line = rawLine.trim();
    if (!line) {
      if (state.section !== "factors" && state.section !== "watch") {
        closeList(state);
      }
      continue;
    }

    const section = parseSectionHeader(line);
    if (section) {
      closeList(state);
      state.pendingWatchLine = false;
      state.section = section;
      const title = line.replace(/^##\s*/, "");
      state.html += `<h3 class="section-title">${escapeHtml(title)}</h3>`;
      continue;
    }

    if (state.section === "factors") {
      const bulletText = line.startsWith("- ") ? line.slice(2) : line;
      addListItem(state, "ul", bulletText);
      continue;
    }

    if (state.section === "watch") {
      if (/^\d+\.\s*$/.test(line)) {
        state.pendingWatchLine = true;
        continue;
      }
      if (state.pendingWatchLine) {
        state.pendingWatchLine = false;
        addWatchItem(state, line);
        continue;
      }
      addWatchItem(state, line);
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      addListItem(state, "ol", line.replace(/^\d+\.\s+/, ""));
      continue;
    }

    if (line.startsWith("- ")) {
      addListItem(state, "ul", line.slice(2));
      continue;
    }

    closeList(state);
    state.html += `<p class="note-paragraph">${formatInline(line)}</p>`;
  }

  closeList(state);
  return `<div class="analyst-note">${state.html}</div>`;
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
  usageEl.textContent = `$${data.spent_usd.toFixed(2)} / $${data.monthly_budget_usd.toFixed(2)} · ${data.model}`;
}

const tickerEl = document.getElementById("ticker");

function fmtPrice(value) {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function fmtChange(pct) {
  if (pct === null || pct === undefined) return { text: "—", cls: "flat" };
  const cls = pct > 0 ? "up" : pct < 0 ? "down" : "flat";
  const sign = pct > 0 ? "+" : "";
  const arrow = pct > 0 ? "▲" : pct < 0 ? "▼" : "•";
  return { text: `${arrow} ${sign}${pct.toFixed(2)}%`, cls };
}

function renderTickerSkeleton() {
  const cells = ["S&P 500", "NASDAQ", "DOW", "RUSSELL"]
    .map(
      (label) =>
        `<div class="ticker-cell loading"><span class="t-label">${label}</span><span class="t-price">····</span><span class="t-change flat">—</span></div>`
    )
    .join("");
  tickerEl.innerHTML = cells;
}

async function refreshTicker() {
  try {
    const res = await fetch("/api/markets");
    const data = await res.json();
    tickerEl.innerHTML = data.indices
      .map((idx) => {
        const change = fmtChange(idx.change_pct);
        return `<div class="ticker-cell"><span class="t-label">${idx.label}</span><span class="t-price">${fmtPrice(
          idx.price
        )}</span><span class="t-change ${change.cls}">${change.text}</span></div>`;
      })
      .join("");
  } catch (err) {
    /* keep skeleton on failure */
  }
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
  "Ask me about stocks — quotes, recent moves, or headlines. Example: \"Summarize AAPL price action and news this month.\"",
  "assistant"
);
refreshUsage();
renderTickerSkeleton();
refreshTicker();
setInterval(refreshTicker, 60000);
