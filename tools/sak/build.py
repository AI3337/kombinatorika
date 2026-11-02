"""Сакаев, том 1: .md (src/*_*.md) + доски (src/boards.txt) -> sak.js для сайта.

Общая часть (привязка ходов к позициям, деревья вариантов) — dvor/06_parse.py,
как у Яковлева. Позиция каждой «Доски N» — из work/align.json (align.py):
сначала позиция, до которой дошли ходы партии, потом доска файла, найденная
по содержанию (номера в .md сбиты), потом доска файла с соседним сдвигом.
Доски файла, которых нет в .md, но которые совпали с позицией в ходах партии,
вставляются после абзаца с этим ходом (EXTRA).

Пропускается: «Дополнительные материалы», мусор после обрыва файла
(пустые заголовки). Курсивная строка — тематический подзаголовок.
Абзац комментария получает "a" — последний ход главной линии перед ним
(на сайте подсвечивается, когда стоим на этом ходу).

Запуск: python3 align.py && python3 build.py (из tools/sak)"""
import json, re, os, sys, importlib.util
import chess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv.append("--no-main")
spec = importlib.util.spec_from_file_location("P", os.path.join(HERE, "../dvor/06_parse.py"))
P = importlib.util.module_from_spec(spec)
cwd = os.getcwd(); os.chdir(os.path.join(HERE, "../dvor")); spec.loader.exec_module(P); os.chdir(cwd)
os.chdir(HERE)
from lib import boards, files, agnostic, read
_mm = P.match_move
def match_move(board, tok):
    """движок + путаница букв фигур в распознанном тексте"""
    mv = _mm(board, tok)
    if mv is None:
        mv = agnostic(board, tok)
        if mv is not None: FIXED[0] += 1
    return mv
FIXED = [0]
P.match_move = match_move

B = boards()
A = json.load(open("work/align.json"))
FIX = json.load(open("fix.json")) if os.path.exists("fix.json") else {}
def extra_boards():
    """доски файла без пары в .md, совпавшие с позицией главной линии какой-то партии"""
    used = {v for g in A["games"] for v in g["boards"].values()}
    seen = set()
    for g in A["games"]:
        bd = None
        for x in g["line"]:
            if x[0] == "root": bd = chess.Board(x[1])
            elif x[0] == "mv" and bd: bd.push_uci(x[2]); seen.add(bd.board_fen())
    return [j for j in B if j not in used and B[j].split()[0] in seen]
EXTRA = extra_boards()

# ---------- позиция каждой метки «Доска N» ----------
def positions():
    pos, order, pairs = {}, [], []
    for g in A["games"]:
        root = None
        for x in g["line"]:
            if x[0] == "root": root = x[1]
            elif x[0] == "at": pos.setdefault(x[1], (x[2].split()[0], x[2].split()[1], "ходы"))
            elif x[0] == "b":
                if x[1] not in pos and root and root.split()[0] == B[x[2]].split()[0]:
                    pos[x[1]] = (root.split()[0], root.split()[1], "файл")
        for md in g["mdboards"]:
            order.append(md)
            j = g["boards"].get(str(md))
            if j: pairs.append((len(order) - 1, md, j))
            if j and md not in pos: pos[md] = (B[j].split()[0], None, "файл")
    # не сопоставленные — доска файла с ближайшим известным сдвигом
    for i, md in enumerate(order):
        if md in pos: continue
        near = min(pairs, key=lambda p: abs(p[0] - i))
        j = md + (near[2] - near[1])
        pos[md] = (B[j].split()[0], None, "сдвиг") if j in B else (None, None, "нет")
    for k, v in FIX.get("boards", {}).items():
        pos[int(k)] = (v.split()[0], v.split()[1] if " " in v else None, "правка")
    return pos
POS = positions()

# ---------- чтение .md ----------
MV = r"(?:[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h](?:x[a-h])?[1-8](?:=?[QRBN])?|0-0-0|0-0|O-O-O|O-O)"
def clean(s):
    s = s.replace("\\[", "[").replace("\\]", "]").replace("\\*", "*").replace("\\-", "-").replace("\\.", ".")
    s = re.sub(r"(\d)\.\s+(?=[KQRBNa-h0O])", r"\1.", s)            # «19. b4» -> «19.b4»
    s = re.sub(r"(\d)\s*\.\.\.\s+(?=[KQRBNa-h0O])", r"\1...", s)
    s = re.sub(r"(\d)…(?=[KQRBNa-h0O])", r"\1...", s)
    return s.strip()
def lead_bold(line):
    """абзац, начатый ожидаемым ходом партии, — продолжение главной линии: начальную цепочку ходов в жирное"""
    m = re.match(r"(?:\s*(?:\d{1,3}\.(?:\.\.)?)?\s*" + MV + r"[+#]*[!?]*\s*)+", line)
    if not m: return line
    k = m.end()
    while k > 0 and line[k - 1] == " ": k -= 1
    return "**" + line[:k] + "**" + line[k:]
