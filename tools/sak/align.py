"""Сопоставление «Доска N» из .md с досками boards.txt по содержанию (номера в .md сбиты).
   Партия проигрывается главной линией (жирные ходы + абзацы, начатые ожидаемым ходом);
   каждая метка доски ищется среди досок файла: позиция совпадает клетка в клетку.
   Старт фрагмента — доска файла, с которой ходы легальны и приводят в следующие доски.
   Пишет work/align.json: {"md→file": {...}, "games": [...]} и короткий отчёт."""
import re, json, os, chess
from lib import *
B = boards(); NB = max(B)
def mainline(body):
    """события партии: ('b', N) | ('m', num, side, tok) | ('cut',) — побочный кусок прерывает линию"""
    ev, exp = [], None
    for para in re.split(r'\n', body):
        p = para.strip()
        mb = re.match(r'^\\?\[?\s*(?i:доска)\s*(\d+)\s*\\?\]?$', p)
        if mb: ev.append(('b', int(mb.group(1)))); continue
        if 'Примечание' in p and re.search(r'\d+\s*\.', p):
            body = p.split(':', 1)[1] if ':' in p else p
            ev.append(('note', [(int(m.group(1)) if m.group(1) else None, None if not m.group(1) else 'w' if m.group(2) == '.' else 'b',
                                 m.group(3) or m.group(4)) for m in TOK.finditer(body)]))
            continue
        segs = re.findall(r'\*\*(.+?)\*\*', p)
        if not segs and re.match(r'^\d+\s*\.(\.\.)?\s*(' + MOVE + ')', p): segs = [p]
        for s in segs:
            s = re.split(r'[(—]', s)[0]
            for m in TOK.finditer(s):
                num, dots, tok = m.group(1), m.group(2), m.group(3) or m.group(4)
                ev.append(('m', int(num) if num else None, (None if not num else 'w' if dots == '.' else 'b'), tok))
            ev.append(('seg',))
    return ev
W = 14
COST = {None: 0, 'уточнение': 0, 'буква': 1, 'буква2': 2, 'клетка': 4, 'продолжение': 2}
def cands(bd, tok):
    """варианты хода: точный разбор; иначе ходы на ту же клетку — с теми же знаками взятия/шаха
       («буква2», дешевле) или без них («клетка»)"""
    mv, how = play(bd, tok)
    if mv is not None and how is None: return [(mv, None)]
    out = [(mv, how)] if mv is not None else []
    t = norm(tok)
    m = re.search(r'([a-h][1-8])(?:=?[QRBN])?[+#]?$', t)
    if m:
        to = chess.parse_square(m.group(1)); cap = 'x' in t; chk = tok.rstrip('!?').endswith(('+', '#'))
        for x in bd.legal_moves:
            if x.to_square != to or any(x == y for y, _ in out): continue
            same = bd.is_capture(x) == cap and (not chk or bd.gives_check(x))
            out.append((x, 'буква2' if same else 'клетка'))
    out.sort(key=lambda p: COST.get(p[1], 4))
    return out
def repair(bd, toks, target, depth=0):
    """ходы toks от bd, каждый можно заменить кандидатом; должно получиться target. -> [(move, how)] | None"""
    if not toks: return [] if bd.board_fen() == target else None
    for mv, how in cands(bd, toks[0])[:8]:
        bd.push(mv)
        r = repair(bd, toks[1:], target, depth + 1)
        bd.pop()
        if r is not None: return [(mv, how)] + r
    return None
def reach(bd, mv, fut):
    """(сколько следующих ходов удаётся сыграть после mv, -цена починок) — поиск в глубину"""
    b = bd.copy(); b.push(mv)
    if not fut: return (0, 0)
    best = (0, 0)
    for c, h in cands(b, fut[0])[:4]:
        d, cost = reach(b, c, fut[1:])
        r = (1 + d, cost - COST.get(h, 3))
        if r > best: best = r
    return best
def upcoming(ev, i, exp, n):
    """следующие n токенов главной линии после текущего (с учётом нумерации)"""
    out, ex = [], (exp[0], 'b') if exp[1] == 'w' else (exp[0] + 1, 'w')
    skip, first, segside = False, False, False
    for e in ev[i:]:
        if e[0] == 'seg': skip = False; first = True; segside = False
        if e[0] != 'm': continue
        if first and e[1] is not None: segside = (e[1], e[2]) != ex
        first = False
        if segside: continue
        if e[1] is not None: skip = (e[1], e[2]) != ex
        if skip: continue
        out.append(e[3]); ex = (ex[0], 'b') if ex[1] == 'w' else (ex[0] + 1, 'w')
        if len(out) >= n: break
    return out
