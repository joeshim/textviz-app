import os
import io
import re
import base64
from io import BytesIO
from collections import Counter

from flask import Flask, request, send_file, render_template, jsonify

from sudachipy import dictionary, tokenizer
from wordcloud import WordCloud

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib import font_manager as fm

import networkx as nx
from pyvis.network import Network


# ==========================
# 基本設定
# ==========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "NotoSansCJKjp-Regular.otf")

# matplotlib 側の日本語フォント（静止画用）
fm.fontManager.addfont(FONT_PATH)
JP_FONT = fm.FontProperties(fname=FONT_PATH)
plt.rcParams["font.family"] = JP_FONT.get_name()

app = Flask(__name__)

# Sudachi 初期化
tokenizer_obj = dictionary.Dictionary().create()
mode = tokenizer.Tokenizer.SplitMode.C


# ==========================
# 共通ストップワード
# ==========================

JP_STOP_DEFAULT = {
    "する", "なる", "いる", "ある", "できる", "ため", "こと", "もの", "よう",
    "それ", "これ", "あれ", "ここ", "そこ", "そして", "また", "など",
    "です", "ます"
}


# ==========================
# トークナイズ（表層形使用）
# ==========================

def tokenize(text: str, stopwords=set()):
    stop = set(stopwords) | JP_STOP_DEFAULT

    # 見出し記号などを軽く除去
    text = re.sub(r"[①②③④⑤★#]", " ", text)

    tokens = []
    for m in tokenizer_obj.tokenize(text, mode):
        pos = m.part_of_speech()[0]  # '名詞'など

        if pos not in ("名詞", "動詞", "形容詞", "形容動詞"):
            continue

        word = m.surface().strip()  # 原形ではなく表層形

        # ノイズ除去
        if len(word) <= 1:
            continue
        if word.isdigit():
            continue
        if word in stop:
            continue
        if re.fullmatch(r"[ぁ-ん]{1,2}", word):
            continue

        tokens.append((word, pos))

    return tokens


def build_cooccurrence_graph(text: str, stopword, window: int, min_edge: int, top_n: int):
    """
    共起ネットワーク用の Graph を返す（画像版・HTML版で共通利用）
    """
    tokens = tokenize(text, set(stopword))
    words = [w for w, _ in tokens]
    pos_dict = {w: p for w, p in tokens}

    freq = Counter(words)
    top_words = set([w for w, _ in freq.most_common(top_n)])

    # window 共起をカウント
    edge_counter = Counter()
    for i in range(len(words)):
        wi = words[i]
        if wi not in top_words:
            continue
        for j in range(i + 1, min(i + window, len(words))):
            wj = words[j]
            if wj not in top_words or wi == wj:
                continue
            pair = tuple(sorted([wi, wj]))
            edge_counter[pair] += 1

    G = nx.Graph()
    for (u, v), w in edge_counter.items():
        if w >= min_edge:
            G.add_edge(u, v, weight=w)

    # ノードが少なすぎる場合は単独ノードも追加（保険）
    for w in list(top_words)[:min(30, len(top_words))]:
        if w not in G:
            G.add_node(w)

    # pyvis 用に value（頻度）を持たせる（※今後の拡張に便利）
    for n in G.nodes():
        G.nodes[n]["value"] = int(freq.get(n, 1))

    return G, freq, pos_dict


# ==========================
# ルート
# ==========================

@app.route("/")
def index():
    return render_template("index.html")


# ==========================
# ワードクラウド（画像）
# ==========================

@app.route("/analyze", methods=["POST"])
def analyze_text():
    data = request.get_json()
    text = data.get("text", "")
    stopword = data.get("stopword", [])

    tokens = tokenize(text, set(stopword))
    words = [w for w, _ in tokens]
    freq = Counter(words)

    wc = WordCloud(
        font_path=FONT_PATH,
        background_color="white",
        width=1200,
        height=800,
        colormap="viridis"
    ).generate_from_frequencies(freq)

    img_io = io.BytesIO()
    wc.to_image().save(img_io, format="PNG")
    img_io.seek(0)

    return send_file(img_io, mimetype="image/png")


# ==========================
# ワードクラウド（画像＋頻出語）
# ==========================

@app.route("/wordcloud_bundle", methods=["POST"])
def wordcloud_bundle():
    try:
        data = request.get_json()
        text = data.get("text", "")
        stopword = data.get("stopword", [])

        tokens = tokenize(text, set(stopword))
        words = [w for w, _ in tokens]
        freq = Counter(words)

        wc = WordCloud(
            font_path=FONT_PATH,
            background_color="white",
            width=1200,
            height=800,
            colormap="viridis"
        ).generate_from_frequencies(freq)

        # PNG → base64(dataURL)
        img = wc.to_image()
        buf = BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_url = f"data:image/png;base64,{b64}"

        top_words = [{"word": w, "count": int(c)} for w, c in freq.most_common(50)]
        return jsonify({"image": data_url, "top_words": top_words})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================
