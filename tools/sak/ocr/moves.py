"""Ходы из PDF (OCR macOS + значки фигур по образцам) -> правки ходов в .md.

1. Страница: строки OCR по колонкам, у слова со значком фигуры — буква фигуры
   (3 ближайших подписанных значка; далеко от всех — «?», пешка — без буквы).
2. Поток книги режется на партии по шапкам «136. М. Ботвинник – …».
3. Ходы партии в .md и в PDF выравниваются по полю назначения (difflib).
   Совпало поле, но другая фигура — в .md ставится фигура из книги; в замене
   одинаковой длины другое поле — поле из книги.
4. Пишет srcfix/*.md (исправленный текст) и work/ocrfix.json (что поменяно).
   Лучше ли стало — решает align.py по каждой партии (см. choose в align).

Запуск: python3 ocr/moves.py (из tools/sak)"""
import os, re, json, glob, difflib
import numpy as np
from PIL import Image
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import sys; sys.path.insert(0, ".")
from ocr.glyphs import glyph_of
from lib import files
from sklearn.neighbors import KNeighborsClassifier

ref = np.load("ocr/glyph_ref.npz")
KNN = KNeighborsClassifier(3).fit(ref["X"].astype(np.float32), ref["Y"])
FAR = 140.0          # квадрат расстояния до ближайшего образца, дальше — не знаем
GL = re.compile(r"([^a-hxх\s.,;:()\-–—]+)(?=x?[a-h][1-8])")

def page_text(p):
    cache = f"work/pdftext/p{p:03d}.txt"
    if os.path.exists(cache): return open(cache, encoding="utf-8").read().split("\n")
    os.makedirs("work/pdftext", exist_ok=True)
    txt = page_text_(p)
    open(cache, "w", encoding="utf-8").write("\n".join(txt))
    return txt

def page_text_(p):
    fn = f"work/ocr/p{p:03d}.tsv"
    if not os.path.exists(fn): return []
    im = Image.open(f"work/pages/p{p:03d}.png"); W, H = im.size
    lines, fixes = [], {}
    for l in open(fn, encoding="utf-8"):
        f = l.rstrip("\n").split("\t")
        if f[0] == "L": lines.append([float(f[1]), float(f[2]), float(f[3]), f[5]]); continue
        if len(f) < 7: continue
        g, _ = glyph_of(im, W, H, f)
        word, after = f[5], int(f[6])
        if g is None: letter = "?"
        else:
            d, _ = KNN.kneighbors([g.ravel()], 1)
            letter = KNN.predict([g.ravel()])[0] if d[0][0] ** 2 < FAR else "?"
        ms = [m for m in GL.finditer(word) if len(word) - m.end() == after]
        if not ms: continue
        m = ms[-1]
        fixes.setdefault(word, word[:m.start()] + ("" if letter == "-" else letter) + word[m.end():])
    # колонки: строки во всю ширину делят страницу на полосы; в полосе — левая, потом правая
    lines.sort(key=lambda r: r[1])
    out, band = [], []
    def flush():
        out.extend(sorted([r for r in band if r[0] < 0.47], key=lambda r: r[1]) +
                   sorted([r for r in band if r[0] >= 0.47], key=lambda r: r[1]))
        band.clear()
    for r in lines:
        if r[2] > 0.62: flush(); out.append(r)
        else: band.append(r)
    flush()
    txt = []
    for r in out:
        s = r[3]
        for w, c in fixes.items(): s = s.replace(w, c)
        txt.append(s)
    return txt

MV = re.compile(r"(?:(\d{1,3})\s*(\.\.\.|…|\.)\s*)?([KQRBN?]?)([a-h]?[1-8]?)(x?)([a-h][1-8])(=?[QRBN])?|(0-0-0|0-0|O-O-O|O-O)")
def tokens(s):
    out = []
    s = s.replace("х", "x")
    for m in MV.finditer(s):
        if m.group(8): out.append({"dest": m.group(8).replace("0", "O"), "pc": "K", "cap": "", "num": None, "a": m.start(), "b": m.end(), "pre": ""}); continue
        num = m.group(1)
        out.append({"dest": m.group(6), "pc": m.group(3), "dis": m.group(4), "cap": m.group(5), "num": num,
                    "a": m.start(3), "b": m.end(6)})
    return out

def game_streams():
    """номер партии -> текст ходов из PDF"""
    allt = []
    for p in range(5, 360): allt += [(p, s) for s in page_text(p)]
    heads = [(i, int(m.group(1))) for i, (p, s) in enumerate(allt)
             if (m := re.match(r"^(\d{1,3})\.\s+[А-ЯЁA-Z]", s)) and int(m.group(1)) <= 248 and re.search(r"\s[–-]\s", s)]
    # шапки идут по возрастанию: выкидываем выбросы (номера ходов «12. Б…»)
    good, last = [], 0
    for i, n in heads:
        if n > last and n - last <= 3: good.append((i, n)); last = n
    res = {}
    for k, (i, n) in enumerate(good):
        j = good[k + 1][0] if k + 1 < len(good) else len(allt)
        res[n] = " ".join(s for _, s in allt[i:j])
    return res

