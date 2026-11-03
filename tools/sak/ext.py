"""Внешняя расшифровка глав (work/ext/*.md, фигуры K Q R B N) -> fix_ext.json.

Главная линия внешнего файла — жирные абзацы, которые начинаются с «**» и продолжают партию
с ожидаемого полухода (позиция — наша, из work/align_noext.json). Каждый ход проверяется
python-chess; цепочка обрывается на первом нелегальном ходе. Жирные ходы нашей главной линии,
расходящиеся с проверенной цепочкой на том же полуходе, заменяются.
Запуск: NO_EXT=1 ALIGN_OUT=work/align_noext.json python3 align.py; python3 ext.py; align.py; build.py"""
import json, re, os, glob, chess
os.environ["NO_EXT"] = "1"
from lib import read, norm, TOK
A = json.load(open("work/align_noext.json"))
G = {g["title"].split(".")[0]: g for g in A["games"]}
MV = re.compile(r"(\d+)(\.\.\.|\.)|((?:[KQRBN][a-h1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8]|[a-h][1-8]|O-O(?:-O)?)(?:=[QRBN])?[+#X]?)")
core = lambda s: re.sub(r"[+#!?]", "", s).replace("0-0-0", "O-O-O").replace("0-0", "O-O")
ply_of = lambda bd: (bd.fullmove_number - 1) * 2 + (0 if bd.turn else 1)

def toks(s):
    ply, out = None, []
    for m in MV.finditer(s):
        if m.group(1): ply = (int(m.group(1)) - 1) * 2 + (0 if m.group(2) == "." else 1)
        elif ply is not None: out.append((ply, m.group(3).replace("X", "#"))); ply += 1
    return out

def parse(bd, s, nxt=()):
    """SAN; при неоднозначности (Rd2 при двух ладьях) — та фигура, после хода которой проходят следующие ходы"""
    try: return bd.parse_san(s.rstrip("+#"))
    except chess.AmbiguousMoveError:
        best = None
        for mv in bd.legal_moves:
            if bd.san(mv)[0] != s[0] or chess.square_name(mv.to_square) != re.sub(r"[+#=QRBN]+$", "", s)[-2:]: continue
            b2, k = bd.copy(), 0
            b2.push(mv)
            for x in nxt:
                m2 = parse(b2, x)
                if m2 is None: break
                b2.push(m2); k += 1
            if best is None or k > best[0]: best = (k, mv)
        return best and best[1]
    except ValueError: return None
SKIP = {"241", "148"}   # 241: вариант выдан за ход партии (правка в fix.json); 148: их ходы хуже наших

def their_line(sec, bd):
    """[(ply, san)] главной линии внешнего файла от позиции bd"""
    exp, out = ply_of(bd), []
    for para in sec.split("\n\n"):
        if not para.startswith("**"): continue
        for seg in re.findall(r"\*\*(.+?)\*\*", para):
            t = toks(seg)
            if not t or t[0][0] != exp: continue
            for i, (p, s) in enumerate(t):
                mv = parse(bd, s, [x for _, x in t[i + 1:i + 14]])
                if mv is None: return out
                out.append((p, bd.san(mv))); bd.push(mv); exp += 1
    return out

SQ = re.compile(r"(?<![\w.])((?:[KQRBN][a-h1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8]|[a-h][1-8]|O-O(?:-O)?|0-0(?:-0)?)(?:=[QRBN])?(?:[+#X](?!-))?)(?![\w])")
letters = lambda s: re.sub(r"[^а-яё]", "", s.lower())

