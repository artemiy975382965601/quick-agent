const $ = (id) => document.getElementById(id);
const state = { sid: null, title: "", model: "", polling: false, seq: 0, mode: "md", access: null, follow: true };

/* Шаблон оформления для HTML-режима: модель пишет только разметку с этими классами. */
/* оформление html-ответов: /static/template.css (тот же файл уходит в промпт) */

/* access-токен живёт только в памяти вкладки; refresh — в HttpOnly cookie */
async function refreshAccess() {
  try {
    const r = await fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" });
    if (!r.ok) return false;
    const d = await r.json();
    state.access = d.access;
    return true;
  } catch {
    return false;
  }
}

async function api(path, opts = {}, allowRetry = true) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (state.access) headers.Authorization = "Bearer " + state.access;
  const r = await fetch(path, { credentials: "same-origin", ...opts, headers });
  if (r.status === 401 && allowRetry) {
    if (await refreshAccess()) return api(path, opts, false);
    state.access = null;
    showLogin();
    throw new Error("auth");
  }
  if (!r.ok) throw new Error((await r.text()).slice(0, 300));
  return r.json();
}

/* ---------------- экраны ---------------- */
function show(screen) {
  for (const s of ["login", "chats", "chat", "settings"]) $(s).classList.add("hidden");
  $(screen).classList.remove("hidden");
  const tabsVisible = screen === "chats" || screen === "settings";
  $("tabs").classList.toggle("hidden", !tabsVisible);
  document.querySelectorAll(".screen").forEach((el) => el.classList.toggle("tabs-on", tabsVisible && el.id === screen));
  for (const t of document.querySelectorAll(".tab")) {
    t.classList.toggle("active", t.dataset.tab === (screen === "chat" ? "chats" : screen));
  }
}
const showLogin = () => show("login");