def simulate(bd, ev, lo):
    """-> (сопоставление {md: file}, сыграно, всего, обрывы, починки, lo, линия)
       линия: ('root', fen) | ('mv', san, uci, исходный токен, починка) | ('b', md, file)"""
    mp, played, total, bad, fixes = {}, 0, 0, [], []
    line, pend, exp = [], [], None          # pend — токены после обрыва до следующей доски
    if bd is not None:
        exp = (bd.fullmove_number, 'w' if bd.turn else 'b'); line.append(('root', bd.fen()))
    broken = None                            # позиция в момент обрыва
    skip = False                             # внутри побочного куска
    first, segside = True, False             # кусок целиком побочный, если начат не тем ходом
    for e in ev:
        if e[0] == 'b':
            if bd is None and broken is None: continue
            rng = range(max(lo, e[1] - W), min(e[1] + W, NB) + 1)
            if isinstance(bd, str):          # линия потеряна — опора на эту доску
                bd = 'resync'; resync = (e[1], rng); continue
            if broken is None:
                line.append(('at', e[1], bd.fen()))
                hit = next((j for j in rng if B[j].split()[0] == bd.board_fen()), None)
                if hit: mp[e[1]] = hit; lo = hit + 1; line.append(('b', e[1], hit))
                continue
            # обрыв: ремонт токенов до этой доски
            for j in rng:
                r = repair(broken.copy(), [p[3] for p in pend], B[j].split()[0]) if len(pend) <= 12 else None
                if r is not None:
                    bd = broken
                    for (mv, how), p in zip(r, pend):
                        san = bd.san(mv)
                        if how: fixes.append([p[3], san, how])
                        line.append(("mv", san, mv.uci(), p[3], how)); bd.push(mv); played += 1
                    bad.pop(); mp[e[1]] = j; lo = j + 1; line.append(('b', e[1], j)); broken = None; pend = []
                    break
            else:
                # не сошлось: новая опора — доска, с которой легальны следующие ходы
                broken = None; pend = []; bd = 'resync'; resync = (e[1], rng)
            continue
        if e[0] == 'seg': skip = False; first = True; segside = False; continue
        if e[0] == 'note':
            nt = [x for x in e[1] if x[2]]
            if not nt or not nt[0][0]: continue
            cur = broken if broken is not None else bd
            if not isinstance(cur, chess.Board): continue
            want = (nt[0][0], chess.WHITE if nt[0][1] == 'w' else chess.BLACK)
            c2, ln, held = cur.copy(), list(line), []
            while c2.move_stack and (c2.fullmove_number, c2.turn) != want:
                c2.pop()
                while ln and ln[-1][0] == 'b': held.append(ln.pop())
                if ln and ln[-1][0] == 'mv': ln.pop()
            if (c2.fullmove_number, c2.turn) != want: continue
            ok = True; tmp = []
            for num, side, tok in nt:
                mv, how = play(c2, tok)
                if mv is None or how: ok = False; break
                tmp.append(('mv', c2.san(mv), mv.uci(), tok, 'примечание')); c2.push(mv)
            if not ok: continue
            line = ln + tmp; bd = c2; broken = None; pend = []
            if bad and bad[-1]: bad.pop()
            for h in reversed(held):
                if B[h[2]].split()[0] == bd.board_fen(): line.append(h)
            exp = (bd.fullmove_number, 'w' if bd.turn else 'b'); played += len(tmp)
            continue
        num, side, tok = e[1], e[2], e[3]
        if first and num is not None and exp and bd != 'resync': segside = (num, side) != exp
        if first: first = False
        if segside: continue
        if num is not None and exp and bd != 'resync': skip = (num, side) != exp
        if skip: continue
        if exp is None and bd == 'resync' and num is not None:
            exp = (num, side)
        if num is not None and exp and (num, side) != exp: continue     # побочный вариант
        if num is None and exp is None: continue
        total += 1
        if bd == 'resync':
            n0, rng = resync; best = None
            for j in rng:
                if j < lo: continue
                b2 = board_from(B[j], exp[1]); b2.fullmove_number = exp[0]
                if not b2.is_valid(): continue
                mv, how = play(b2, tok)
                if mv is not None and how is None: best = j; break
            if best is None: bd = 'dead'
            else:
                bd = board_from(B[best], exp[1]); bd.fullmove_number = exp[0]
                mp[n0] = best; lo = best + 1; line += [('root', bd.fen()), ('b', n0, best)]
        if bd == 'dead' or bd is None: continue
        if broken is not None:
            pend.append(e); exp = (exp[0], 'b') if exp[1] == 'w' else (exp[0] + 1, 'w'); continue
        mv, how = play(bd, tok)
        if mv is None:
            # ремонт по продолжению: замена, после которой дальше идёт самая длинная легальная цепочка
            fut = upcoming(ev, ev.index(e) + 1, exp, 6)
            ok = []
            for c, h in cands(bd, tok)[:8]:
                d, cost = reach(bd, c, fut); ok.append(((d, cost - COST.get(h, 3)), c))
            ok.sort(key=lambda x: x[0], reverse=True)
            need = min(3, len(fut))
            if ok and ok[0][0][0] >= max(need, 1) and (len(ok) == 1 or ok[1][0] < ok[0][0]):
                mv, how = ok[0][1], 'продолжение'
        if mv is None:
            bad.append([exp, tok, bd.fen()]); broken = bd.copy(); pend = [e]
            exp = (exp[0], 'b') if exp[1] == 'w' else (exp[0] + 1, 'w'); continue
        san = bd.san(mv)
        if how: fixes.append([tok, san, how])
        line.append(('mv', san, mv.uci(), tok, how)); bd.push(mv); played += 1
        exp = (bd.fullmove_number, 'w' if bd.turn else 'b')
    return mp, played, total, bad, fixes, lo, line
