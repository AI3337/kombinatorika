"""Сакаев, том 1: разбор .md (src/*_*.md) и досок (src/boards.txt), проверка ходов python-chess."""
import re, glob, chess, json, os
def boards():
    """доски файла; правки распознавания — fix.json "fens": {"78": "расстановка"} (сверено с PDF)"""
    t = open('src/boards.txt').read()
    B = {int(a): f for a, b, f in re.findall(r'Доска (\d+) / Доска (\S+)\n(\S+)', t)}
    for fn in fix_files():
        try: fens = json.load(open(fn)).get('fens', {})
        except ValueError: continue
        for k, v in fens.items(): B[int(k)] = v
    return B
def fix_files():
    """fix.json (ручные правки) + fix_a*.json (правки помощников) + FIX_EXTRA"""
    out = ['fix.json'] + sorted(glob.glob('fix_a*.json')) + [os.environ.get('FIX_EXTRA', '')]
    return [f for f in dict.fromkeys(out) if f and os.path.exists(f)]
import json, os
def patches():
    """правки текста после сверки с PDF: fix.json {"patches": [{"game": "136", "from": "...", "to": "..."}]}
       + файл из переменной FIX_EXTRA (черновик помощника)"""
    out = []
    for fn in fix_files():
        try: out += json.load(open(fn)).get('patches', [])
        except ValueError: pass          # файл помощника в процессе записи
    return out
def read(f):
    """текст .md с правками: замена ищется внутри своей партии (### N.)"""
    fx = os.path.join('srcfix', os.path.basename(f))          # ходы, сверенные с PDF (ocr/moves.py)
    t = open(fx if os.path.exists(fx) else f, encoding='utf-8').read()
    for p in patches():
        m = re.search(r'^### ' + re.escape(str(p['game'])) + r'\.', t, re.M)
        if not m: continue
        end = t.find('\n### ', m.end()); end = len(t) if end < 0 else end
        j = t.find('\n## ', m.end()); end = min(end, j) if j >= 0 else end
        sec = t[m.start():end]
        if p['from'] in sec: t = t[:m.start()] + sec.replace(p['from'], p['to'], 1) + t[end:]
        else: print('! правка не найдена:', p['game'], p['from'][:40])
    return t
def files():
    return sorted(glob.glob('src/*_*.md'), key=lambda x: int(re.findall(r'(\d+)_', x)[0]))
MOVE = r'(?:[KQRBNdE2][a-h]?[1-8]?[x:]?[a-h][1-8]|[a-h](?:[x:][a-h])?[1-8](?:=?[QRBN])?|[O0]-[O0](?:-[O0])?)[+#]?'
TOK = re.compile(r'(\d+)\s*(\.\.\.|…|\.)\s*(' + MOVE + ')|(' + MOVE + r')(?![\w])')
def board_from(fen, side):
    bd = chess.Board(fen.split()[0] + ' ' + side + ' - - 0 1')
    cr = ''
    W, Bk = chess.Piece(chess.KING, True), chess.Piece(chess.KING, False)
    R, r = chess.Piece(chess.ROOK, True), chess.Piece(chess.ROOK, False)
    if bd.piece_at(chess.E1) == W:
        cr += 'K' if bd.piece_at(chess.H1) == R else ''; cr += 'Q' if bd.piece_at(chess.A1) == R else ''
    if bd.piece_at(chess.E8) == Bk:
        cr += 'k' if bd.piece_at(chess.H8) == r else ''; cr += 'q' if bd.piece_at(chess.A8) == r else ''
    bd.set_castling_fen(cr or '-')
    return bd
def norm(s):
    s = s.replace(':', 'x').replace('0', 'O')
    return re.sub(r'([a-h][18])([QRBN])$', r'\1=\2', s.rstrip('+#'))
def play(bd, tok):
    """ход из книги -> chess.Move (с починкой распознавания) или None; второй результат — пометка починки"""
    t = norm(tok)
    chk = tok.rstrip('!?').endswith(('+', '#'))
    try:
        mv = bd.parse_san(t)
        if not chk or bd.gives_check(mv): return mv, None
    except Exception: pass
    # только недостающее/лишнее уточнение (Nbd2 vs Nd2), без смены фигуры
    m = re.match(r'^([KQRBN])([a-h]?[1-8]?)x?([a-h][1-8])$', t)
    if m:
        to = chess.parse_square(m.group(3)); kind = chess.Piece.from_symbol(m.group(1)).piece_type
        c = [mv for mv in bd.legal_moves if mv.to_square == to and bd.piece_type_at(mv.from_square) == kind]
        if len(c) == 1: return c[0], 'уточнение'
    mv = agnostic(bd, tok)
    if mv is not None: return mv, 'буква'
    return None, None

def agnostic(bd, tok):
    """распознавание путает буквы фигур (Bxc4 вместо Nxc4, Bf6 вместо f6): единственный
       легальный ход на ту же клетку с тем же видом (взятие, превращение, шах, если указан)"""
    t = norm(tok) if tok else ''
    m = re.match(r'^([KQRBN]?)([a-h]?[1-8]?)(x?)([a-h][1-8])(=[QRBN])?$', t)
    if not m: return None
    to, cap, pr = chess.parse_square(m.group(4)), bool(m.group(3)), m.group(5)
    chk = tok.rstrip('!?').endswith(('+', '#'))
    c = [x for x in bd.legal_moves if x.to_square == to and bd.is_capture(x) == cap
         and (x.promotion is not None) == bool(pr) and (not chk or bd.gives_check(x))]
    return c[0] if len(c) == 1 else None