# 共起ネットワーク（静止画）
# ==========================

@app.route("/cooccurrence_analysis", methods=["POST"])
def cooccurrence():
    data = request.get_json()
    text = data.get("text", "")
    stopword = data.get("stopword", [])
    window = int(data.get("window", 4))
    min_edge = int(data.get("frequency", 2))
    top_n = int(data.get("top_n", 40))

    G, freq, pos_dict = build_cooccurrence_graph(text, stopword, window, min_edge, top_n)

    plt.figure(figsize=(14, 10))
    layout_pos = nx.spring_layout(G, seed=42, k=0.9)

    pos_color = {
        "名詞": "lightskyblue",
        "動詞": "mediumspringgreen",
        "形容詞": "lightsalmon",
        "形容動詞": "lightsalmon",
    }

    node_sizes = [max(200, freq.get(n, 1) * 200) for n in G.nodes()]
    node_colors = [pos_color.get(pos_dict.get(n, ""), "lightgray") for n in G.nodes()]
    edge_widths = [max(1, G[u][v]["weight"] * 0.8) for u, v in G.edges()]

    nx.draw_networkx_edges(G, layout_pos, width=edge_widths, alpha=0.4, edge_color="gray")
    nx.draw_networkx_nodes(
        G, layout_pos,
        node_size=node_sizes,
        node_color=node_colors,
        edgecolors="white",
        linewidths=1.5,
        alpha=0.95
    )

    # networkx の labels を使わず、自前で描画（フォントを確実適用）
    for node, (x, y) in layout_pos.items():
        plt.text(
            x, y, node,
            fontproperties=JP_FONT,
            fontsize=10,
            ha="center", va="center",
            path_effects=[pe.withStroke(linewidth=3, foreground="white")]
        )

    plt.axis("off")

    img_io = io.BytesIO()
    plt.savefig(img_io, format="PNG", bbox_inches="tight", dpi=150)
    plt.close()
    img_io.seek(0)

    return send_file(img_io, mimetype="image/png")


# ==========================
# 共起ネットワーク（インタラクティブHTML）
# ※ 見え方は「ラベルがノードの下」を維持
# ==========================

