import os
import io
import re
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

# ==========================
# 基本設定
# ==========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "NotoSansCJKjp-Regular.otf")

# ★ FONT_PATH定義後に登録（順番重要）
fm.fontManager.addfont(FONT_PATH)
JP_FONT = fm.FontProperties(fname=FONT_PATH)
plt.rcParams["font.family"] = JP_FONT.get_name()

app = Flask(__name__)

# Sudachi初期化
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

    # 見出し記号などを軽く除去（任意）
    text = re.sub(r"[①②③④⑤★#]", " ", text)

    tokens = []
    for m in tokenizer_obj.tokenize(text, mode):
        pos = m.part_of_speech()[0]  # '名詞'など

        if pos not in ("名詞", "動詞", "形容詞", "形容動詞"):
            continue

        word = m.surface().strip()  # ★原形ではなく表層形

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


# ==========================
# ルート
# ==========================

@app.route("/")
def index():
    return render_template("index.html")


# ==========================
# ワードクラウド
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
# 共起ネットワーク（Springレイアウト）
# ==========================

@app.route("/cooccurrence_analysis", methods=["POST"])
def cooccurrence():
    data = request.get_json()
    text = data.get("text", "")
    stopword = data.get("stopword", [])
    window = int(data.get("window", 4))
    min_edge = int(data.get("frequency", 2))
    top_n = int(data.get("top_n", 40))

    tokens = tokenize(text, set(stopword))
    words = [w for w, _ in tokens]
    pos_dict = {w: p for w, p in tokens}

    freq = Counter(words)
    top_words = set([w for w, _ in freq.most_common(top_n)])

    # window共起をカウント
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
    for w in list(top_words)[:30]:
        if w not in G:
            G.add_node(w)

    # ==========================
    # 描画（品詞カラー）
    # ==========================

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

    # ★ networkxのlabelsは使わず、自前で描画（フォントを確実適用）
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
# 実行
# ==========================

if __name__ == "__main__":
    app.run(debug=True)