/* ---------------- вход ---------------- */
$("login-btn").onclick = async () => {
  $("login-err").textContent = "";
  const body = { password: $("pass").value };
  if (!$("totp-code").classList.contains("hidden")) body.totp = $("totp-code").value.trim();
  const r = await fetch("/api/login", {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) {
    if (d.detail === "totp_required") {
      $("totp-code").classList.remove("hidden");
      $("totp-code").focus();
      $("login-err").textContent = "код из приложения";
      return;
    }
    $("login-err").textContent = d.detail || "wrong password";
    return;
  }
  state.access = d.access;
  $("pass").value = "";
  $("totp-code").value = "";
  await boot();
};
$("pass").addEventListener("keydown", (e) => { if (e.key === "Enter") $("login-btn").click(); });
$("logout").onclick = async () => {
  try { await api("/api/logout", { method: "POST" }, false); } catch {}
  state.access = null;
  showLogin();
};

/* ---------------- список чатов ---------------- */
async function loadChats() {
  const rows = await api("/api/sessions");
  const list = $("chat-list");
  list.innerHTML = "";
  if (!rows.length) {
    list.innerHTML = '<div class="empty">No chats yet.<br>Tap + to start.</div>';
    return;
  }
  for (const s of rows.reverse()) {
    const el = document.createElement("div");
    el.className = "chat-item";
    el.innerHTML = `<div class="t"></div><button class="dots" aria-label="Actions">
      <svg viewBox="0 0 24 24"><circle cx="12" cy="5" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="12" cy="19" r="1.6"/></svg>
    </button>`;
    el.querySelector(".t").textContent = s.title || "untitled";
    el.onclick = () => openChat(s);
    el.querySelector(".dots").onclick = (ev) => {
      ev.stopPropagation();
      openSheet(s);
    };
    list.appendChild(el);
  }
}

$("new-chat").onclick = () => {
  openModal({
    title: "New chat",
    value: "",
    text: "Title can be empty",
    onOk: async (name) => {
      const s = await api("/api/sessions", {
        method: "POST",
        body: JSON.stringify(name.trim() ? { title: name.trim() } : {}),
      });
      await loadChats();
      openChat(s);
    },
  });
};

/* ---------------- чат ---------------- */
async function openChat(session) {
  state.sid = session.id;
  state.title = session.title || "untitled";
  state.model = session.model_alias || "";
  $("chat-title").textContent = state.title;
  $("messages").innerHTML = "";
  state.mode = localStorage.getItem("mode:" + session.id) || "md";
  paintMode();
  show("chat");
  const h = await api(`/api/chat/${session.id}?limit=30`);
  const stored = localStorage.getItem("mode:" + session.id);
  if (stored) {
    state.mode = stored;
  } else if (h.messages.some((m) => m.kind === "assistant" && looksHtml(m.text))) {
    state.mode = "html";
    localStorage.setItem("mode:" + session.id, "html");
  }
  paintMode();
  for (const m of h.messages) renderMessage(m);
  state.follow = true;
  state.nearBottom = true;
  /* при открытии чата один раз встаём в конец; дальше никакой автопрокрутки */
  const box = $("messages");
  box.scrollTop = box.scrollHeight;
  settleScroll();
  updateToBottom();
}

function scrollDown() {
  /* тянем вниз только если пользователь у самого низа; иначе не трогаем */
  if (state.follow === false) return;
  const box = $("messages");
  box.scrollTop = box.scrollHeight;
}

function nearBottom() {
  const box = $("messages");
  return box.scrollHeight - box.scrollTop - box.clientHeight < 24;
}

/* любая прокрутка вверх сразу отключает автодоводку */
$("messages").addEventListener("scroll", () => {
  state.follow = nearBottom();
  updateToBottom();
}, { passive: true });

function updateToBottom() {
  const btn = $("to-bottom");
  if (!btn) return;
  btn.classList.toggle("hidden", nearBottom() || !state.sid);
}

function settleScroll() {
  /* ничего не прокручиваем сами — только обновляем кнопку «вниз» */
  [0, 120, 350, 800, 1500].forEach((t) => setTimeout(() => {
    updateToBottom();
  }, t));
}

function md(text) {
  const raw = marked.parse(text || "", { breaks: true, gfm: true });
  return DOMPurify.sanitize(raw, { FORBID_TAGS: ["img", "iframe", "style"] });
}

function stripDocument(html) {
  return (html || "")
    .replace(/<!doctype[^>]*>/gi, "")
    .replace(/<\/?(html|head|body)[^>]*>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "");
}

function looksHtml(text) {
  const t = (text || "").trim();
  if (!t.startsWith("<")) return false;
  const m = t.match(/^<([a-z][a-z0-9]*)\b/i);
  if (!m) return false;
  const block = ["div", "section", "article", "header", "main", "h1", "h2", "h3",
                 "p", "table", "ul", "ol", "figure", "aside"];
  return block.includes(m[1].toLowerCase());
}

let mermaidReady = false;
function initMermaid() {
  if (mermaidReady || typeof mermaid === "undefined") return;
  mermaid.initialize({
    startOnLoad: false,
    theme: "base",
    securityLevel: "loose",
    fontFamily: '"JetBrains Mono", ui-monospace, monospace',
    themeVariables: {
      background: "transparent",
      primaryColor: "transparent",
      primaryTextColor: "#e6e2ef",
      primaryBorderColor: "#b06bff",
      secondaryColor: "transparent",
      secondaryTextColor: "#e6e2ef",
      secondaryBorderColor: "#35d6a5",
      tertiaryColor: "transparent",
      tertiaryTextColor: "#e6e2ef",
      tertiaryBorderColor: "#f2c14e",
      lineColor: "#8b83a0",
      textColor: "#e6e2ef",
      mainBkg: "transparent",
      nodeBorder: "#b06bff",
      clusterBkg: "transparent",
      clusterBorder: "#35d6a5",
      edgeLabelBackground: "#0a0c11",
      fontSize: "15px",
      actorBkg: "#0b0d12",
      actorBorder: "#b06bff",
      actorTextColor: "#e6e2ef",
      signalColor: "#8b83a0",
      signalTextColor: "#cfc8de",
      labelBoxBkgColor: "#0a0c11",
      labelBoxBorderColor: "#35d6a5",
      labelTextColor: "#e6e2ef",
      loopTextColor: "#e6e2ef",
      noteBkgColor: "rgba(242,193,78,.10)",
      noteBorderColor: "#f2c14e",
      noteTextColor: "#f0e8d5"
    },
    flowchart: { curve: "basis", nodeSpacing: 44, rankSpacing: 58, padding: 14, useMaxWidth: true },
    sequence: { actorMargin: 64, boxMargin: 12, messageMargin: 44, useMaxWidth: true }
  });
  mermaidReady = true;
}

const diagramCache = new Map();

function asset(name) {
  const meta = document.querySelector('meta[name="assets"]');
  const [tpl, hljs] = ((meta && meta.content) || "0|0").split("|");
  return name === "template.css" ? tpl : hljs;
}

const MERMAID_SRC = "/static/vendor/mermaid.min.js";
let mermaidLoading = null;

function loadMermaid() {
  if (typeof mermaid !== "undefined") return Promise.resolve(true);
  if (mermaidLoading) return mermaidLoading;
  mermaidLoading = new Promise((resolve) => {
    const s = document.createElement("script");
    s.src = MERMAID_SRC;
    s.onload = () => resolve(typeof mermaid !== "undefined");
    s.onerror = () => resolve(false);
    document.head.appendChild(s);
  });
  return mermaidLoading;
}

async function renderDiagrams(root) {
  if (!root || !root.querySelector("pre, code, .mermaid")) return;
  if (!(await loadMermaid())) return;
  initMermaid();
  /* модель может прислать «pre class=mermaid», «pre>code.language-mermaid» или просто pre с flowchart */
  const HEAD = /^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram|stateDiagram-v2|erDiagram|journey|gantt|pie|mindmap|timeline|gitGraph)\b/;
  const seen = new Set();
  const blocks = [];
  root.querySelectorAll("pre, code, div.mermaid, span.mermaid").forEach((n) => {
    const tag = n.tagName.toLowerCase();
    const owns = n.classList.contains("mermaid") || (tag === "code" && n.classList.contains("language-mermaid"));
    const looks = tag === "pre" && HEAD.test((n.textContent || "").trim());
    if (!owns && !looks) return;
    const host = tag === "pre" ? n : n.closest("pre") || n;
    if (seen.has(host)) return;
    seen.add(host);
    blocks.push({ host, src: n });
  });
  for (const item of blocks) {
    const pre = item.host;
    const code = item.src;
    /* незакрытый блок не трогаем: mermaid на недописанном коде падает */
    const raw = (code.textContent || "").trim();
    if (!/\n/.test(raw) || raw.endsWith("```")) continue;
    /* <br> превращаем в маркер, чтобы слова не склеивались, и возвращаем как <br/> для mermaid */
    const clone = code.cloneNode(true);
    clone.querySelectorAll(".mermaid-svg").forEach((m) => m.remove());
    clone.querySelectorAll("br").forEach((b) => b.replaceWith(document.createTextNode("\u0001")));
    const src = clone.textContent.split("\u0001").join("<br/>").trim();
    if (pre.dataset.mmdSrc === src) continue;   /* уже пробовали этот вариант */
    pre.dataset.mmdSrc = src;
    try {
      let svg = diagramCache.get(src);
      if (!svg) {
        const id = "mmd" + Math.random().toString(36).slice(2, 9);
        const res = await mermaid.render(id, src);
        svg = res.svg;
        diagramCache.set(src, svg);
      }
      const box = document.createElement("div");
      box.className = "mermaid-svg";
      box.innerHTML = svg;
      /* без viewBox и явных размеров SVG может схлопнуться: видно текст, нет фигур */
      const svgEl = box.querySelector("svg");
      if (svgEl) {
        const vb = (svgEl.getAttribute("viewBox") || "").split(/[\s,]+/).map(Number);
        if (vb.length === 4 && vb[2] > 0) {
          svgEl.setAttribute("width", String(Math.round(vb[2])));
          svgEl.setAttribute("height", String(Math.round(vb[3])));
        }
        svgEl.style.maxWidth = "100%";
        svgEl.style.height = "auto";
        svgEl.style.display = "block";
      }
      box.querySelectorAll("rect, polygon").forEach((r) => {
        if (r.closest(".cluster") || r.closest(".note")) return;
        r.setAttribute("rx", "10");
        r.setAttribute("ry", "10");
      });
      box.querySelectorAll("text, tspan").forEach((t) => t.setAttribute("fill", "#e6e2ef"));
      box.querySelectorAll("g.node rect, rect.actor, rect.label-container").forEach((r) => r.setAttribute("fill", "#0b0d12"));
      pre.replaceWith(box);
    } catch (_) {
      /* если mermaid не осилил — остаётся кодом */
    }
  }
}

