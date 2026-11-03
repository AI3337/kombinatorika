"""Партии из базы 365chess (work/found.txt, строки «N|gid|совпало/всего|строк|шапка|ходы SAN») -> fix_db.json.

Партия из базы принимается, только если она проходит через стартовую позицию книги
(доска файла, с которой начат фрагмент) или, для партии с 1-го хода, совпадают первые 6 ходов.
Тогда:
  * жирные ходы главной линии, расходящиеся с базой на том же полуходе, заменяются записью базы
    (знаки !? книги сохраняются);
  * фрагменту перед первой доской добавляется абзац «Начало партии» с ходами от 1-го —
    дерево партии начинается с первого хода.
Правки — обычные "patches" (lib.read), файл fix_db.json.
Запуск: python3 db.py (из tools/sak), потом align.py и build.py."""
import json, re, os
os.environ["NO_DB"] = "1"          # читаем текст без прошлых правок базы
import chess
from lib import read, boards, norm, TOK
B = boards()
A = json.load(open("work/align.json"))
G = {g["title"].split(".")[0]: g for g in A["games"]}

def replay(sans):
    bd = chess.Board(); out = []
    for s in sans:
        try: mv = bd.parse_san(s)
        except ValueError: break
        out.append((bd.san(mv), mv)); bd.push(mv)
    return out

def plies_from(line_moves):
    """позиции после каждого полухода партии базы: [(ply, placement)]"""
    bd = chess.Board(); res = [(0, bd.board_fen())]
    for i, (s, mv) in enumerate(line_moves):
        bd.push(mv); res.append((i + 1, bd.board_fen()))
    return res

core = lambda s: re.sub(r"[+#!?]", "", s).replace("0-0-0", "O-O-O").replace("0-0", "O-O")

def main():
    patches, report = [], []
    for l in open("work/found.txt", encoding="utf-8"):
        f = l.rstrip("\n").split("|")
        if len(f) < 6 or not f[5].strip(): continue
        n, sans = f[0], f[5].split()
        g = G.get(n)
        if not g: continue
        mv = replay(sans)
        pos = plies_from(mv)
        # проверка: позиция стартовой доски книги есть в партии базы
        start_ply = None
        if g["start"]:
            want = B[g["start"]].split()[0]
            start_ply = next((p for p, pl in pos if pl == want), None)
            if start_ply is None:
                report.append(f"{n}: не та партия (нет позиции доски {g['start']})"); continue
        else:
            first = [x[1] for x in g["line"] if x[0] == "mv"][:6]
            if [s for s, _ in mv[:len(first)]] != first and len(first) >= 4:
                report.append(f"{n}: не та партия (другие первые ходы)"); continue
        f0 = g["file"]; t = read(f0)
        m = re.search(r"^### %s\..*$" % re.escape(n), t, re.M)
        end = t.find("\n### ", m.end()); end = len(t) if end < 0 else end
        j = t.find("\n## ", m.end()); end = min(end, j) if j >= 0 else end
        sec = t[m.start():end]
        cut = sec.find("**Дополнительные материалы"); sec = sec if cut < 0 else sec[:cut]
        # жирные куски главной линии: номер первого хода совпадает с ожидаемым полуходом
        exp = start_ply if start_ply is not None else 0
        nfix = 0
        for bm in re.finditer(r"\*\*(.+?)\*\*", sec):
            seg = bm.group(1)
            toks = list(TOK.finditer(seg))
            if not toks: continue
            t0 = toks[0]
            if not t0.group(1): continue
            p0 = (int(t0.group(1)) - 1) * 2 + (0 if t0.group(2) == "." else 1)
            if p0 != exp: continue                      # побочный жирный кусок
            new, last, ply = [], 0, p0
            for tk in toks:
                if tk.group(1):
                    ply = (int(tk.group(1)) - 1) * 2 + (0 if tk.group(2) == "." else 1)
                tok = tk.group(3) or tk.group(4)
                a, b = tk.start(3) if tk.group(3) else tk.start(4), tk.end(3) if tk.group(3) else tk.end(4)
                if ply < len(mv) and core(norm(tok)) != core(mv[ply][0]):
                    new.append(seg[last:a] + mv[ply][0].rstrip("+#")); last = b; nfix += 1
                ply += 1
            new.append(seg[last:])
            exp = ply
            fixed = "".join(new)
            if fixed != seg:
                patches.append({"game": n, "from": "**" + seg + "**", "to": "**" + fixed + "**", "pdf": "база 365chess gid " + f[1]})
        # начало партии для фрагмента
        if start_ply:
            bd = chess.Board(); parts = []
            for i, (s, _) in enumerate(mv[:start_ply]):
                parts.append((f"{i // 2 + 1}." if i % 2 == 0 else "") + s)
            dm = re.search(r"\\?\[Доска \d+\\?\]|\[?Доска \d+\]?", sec)
            if dm:
                head = sec[:dm.start()].rstrip("\n")
                patches.append({"game": n, "from": sec[dm.start():dm.end()],
                                "to": "*Начало партии (по базе 365chess):* **" + " ".join(parts) + "**\n\n" + sec[dm.start():dm.end()],
                                "pdf": "база 365chess gid " + f[1]})
        report.append(f"{n}: принято, исправлено ходов {nfix}" + (f", начало с 1-го хода ({start_ply} полуходов)" if start_ply else ""))
    json.dump({"patches": patches}, open("fix_db.json", "w"), ensure_ascii=False, indent=1)
    print("\n".join(report)); print("правок:", len(patches))

if __name__ == "__main__":
    main()
