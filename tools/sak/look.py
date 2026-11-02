"""Точечный взгляд в PDF: строки с ходом N партии G, вырезка ±2 строки.
   python3 look.py 5 17... [ещё ходы]  -> картинки в $OUT"""
import sys, os, re, glob
from PIL import Image
OUT = os.environ.get("OUT", "/tmp")
game, want = sys.argv[1], sys.argv[2:]
pages = sorted(glob.glob("work/ocr/p*.tsv"))
# страница шапки партии и следующей
start = None; hy = 0; hx = 0
for fn in pages:
    for l in open(fn, encoding="utf-8"):
        f = l.split("\t")
        if f[0] == "L" and re.match(r"^%s\.\s+[А-ЯЁA-Z]" % game, f[5]) and re.search(r"\s[–-]\s", f[5]):
            start = int(fn[-7:-4]); hy = float(f[2]); hx = float(f[1]); break
    if start: break
def after_head(p, f):
    """на странице шапки — только ниже неё в той же колонке или в правой колонке"""
    if p != start: return True
    x, y = float(f[1]), float(f[2])
    return (y > hy and (x < 0.47) == (hx < 0.47)) or (hx < 0.47 and x >= 0.47)
import numpy as np
def ink(p, f):
    """доля тёмных пикселей строки: жирная главная линия темнее комментария"""
    im = Image.open(f"work/pages/p{p:03d}.png"); W, H = im.size
    x, y, w_, h = map(float, f[1:5])
    a = np.array(im.crop((int(x * W), int(y * H), int((x + w_) * W), int((y + h) * H))).convert("L")) < 128
    return a.mean()
for w in want:
    num = re.match(r"\d+", w).group(0); black = "..." in w
    pat = re.compile(r"(?<![\d.])%s\s*%s" % (num, r"\.\s*[.…]" if black else r"\.\s*[^.\s…]"))
    hit = None
    pats = [pat] + ([re.compile(r"(?<![\d.])%s\s*\.\s*[^.\s…]" % num)] if black else [])
    for pat in pats:
      if hit: break
      for p in range(start, start + 6):
        L = [l.rstrip("\n").split("\t") for l in open(f"work/ocr/p{p:03d}.tsv", encoding="utf-8") if l.startswith("L")]
        for k, f in enumerate(L):
            if pat.search(f[5]) and after_head(p, f):
                d = ink(p, f)
                if hit is None or d > hit[3] * 1.12: hit = (p, L, k, d)
    if not hit: print("не найдено", w, "шапка на стр.", start); continue
    p, L, k, _ = hit
    im = Image.open(f"work/pages/p{p:03d}.png"); W, H = im.size
    x, y, w_, h = map(float, L[k][1:5])
    col = (0, 0.5) if x < 0.47 and w_ < 0.62 else (0.47, 1.0) if w_ < 0.62 else (0, 1)
    y0, y1 = max(0, y - 2.4 * h), min(1, y + 3.4 * h)
    crop = im.crop((int(col[0] * W), int(y0 * H), int(col[1] * W), int(y1 * H)))
    crop = crop.resize((crop.size[0] * 2 // 3, crop.size[1] * 2 // 3))
    fn = f"{OUT}/g{game}_{w.replace('.', '_')}.png"; crop.save(fn); print(fn, "стр.", p)