function highlight(root) {
  if (!root) return;
  if (typeof hljs !== "undefined") {
    const weak = ["makefile", "text", "plaintext", "none", "output", "log", ""];
    root.querySelectorAll("pre code").forEach((block) => {
      if (block.dataset.hl === "1") return;
      block.dataset.hl = "1";
      const cls = [...block.classList].find((c) => c.startsWith("language-"));
      const lang = cls ? cls.slice(9).toLowerCase() : "";
      if (weak.includes(lang)) {
        try {
          const res = hljs.highlightAuto(block.textContent);
          if (res.relevance >= 4) {
            block.innerHTML = res.value;
            block.className = "hljs language-" + res.language;
            return;
          }
        } catch (_) {}
      }
      try { hljs.highlightElement(block); } catch (_) {}
    });
  }
}

async function renderHtml(el, raw, final = true) {
  /* последний вызов побеждает: иначе поздний черновик затирает готовый ответ со схемой */
  const seq = (el.__seq = (el.__seq || 0) + 1);
  const clean = DOMPurify.sanitize(stripDocument(raw), {
    FORBID_TAGS: ["script", "style", "link", "meta", "iframe", "object", "embed", "base"],
    FORBID_ATTR: ["onerror", "onload", "onclick", "onmouseover", "srcdoc"],
  });
  el.classList.add("htmlmsg");

  const holder = document.createElement("div");
  holder.innerHTML = clean;
  await renderDiagrams(holder);   /* рисуем сразу, по мере появления готовых блоков */
  if (el.__seq !== seq) return;
  [...holder.querySelectorAll("*")].reverse().forEach((n) => {
    if (n.closest("svg")) return;               /* внутрь диаграмм не лезем */
    const tag = (n.tagName || "").toUpperCase();
    if (["HR", "BR", "IMG", "SVG"].includes(tag)) return;
    const hasMedia = n.querySelector("img,svg,hr,br");
    if (!hasMedia && !(n.textContent || "").trim()) n.remove();
  });

  unwrapLinkCode(holder);

  /* кнопки берём себе и убираем из HTML, иначе они видны вторым рядом как дефолтные */
  const actions = [...holder.querySelectorAll("[data-send]")].map((btn) => ({
    label: (btn.textContent || "").trim(),
    value: (btn.getAttribute("data-send") || btn.textContent || "").trim(),
  }));
  [...holder.querySelectorAll("[data-send]")].forEach((btn) => {
    const bar = btn.closest(".actions");
    btn.remove();
    if (bar && !bar.children.length) bar.remove();
  });
  holder.querySelectorAll(".actions").forEach((bar) => {
    if (!bar.children.length && !(bar.textContent || "").trim()) bar.remove();
  });

  /* многостраничный ответ: <section class="page"> … </section> */
  const pageNodes = [...holder.querySelectorAll(".page")];
  let pages;
  if (pageNodes.length) {
    pages = pageNodes.map((p) => ({ title: p.getAttribute("data-title") || "", html: p.innerHTML }));
    /* всё, что модель написала вокруг страниц (часто это схема), не теряем */
    const outside = [...holder.childNodes].filter(
      (n) => !(n.nodeType === 1 && n.classList && n.classList.contains("page"))
    );
    const box = document.createElement("div");
    outside.forEach((n) => box.appendChild(n.cloneNode(true)));
    if ((box.textContent || "").trim() || box.querySelector("svg")) {
      pages.unshift({ title: pages[0].title ? "Обзор" : "", html: box.innerHTML });
    }
  } else {
    pages = [{ title: "", html: holder.innerHTML }];
  }

  el.__pages = pages;
  if (typeof el.__pageIdx !== "number" || el.__pageIdx >= pages.length) el.__pageIdx = 0;

  let f = el.querySelector("iframe.html-frame");
  if (!f) {
    f = document.createElement("iframe");
    f.className = "html-frame";
    f.setAttribute("sandbox", "allow-same-origin allow-popups allow-popups-to-escape-sandbox");
    f.setAttribute("referrerpolicy", "no-referrer");
    el.appendChild(f);
    f.srcdoc = `<!doctype html><html><head><meta charset="utf-8"><base target="_blank">`
      + `<link rel="stylesheet" href="/static/template.css?v=${asset("template.css")}">`
      + `<link rel="stylesheet" href="/static/hljs.css?v=${asset("hljs.css")}">`
      + `</head><body></body></html>`;
    /* документ готов только после load — иначе пишем в пустой about:blank */
    f.addEventListener("load", () => { f.__ready = true; if (typeof f.__render === "function") f.__render(); }, { once: true });
  }

  const fit = () => {
    try {
      const d = f.contentDocument;
      if (!d || !d.body) return;
      /* меряем body, а не documentElement: иначе высота iframe подпирает сама себя */
      const h = Math.ceil(d.body.getBoundingClientRect().height) + 2;
      const cur = parseInt(f.style.height, 10) || 0;
      const next = final ? h : Math.max(cur, h);
      f.style.height = Math.min(Math.max(next, 40), 6000) + "px";
    } catch (_) {}
  };

  const render = () => {
    const page = pages[el.__pageIdx] || pages[0];
    const wrap = document.createElement("div");
    /* .page возвращаем при вставке — иначе пропадает ритм отступов */
    wrap.innerHTML = `<div class="page">${page.html}</div>`;
    highlight(wrap);
    const html = wrap.innerHTML;
    const apply = () => {
      if (el.__seq !== seq) return;
      try {
        const d = f.contentDocument;
        if (!d || !d.body) return;
        /* запоминаем, куда прокручены таблицы: иначе при каждой перерисовке скачут в начало */
        const shifts = [...d.querySelectorAll("table")].map((t) => t.scrollLeft);
        d.body.innerHTML = html;
        [...d.querySelectorAll("table")].forEach((t, i) => {
          if (shifts[i]) t.scrollLeft = shifts[i];
        });
        [...d.querySelectorAll("a[href]")].forEach((a) => {
          a.target = "_blank";
          a.rel = "noopener noreferrer";
        });
        const exact = () => {
          const hh = Math.ceil(d.body.getBoundingClientRect().height) + 2;
          const cur = parseInt(f.style.height, 10) || 0;
          /* при потоке не ужимаем: постоянные скачки высоты и есть то дёрганье */
          const next = final ? hh : Math.max(cur, hh);
          f.style.height = Math.min(Math.max(next, 40), 6000) + "px";
        };
        exact();
        setTimeout(exact, 60);
        setTimeout(exact, 200);
      } catch (_) {}
    };
    const doc = f.contentDocument;
    if (doc && doc.readyState === "complete" && doc.body) apply();
    else f.addEventListener("load", apply, { once: true });
  };

  /* навигация по страницам: вкладки с названиями */
  const oldNav = el.querySelector(".pages-nav");
  if (oldNav) oldNav.remove();
  if (pages.length > 1) {
    const nav = document.createElement("div");
    nav.className = "pages-nav";
    const tabs = document.createElement("div");
    tabs.className = "page-tabs";
    const paintNav = () => {
      [...tabs.children].forEach((b, i) => b.classList.toggle("active", i === el.__pageIdx));
    };
    pages.forEach((p, i) => {
      const b = document.createElement("button");
      b.className = "page-tab";
      b.textContent = p.title || `Страница ${i + 1}`;
      b.onclick = () => {
        el.__pageIdx = i;
        render();
        paintNav();
        /* возвращаем вид ровно к началу этого ответа */
        state.follow = false;
        const box = $("messages");
        const top = el.offsetTop - 10;
        box.scrollTo({ top, behavior: "smooth" });
        updateToBottom();
      };
      tabs.appendChild(b);
    });
    nav.appendChild(tabs);
    el.appendChild(nav);
    paintNav();
  }

  f.__render = render;
  if (f.__ready) render();

  const stale = el.querySelector(".actions");
  if (stale) stale.remove();
  if (actions.length) {
    const bar = document.createElement("div");
    bar.className = "actions";
    actions.forEach((a) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "action-btn";
      btn.textContent = a.label;
      btn.onclick = () => {
        if (!state.sid) return;
        $("input").value = a.value;
        send();
      };
      bar.appendChild(btn);
    });
    el.appendChild(bar);
  }
}

