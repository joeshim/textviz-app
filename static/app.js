/* =========================
   Helpers / Elements
========================= */
const $ = (id) => document.getElementById(id);

const els = {
  // inputs
  text: $("text"),
  stopword: $("stopword"),
  window: $("window"),
  frequency: $("frequency"),
  topN: $("top_n"),

  // buttons
  btnWordcloud: $("btnWordcloud"),
  saveWordcloud: $("saveWordcloud"),
  btnCooc: $("btnCooc"),
  saveCooc: $("saveCooc"),
  clearBtn: $("clearBtn"),

  // wordcloud
  wcPreview: $("wcPreview"),
  imgWordcloud: $("imgWordcloud"),
  wordList: $("wordList"),

  // highlight UI
  hlPanel: $("hlPanel"),
  tabExcerpt: $("tabExcerpt"),
  tabFull: $("tabFull"),
  kwicBox: $("kwicBox"),
  textPreview: $("textPreview"),

  // cooc
  coocToggle: $("coocToggle"),
  coocPreview: $("coocPreview"), // ★画像側ラッパー
  imgCooc: $("imgCooc"),
  iframeCooc: $("iframeCooc"),
};

// 生成物URL管理
let lastWordcloudUrl = null; // dataURL
let lastCoocUrl = null;      // blob url (png)
let lastCoocHtmlUrl = null;  // blob url (html)

let currentWord = "";        // 現在選択中の頻出語
let currentMode = "excerpt"; // "excerpt" | "full"

// 抜粋表示件数（要望：20）
const KWIC_MAX = 20;
const KWIC_CONTEXT = 30;


/* =========================
   Utils
========================= */
function parseStopwords(str) {
  if (!str) return [];
  return str.split(",").map(s => s.trim()).filter(Boolean);
}

function revokeUrlSafely(url) {
  try { if (url) URL.revokeObjectURL(url); } catch (_) {}
}

