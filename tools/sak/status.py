"""Где рвётся главная линия партии: строка .md и строки PDF с тем же номером хода.
   python3 status.py 5 9 15 …   (после align.py)"""
import sys, json, re, glob
from lib import read
import os
A = json.load(open(os.environ.get("ALIGN_OUT", "work/align.json")))
pdf = {int(f[-7:-4]): open(f, encoding="utf-8").read().split("\n") for f in glob.glob("work/pdftext/p*.txt")}
heads = {}
for p in sorted(pdf):
    for s in pdf[p]:
        m = re.match(r"^(\d{1,3})\.\s+[А-ЯЁA-Z]", s)
        if m and re.search(r"\s[–-]\s", s): heads.setdefault(int(m.group(1)), p)
for n in sys.argv[1:]:
    g = next(x for x in A["games"] if x["title"].split(".")[0] == n)
    if not g["bad"]:
        print(f"№{n}: чисто, сыграно {g['played']}" + ("" if g["start"] is not None else ", СТАРТ НЕ НАЙДЕН")); continue
    (num, side), tok, fen = g["bad"][0]
    t = read(g["file"]); sec = t[t.index(f"### {n}."):]; sec = sec[:sec.find("\n### ", 5)]
    key = f"{num}." if side == "w" else f"{num}..."
    md = [l[:150] for l in sec.split("\n") if key in l and l.startswith("**")][:2]
    p0 = heads.get(int(n), 0)
    pl = [f"p{p}: {s[:90]}" for p in range(p0, p0 + 5) if p in pdf for s in pdf[p] if re.search(r"(?<![\d.])%d\s*\." % num, s)][:4]
    print(f"№{n}: обрыв {key}{tok} | {fen.split()[0]}\n  md: " + "\n  md: ".join(md) + "\n  pdf: " + "\n  pdf: ".join(pl))