function paintMode() {
  const b = $("mode");
  b.textContent = state.mode === "html" ? "HTML" : "MD";
  b.classList.toggle("html", state.mode === "html");
  b.title = state.mode === "html" ? "Ответ как HTML-страница" : "Ответ как Markdown";
}

function renderMessage(m) {
  const box = $("messages");
  if (m.kind === "tool") {
    const el = document.createElement("div");
    el.className = "msg tool";
    el.textContent = "⚙ " + m.name;
    box.appendChild(el);
    return;
  }
  const el = document.createElement("div");
  el.className = "msg " + (m.kind === "user" ? "user" : "bot");
  if (m.kind === "user") el.textContent = m.text;
  else if (m.kind === "assistant" && looksHtml(m.text)) renderHtml(el, m.text);
  else { el.innerHTML = md(m.text); highlight(el); }
  box.appendChild(el);
}

/* ---------------- отправка ---------------- */
async function send(opts = {}) {
  const retry = opts.retry === true;
  const input = $("input");
  const text = retry ? "" : input.value.trim();
  if (!state.sid) return;
  if (!retry && !text) return;

  const box = $("messages");
  const newBubble = () => {
    const b = document.createElement("div");
    b.className = "msg bot cursor";
    box.appendChild(b);
    return b;
  };
  const paint = (b, value, final = false) => {
    if (!value.trim()) return;
    const isHtml = state.mode === "html" && value.trimStart().startsWith("<") && looksHtml(value);
    if (isHtml) renderHtml(b, value, final);
    else {
      b.classList.remove("htmlmsg");
      const shifts = [...b.querySelectorAll("table")].map((t) => t.scrollLeft);
      b.innerHTML = md(value);
      [...b.querySelectorAll("table")].forEach((t, i) => {
        if (shifts[i]) t.scrollLeft = shifts[i];
      });
      if (final) unwrapLinkCode(b);
      [...b.querySelectorAll("a[href]")].forEach((a) => {
        a.target = "_blank";
        a.rel = "noopener noreferrer";
      });
      /* схему рисуем сразу, как только она дописана; остальное — по финалу */
      if (value.includes("```") || value.includes("mermaid")) renderDiagrams(b);
      if (final) highlight(b);
    }
  };

  let bubble;

  try {
    if (retry) {
      /* сервер сам убирает старый ответ и повторяет тот же вопрос */
      await api(`/api/chat/${state.sid}/retry`, {
        method: "POST",
        body: JSON.stringify({ query: "", mode: state.mode }),
      });
      await openChat({ id: state.sid, title: state.title, model_alias: state.model });
    } else {
      input.value = "";
      input.style.height = "auto";
      renderMessage({ kind: "user", text });
      state.follow = true;
      scrollDown();
      await api(`/api/chat/${state.sid}/start`, {
        method: "POST",
        body: JSON.stringify({ query: text, mode: state.mode }),
      });
    }
    $("stop").classList.remove("hidden");
    state.seq = 0;
    state.aborted = false;
    bubble = newBubble();
    let buf = "";
    for (;;) {
      const r = await api(`/api/stream/${state.sid}?after=${state.seq}`);
      for (const e of r.events) {
        if (e.k === "delta") {
          if (e.d === "None" || e.d === "null") continue;
          buf += e.d;
          if (!state.paintPending) {
            state.paintPending = true;
            state.paintTimer = setTimeout(() => {
              state.paintPending = false;
              paint(bubble, buf);
            }, 260);
          }
        } else if (e.k === "tool_called") {
          bubble.classList.remove("cursor");
          if (!buf.trim()) bubble.remove();
          else paint(bubble, buf);
          const t = document.createElement("div");
          t.className = "msg tool";
          t.textContent = "⚙ " + e.d;
          box.appendChild(t);
          bubble = newBubble();
          buf = "";
        } else if (e.k === "error") {
          let info = {};
          try { info = JSON.parse(e.d); } catch { info = { message: e.d }; }
          bubble.classList.remove("cursor");
          bubble.innerHTML = md(buf) + `<p class="err">⚠️ ${info.code || "error"}: ${info.message || ""}</p>`;
        }
      }
      state.seq = r.seq;
      if (r.done || state.aborted) break;
    }
    /* отменяем отложенную перерисовку: иначе она затрёт финальный вариант со схемой */
    clearTimeout(state.paintTimer);
    state.paintPending = false;
    bubble.classList.remove("cursor");
    if (buf.trim()) paint(bubble, buf, true);
    else bubble.remove();
  } catch (e) {
    if (bubble && bubble.isConnected) bubble.innerHTML = `<p class="err">${e.message}</p>`;
    else {
      const b = newBubble();
      b.classList.remove("cursor");
      b.innerHTML = `<p class="err">${e.message}</p>`;
    }
  } finally {
    $("stop").classList.add("hidden");
  }
}