def plies(text):
    """номер/сторона последнего хода в тексте ходов (жирной цепочке)"""
    last = None
    for m in re.finditer(r"(\d{1,3})(\.\.\.|\.)" + MV + r"|(?<![\w.])" + MV, text):
        if m.group(1): last = (int(m.group(1)), "w" if m.group(2) == "." else "b")
        elif last: last = (last[0], "b") if last[1] == "w" else (last[0] + 1, "w")
    return last

def load(texts=None):
    items = []          # (kind, payload)
    part = None
    for src in (texts if texts is not None else [read(f) for f in files()]):
        skip = False
        for raw in src.split("\n"):
            l = raw.strip()
            if not l: continue
            if re.fullmatch(r"#{1,3}\s*", l): break                  # обрыв файла: дальше мусор
            if l.startswith("# "): part = l[2:].strip().capitalize(); skip = False; continue
            m = re.match(r"## Глава (\d+)\.\s*(.*)", l)
            if m:
                items.append(("chapter", (int(m.group(1)), clean(m.group(2)), part))); skip = False; continue
            m = re.match(r"### (\d+)\.\s*(.*)", l)
            if m:
                items.append(("sec", (m.group(1), clean(m.group(2))))); skip = False; nxt_game = True; continue
            if l.startswith("**Дополнительные материалы"): skip = True; continue
            if skip: continue
            l = clean(l)
            if items and items[-1][0] == "sec" and not re.search(r"\d+\.", l) and len(l) < 80 and "Доска" not in l:
                st = len(re.findall(r"\*", l)); place = l.replace("*", "").strip()
                items.append(("game", place + (" | " + "★" * st if st else ""))); continue
            m = re.fullmatch(r"\[?\s*Доска\s*(\d+)\s*\]?", l, re.I)
            if m: items.append(("diag", int(m.group(1)))); continue
            if re.fullmatch(r"\*[^*].*[^*]\*", l): items.append(("u", l.strip("*"))); continue
            if "Примечание" in l: items.append(("note", l.strip("*()"))); continue
            items.append(("p", l))
    return items

def pick_roots(items):
    """доски, позиция которых не из ходов: перебор досок файла рядом с номером (±10),
       берём ту, к которой привязывается больше ходов следующего текста"""
    n_fix = 0
    for i, (k, pl) in enumerate(items):
        if k != "diag" or POS.get(pl, (0, 0, ""))[2] in ("ходы", "правка"): continue
        nxt = []
        for k2, p2 in items[i + 1:]:
            if k2 in ("diag", "sec", "chapter"): break
            if k2 == "p": nxt.append(p2)
        text = "\n".join(nxt)
        if not re.search(r"\d+\.", text): continue
        base = POS[pl][0]
        cands = [base] + [B[j].split()[0] for j in range(pl - 10, pl + 11) if j in B]
        best = None
        for c in dict.fromkeys(cands):
            try:
                fen = P.best_root(c, None, text, repair=False)
                sc = P.links_from(fen, text)
            except Exception: continue
            if best is None or sc > best[0]: best = (sc, fen)
        if best and best[0] < 3:
            try:
                fen = P.best_root(base, None, text, repair=True); sc = P.links_from(fen, text)
                if sc > best[0]: best = (sc, fen)
            except Exception: pass
        if best and best[1].split()[0] != base: n_fix += 1
        if best: POS[pl] = (best[1].split()[0], best[1].split()[1], "подбор")
    return n_fix

def chapters(items):
    out = []
    for k, pl in items:
        if k == "chapter":
            out.append({"n": pl[0], "title": pl[1], "part": pl[2], "items": []}); continue
        if out: out[-1]["items"].append((k, pl))
    return out

# ---------- сборка главы ----------
def render(ch):
    t = P.Tree(); L = P.Linker(t)
    out, run, last = [], [], None
    def go():
        if run: out.extend(P.render(run, L)); run.clear()
    for k, pl in ch["items"]:
        if k == "sec":
            go(); L.scope = []; L.cur = None; L.main = None; L.stack = []; last = None
            out.append({"t": "s", "n": pl[0], "x": pl[1]}); continue
        if k == "u": go(); out.append({"t": "u", "x": pl}); continue
        if k == "note": go(); out.append({"t": "p", "x": pl, "r": 1}); continue
        if k == "game": run.append({"kind": "game", "pl": pl.split(" | ")[0] + (" | " + pl.split(" | ")[1] if " | " in pl else "")}); continue
        if k == "diag":
            placement, turn, src = POS.get(pl, (None, None, "нет"))
            run.append({"kind": "diag", "pl": {"n": str(pl), "turn": turn, "small": False, "fen": placement, "src": f"доска {pl}"}})
            continue
        # абзац: если начат ожидаемым ходом партии — это главная линия
        if "**" not in pl[:3] and last and re.match(r"\d{1,3}\.", pl):
            m = re.match(r"(\d{1,3})(\.\.\.|\.)", pl)
            want = (last[0], "b") if last[1] == "w" else (last[0] + 1, "w")
            if (int(m.group(1)), "w" if m.group(2) == "." else "b") == want: pl = lead_bold(pl)
        for seg in re.findall(r"\*\*(.+?)\*\*", pl):
            p2 = plies(seg)
            if p2 and not seg.startswith("("): last = p2
        run.append({"kind": "p", "pl": pl})
    go()
    return out, t, L

