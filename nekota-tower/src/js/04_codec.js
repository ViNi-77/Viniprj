/* 04_codec.js — メモリーカード（CSV + かな64）の符号化・復号
 *
 * ブラウザ（classic <script> → window.NT.Codec）と Node 22（module.exports）の両方で動く。依存なし。
 *
 * バイト列: "NKT1"(4) | flags(1: bit0=password, bit1=deflated) | salt(16, bit0 時のみ) | iv(12) | AES-GCM(ct+tag)
 * AAD      : ASCII 'nekota-tower/v1'
 * 平文     : UTF-8 JSON {v:1, entries:[{slot, record}]}。CompressionStream('deflate-raw') があれば圧縮して bit1 を立てる。
 * かな64   : 1 記号 = 6 bit。記号数 = ceil(8n/6)、末尾の余りは 0 ビットで埋め、パディング記号は付けない。
 *            復号は floor(6m/8) バイトを取り出す。m % 4 == 1 の長さと、0 でない余りビットは 'format' エラー。
 * CSV      : UTF-8 BOM + "slot,line,data" + 1 行 40 かな。スロットごとに独立した blob（行をスロット単位で連結して復号）。
 */
(function () {
  'use strict';
  var NT = (typeof window !== 'undefined' ? (window.NT = window.NT || {}) : (globalThis.NT = globalThis.NT || {}));

  const VERSION = 1;
  const AAD = 'nekota-tower/v1';
  const MAGIC = 'NKT1';
  const HEADER = 'slot,line,data';
  const BOM = '﻿';
  const LINE_KANA = 40;
  const PBKDF2_ITER = 600000;
  const FLAG_PASSWORD = 1;
  const FLAG_DEFLATED = 2;
  const MAX_LINES = 100000;

  // 埋め込み鍵。ソースを読めば分かるので暗号としての安全性はなく、CSV を手で書き換えにくくする
  // 「難読化」に過ぎない。本当に守りたい場合は opts.password（PBKDF2 → AES-GCM）を使う。
  const EMBEDDED_KEY = new Uint8Array([
    193, 214, 179, 82, 249, 124, 75, 70, 65, 201, 102, 73, 147, 251, 185, 52,
    217, 36, 179, 208, 70, 75, 138, 94, 253, 11, 153, 91, 68, 166, 202, 95
  ]);

  // 凍結表（64 字、重複なし）。見分けにくい対を除外した: ぬ(め) ね・わ(れ) ろ(る) ほ(は) さ(ち) ぢ(じ)。
  // 基本 40 字 + 濁音・半濁音 24 字。変更したら KANA_HASH も更新すること。
  const KANA = 'あいうえおかきくけこしすせそたちつてとなにのはひふへまみむめもやゆよらりるれをん' +
               'がぎぐげござじずぜぞだづでどばびぶべぼぱぴぷぺぽ';
  const KANA_HASH = '9ac27118c62c584b225393593656d1056701390dce4c3025f7ebd6e2e53b90e9';
  const KANA_INDEX = new Map();
  Array.from(KANA).forEach((ch, i) => { KANA_INDEX.set(ch, i); });
  if (KANA.length !== 64 || KANA_INDEX.size !== 64) throw new Error('04_codec: KANA table is broken');

  class CodecError extends Error {
    constructor(code) {
      super('CodecError: ' + code); // 詳細は載せない（呼び出し側で文言を統一する）
      this.name = 'CodecError';
      this.code = code; // 'format' | 'auth' | 'version' | 'unsupported'
    }
  }
  const fail = (code) => new CodecError(code);

  const G = globalThis;
  const subtle = (G.crypto && G.crypto.subtle) ? G.crypto.subtle : null;
  const hasDeflate = typeof G.CompressionStream === 'function' && typeof G.DecompressionStream === 'function';
  const enc = new TextEncoder();
  const dec = new TextDecoder('utf-8', { fatal: true });

  function isSupported() {
    return !!(subtle && hasDeflate && typeof G.TextEncoder === 'function');
  }
  function randomBytes(n) {
    return G.crypto.getRandomValues(new Uint8Array(n));
  }
  function concat(parts) {
    const out = new Uint8Array(parts.reduce((s, p) => s + p.length, 0));
    let o = 0;
    parts.forEach((p) => { out.set(p, o); o += p.length; });
    return out;
  }
  async function pipe(bytes, stream) {
    return new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(stream)).arrayBuffer());
  }
  function sha256hex(bytes) {
    return subtle.digest('SHA-256', bytes).then((buf) =>
      Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, '0')).join(''));
  }
  // 凍結表が改変されていないか（起動時にも一度確認してコンソールへ出す）
  function verifyKana() {
    if (!subtle) return Promise.resolve(false);
    return sha256hex(enc.encode(KANA)).then((h) => h === KANA_HASH);
  }

  // ---- かな64 ----
  function kanaEncode(bytes) {
    if (!(bytes instanceof Uint8Array)) throw fail('format');
    let out = '';
    let acc = 0;
    let nbits = 0;
    for (let i = 0; i < bytes.length; i++) {
      acc = (acc << 8) | bytes[i];
      nbits += 8;
      while (nbits >= 6) {
        nbits -= 6;
        out += KANA[(acc >> nbits) & 63];
      }
      acc &= (1 << nbits) - 1;
    }
    if (nbits > 0) out += KANA[(acc << (6 - nbits)) & 63]; // 余りは 0 埋め
    return out;
  }
  function kanaDecode(str) {
    if (typeof str !== 'string') throw fail('format');
    const chars = Array.from(str);
    if (chars.length % 4 === 1) throw fail('format'); // この長さは符号化では生じない
    const out = new Uint8Array(Math.floor(chars.length * 6 / 8));
    let acc = 0;
    let nbits = 0;
    let j = 0;
    for (const ch of chars) {
      const v = KANA_INDEX.get(ch);
      if (v === undefined) throw fail('format');
      acc = (acc << 6) | v;
      nbits += 6;
      if (nbits >= 8) {
        nbits -= 8;
        out[j++] = (acc >> nbits) & 255;
        acc &= (1 << nbits) - 1;
      }
    }
    if (acc !== 0) throw fail('format'); // 余りビットが 0 でない
    return out;
  }

  // ---- 暗号 ----
  async function getKey(password, salt) {
    const usage = ['encrypt', 'decrypt'];
    if (password == null) return subtle.importKey('raw', EMBEDDED_KEY, 'AES-GCM', false, usage);
    const base = await subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveKey']);
    return subtle.deriveKey({ name: 'PBKDF2', salt, iterations: PBKDF2_ITER, hash: 'SHA-256' },
      base, { name: 'AES-GCM', length: 256 }, false, usage);
  }
  async function seal(plain, password) {
    if (!subtle) throw fail('unsupported');
    let flags = 0;
    let body = plain;
    if (hasDeflate) { flags |= FLAG_DEFLATED; body = await pipe(plain, new G.CompressionStream('deflate-raw')); }
    const salt = password != null ? randomBytes(16) : new Uint8Array(0);
    if (password != null) flags |= FLAG_PASSWORD;
    const iv = randomBytes(12);
    const key = await getKey(password, salt);
    const ct = new Uint8Array(await subtle.encrypt({ name: 'AES-GCM', iv, additionalData: enc.encode(AAD) }, key, body));
    return concat([enc.encode(MAGIC), Uint8Array.of(flags), salt, iv, ct]);
  }
  async function open(blob, password) {
    if (!subtle) throw fail('unsupported');
    if (blob.length < 5) throw fail('format');
    const magic = String.fromCharCode(blob[0], blob[1], blob[2], blob[3]);
    if (magic.slice(0, 3) !== MAGIC.slice(0, 3)) throw fail('format');
    if (magic !== MAGIC) throw fail('version');
    const flags = blob[4];
    if (flags & ~(FLAG_PASSWORD | FLAG_DEFLATED)) throw fail('unsupported');
    const withPw = !!(flags & FLAG_PASSWORD);
    let p = 5;
    const salt = withPw ? blob.slice(p, p + 16) : new Uint8Array(0);
    p += salt.length;
    const iv = blob.slice(p, p + 12);
    p += 12;
    const ct = blob.slice(p);
    if (iv.length !== 12 || salt.length !== (withPw ? 16 : 0) || ct.length < 16) throw fail('format');
    if (withPw && password == null) throw fail('auth');
    let body;
    try {
      const key = await getKey(withPw ? password : null, salt);
      body = new Uint8Array(await subtle.decrypt({ name: 'AES-GCM', iv, additionalData: enc.encode(AAD) }, key, ct));
    } catch (e) {
      throw fail('auth'); // 鍵違い・改ざんはすべて auth（内訳は漏らさない）
    }
    if (flags & FLAG_DEFLATED) {
      if (!hasDeflate) throw fail('unsupported');
      try { body = await pipe(body, new G.DecompressionStream('deflate-raw')); } catch (e) { throw fail('format'); }
    }
    let obj;
    try { obj = JSON.parse(dec.decode(body)); } catch (e) { throw fail('format'); }
    if (!obj || typeof obj !== 'object') throw fail('format');
    if (obj.v !== VERSION) throw fail('version');
    if (!Array.isArray(obj.entries)) throw fail('format');
    return obj;
  }

  // ---- CSV ----
  function isRecord(r) { return !!r && typeof r === 'object'; }
  function checkEntries(entries) {
    if (!Array.isArray(entries) || entries.length === 0) throw fail('format');
    const seen = new Set();
    for (const e of entries) {
      if (!e || !Number.isInteger(e.slot) || e.slot < 1 || e.slot > 3 || !isRecord(e.record)) throw fail('format');
      if (seen.has(e.slot)) throw fail('format');
      seen.add(e.slot);
    }
  }
  function passwordOf(opts) {
    const pw = opts && opts.password;
    return (typeof pw === 'string' && pw.length > 0) ? pw : null;
  }

  // entries: [{slot:1..3, record:Object}] → BOM 付き CSV 文字列。スロットごとに 1 blob。
  async function encodeCard(entries, opts) {
    checkEntries(entries);
    const password = passwordOf(opts);
    const lines = [HEADER];
    for (const e of entries) {
      const plain = enc.encode(JSON.stringify({ v: VERSION, entries: [{ slot: e.slot, record: e.record }] }));
      const kana = kanaEncode(await seal(plain, password));
      for (let i = 0, n = 0; i < kana.length; i += LINE_KANA, n++) {
        lines.push(e.slot + ',' + n + ',' + kana.slice(i, i + LINE_KANA));
      }
    }
    return BOM + lines.join('\n') + '\n';
  }

  // CSV 文字列 → [{slot, record}]（slot 昇順）。失敗は CodecError。
  async function decodeCard(csvText, opts) {
    if (typeof csvText !== 'string') throw fail('format');
    const text = csvText.charCodeAt(0) === 0xFEFF ? csvText.slice(1) : csvText;
    const password = passwordOf(opts);
    const groups = new Map(); // slot → Map(line → data)
    for (const raw of text.split(/\r\n|\n|\r/)) {
      const line = raw.trim();
      if (!line) continue;
      const cells = line.split(',').map((s) => s.trim());
      if (cells.length !== 3) throw fail('format');
      if (cells.join(',').toLowerCase() === HEADER) continue;
      if (!/^\d{1,3}$/.test(cells[0]) || !/^\d{1,6}$/.test(cells[1])) throw fail('format');
      const slot = Number(cells[0]);
      const n = Number(cells[1]);
      const data = cells[2].replace(/[\s　]+/g, '');
      if (!data || n >= MAX_LINES) throw fail('format');
      if (!groups.has(slot)) groups.set(slot, new Map());
      const g = groups.get(slot);
      if (g.has(n)) throw fail('format'); // 行番号の重複
      g.set(n, data);
    }
    if (groups.size === 0) throw fail('format');
    const out = [];
    for (const [slot, g] of groups) {
      let kana = '';
      for (let i = 0; i < g.size; i++) {
        if (!g.has(i)) throw fail('format'); // 欠番
        kana += g.get(i);
      }
      const obj = await open(kanaDecode(kana), password);
      for (const ent of obj.entries) {
        if (!ent || ent.slot !== slot || !isRecord(ent.record)) throw fail('format');
        out.push({ slot: ent.slot, record: ent.record });
      }
    }
    out.sort((a, b) => a.slot - b.slot);
    return out;
  }

  // 'nekota-tower_card_YYYYMMDD_slotN.csv'（呼び出し側のローカル時刻）
  function fileName(slot, date) {
    const d = date instanceof Date ? date : new Date(date === undefined ? Date.now() : date);
    if (!Number.isInteger(slot) || Number.isNaN(d.getTime())) throw fail('format');
    const p = (n) => String(n).padStart(2, '0');
    return 'nekota-tower_card_' + d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate()) + '_slot' + slot + '.csv';
  }

  NT.Codec = Object.freeze({
    VERSION, AAD, KANA, KANA_HASH, LINE_KANA, CodecError,
    encodeCard, decodeCard, kanaEncode, kanaDecode, isSupported, fileName, verifyKana
  });

  verifyKana().then((ok) => { if (subtle && !ok) console.error('04_codec: KANA_HASH mismatch'); });

  if (typeof module !== 'undefined') module.exports = NT.Codec;
})();