$("mode").onclick = () => {
  state.mode = state.mode === "md" ? "html" : "md";
  if (state.sid) localStorage.setItem("mode:" + state.sid, state.mode);
  paintMode();
};

/* отправка только с клавиатуры: Enter — отправить, Shift+Enter — перенос */
$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
$("input").addEventListener("input", (e) => {
  e.target.style.height = "auto";
  e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
});
$("stop").onclick = async () => {
  if (!state.sid) return;
  state.aborted = true;
  await api(`/api/chat/${state.sid}/cancel`, { method: "POST" });
  await openChat({ id: state.sid, title: state.title, model_alias: state.model });
};

$("retry").onclick = async () => {
  if (!state.sid) return;
  state.aborted = false;
  send({ retry: true });
};

/* ---------------- навигация и настройки ---------------- */
$("back").onclick = () => { show("chats"); loadChats(); };
for (const t of document.querySelectorAll(".tab")) {
  t.onclick = () => {
    if (t.dataset.tab === "chats") { show("chats"); loadChats(); }
    else { show("settings"); loadSettingsInfo(); }
  };
}
async function loadSettingsInfo() {
  try {
    const rows = await api("/api/sessions");
    $("chats-count").textContent = rows.length;
  } catch {}
  try {
    const t = await api("/api/auth/totp");
    $("totp-state").textContent = t.enabled ? "включён" : "выключен";
    $("totp-setup").classList.toggle("hidden", t.enabled);
    $("totp-off").classList.toggle("hidden", !t.enabled);
  } catch {}
  try {
    const s = await api("/api/auth/sessions");
    $("sessions-count").textContent = s.length;
  } catch {}
}

