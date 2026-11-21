#!/usr/bin/env node
/**
 * Конвертер 7 Markdown-глав книги Бориса Гельфанда
 * «Принятие позиционных решений в шахматах» -> gelfand.js
 *
 * Использует собственный шахматный движок сайта из app.js (parseFen, makeMove,
 * legalTargets, fenState), поэтому 100% диаграмм и кликабельных ходов
 * гарантированно совместимы с читалкой сайта.
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const REPO_DIR = path.resolve(__dirname, "../..");
const MD_DIR = path.resolve(REPO_DIR, "../Позиционные решения");
const OUT_FILE = path.join(REPO_DIR, "gelfand.js");
const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

// 1. Загружаем шахматный движок напрямую из app.js
function loadEngine() {
  const appLines = fs.readFileSync(path.join(REPO_DIR, "app.js"), "utf8").split("\n");
  // Строки 236..488 (генератор легальных ходов и makeMove) + 769..779 (parseFen)
  const chunk1 = appLines.slice(235, 488).join("\n");
  const chunk2 = appLines.slice(768, 779).join("\n");
  const code = `
    const FILES = "abcdefgh";
    ${chunk2}
    ${chunk1}
    module.exports = { FILES, parseFen, fenState, legalTargets, makeMove, boardToFen, kingSq };
  `;
  const sandbox = { module: { exports: {} } };
  vm.runInNewContext(code, sandbox);
  return sandbox.module.exports;
}

const E = loadEngine();

// Кэш всех легальных ходов для позиции FEN (ускоряет парсинг в разы)
const legalCache = new Map();
function getAllLegalMoves(fen) {
  let list = legalCache.get(fen);
  if (list) return list;
  list = [];
  const sf = E.fenState(fen);
  // Проверяем, есть ли короли — на схематических досках без королей ходов не строим
  if (!E.kingSq(sf.pos, "w") || !E.kingSq(sf.pos, "b")) {
    legalCache.set(fen, list);
    return list;
  }
  const wantWhite = sf.turn === "w";
  for (const from in sf.pos) {
    const pc = sf.pos[from];
    const isWhite = pc === pc.toUpperCase();
    if (isWhite !== wantWhite) continue;
    const targets = E.legalTargets(fen, from);
    const isPawn = pc.toLowerCase() === "p";
    for (const to of targets) {
      const promoRank = isPawn && (to[1] === "8" || to[1] === "1");
      if (promoRank) {
        for (const pr of ["q", "r", "b", "n"]) {
          const mv = E.makeMove(fen, from, to, pr);
          if (mv) list.push(mv);
        }
      } else {
        const mv = E.makeMove(fen, from, to);
        if (mv) list.push(mv);
      }
    }
  }
  legalCache.set(fen, list);
  return list;
}

function normSan(s) {
  return s
    .replace(/0-0-0/g, "O-O-O")
    .replace(/0-0/g, "O-O")
    .replace(/О-О-О/g, "O-O-O")
    .replace(/О-О/g, "O-O")
    .replace(/:/g, "x")
    .replace(/[+#!?]+/g, "")
    .replace(/=([QRBN])/i, (_, p) => "=" + p.toUpperCase())
    .trim();
}

function findMove(fen, rawSan) {
  const target = normSan(rawSan);
  if (!target) return null;
  const moves = getAllLegalMoves(fen);
  for (const mv of moves) {
    if (normSan(mv.san) === target) return mv;
  }
  // Иногда в книгах опускают «x» при взятии или добавляют лишнюю спецификацию
  const targetNoX = target.replace(/x/g, "");
  const cands = moves.filter(mv => normSan(mv.san).replace(/x/g, "") === targetNoX);
  if (cands.length === 1) return cands[0];
  return null;
}

function fenBoardTurn(fen) {
  const p = fen.split(" ");
  return p[0] + " " + (p[1] || "w");
}

function fenMoveNum(fen) {
  const p = fen.split(" ");
  return +(p[5] || 1);
}

function fenTurn(fen) {
  return (fen.split(" ")[1] || "w");
}

function setFenMoveNum(fen, num) {
  const p = fen.split(" ");
  while (p.length < 6) p.push(p.length === 1 ? "w" : p.length === 2 ? "-" : p.length === 3 ? "-" : p.length === 4 ? "0" : "1");
  p[5] = String(num);
  return p.slice(0, 6).join(" ");
}

function validateFen(fen) {
  if (!fen || typeof fen !== "string") return false;
  const parts = fen.trim().split(/\s+/);
  if (parts.length < 2) return false;
  const rows = parts[0].split("/");
  if (rows.length !== 8) return false;
  for (const row of rows) {
    let cnt = 0;
    for (const ch of row) {
      if (ch >= "1" && ch <= "8") cnt += +ch;
      else if ("PNBRQKpnbrqk".includes(ch)) cnt += 1;
      else return false;
    }
    if (cnt !== 8) return false;
  }
  if (parts[1] !== "w" && parts[1] !== "b") return false;
  return true;
}

// Класс дерева ходов для одной главы
class ChapterTree {
  constructor() {
    this.roots = [];       // массив FEN-строк; ссылка на корень k: -(k+1)
    this.nodes = [];       // [parent, uci, san, isMain]
    this.fens = [];        // вычисленный FEN для каждого nodeId
    this.rootByKey = new Map(); // fen (полный) -> negIdx
    this.childMap = new Map();  // `${parent}|${uci}` -> nodeId
  }

  fenOf(id) {
    if (id == null) return null;
    return id < 0 ? this.roots[-id - 1] : this.fens[id];
  }

  addRoot(fen) {
    const clean = fen.trim();
    if (this.rootByKey.has(clean)) return this.rootByKey.get(clean);
    const idx = -(this.roots.length + 1);
    this.roots.push(clean);
    this.rootByKey.set(clean, idx);
    return idx;
  }

  addMove(parentId, mv, isMain) {
    const key = `${parentId}|${mv.uci}`;
    if (this.childMap.has(key)) {
      const existing = this.childMap.get(key);
      if (isMain) this.nodes[existing][3] = 1;
      return existing;
    }
    const id = this.nodes.length;
    this.nodes.push([parentId, mv.uci, mv.san, isMain ? 1 : 0]);
    this.fens.push(mv.fen);
    this.childMap.set(key, id);
    return id;
  }
}

// Регулярка для одного хода в тексте (с опциональным номером и оценкой)
// Примеры: 1.d4, 14...Nf6, O-O-O, 0-0, Nxd5+, exf6, e8=Q#, Rad8!?, 23.Bxf7+!
const MOVE_RE = /(?:(\d+)\s*(\.{1,3}|…)\s*)?(O-O-O|O-O|0-0-0|0-0|[KQRBN][a-h]?[1-8]?x?[a-h][1-8]|[a-h]x[a-h][1-8](?:=[QRBN])?|[a-h][1-8](?:=[QRBN])?)([+#]?[!?]{0,2})/g;

// Очистка Markdown-форматирования внутри текста (кроме **...** и `...`, которые разбираем отдельно)
function cleanInlineMd(s) {
  return s
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/\\([*_`\[\]])/g, "$1");
}

// Парсинг одного файла главы
function parseChapterFile(filePath, meta) {
  const raw = fs.readFileSync(filePath, "utf8");
  const lines = raw.split(/\r?\n/);

  const tree = new ChapterTree();
  const blocks = [];

  let secCount = 0;
  let diagCount = 0;
  let totalMoveTokens = 0;
  let linkedMoveTokens = 0;

  // Контекст текущей партии/раздела для привязки ходов
  let mainNode = null;          // текущая позиция главной линии
  let mainHistory = [];         // все узлы главной линии текущей партии (для возврата назад при вариантах)
  let recentNodes = [];         // недавно посещённые узлы (включая варианты и диаграммы)
  let gameDiagNodes = [];       // узлы диаграмм текущей партии

  function resetGameContext() {
    mainNode = null;
    mainHistory = [];
    recentNodes = [];
    gameDiagNodes = [];
  }

  function rememberNode(id, isMain) {
    if (id == null) return;
    if (isMain) {
      mainNode = id;
      if (!mainHistory.includes(id)) mainHistory.push(id);
    }
    const idx = recentNodes.indexOf(id);
    if (idx >= 0) recentNodes.splice(idx, 1);
    recentNodes.push(id);
    if (recentNodes.length > 120) recentNodes.shift();
  }

  // Найти подходящего родителя для хода (num, dots, san) среди известных позиций
  function resolveMove(rawSan, moveNum, dots, isMain, curVarNode) {
    const wantTurn = dots ? (dots.length >= 2 || dots === "…" ? "b" : "w") : null;

    // 1. Сначала пробуем прямое продолжение
    const primary = isMain ? mainNode : (curVarNode != null ? curVarNode : mainNode);
    if (primary != null) {
      const pf = tree.fenOf(primary);
      if (pf && (!wantTurn || fenTurn(pf) === wantTurn)) {
        const mv = findMove(pf, rawSan);
        if (mv) {
          // Если номер хода задан и расходится с FEN — проверим, нет ли более точного совпадения в истории
          if (!moveNum || fenMoveNum(pf) === moveNum) {
            return { parent: primary, mv };
          }
          // Если FEN от диаграммы без точного номера хода (fullmove === 1), всё равно берём primary!
          if (fenMoveNum(pf) === 1 && primary < 0) {
            return { parent: primary, mv };
          }
        }
      }
    }

    // 2. Если это ход 1 белых — пробуем начальную позицию
    if (moveNum === 1 && wantTurn === "w") {
      const mv = findMove(START_FEN, rawSan);
      if (mv) {
        const r = tree.addRoot(START_FEN);
        return { parent: r, mv };
      }
    }

    // 3. Для вариантов: часто это альтернатива последнему ходу (т.е. ход от родителя mainNode)
    const candidates = [];
    if (curVarNode != null && curVarNode !== primary) candidates.push(curVarNode);
    if (mainNode != null && mainNode >= 0) {
      const pOfMain = tree.nodes[mainNode][0];
      if (pOfMain != null) candidates.push(pOfMain);
    }
    // Последние узлы главной линии и диаграммы (с конца — самые свежие первыми)
    for (let i = mainHistory.length - 1; i >= 0; i--) candidates.push(mainHistory[i]);
    for (let i = gameDiagNodes.length - 1; i >= 0; i--) candidates.push(gameDiagNodes[i]);
    for (let i = recentNodes.length - 1; i >= 0; i--) candidates.push(recentNodes[i]);

    const seen = new Set();
    let fallback = null;
    for (const cid of candidates) {
      if (cid == null || seen.has(cid)) continue;
      seen.add(cid);
      const pf = tree.fenOf(cid);
      if (!pf) continue;
      if (wantTurn && fenTurn(pf) !== wantTurn) continue;
      const mv = findMove(pf, rawSan);
      if (!mv) continue;
      if (!moveNum || fenMoveNum(pf) === moveNum) {
        return { parent: cid, mv };
      }
      if (!fallback) fallback = { parent: cid, mv };
    }

    // 4. Если ход всё-таки легален из primary (например, номер хода на диаграмме был 1)
    if (primary != null) {
      const pf = tree.fenOf(primary);
      if (pf && (!wantTurn || fenTurn(pf) === wantTurn)) {
        const mv = findMove(pf, rawSan);
        if (mv) return { parent: primary, mv };
      }
    }

    return fallback;
  }

  // Превращает фрагмент текста (главной линии или варианта) в массив сегментов
  function parseMoveChunk(text, isMain, startVarNode) {
    const segs = [];
    let lastIdx = 0;
    let curVar = startVarNode;
    MOVE_RE.lastIndex = 0;
    let m;
    while ((m = MOVE_RE.exec(text)) !== null) {
      const full = m[0];
      const start = m[0] ? m.index : 0;
      const before = start > 0 ? text[start - 1] : " ";
      const after = text[start + full.length] || " ";

      // Отсекаем ложные срабатывания внутри слов (например, "a4" внутри латинского слова или "1. " списка)
      if (/[A-Za-zА-Яа-яЁё0-9_]/.test(before) || /[A-Za-zА-Яа-яЁё]/.test(after)) {
        continue;
      }

      const moveNum = m[1] ? parseInt(m[1], 10) : null;
      const dots = m[2] || null;
      const rawSan = m[3];

      // Одиночное поле вроде "e4" или "d5" без номера хода в обычном русском тексте (не в backticks и не в bold) — не считаем ходом, если это не внутри `` или **
      totalMoveTokens++;
      const res = resolveMove(rawSan, moveNum, dots, isMain, curVar);
      if (res) {
        if (start > lastIdx) segs.push(cleanInlineMd(text.slice(lastIdx, start)));
        const nodeId = tree.addMove(res.parent, res.mv, isMain);
        rememberNode(nodeId, isMain);
        curVar = nodeId;
        linkedMoveTokens++;
        const seg = { m: nodeId, s: full };
        if (isMain) seg.b = 1;
        segs.push(seg);
        lastIdx = start + full.length;
      }
    }
    if (lastIdx < text.length) segs.push(cleanInlineMd(text.slice(lastIdx)));
    return { segs, lastVar: curVar };
  }

  // Разбор целого абзаца: выделяем **главную линию** и `варианты`, сохраняя остальной текст
  function parseParagraph(paraText) {
    const segs = [];
    // Токенизируем на **...** и `...`
    const TOKEN_RE = /(\*\*[^*]+\*\*|`[^`]+`)/g;
    let last = 0;
    let m;
    let curVar = null;
    while ((m = TOKEN_RE.exec(paraText)) !== null) {
      if (m.index > last) {
        const plain = cleanInlineMd(paraText.slice(last, m.index));
        if (plain) segs.push(plain);
      }
      const tok = m[0];
      if (tok.startsWith("**")) {
        const inner = tok.slice(2, -2);
        // Проверяем, похоже ли это на шахматные ходы (начинается с номера хода или фигуры/рокировки)
        if (/^(?:\d+\s*(?:\.{1,3}|…)\s*)?(?:O-O|0-0|[KQRBN][a-h1-8x]|[a-h]x?[a-h]?[1-8])/.test(inner.trim())) {
          const { segs: sub } = parseMoveChunk(inner, true, null);
          segs.push(...sub);
          curVar = null;
        } else {
          segs.push(inner);
        }
      } else if (tok.startsWith("`")) {
        const inner = tok.slice(1, -1);
        const { segs: sub, lastVar } = parseMoveChunk(inner, false, curVar);
        segs.push(...sub);
        if (lastVar != null) curVar = lastVar;
      }
      last = m.index + tok.length;
    }
    if (last < paraText.length) {
      const plain = cleanInlineMd(paraText.slice(last));
      if (plain) segs.push(plain);
    }

    // Склеиваем соседние строки
    const merged = [];
    for (const s of segs) {
      if (!s) continue;
      if (typeof s === "string" && merged.length && typeof merged[merged.length - 1] === "string") {
        merged[merged.length - 1] += s;
      } else {
        merged.push(s);
      }
    }
    return merged;
  }

  // Обработка диаграммы: ищем совпадение в текущем дереве или добавляем новый корень
  function addDiagram(fen, moveHintText, noteText) {
    if (!validateFen(fen)) {
      throw new Error(`Некорректный FEN в ${path.basename(filePath)}: ${fen}`);
    }
    diagCount++;

    // Пробуем извлечь номер хода из подсказки вида "белых (после `16...Rab8`)"
    let hintMoveNum = null;
    if (moveHintText) {
      const mAfter = /после\s+`?(\d+)(\.{1,3}|…)?/.exec(moveHintText);
      if (mAfter) {
        const n = parseInt(mAfter[1], 10);
        const isBlackMove = mAfter[2] && (mAfter[2].length >= 2 || mAfter[2] === "…");
        hintMoveNum = isBlackMove ? n + 1 : n;
      }
    }

    const targetBT = fenBoardTurn(fen);
    let matchedId = null;
    // Сначала проверяем текущий mainNode и историю главной линии
    const checkOrder = [];
    if (mainNode != null) checkOrder.push(mainNode);
    for (let i = mainHistory.length - 1; i >= 0; i--) checkOrder.push(mainHistory[i]);
    for (let i = recentNodes.length - 1; i >= 0; i--) checkOrder.push(recentNodes[i]);

    for (const cid of checkOrder) {
      const cf = tree.fenOf(cid);
      if (cf && fenBoardTurn(cf) === targetBT) {
        matchedId = cid;
        break;
      }
    }

    let diagNodeId;
    if (matchedId != null) {
      diagNodeId = matchedId;
    } else {
      let useFen = fen.trim();
      if (hintMoveNum && fenMoveNum(useFen) === 1 && hintMoveNum > 1) {
        useFen = setFenMoveNum(useFen, hintMoveNum);
      }
      diagNodeId = tree.addRoot(useFen);
    }

    // Обновляем контекст: диаграмма задаёт актуальную точку опоры для следующих ходов
    gameDiagNodes.push(diagNodeId);
    rememberNode(diagNodeId, mainNode == null || matchedId === mainNode);
    if (mainNode == null) {
      mainNode = diagNodeId;
      mainHistory.push(diagNodeId);
    } else if (matchedId == null) {
      // Если диаграмма пришла не по цепочке (например, пропущены ходы или новая позиция),
      // обновляем mainNode, чтобы следующие жирные ходы продолжились от неё
      const hasKings = E.kingSq(E.parseFen(tree.fenOf(diagNodeId)), "w") && E.kingSq(E.parseFen(tree.fenOf(diagNodeId)), "b");
      if (hasKings) {
        mainNode = diagNodeId;
        mainHistory.push(diagNodeId);
      }
    }

    blocks.push({ t: "d", n: diagNodeId });
    if (noteText) {
      blocks.push({ t: "c", s: [cleanInlineMd(noteText)] });
    }
  }

  // Проход по строкам Markdown
  let i = 0;
  let pendingSection = false;
  let paraBuf = [];

  function flushPara() {
    if (!paraBuf.length) return;
    const text = paraBuf.join(" ").trim();
    paraBuf = [];
    if (!text) return;
    const segs = parseParagraph(text);
    if (segs.length === 1 && typeof segs[0] === "string") {
      blocks.push({ t: "p", x: segs[0] });
    } else if (segs.length) {
      blocks.push({ t: "p", s: segs });
    }
  }

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // Пустая строка или горизонтальный разделитель
    if (!trimmed || trimmed === "---") {
      flushPara();
      i++;
      continue;
    }

    // Заголовок главы (# ...) — уже в метаданных главы, пропускаем
    if (trimmed.startsWith("# ")) {
      flushPara();
      i++;
      continue;
    }

    // Блок диаграммы (#### Доска ...)
    if (trimmed.startsWith("#### ")) {
      flushPara();
      i++;
      let fen = null;
      let moveHint = "";
      let note = "";
      while (i < lines.length) {
        const sub = lines[i].trim();
        if (!sub) { i++; break; }
        if (sub.startsWith("#") || sub === "---") break;
        const mFen = /\*\*FEN:\*\*\s*`([^`]+)`/.exec(sub);
        const mMove = /\*\*Ход:\*\*\s*(.+)/.exec(sub);
        const mNote = /^\-\s*\*Примечание[^*]*:\*\s*(.+)/.exec(sub);
        const mType = /\*\*Тип:\*\*\s*(.+)/.exec(sub);
        if (mFen) fen = mFen[1].trim();
        else if (mMove) moveHint = mMove[1].trim();
        else if (mNote) note = mNote[1].trim();
        else if (mType && !note) note = mType[1].trim();
        else if (!sub.startsWith("- ")) break;
        i++;
      }
      if (fen) {
        addDiagram(fen, moveHint, note);
      }
      continue;
    }

    // Подзаголовок темы (## ...)
    if (trimmed.startsWith("## ")) {
      flushPara();
      const title = cleanInlineMd(trimmed.slice(3).trim());
      blocks.push({ t: "u", x: title });
      pendingSection = false;
      i++;
      continue;
    }

    // Раздел / Партия (### ...)
    if (trimmed.startsWith("### ")) {
      flushPara();
      resetGameContext();
      secCount++;
      const title = cleanInlineMd(trimmed.slice(4).trim());
      blocks.push({ t: "s", n: null, key: `${meta.n}.${secCount}`, x: title });
      pendingSection = true;
      i++;
      continue;
    }

    // Курсивная строка с названием турнира/года сразу после ###
    if (pendingSection && /^\*[^*]+\*$/.test(trimmed)) {
      flushPara();
      blocks.push({ t: "g", x: trimmed.slice(1, -1).trim() });
      pendingSection = false;
      i++;
      continue;
    }
    pendingSection = false;

    // Таблица Markdown (Перечень используемых символов в Предисловии)
    if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
      flushPara();
      const cells = trimmed.slice(1, -1).split("|").map(c => c.trim());
      // Пропускаем заголовок и разделитель |---|---|
      if (!cells.every(c => /^[-:]+$/.test(c)) && !(cells[0] === "Символ" || cells[0] === "**Символ**")) {
        const sym = cleanInlineMd(cells[0] || "");
        const desc = cleanInlineMd(cells.slice(1).join(" — "));
        if (sym || desc) {
          blocks.push({ t: "p", x: sym ? `${sym} — ${desc}` : desc });
        }
      }
      i++;
      continue;
    }

    // Цитата > ...
    if (trimmed.startsWith("> ")) {
      flushPara();
      const segs = parseParagraph(trimmed.slice(2).trim());
      blocks.push({ t: "p", r: 1, s: segs });
      i++;
      continue;
    }

    // Обычный маркированный список - ...
    if (trimmed.startsWith("- ")) {
      flushPara();
      const segs = parseParagraph("• " + trimmed.slice(2).trim());
      blocks.push({ t: "p", s: segs });
      i++;
      continue;
    }

    // Обычный абзац
    paraBuf.push(trimmed);
    i++;
  }
  flushPara();

  const chObj = {
    n: meta.n,
    title: meta.title,
    intro: blocks,
    roots: tree.roots,
    secs: secCount,
    diags: diagCount,
    nodes: tree.nodes,
  };
  if (meta.rawTitle) chObj.rawTitle = true;

  return {
    chapter: chObj,
    stats: {
      file: path.basename(filePath),
      secs: secCount,
      diags: diagCount,
      roots: tree.roots.length,
      nodes: tree.nodes.length,
      linked: linkedMoveTokens,
      total: totalMoveTokens,
    },
  };
}

function main() {
  const files = fs.readdirSync(MD_DIR).filter(f => f.endsWith(".md")).sort();
  const chaptersSpec = [
    { prefix: "00_", n: 0, title: "Предисловие" },
    { prefix: "01_", n: 1, title: "Игра в стиле Акибы Рубинштейна" },
    { prefix: "02_", n: 2, title: "Зажим" },
    { prefix: "03_", n: 3, title: "Пространственный перевес" },
    { prefix: "04_", n: 4, title: "Трансформация пешечной структуры" },
    { prefix: "05_", n: 5, title: "Трансформация преимущества" },
    { prefix: "06_", n: 6, title: "Приложение. Не могу выйти из дома!", rawTitle: true },
  ];

  const chapters = [];
  let totDiags = 0, totNodes = 0, totLinked = 0, totMoves = 0;

  for (const spec of chaptersSpec) {
    const fn = files.find(f => f.startsWith(spec.prefix));
    if (!fn) throw new Error(`Не найден файл с префиксом ${spec.prefix} в ${MD_DIR}`);
    const { chapter, stats } = parseChapterFile(path.join(MD_DIR, fn), spec);
    chapters.push(chapter);
    totDiags += stats.diags;
    totNodes += stats.nodes;
    totLinked += stats.linked;
    totMoves += stats.total;
    const pct = stats.total ? ((100 * stats.linked) / stats.total).toFixed(1) : "100.0";
    console.log(
      `${stats.file}: secs=${stats.secs}, diags=${stats.diags}, roots=${stats.roots}, nodes=${stats.nodes}, moves=${stats.linked}/${stats.total} (${pct}%)`
    );
  }

  const book = [{
    id: "gelfand",
    title: "Принятие позиционных решений в шахматах",
    author: "Борис Гельфанд",
    unit: "sec",
    chapters,
  }];

  const outJs = "window.GELFAND = " + JSON.stringify(book) + ";\n";
  fs.writeFileSync(OUT_FILE, outJs, "utf8");
  console.log(`\nГотово: ${OUT_FILE} (${(outJs.length / 1024).toFixed(1)} КБ)`);
  console.log(`Итого: глав=${chapters.length}, диаграмм=${totDiags}, узлов=${totNodes}, кликабельных ходов=${totLinked}/${totMoves} (${((100 * totLinked) / totMoves).toFixed(1)}%)`);
}

main();
