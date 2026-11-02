"""Значки фигур в тексте книги: вырезка по рамкам символов из OCR (строки G в work/ocr/*.tsv),
группировка похожих (k-средних) и сводная картинка групп для подписи глазами.

  python3 ocr/glyphs.py cut          -> work/glyphs.npy, work/glyphs.json, work/glyph_groups.png
  python3 ocr/glyphs.py label 0=N 1=B …   -> work/glyph_labels.json (группа -> фигура)

Подписанные группы дальше превращают «Exc4» в «Nxc4» (ocr/moves.py)."""
import sys, os, json, glob
import numpy as np
from PIL import Image, ImageDraw
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
S = 28          # сторона нормализованного значка

def norm(crop):
    a = np.array(crop.convert("L")) < 140
    ys, xs = np.nonzero(a)
    if len(xs) < 8: return None
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = a.shape
    if h < 10 or w < 6 or w > 3 * h: return None
    side = max(h, w)
    sq = np.zeros((side, side), bool)
    sq[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = a
    return np.array(Image.fromarray(sq.astype(np.uint8) * 255).resize((S, S), Image.BILINEAR)) / 255.0

def segments(a):
    """бинарная картинка слова -> [(x0, x1)] знаков по пустым столбцам"""
    col = a.any(axis=0); out, x = [], 0
    while x < len(col):
        if not col[x]: x += 1; continue
        x0 = x
        while x < len(col) and col[x]: x += 1
        out.append((x0, x))
    return out

def glyph_of(im, W, H, f):
    """значок фигуры в слове: справа отсчитываем знаки после значка (поле, x, +!?), значок — перед ними"""
    x, y, w, h = map(float, f[1:5]); word, after = f[5], int(f[6])
    box = (int(x * W) - 3, int(y * H) - 2, int((x + w) * W) + 3, int((y + h) * H) + 2)
    a = np.array(im.crop(box).convert("L")) < 140
    seg = segments(a); hpx = box[3] - box[1]
    # мелочь (точки, хвосты «!») не считаем знаком, если она не последняя
    seg = [s for s in seg if s[1] - s[0] >= 2]
    if len(seg) <= after: return None, None
    g = seg[-after - 1]
    # значок узкий — склеен из двух частей
    if g[1] - g[0] < 0.45 * hpx and len(seg) > after + 1:
        g = (seg[-after - 2][0], g[1])
    if g[1] - g[0] > 1.6 * hpx: return None, None
    crop = im.crop((box[0] + g[0], box[1], box[0] + g[1], box[3]))
    return norm(crop), (box[0] + g[0], box[1], box[0] + g[1], box[3])

def cut():
    feats, meta = [], []
    for fn in sorted(glob.glob("work/ocr/p*.tsv")):
        p = int(fn[-7:-4])
        im = Image.open(f"work/pages/p{p:03d}.png"); W, H = im.size
        for l in open(fn, encoding="utf-8"):
            f = l.rstrip("\n").split("\t")
            if f[0] != "G" or len(f) < 7: continue
            g, box = glyph_of(im, W, H, f)
            if g is None: continue
            feats.append(g.ravel()); meta.append([p, f[5], int(f[6]), box])
    X = np.array(feats)
    from sklearn.cluster import KMeans
    k = int(os.environ.get("K", 14))
    km = KMeans(n_clusters=k, n_init=10, random_state=0).fit(X)
    np.save("work/glyphs.npy", X); json.dump({"meta": meta, "lab": km.labels_.tolist(), "cent": km.cluster_centers_.tolist()}, open("work/glyphs.json", "w"))
    # сводная: строка на группу, 16 примеров, увеличено
    Z = 3 * S
    sheet = Image.new("L", (40 + 16 * (Z + 4), k * (Z + 6)), 255); d = ImageDraw.Draw(sheet)
    for c in range(k):
        idx = np.nonzero(km.labels_ == c)[0]
        d.text((4, c * (Z + 6) + Z // 2 - 6), str(c), fill=0)
        rng = np.random.default_rng(c)
        for i, j in enumerate(rng.choice(idx, min(16, len(idx)), replace=False)):
            g = Image.fromarray((255 - X[j].reshape(S, S) * 255).astype(np.uint8)).resize((Z, Z))
            sheet.paste(g, (40 + i * (Z + 4), c * (Z + 6)))
    sheet.save("work/glyph_groups.png")
    print("значков", len(X), "групп", k, [int((km.labels_ == c).sum()) for c in range(k)])

def label(args):
    lab = {a.split("=")[0]: a.split("=")[1] for a in args}
    json.dump(lab, open("work/glyph_labels.json", "w"))
    print(lab)

if __name__ == "__main__":
    cut() if sys.argv[1] == "cut" else label(sys.argv[2:])