/* ---------------- меню чата (три точки) ---------------- */
let sheetTarget = null;

function openSheet(session) {
  sheetTarget = session;
  $("sheet-title").textContent = session.title || "untitled";
  $("sheet").classList.remove("hidden");
}
function closeSheet() {
  $("sheet").classList.add("hidden");
  sheetTarget = null;
}

document.querySelectorAll("#sheet .sheet-item").forEach((btn) => {
  btn.onclick = async () => {
    const act = btn.dataset.act;
    const s = sheetTarget;
    if (act === "cancel" || !s) return closeSheet();
    if (act === "rename") {
      closeSheet();
      openModal({
        title: "Chat title",
        value: s.title === "untitled" ? "" : s.title,
        onOk: async (value) => {
          if (!value.trim()) return;
          await api(`/api/sessions/${s.id}`, { method: "PATCH", body: JSON.stringify({ title: value.trim() }) });
          if (state.sid === s.id) $("chat-title").textContent = value.trim();
          await loadChats();
        },
      });
      return;
    }
    if (act === "clone") {
      closeSheet();
      openModal({
        title: "Clone chat",
        value: "копия: " + (s.title || "untitled"),
        text: "Copies provider and pinned files",
        onOk: async (name) => {
          const created = await api("/api/sessions", {
            method: "POST",
            body: JSON.stringify({ title: name.trim() || null, clone_from: s.id }),
          });
          await loadChats();
          openChat(created);
        },
      });
      return;
    }
    if (act === "clear") {
      closeSheet();
      await api(`/api/chat/${s.id}/history`, { method: "DELETE" });
      if (state.sid === s.id) $("messages").innerHTML = "";
      return;
    }
    if (act === "delete") {
      closeSheet();
      await api(`/api/sessions/${s.id}`, { method: "DELETE" });
      if (state.sid === s.id) { state.sid = null; show("chats"); }
      await loadChats();
      return;
    }
  };
});
$("sheet").querySelector(".sheet-backdrop").onclick = closeSheet;