FIG = {chess.KNIGHT: "N", chess.BISHOP: "B", chess.ROOK: "R", chess.QUEEN: "Q", chess.KING: "K"}
def fix_text(blocks, t):
    """ход, у которого в тексте не та фигура, показываем записью с доски (знаки !? сохраняем)"""
    n = 0
    for b in blocks:
        for x in b.get("s") or []:
            if not isinstance(x, dict) or x.get("w"): continue
            san = t.nodes[x["m"]]["san"]
            m = re.match(r"^(\d+\s*\.(?:\.\.)?\s*)?(.*?)([!?]*)$", x["s"])
            pre, mv, suf = m.group(1) or "", m.group(2), m.group(3)
            core = lambda s: re.sub(r"[+#]", "", s).replace("0", "O")
            if core(mv) != core(san) and core(mv).replace("x", "") != core(san).replace("x", ""):
                x["s"] = pre + san + suf; n += 1
    return n

def anchor(blocks):
    """комментарий -> последний ход главной линии перед ним; доски EXTRA после своего хода"""
    last = None
    for b in blocks:
        if b["t"] == "s": last = None
        if b["t"] == "d" and b.get("n") is not None: last = b["n"]
        if b["t"] != "p" or not b.get("s"): continue
        mains = [x["m"] for x in b["s"] if isinstance(x, dict) and x.get("b")]
        if mains: last = mains[-1]
        elif last is not None: b["a"] = last
    return blocks

INSERTED = set()
def extra(blocks, t):
    want = {B[j].split()[0]: j for j in EXTRA}
    out = []
    for b in blocks:
        out.append(b)
        if b["t"] != "p" or not b.get("s"): continue
        mains = [x["m"] for x in b["s"] if isinstance(x, dict) and x.get("b")]
        if mains and t.fen(mains[-1]).split()[0] in want:
            j = want.pop(t.fen(mains[-1]).split()[0]); INSERTED.add(j)
            out.append({"t": "d", "n": mains[-1], "small": False, "extra": j})
    return out, list(want.values())

def main():
    items = load()
    print("вставки EXTRA:", EXTRA, flush=True)
    print("досок с подобранной позицией:", pick_roots(items), flush=True)
    res, tot_l, tot_b, miss, lost = [], 0, 0, [], []
    for ch in chapters(items):
        blocks, t, L = render(ch)
        blocks, left = extra(blocks, t)
        lost += left
        nfix = fix_text(blocks, t)
        blocks = anchor(blocks)
        miss += [b["miss"] for b in blocks if b["t"] == "d" and "miss" in b]
        linked = sum(1 for b in blocks for s in (b.get("s") or []) if isinstance(s, dict))
        tot_l += linked; tot_b += len(L.bad)
        secs = [b for b in blocks if b["t"] == "s"]
        diags = [b for b in blocks if b["t"] == "d" and b.get("n") is not None]
        res.append({"n": ch["n"], "title": ch["title"], "part": ch["part"], "intro": blocks,
                    "roots": t.roots, "secs": len(secs), "diags": len(diags),
                    "nodes": [[x["parent"], x["uci"], x["san"], 1 if x["main"] else 0] + ([x["base"]] if x.get("threat") else [])
                              for x in t.nodes]})
        open(f"work/unlinked_{ch['n']:02d}.txt", "w").write("\n".join(L.bad))
        print(f"гл.{ch['n']:2d} партий {len(secs):2d} досок {len(diags):2d} связано {linked:4d} не связано {len(L.bad):3d}")
    book = {"id": "sak1", "title": "Том 1", "author": "Константин Сакаев", "chapters": res}
    js = "/* Константин Сакаев, том 1: из .md и досок (tools/sak). Генерируется build.py */\n"
    js += "window.SAK = " + json.dumps([book], ensure_ascii=False, separators=(",", ":")) + ";\n"
    open(os.path.join(HERE, "../../sak.js"), "w", encoding="utf-8").write(js)
    print(f"итого связано {tot_l}, не связано {tot_b} ({100 * tot_b / max(1, tot_l + tot_b):.1f}%)",
          "| доски без позиции:", miss, "| EXTRA не вставлены:", sorted(set(EXTRA) - INSERTED))

if __name__ == "__main__":
    main()