@app.route("/cooccurrence_html", methods=["POST"])
def cooccurrence_html():
    try:
        data = request.get_json()
        text = data.get("text", "")
        stopword = data.get("stopword", [])
        window = int(data.get("window", 4))
        min_edge = int(data.get("frequency", 2))
        top_n = int(data.get("top_n", 40))

        G, freq, pos_dict = build_cooccurrence_graph(text, stopword, window, min_edge, top_n)

        pos_color = {
            "名詞": "#7bc4ff",
            "動詞": "#3ddc97",
            "形容詞": "#ff9f8a",
            "形容動詞": "#ff9f8a",
        }

        net = Network(height="650px", width="100%", bgcolor="#ffffff", font_color="#222")

        # ★options はここに集約（add_node での font 指定は最小に）
        net.set_options(r"""
        {
        "interaction": {
            "hover": true,
            "dragNodes": true,
            "zoomView": true,
            "navigationButtons": true
        },
        "physics": { "enabled": true },

        "nodes": {
            "shape": "circle",
            "font": {
            "size": 22,
            "strokeWidth": 4,
            "strokeColor": "#ffffff",
            "color": "#222"
            }
        },

        "edges": {
            "smooth": { "enabled": false },
            "color": { "color": "#b0b0b0" },
            "width": 2
        }
        }
        """)

        # ノード
        for n in G.nodes():
            p = pos_dict.get(n, "")
            color = pos_color.get(p, "#d0d0d0")
            size = max(12, min(40, int(freq.get(n, 1) * 3)))
            net.add_node(n, label=n, color=color, size=size, borderWidth=2)

        # エッジ（クリックでupdateするので id を付与）
        edge_id = 0
        for u, v, d in G.edges(data=True):
            w = int(d.get("weight", 1))
            net.add_edge(u, v, value=w, width=max(2, w), color="#b0b0b0", id=edge_id)
            edge_id += 1

        html = net.generate_html()

        ui_css = """
        <style>
        /* ズームUIを左下に固定 */
        .vis-navigation{
        position: absolute !important;
        left: 12px !important;
        bottom: 12px !important;
        top: auto !important;
        right: auto !important;
        }

        /* “画面（背景）ドラッグ”のカーソル */
        #mynetwork{ cursor: grab; }
        #mynetwork.is-grabbing{ cursor: grabbing; }
        </style>
        """
        html = html.replace("</head>", ui_css + "\n</head>")

        # 右下ズームスライダー
        zoom_ui_css = """
        <style>
        .zoom-slider{
        position: absolute;
        right: 12px;
        bottom: 12px;
        z-index: 9999;
        background: rgba(255,255,255,0.92);
        border: 1px solid #e6e6e6;
        border-radius: 10px;
        padding: 10px 10px 8px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.06);
        width: 160px;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        .zoom-slider label{
        display:flex;
        justify-content:space-between;
        align-items:center;
        font-size: 12px;
        color:#444;
        margin: 0 0 6px 0;
        }

        .zoom-slider input[type="range"]{
        width: 100%;
        }

        /* 既存の grab/grabbing（前回のものがある前提。なければ追加してください） */
        #mynetwork{ cursor: grab; }
        #mynetwork.is-grabbing{ cursor: grabbing; }
        </style>
        """
        html = html.replace("</head>", zoom_ui_css + "\n</head>")

        zoom_ui_js = """
        <script>
        (function(){
        const container = document.getElementById("mynetwork");
        if(!container || typeof network === "undefined") return;

        // ----- UIを追加 -----
        const box = document.createElement("div");
        box.className = "zoom-slider";
        box.innerHTML = `
            <label>
            <span>ズーム</span>
            <span id="zoomVal"></span>
            </label>
            <input id="zoomRange" type="range" min="30" max="220" value="100" step="1" />
        `;
        container.appendChild(box);

        const range = box.querySelector("#zoomRange");
        const zoomVal = box.querySelector("#zoomVal");

        // min/max scale（好みで調整）
        const MIN_SCALE = 0.3;
        const MAX_SCALE = 2.2;

        // slider(30-220) <-> scale(0.3-2.2)
        function sliderToScale(v){
            const t = (v - 30) / (220 - 30);
            return MIN_SCALE + t * (MAX_SCALE - MIN_SCALE);
        }
        function scaleToSlider(s){
            const t = (s - MIN_SCALE) / (MAX_SCALE - MIN_SCALE);
            return 30 + t * (220 - 30);
        }
        function updateLabel(scale){
            zoomVal.textContent = Math.round(scale * 100) + "%";
        }

        // 初期表示を現在ズームに合わせる
        try{
            const cur = network.getScale ? network.getScale() : 1.0;
            range.value = Math.round(scaleToSlider(cur));
            updateLabel(cur);
        }catch(e){
            updateLabel(1.0);
        }

        // スライダー操作でズーム
        range.addEventListener("input", () => {
            const scale = sliderToScale(Number(range.value));
            const pos = network.getViewPosition ? network.getViewPosition() : {x:0, y:0};
            network.moveTo({ position: pos, scale: scale, animation: false });
            updateLabel(scale);
        });

        // マウスホイール等でズームしたらスライダーも追従
        if(network.on){
            network.on("zoom", (p) => {
            const s = p.scale;
            range.value = Math.round(scaleToSlider(s));
            updateLabel(s);
            });
        }

        // ----- 背景ドラッグ中だけ grabbing（前回のやつ） -----
        container.addEventListener("mousedown", (e) => {
            if(e.target && e.target.tagName === "CANVAS"){
            container.classList.add("is-grabbing");
            }
        });
        window.addEventListener("mouseup", () => container.classList.remove("is-grabbing"));
        window.addEventListener("blur", () => container.classList.remove("is-grabbing"));
        })();
        </script>
        """
        html = html.replace("</body>", zoom_ui_js + "\n</body>")

        # ノードクリックで「接続エッジのみ青」、それ以外は薄く。空クリックでリセット。
        highlight_js = r"""
        <script>
        (function(){
        if (typeof network === "undefined" || typeof edges === "undefined") return;

        function resetEdges(){
            edges.get().forEach(function(e){
            edges.update({ id: e.id, color: "#b0b0b0", width: 2 });
            });
        }

        network.on("click", function(params){
            if (!params.nodes || params.nodes.length === 0) {
            resetEdges();
            return;
            }

            const nodeId = params.nodes[0];

            edges.get().forEach(function(e){
            const connected = (e.from === nodeId || e.to === nodeId);

            edges.update({
                id: e.id,
                color: connected ? "#2f6fff" : "#e0e0e0",
                width: connected ? 4 : 1
            });
            });
        });
        })();
        </script>
        """
        html = html.replace("</body>", highlight_js + "\n</body>")

        cursor_js = """
        <script>
        (function(){
        // PyVisのコンテナは id="mynetwork"
        const container = document.getElementById("mynetwork");
        if(!container) return;

        // “背景ドラッグ（pan）”中だけ grabbing にする
        // ここで重要：mousedown のターゲットが canvas のときだけ反応させる
        container.addEventListener("mousedown", (e) => {
            if(e.target && e.target.tagName === "CANVAS"){
            container.classList.add("is-grabbing");
            }
        });

        window.addEventListener("mouseup", () => {
            container.classList.remove("is-grabbing");
        });

        window.addEventListener("blur", () => {
            container.classList.remove("is-grabbing");
        });
        })();
        </script>
        """
        html = html.replace("</body>", cursor_js + "\n</body>")

        return jsonify({"html": html})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================
# 実行
# ==========================

if __name__ == "__main__":
    app.run(debug=True)