/* ---------------- модалка ввода ---------------- */
let modalOk = null;
function openModal({ title, value = "", text = "", onOk }) {
  $("modal-title").textContent = title;
  $("modal-input").value = value;
  $("modal-input").classList.remove("hidden");
  $("modal-text").textContent = text;
  $("modal-text").classList.toggle("hidden", !text);
  $("modal").classList.remove("hidden");
  modalOk = onOk;
  setTimeout(() => $("modal-input").focus(), 50);
}
function closeModal() {
  $("modal").classList.add("hidden");
  modalOk = null;
}
$("modal-ok").onclick = async () => {
  const value = $("modal-input").value;
  const cb = modalOk;
  closeModal();
  if (cb) await cb(value);
};
$("modal-cancel").onclick = closeModal;
$("modal").querySelector(".sheet-backdrop").onclick = closeModal;
$("modal-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("modal-ok").click();
});


/* ---------------- настройки чата ---------------- */
let MODELS = null;

async function loadModels() {
  if (!MODELS) MODELS = (await api("/api/models")).models;
  return MODELS;
}

async function refreshFiles() {
  const box = $("cs-files");
  box.innerHTML = '<span class="muted">loading…</span>';
  let list = [];
  try { list = await api(`/api/sessions/${state.sid}/pinned`); } catch { box.innerHTML = '<span class="muted">failed to load</span>'; return; }
  box.innerHTML = "";
  if (!list.length) {
    box.innerHTML = '<span class="muted">no pinned files</span>';
    return;
  }
  for (const f of list) {
    const row = document.createElement("div");
    row.className = "cs-file";
    const name = document.createElement("span");
    name.className = "cs-name";
    name.textContent = f.file.split("/").pop();
    name.title = f.file;
    const tag = document.createElement("em");
    tag.textContent = f.type_of_inject;
    const x = document.createElement("button");
    x.className = "cs-x";
    x.textContent = "×";
    x.title = "Открепить";
    x.onclick = async () => {
      await api(`/api/sessions/${state.sid}/pinned`, {
        method: "DELETE",
        body: JSON.stringify({ full_paths: [f.file] }),
      });
      await refreshFiles();
    };
    row.append(name, tag, x);
    box.appendChild(row);
  }
}

async function openChatSettings() {
  if (!state.sid) return;
  $("cs-name").value = state.title === "untitled" ? "" : state.title;
  const models = await loadModels();
  const sel = $("cs-model");
  sel.innerHTML = "";
  for (const m of models) {
    const o = document.createElement("option");
    o.value = m.alias;
    o.textContent = m.alias + " · " + m.model;
    sel.appendChild(o);
  }
  if (state.model) sel.value = state.model;
  await refreshFiles();
  $("chat-sheet").classList.remove("hidden");
}

$("chat-menu").onclick = openChatSettings;
$("cs-close").onclick = () => $("chat-sheet").classList.add("hidden");
$("chat-sheet").querySelector(".sheet-backdrop").onclick = () => $("chat-sheet").classList.add("hidden");

$("cs-save-name").onclick = async () => {
  const value = $("cs-name").value.trim();
  if (!value) return;
  await api(`/api/sessions/${state.sid}`, { method: "PATCH", body: JSON.stringify({ title: value }) });
  state.title = value;
  $("chat-title").textContent = value;
  await loadChats();
};

$("cs-model").onchange = async (e) => {
  const alias = e.target.value;
  await api(`/api/sessions/${state.sid}`, { method: "PATCH", body: JSON.stringify({ model_alias: alias }) });
  state.model = alias;
};

$("cs-pin").onclick = async () => {
  const path = $("cs-path").value.trim();
  if (!path) return;
  try {
    await api(`/api/sessions/${state.sid}/pinned`, {
      method: "POST",
      body: JSON.stringify({ full_paths: [path], space_for_insert: $("cs-space").value }),
    });
    $("cs-path").value = "";
    await refreshFiles();
  } catch (e) {
    $("cs-files").innerHTML = `<span class="err">${e.message.slice(0, 160)}</span>`;
  }
};