def comments(report):
    """абзацы прозы: та же речь (буквы совпадают > 75%) и столько же ходов — берём ходы внешнего файла, текст оставляем наш"""
    import difflib
    out = []
    for fn in sorted(glob.glob("work/ext/*.md")):
        for sec in re.split(r"\n## ", open(fn, encoding="utf-8").read())[1:]:
            n = sec.split(".")[0]; g = G.get(n)
            if not n.isdigit() or not g: continue
            t = read(g["file"]); m = re.search(r"^### %s\..*$" % n, t, re.M)
            e = t.find("\n### ", m.end()); s = t[m.start():e if e > 0 else len(t)]
            cut = s.find("**Дополнительные"); s = s if cut < 0 else s[:cut]
            theirs = [p for p in sec.split("\n\n")[1:] if not p.startswith("**") and len(letters(p)) > 15]
            k = 0
            for p in s.split("\n\n")[1:]:
                if p.startswith("**") or "Доска" in p or len(letters(p)) < 15 or not theirs: continue
                r, q = max((difflib.SequenceMatcher(None, letters(p), letters(q)).ratio(), q) for q in theirs)
                a, b = list(SQ.finditer(p)), [x.group(1).replace("X", "#") for x in SQ.finditer(q)]
                if r < 0.75 or not a or len(a) != len(b): continue
                new, last = [], 0
                for x, y in zip(a, b):
                    new.append(p[last:x.start(1)] + y); last = x.end(1)
                new.append(p[last:]); new = "".join(new)
                if new != p:
                    out.append({"game": n, "from": p, "to": new, "pdf": "внешняя расшифровка, ходы в комментарии"}); k += 1
            if k: report.append(f"{n}: комментариев с исправленными ходами {k}")
    return out

def main():
    patches, report = [], []
    for fn in sorted(glob.glob("work/ext/*.md")):
        ext = open(fn, encoding="utf-8").read()
        for sec in re.split(r"\n## ", ext)[1:]:
            n = sec.split(".")[0]
            g = G.get(n)
            if not n.isdigit() or not g or not g["line"]: report.append(f"{n}: нет нашей стартовой позиции"); continue
            if not g["bad"] or n in SKIP: continue                      # наша линия чистая — не трогаем
            first = next((t for para in sec.split("\n\n") if para.startswith("**")
                          for t in [toks(para)] if t), None)
            if not first: report.append(f"{n}: нет ходов"); continue
            # позиция у первого хода внешнего файла — по нашей линии
            bd = chess.Board(g["line"][0][1])
            for x in g["line"][1:]:
                if ply_of(bd) >= first[0][0] or x[0] != "mv": break
                bd.push(chess.Move.from_uci(x[2]))
            if ply_of(bd) != first[0][0]: report.append(f"{n}: не дошли до полухода {first[0][0]}"); continue
            line = dict(their_line(sec, bd))
            t = read(g["file"])
            m = re.search(r"^### %s\..*$" % n, t, re.M)
            end = t.find("\n### ", m.end()); end = len(t) if end < 0 else end
            s = t[m.start():end]; cut = s.find("**Дополнительные"); s = s if cut < 0 else s[:cut]
            exp, nfix = first[0][0], 0
            for bm in re.finditer(r"\*\*(.+?)\*\*", s):
                seg = bm.group(1); tk = list(TOK.finditer(seg))
                if not tk or not tk[0].group(1): continue
                p = (int(tk[0].group(1)) - 1) * 2 + (0 if tk[0].group(2) == "." else 1)
                if p != exp: continue
                new, last, ply = [], 0, p
                for k in tk:
                    if k.group(1): ply = (int(k.group(1)) - 1) * 2 + (0 if k.group(2) == "." else 1)
                    i = 3 if k.group(3) else 4
                    if ply in line and core(norm(k.group(i))) != core(line[ply]):
                        new.append(seg[last:k.start(i)] + line[ply].rstrip("+#")); last = k.end(i); nfix += 1
                    ply += 1
                new.append(seg[last:]); exp = ply
                fixed = "".join(new)
                if fixed != seg:
                    patches.append({"game": n, "from": "**" + seg + "**", "to": "**" + fixed + "**", "pdf": "внешняя расшифровка " + os.path.basename(fn)})
            report.append(f"{n}: их цепочка {len(line)} ходов, заменено {nfix}")
    patches += comments(report)
    json.dump({"patches": patches}, open("fix_ext.json", "w"), ensure_ascii=False, indent=1)
    print("\n".join(report)); print("правок:", len(patches))

if __name__ == "__main__":
    main()
