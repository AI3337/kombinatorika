"""Хвост партии из PDF одной картинкой: от строки с ходом до «сдались/Ничья/выиграли» или следующей шапки.
   python3 tail.py 27 23. out.png      (ход «23...» — ход чёрных)"""
import sys, re, glob
from PIL import Image
game, mv, out = sys.argv[1:4]
seq = []                     # (стр, колонка, строка) по порядку чтения
for fn in sorted(glob.glob("work/ocr/p*.tsv")):
    q = int(fn[-7:-4])
    L = [l.rstrip("\n").split("\t") for l in open(fn, encoding="utf-8") if l.startswith("L")]
    full = sorted([f for f in L if float(f[3]) >= 0.62], key=lambda f: float(f[2]))
    left = sorted([f for f in L if float(f[3]) < 0.62 and float(f[1]) < 0.47], key=lambda f: float(f[2]))
    right = sorted([f for f in L if float(f[3]) < 0.62 and float(f[1]) >= 0.47], key=lambda f: float(f[2]))
    seq += [(q, 2, f) for f in full if float(f[2]) < 0.12] + [(q, 0, f) for f in left] + [(q, 1, f) for f in right] + \
           [(q, 2, f) for f in full if float(f[2]) >= 0.12]
head = next(k for k, (q, c, f) in enumerate(seq) if re.match(r"^%s\.\s+[А-ЯЁA-Z]" % game, f[5]) and re.search(r"\s[–-]\s", f[5]))
num = re.match(r"\d+", mv).group(0); black = "..." in mv
pats = ([re.compile(r"(?<![\d.])%s\s*\.\s*[.…]" % num)] if black else []) + [re.compile(r"(?<![\d.])%s\s*\.\s*[^.\s…]" % num)]
import numpy as np
def ink(q, f):
    im = Image.open(f"work/pages/p{q:03d}.png"); W, H = im.size
    x, y, w_, h = map(float, f[1:5])
    return (np.array(im.crop((int(x * W), int(y * H), int((x + w_) * W), int((y + h) * H))).convert("L")) < 128).mean()
nxt = next((k for k in range(head + 1, len(seq)) if re.match(r"^\d{1,3}\.\s+[А-ЯЁA-Z].*\s[–-]\s", seq[k][2][5])), len(seq))
i = None
for pat in pats:
    c = [k for k in range(head, nxt) if pat.search(seq[k][2][5])]
    if c: i = max(c, key=lambda k: ink(seq[k][0], seq[k][2]) * (1.12 if k == c[0] else 1)); break
j = next(k for k in range(i, i + 200) if re.search(r"сдал|Ничья|ничья\.|выиграли", seq[k][2][5])
         or re.match(r"^\d{1,3}\.\s+[А-ЯЁA-Z].*\s[–-]\s", seq[k][2][5]))
parts, cur = [], None
for q, col, f in seq[i:j + 1]:
    y, h = float(f[2]), float(f[4])
    if cur and cur[0] == (q, col): cur[2] = y + h
    else: cur = [(q, col), y, y + h]; parts.append(cur)
ims = []
for (q, col), y0, y1 in parts:
    im = Image.open(f"work/pages/p{q:03d}.png"); W, H = im.size
    x0, x1 = {0: (0, 0.5), 1: (0.47, 1), 2: (0, 1)}[col]
    c = im.crop((int(x0 * W), int((y0 - 0.005) * H), int(x1 * W), int((y1 + 0.006) * H)))
    ims.append(c.resize((c.size[0] * 2 // 3, c.size[1] * 2 // 3)))
s = Image.new("L", (max(c.size[0] for c in ims), sum(c.size[1] + 6 for c in ims)), 255); y = 0
for c in ims: s.paste(c, (0, y)); y += c.size[1] + 6
s.save(out); print(out, s.size, "стр.", parts[0][0][0])
