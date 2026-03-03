const $ = (id) => document.getElementById(id);

const imgWordcloud = $("imgWordcloud");
const imgCooc = $("imgCooc");

let lastWordcloudUrl = null;
let lastCoocUrl = null;

function parseStopwords(str) {
  if (!str) return [];
  return str
    .split(",")
    .map(s => s.trim())
    .filter(Boolean);
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

// ワードクラウド生成
$("btnWordcloud").addEventListener("click", async () => {
  try {
    const payload = {
      text: $("text").value,
      stopword: parseStopwords($("stopword").value),
    };
    const url = await postForImage("/analyze", payload);
    lastWordcloudUrl = url;
    imgWordcloud.src = url;
  } catch (e) {
    alert(e.message);
  }
});

// 共起ネットワーク生成
$("btnCooc").addEventListener("click", async () => {
  try {
    const payload = {
      text: $("text").value,
      stopword: parseStopwords($("stopword").value),
      window: Number($("window").value || 4),
      frequency: Number($("frequency").value || 2),
      top_n: Number($("top_n").value || 40),
    };
    const url = await postForImage("/cooccurrence_analysis", payload);
    lastCoocUrl = url;
    imgCooc.src = url;
  } catch (e) {
    alert(e.message);
  }
});

// クリア
$("clearBtn").addEventListener("click", () => {
  $("text").value = "";
  $("stopword").value = "";
  imgWordcloud.removeAttribute("src");
  imgCooc.removeAttribute("src");
  lastWordcloudUrl = null;
  lastCoocUrl = null;
});

// 画像保存（ワードクラウド）
$("saveWordcloud").addEventListener("click", () => {
  if (!lastWordcloudUrl) {
    alert("先にワードクラウドを生成してください。");
    return;
  }
  const a = document.createElement("a");
  a.href = lastWordcloudUrl;
  a.download = "wordcloud.png";
  document.body.appendChild(a);
  a.click();
  a.remove();
});

// 画像保存（共起ネットワーク）
$("saveCooc").addEventListener("click", () => {
  if (!lastCoocUrl) {
    alert("先に共起ネットワークを生成してください。");
    return;
  }
  const a = document.createElement("a");
  a.href = lastCoocUrl;
  a.download = "cooccurrence.png";
  document.body.appendChild(a);
  a.click();
  a.remove();
});