games = []
for f in files():
    t = read(f)
    chap = title = None
    for blk in re.split(r'^(#{2,3} .*)$', t, flags=re.M):
        if blk.startswith('## '): chap = blk[3:].strip(); continue
        if blk.startswith('### '): title = blk[4:].strip(); continue
        if not chap or not re.match(r'\d+\.', title or ''): continue
        ev = mainline(blk)
        mvs = [e for e in ev if e[0] == 'm']
        bi = [i for i, e in enumerate(ev) if e[0] == 'b']
        cands_ = []                        # (очки, старт, результат simulate)
        if mvs and mvs[0][1] == 1 and mvs[0][2] == 'w' and (not bi or ev.index(mvs[0]) < bi[0]):
            r = simulate(chess.Board(), ev, 1); cands_.append((r[1] + 25 * len(r[0]), 0, r))
        elif bi:
            n0 = ev[bi[0]][1]
            side = next((e[2] for e in ev[bi[0]:] if e[0] == 'm' and e[2]), 'w')
            num = next((e[1] for e in ev[bi[0]:] if e[0] == 'm' and e[1]), 1)
            for j in range(max(1, n0 - W), min(n0 + W, NB) + 1):
                bd = board_from(B[j], side); bd.fullmove_number = num
                if not bd.is_valid(): continue
                r = simulate(bd, ev[bi[0] + 1:], j + 1)
                if r[1] == 0 and r[2] > 0: continue
                r[0][n0] = j
                cands_.append((r[1] + 25 * len(r[0]), j, r))
        games.append({'file': f, 'chap': chap, 'title': title, 'ev': ev, 'cands': cands_,
                      'mdboards': [e[1] for e in ev if e[0] == 'b'], 'total': len(mvs)})
        title = None
# DP: у каждой партии выбрать кандидата (или ничего) так, чтобы доски файла строго возрастали
NEG = -1e9
dp = [{0: (0, None, None)}]                 # последняя занятая доска -> (очки, откуда, кандидат)
for gi, g in enumerate(games):
    cur = {}
    for last, (sc, _, _) in dp[-1].items():
        if cur.get(last, (NEG,))[0] < sc: cur[last] = (sc, last, None)
        for c in g['cands']:
            vals = sorted(c[2][0].values())
            if not vals:                     # партия без досок: ни на что не влияет
                if cur.get(last, (NEG,))[0] < sc + c[0]: cur[last] = (sc + c[0], last, c)
                continue
            if vals[0] > last:
                k = vals[-1]
                if cur.get(k, (NEG,))[0] < sc + c[0]: cur[k] = (sc + c[0], last, c)
    # обрезка: оставить лучшие состояния
    dp.append(dict(sorted(cur.items(), key=lambda x: -x[1][0])[:60]))
last = max(dp[-1], key=lambda k: dp[-1][k][0])
pick = [None] * len(games)
for gi in range(len(games), 0, -1):
    sc, prev, c = dp[gi][last]
    pick[gi - 1] = c; last = prev
md2f, out = {}, []
for g, c in zip(games, pick):
    mp, played, total, bad, fixes, _, line = c[2] if c else ({}, 0, g['total'], [], [], 0, [])
    md2f.update(mp)
    out.append({'file': g['file'], 'chap': g['chap'], 'title': g['title'], 'start': c[1] if c else None,
                'boards': {str(k): v for k, v in mp.items()}, 'mdboards': g['mdboards'],
                'played': played, 'total': total, 'line': line, 'bad': bad, 'fixes': fixes})
games = out
os.makedirs('work', exist_ok=True)
json.dump({'md2f': md2f, 'games': games}, open(os.environ.get('ALIGN_OUT', 'work/align.json'), 'w'), ensure_ascii=False)
allmd = [b for g in games for b in g['mdboards']]
used = set(md2f.values())
print('партий', len(games), '| меток досок в .md', len(allmd), '| сопоставлено', len(md2f))
print('ходов главной линии сыграно', sum(g['played'] for g in games), 'из', sum(g['total'] for g in games),
      '| партий с обрывом', sum(1 for g in games if g['bad']), '| починок', sum(len(g['fixes']) for g in games))
print('метки .md без пары:', [b for b in allmd if b not in md2f])
print('доски файла без пары:', [j for j in range(1, NB + 1) if j not in used])