$("cs-clear").onclick = async () => {
  await api(`/api/chat/${state.sid}/history`, { method: "DELETE" });
  $("messages").innerHTML = "";
  $("chat-sheet").classList.add("hidden");
};

$("cs-delete").onclick = async () => {
  const sid = state.sid;
  $("chat-sheet").classList.add("hidden");
  await api(`/api/sessions/${sid}`, { method: "DELETE" });
  state.sid = null;
  show("chats");
  await loadChats();
};

$("cs-clone").onclick = () => {
  const src = { id: state.sid, title: state.title };
  $("chat-sheet").classList.add("hidden");
  openModal({
    title: "Clone chat",
    value: "копия: " + (src.title || "untitled"),
    text: "Copies provider and pinned files",
    onOk: async (name) => {
      const created = await api("/api/sessions", {
        method: "POST",
        body: JSON.stringify({ title: name.trim() || null, clone_from: src.id }),
      });
      await loadChats();
      openChat(created);
    },
  });
};

$("to-bottom").onclick = () => {
  state.nearBottom = true;
  $("messages").scrollTo({ top: $("messages").scrollHeight, behavior: "smooth" });
  updateToBottom();
};

$("messages").addEventListener("scroll", () => {
  state.follow = nearBottom();
  updateToBottom();
});

/* колесо или свайп по чату — сразу отключаем прижимание, чтобы не выдёргивало */
["wheel", "touchmove"].forEach((ev) => {
  $("messages").addEventListener(ev, () => {
    if (!nearBottom()) {
      state.follow = false;
      updateToBottom();
    }
  }, { passive: true });
});


/* ---------------- экран под клавиатуру ---------------- */
function fitAppHeight() {
  const vv = window.visualViewport;
  /* высота раскладки не меняется при зуме пальцами; уменьшаемся только под клавиатуру */
  const layout = document.documentElement.clientHeight || window.innerHeight;
  const zoomed = vv ? vv.scale > 1.02 : false;
  const h = (vv && !zoomed && vv.height < layout - 120) ? Math.round(vv.height) : layout;
  document.documentElement.style.setProperty("--app-h", h + "px");
  const box = document.getElementById("messages");
  if (box && box.scrollHeight - box.scrollTop - box.clientHeight < 140) {
    box.scrollTop = box.scrollHeight;
  }
}
if (window.visualViewport) {
  visualViewport.addEventListener("resize", fitAppHeight);
  visualViewport.addEventListener("scroll", fitAppHeight);
}
window.addEventListener("resize", fitAppHeight);
window.addEventListener("orientationchange", () => setTimeout(fitAppHeight, 120));
fitAppHeight();

/* если модель завернула ссылку в <pre><code> — делаем её обычной ссылкой */
function unwrapLinkCode(root) {
  root.querySelectorAll("pre > code").forEach((code) => {
    const t = (code.textContent || "").trim();
    if (!/^https?:\/\/\S+$/.test(t) || /\s/.test(t)) return;
    const p = document.createElement("p");
    const a = document.createElement("a");
    a.href = t;
    a.textContent = t;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    p.appendChild(a);
    const pre = code.closest("pre");
    if (pre) pre.replaceWith(p);
  });
}

/* ---------------- 2FA ---------------- */
let totpMode = "enable";

$("totp-setup").onclick = async () => {
  const d = await api("/api/auth/totp/setup");
  $("totp-qr").src = d.qr;
  $("totp-secret").textContent = d.secret;
  totpMode = "enable";
  $("totp-enter").value = "";
  $("totp-sheet").classList.remove("hidden");
};

$("totp-off").onclick = () => {
  totpMode = "disable";
  $("totp-qr").removeAttribute("src");
  $("totp-secret").textContent = "";
  $("totp-enter").value = "";
  $("totp-sheet").classList.remove("hidden");
};

$("totp-enable").onclick = async () => {
  const code = $("totp-enter").value.trim();
  if (!code) return;
  try {
    await api(totpMode === "enable" ? "/api/auth/totp/enable" : "/api/auth/totp/disable",
      { method: "POST", body: JSON.stringify({ code }) });
    $("totp-sheet").classList.add("hidden");
    await loadSettingsInfo();
  } catch (e) {
    $("totp-secret").textContent = "неверный код, попробуй ещё раз";
  }
};

$("totp-close").onclick = () => $("totp-sheet").classList.add("hidden");
$("totp-sheet").querySelector(".sheet-backdrop").onclick = () => $("totp-sheet").classList.add("hidden");

/* ---------------- старт ---------------- */
async function boot() {
  try {
    const me = await api("/api/me");
    $("srv").textContent = me.agent;
    show("chats");
    await loadChats();
  } catch { showLogin(); }
}

boot();