function escapeHtml(s) {
  return (s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeRegExp(s) {
  return (s ?? "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function postForImage(endpoint, payload) {
  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    let err = "エラーが発生しました";
    try {
      const j = await res.json();
      err = j.error || err;
    } catch (_) {}
    throw new Error(err);
  }

  const blob = await res.blob();
  return URL.createObjectURL(blob);
}


/* =========================
   Cooc Toggle (OFF=image / ON=interactive)
   ★ imgCooc.style.display は触らない
========================= */
function isInteractiveOn() {
  return els.coocToggle?.checked === true;
}

function setCoocVisibleByToggle() {
  const interactive = isInteractiveOn();

  // 画像枠（ラッパー）とiframeだけ切替
  if (els.coocPreview) els.coocPreview.style.display = interactive ? "none" : "block";
  if (els.iframeCooc) els.iframeCooc.style.display = interactive ? "block" : "none";
}


/* =========================
   Highlight Panel (Excerpt / Full)
   - 初期は非表示
   - 頻出語クリックで表示
========================= */
function showHighlightPanel() {
  if (els.hlPanel) els.hlPanel.style.display = "block";
}

function setHighlightMode(mode) {
  currentMode = mode;

  // tabs
  if (els.tabExcerpt) {
    els.tabExcerpt.classList.toggle("is-active", mode === "excerpt");
    els.tabExcerpt.setAttribute("aria-selected", String(mode === "excerpt"));
  }
  if (els.tabFull) {
    els.tabFull.classList.toggle("is-active", mode === "full");
    els.tabFull.setAttribute("aria-selected", String(mode === "full"));
  }

  // panels
  if (els.kwicBox) els.kwicBox.style.display = (mode === "excerpt") ? "block" : "none";
  if (els.textPreview) els.textPreview.style.display = (mode === "full") ? "block" : "none";
}

function renderFullHighlight() {
  const raw = els.text?.value || "";

  if (!els.textPreview) return;

  if (!raw.trim()) {
    els.textPreview.innerHTML = `<div class="placeholder">頻出語をクリックすると、全文ハイライトを表示できます</div>`;
    return;
  }

  if (!currentWord) {
    // 「全文」なのに語未選択、というケースは通常起きないが保険
    els.textPreview.innerHTML = escapeHtml(raw);
    return;
  }

  const re = new RegExp(escapeRegExp(currentWord), "g");
  const safe = escapeHtml(raw).replace(re, (m) => `<mark>${m}</mark>`);
  els.textPreview.innerHTML = safe;
}

function renderKWIC() {
  if (!els.kwicBox) return;

  const text = els.text?.value || "";
  if (!text.trim()) {
    els.kwicBox.innerHTML = `<div class="placeholder">頻出語をクリックすると、該当箇所の抜粋が表示されます</div>`;
    return;
  }

  if (!currentWord) {
    els.kwicBox.innerHTML = `<div class="placeholder">頻出語をクリックすると、該当箇所の抜粋が表示されます</div>`;
    return;
  }

  const escaped = escapeRegExp(currentWord);
  const reFind = new RegExp(escaped, "g");
  const reMark = new RegExp(escaped, ""); // snippet内で1回だけmark（簡単・軽量）

  const hits = [];
  let match;

  while ((match = reFind.exec(text)) !== null) {
    const start = Math.max(0, match.index - KWIC_CONTEXT);
    const end = Math.min(text.length, match.index + currentWord.length + KWIC_CONTEXT);

    let snippet = text.slice(start, end);
    snippet = escapeHtml(snippet).replace(reMark, (m) => `<mark>${m}</mark>`);

    hits.push(`<div class="kwic-item">…${snippet}…</div>`);
    if (hits.length >= KWIC_MAX) break;

    // 念のため：ゼロ幅一致無限ループ回避
    if (match.index === reFind.lastIndex) reFind.lastIndex++;
  }

  els.kwicBox.innerHTML = hits.length
    ? hits.join("")
    : `<div class="kwic-item">一致なし</div>`;
}


/* =========================
   Top Words (tags)
========================= */
function renderTopWords(items) {
  if (!els.wordList) return;

  els.wordList.innerHTML = "";
  if (!items || items.length === 0) return;

  items.forEach(({ word, count }) => {
    const tag = document.createElement("div");
    tag.className = "word-tag";
    tag.textContent = word;

    const sm = document.createElement("small");
    sm.textContent = count;
    tag.appendChild(sm);

    tag.addEventListener("click", () => {
      // 同じ語を再クリックで解除（好み：解除したい場合）
      currentWord = (currentWord === word) ? "" : word;

      // パネル表示
      showHighlightPanel();

      if (!currentWord) {
        // 解除時：抜粋/全文をプレースホルダーに戻す
        renderKWIC();
        renderFullHighlight();
        setHighlightMode("excerpt");
        return;
      }

      // 抜粋を先に見せる（要件：初期は抜粋）
      renderKWIC();
      renderFullHighlight();
      setHighlightMode("excerpt");
    });

    els.wordList.appendChild(tag);
  });
}


/* =========================
   Wordcloud (image + top words)
========================= */
async function generateWordcloud() {
  const payload = {
    text: els.text?.value || "",
    stopword: parseStopwords(els.stopword?.value || ""),
  };

  const res = await fetch("/wordcloud_bundle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    let err = "エラーが発生しました";
    try {
      const j = await res.json();
      err = j.error || err;
    } catch (_) {}
    throw new Error(err);
  }

  const j = await res.json();

  // dataURL（base64）
  els.imgWordcloud.src = j.image || "";
  lastWordcloudUrl = j.image || null;

  renderTopWords(j.top_words || []);

  // ワードクラウド生成後は、頻出語クリック待ちなのでハイライトパネルは非表示のままでOK
}


/* =========================
   Cooccurrence (image + html simultaneously)
========================= */
async function generateCooc() {
  const payload = {
    text: els.text?.value || "",
    stopword: parseStopwords(els.stopword?.value || ""),
    window: Number(els.window?.value || 4),
    frequency: Number(els.frequency?.value || 2),
    top_n: Number(els.topN?.value || 40),
  };

  // 表示はトグルに従う
  setCoocVisibleByToggle();

  // 前回URL破棄
  revokeUrlSafely(lastCoocUrl);
  revokeUrlSafely(lastCoocHtmlUrl);
  lastCoocUrl = null;
  lastCoocHtmlUrl = null;

  // 画像生成
  const imgUrl = await postForImage("/cooccurrence_analysis", payload);

  // html生成
  const htmlRes = await fetch("/cooccurrence_html", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!htmlRes.ok) {
    let err = "エラーが発生しました";
    try {
      const j = await htmlRes.json();
      err = j.error || err;
    } catch (_) {}
    throw new Error(err);
  }

  const htmlJson = await htmlRes.json();

  // 画像セット（srcが入るとCSSで表示される）
  lastCoocUrl = imgUrl;
  els.imgCooc.src = imgUrl;

  // iframeセット
  const html = htmlJson.html || "<html><body>no html</body></html>";
  const blob = new Blob([html], { type: "text/html" });
  const url = URL.createObjectURL(blob);
  lastCoocHtmlUrl = url;
  els.iframeCooc.src = url;

  // 最後にトグルに従って表示
  setCoocVisibleByToggle();
}


/* =========================
   Save images
========================= */
function saveWordcloud() {
  if (!lastWordcloudUrl) {
    alert("先にワードクラウドを生成してください。");
    return;
  }
  const a = document.createElement("a");
  a.href = lastWordcloudUrl; // dataURL
  a.download = "wordcloud.png";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function saveCooc() {
  if (!lastCoocUrl) {
    alert("先に共起ネットワークを生成してください。");
    return;
  }
  const a = document.createElement("a");
  a.href = lastCoocUrl; // blob url
  a.download = "cooccurrence.png";
  document.body.appendChild(a);
  a.click();
  a.remove();
}


/* =========================
   Clear
========================= */
function clearAll() {
  if (els.text) els.text.value = "";
  if (els.stopword) els.stopword.value = "";

  // 画像・iframeを消す（src属性を外す）
  els.imgWordcloud?.removeAttribute("src");
  els.imgCooc?.removeAttribute("src");
  els.iframeCooc?.removeAttribute("src");

  // 頻出語タグ
  if (els.wordList) els.wordList.innerHTML = "";

  // ハイライト領域
  currentWord = "";
  if (els.hlPanel) els.hlPanel.style.display = "none";
  if (els.kwicBox) els.kwicBox.innerHTML = "";
  if (els.textPreview) els.textPreview.innerHTML = "";

  // URL破棄
  revokeUrlSafely(lastCoocUrl);
  revokeUrlSafely(lastCoocHtmlUrl);
  lastWordcloudUrl = null;
  lastCoocUrl = null;
  lastCoocHtmlUrl = null;

  // 共起トグルを画像に戻す
  if (els.coocToggle) els.coocToggle.checked = false;
  setCoocVisibleByToggle();

  // タブも初期化
  setHighlightMode("excerpt");
}


/* =========================
   Events / Init
========================= */
function init() {
  // cooc toggle
  els.coocToggle?.addEventListener("change", setCoocVisibleByToggle);

  // highlight tabs
  els.tabExcerpt?.addEventListener("click", () => setHighlightMode("excerpt"));
  els.tabFull?.addEventListener("click", () => {
    // 全文は重いので、切替タイミングで再描画しておく（安全）
    renderFullHighlight();
    setHighlightMode("full");
  });

  // buttons
  els.btnWordcloud?.addEventListener("click", async () => {
    try { await generateWordcloud(); }
    catch (e) { alert(e.message); }
  });

  els.btnCooc?.addEventListener("click", async () => {
    try { await generateCooc(); }
    catch (e) { alert(e.message); }
  });

  els.saveWordcloud?.addEventListener("click", saveWordcloud);
  els.saveCooc?.addEventListener("click", saveCooc);
  els.clearBtn?.addEventListener("click", clearAll);

  // 初期状態
  setCoocVisibleByToggle();
  if (els.hlPanel) els.hlPanel.style.display = "none";
  setHighlightMode("excerpt");
}

init();