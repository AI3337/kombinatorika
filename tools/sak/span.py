"""Кусок колонки PDF от строки с текстом A до строки с текстом B (включительно), может переходить на следующую колонку/страницу.
   python3 span.py p38 "18..." "Черные сдались" out.png"""
import sys
from PIL import Image
p, a, b, out = int(sys.argv[1].lstrip("p")), sys.argv[2], sys.argv[3], sys.argv[4]
seq = []
for q in (p, p + 1):
    L = [l.rstrip("\n").split("\t") for l in open(f"work/ocr/p{q:03d}.tsv", encoding="utf-8") if l.startswith("L")]
    L.sort(key=lambda f: (float(f[1]) >= 0.47 and float(f[3]) < 0.62, float(f[2])))
    seq += [(q, f) for f in L]
i = next(k for k, (q, f) in enumerate(seq) if a in f[5])
j = next(k for k, (q, f) in enumerate(seq) if k >= i and b in f[5])
parts, cur = [], None
for q, f in seq[i:j + 1]:
    x, y, h = float(f[1]), float(f[2]), float(f[4]); col = 1 if x >= 0.47 and float(f[3]) < 0.62 else 0
    key = (q, col)
    if cur and cur[0] == key: cur[2] = y + h
    else: cur = [key, y, y + h]; parts.append(cur)
ims = []
for (q, col), y0, y1 in parts:
    im = Image.open(f"work/pages/p{q:03d}.png"); W, H = im.size
    c = im.crop((int(col * 0.47 * W), int((y0 - 0.005) * H), int((0.5 + col * 0.5) * W), int((y1 + 0.006) * H)))
    ims.append(c.resize((c.size[0] * 2 // 3, c.size[1] * 2 // 3)))
s = Image.new("L", (max(i.size[0] for i in ims), sum(i.size[1] + 6 for i in ims)), 255); y = 0
for c in ims: s.paste(c, (0, y)); y += c.size[1] + 6
s.save(out); print(out, s.size)
