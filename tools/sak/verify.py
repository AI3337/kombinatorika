"""Проверка: каждая партия проигрывается ходами главной линии; на каждой «Доске N»
   позиция сравнивается с доской N из boards.txt. Главная линия — жирные ходы и абзацы,
   начинающиеся ровно с ожидаемого хода. Пишет work/verify.json и короткий отчёт."""
import re, json, os, chess
from lib import *
B = boards()
rep = {'ok': [], 'diff': [], 'nofen': [], 'fix': [], 'bad': [], 'fragstart': [], 'dead': []}
for f in files():
    t = open(f).read()
    for g in re.split(r'^### ', t, flags=re.M)[1:]:
        title = g.split('\n', 1)[0].strip()
        if not re.match(r'\d+\.', title): continue
        body = g.split('\n', 1)[1] if '\n' in g else ''
        bd, exp = None, None          # позиция и ожидаемый (номер, сторона)
        for para in re.split(r'\n\s*\n|\n', body):
            p = para.strip()
            mb = re.search(r'(?i)доска\s*(\d+)', p)
            if mb and len(p) < 30:
                n = int(mb.group(1))
                if n not in B: rep['nofen'].append(n); continue
                if bd is None:
                    rep['fragstart'].append(n); bd = 'pending:' + str(n); continue
                if isinstance(bd, str): rep['dead' if bd == 'dead' else 'nofen'].append([n, title[:30]]); continue
                (rep['ok'] if bd.board_fen() == B[n].split()[0] else rep['diff']).append([n, title[:30]])
                continue
            # главная линия: жирные куски + абзац, который начинается с ожидаемого хода
            segs = re.findall(r'\*\*(.+?)\*\*', p)
            if not segs and re.match(r'^\d+\s*\.', p) and exp: segs = [p]
            elif segs and not p.startswith('**') and re.match(r'^\d+\s*\.', p) and exp: segs = [p.replace('**', '')]
            for s in segs:
                s = s.split('(')[0]
                for m in TOK.finditer(s):
                    num, dots, mv = m.group(1), m.group(2), m.group(3) or m.group(4)
                    side = None if not num else ('w' if dots == '.' else 'b')
                    if bd == 'dead': break
                    if isinstance(bd, str):          # фрагмент: старт с доски
                        if not num: break
                        bd = board_from(B[int(bd.split(':')[1])], side); exp = (int(num), side)
                    if bd is None:
                        if num != '1': break
                        bd = chess.Board(); exp = (1, 'w')
                    if num and (int(num), side) != exp: break      # побочный вариант
                    mvv, how = play(bd, mv)
                    if mvv is None: rep['bad'].append([title[:30], exp, mv, bd.fen()]); exp = None; break
                    if how: rep['fix'].append([title[:30], mv, bd.san(mvv), how])
                    bd.push(mvv)
                    exp = (exp[0], 'b') if exp[1] == 'w' else (exp[0] + 1, 'w')
                if exp is None: break
            if exp is None and bd is not None and not isinstance(bd, str): bd = 'dead'
os.makedirs('work', exist_ok=True); json.dump(rep, open('work/verify.json', 'w'), ensure_ascii=False, indent=0)
print({k: len(v) for k, v in rep.items()})