AL = None
def score(n, body):
    """(ходов главной линии сыграно, досок совпало) — проверщик align.py на одной партии"""
    import chess
    global AL
    if AL is None:
        import align as AL_; AL = AL_
    g = next((x for x in AL.games if x["title"].split(".")[0] == str(n)), None)
    ev = AL.mainline(body)
    if g is None: return (0, 0)
    if g["start"] == 0 or g["start"] is None and any(e[0] == "m" and e[1] == 1 for e in ev[:3]):
        r = AL.simulate(chess.Board(), ev, 1)
    elif g["start"]:
        bi = next((i for i, e in enumerate(ev) if e[0] == "b"), None)
        if bi is None: return (0, 0)
        side = next((e[2] for e in ev[bi:] if e[0] == "m" and e[2]), "w")
        num = next((e[1] for e in ev[bi:] if e[0] == "m" and e[1]), 1)
        bd = AL.board_from(AL.B[g["start"]], side); bd.fullmove_number = num
        r = AL.simulate(bd, ev[bi + 1:], g["start"] + 1)
    else: return (0, 0)
    return (r[1], len(r[0])) + links(n, body)

BD = None
def links(n, body):
    """(связано, -не связано) движком сайта на тексте одной партии"""
    global BD
    if BD is None:
        import build as BD_; BD = BD_
    items = BD.load(["## Глава 0. x\n### %d. x\n" % n + body])
    ch = BD.chapters(items)
    if not ch: return (0, 0)
    blocks, t, L = BD.render(ch[0])
    ln = sum(1 for b in blocks for s in (b.get("s") or []) if isinstance(s, dict))
    return (ln, -len(L.bad))

def main():
    G = game_streams()
    os.makedirs("srcfix", exist_ok=True)
    log = {}
    for f in files():
        t = open(f, encoding="utf-8").read()
        parts = re.split(r"(?m)^(### \d+\..*)$", t)
        for i in range(1, len(parts), 2):
            n = int(re.match(r"### (\d+)", parts[i]).group(1))
            body = parts[i + 1]
            # «Дополнительные материалы» и дальше не трогаем
            cut = body.find("**Дополнительные материалы"); tail = body[cut:] if cut >= 0 else ""
            body = body[:cut] if cut >= 0 else body
            if n not in G: continue
            A, Bt = tokens(body), tokens(G[n])
            sm = difflib.SequenceMatcher(None, [x["dest"] for x in A], [x["dest"] for x in Bt], autojunk=False)
            edits = []
            for op, a0, a1, b0, b1 in sm.get_opcodes():
                if op == "equal":
                    for x, y in zip(A[a0:a1], Bt[b0:b1]):
                        if y["pc"] in ("K", "Q", "R", "B", "N") and x["pc"] != y["pc"] and x["dest"][0] != "O":
                            edits.append((x, y["pc"] + x.get("dis", "") + x["cap"] + x["dest"]))
                elif op == "replace" and a1 - a0 == b1 - b0 and a1 - a0 <= 3:
                    # другое поле: ход целиком из книги (фигура из книги, если распознана)
                    for x, y in zip(A[a0:a1], Bt[b0:b1]):
                        if x["dest"][0] == "O" or y["dest"][0] == "O": continue
                        pc = y["pc"] if y["pc"] in ("K", "Q", "R", "B", "N") else x["pc"]
                        edits.append((x, pc + x.get("dis", "") + y["cap"] + y["dest"]))
            if not edits: continue
            # по одной: правка остаётся, если партия проходит ходами не хуже
            edits.sort(key=lambda e: e[0]["a"]); shift = 0; cur = score(n, body)
            for x, new in edits:
                a, b = x["a"] + shift, x["b"] + shift
                old = body[a:b]
                cand = body[:a] + new + body[b:]
                sc = score(n, cand)
                if sc > cur:
                    log.setdefault(str(n), []).append([old, new]); body = cand; cur = sc; shift += len(new) - len(old)
            parts[i + 1] = body + tail
        open("srcfix/" + os.path.basename(f), "w", encoding="utf-8").write("".join(parts))
    json.dump(log, open("work/ocrfix.json", "w"), ensure_ascii=False, indent=0)
    print("партий из PDF:", len(G), "| партий с правками:", len(log), "| правок:", sum(len(v) for v in log.values()))

if __name__ == "__main__":
    main()
