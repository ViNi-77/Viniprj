// 04_codec.js のテスト。実行: node --test scripts/codec_test.mjs（nekota-tower/ で）
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { randomBytes, createHash } from 'node:crypto';

const require = createRequire(import.meta.url);
const Codec = require('../src/js/04_codec.js');
const { CodecError } = Codec;

const record = (n) => ({
  name: 'ねこた' + n,
  floor: 10 - n,
  hp: 123,
  items: ['おすし', 'まぐろ', { id: 'key', note: '塔の鍵（第' + n + '層）' }],
  flags: { boss: false, metElder: true, quests: { q10: 'done', q9: 'open' } },
  playedMs: 1234567,
  emoji: '🐱',
});

async function rejectsWith(promise, codes) {
  let err;
  try { await promise; } catch (e) { err = e; }
  assert.ok(err instanceof CodecError, 'CodecError expected, got ' + err);
  assert.ok(codes.includes(err.code), 'code ' + err.code + ' not in ' + codes.join('/'));
}

test('isSupported in Node 22', () => {
  assert.equal(Codec.isSupported(), true);
  assert.equal(Codec.VERSION, 1);
  assert.equal(Codec.AAD, 'nekota-tower/v1');
});

test('kana table: 64 unique BMP chars, hash matches', async () => {
  const chars = Array.from(Codec.KANA);
  assert.equal(chars.length, 64);
  assert.equal(new Set(chars).size, 64);
  assert.ok(chars.every((c) => /^[ぁ-ゖ]$/.test(c)), 'all hiragana');
  const h = createHash('sha256').update(Codec.KANA, 'utf8').digest('hex');
  assert.equal(h, Codec.KANA_HASH);
  assert.equal(await Codec.verifyKana(), true);
});

test('kanaEncode/kanaDecode round trip for lengths 0..70', () => {
  for (let n = 0; n <= 70; n++) {
    const bytes = new Uint8Array(randomBytes(n));
    const s = Codec.kanaEncode(bytes);
    assert.equal(Array.from(s).length, Math.ceil(n * 8 / 6), 'symbol count for n=' + n);
    assert.deepEqual(Codec.kanaDecode(s), bytes, 'round trip n=' + n);
  }
  assert.equal(Codec.kanaEncode(new Uint8Array(0)), '');
  assert.deepEqual(Codec.kanaDecode(''), new Uint8Array(0));
});

test('kanaDecode rejects bad input', () => {
  assert.throws(() => Codec.kanaDecode('あ'), (e) => e.code === 'format'); // 長さ 1 mod 4
  assert.throws(() => Codec.kanaDecode('あいぬ'), (e) => e.code === 'format'); // 表外
  assert.throws(() => Codec.kanaDecode('あぽ'), (e) => e.code === 'format'); // 余りビット非 0
});

test('encodeCard → decodeCard identity (1 slot)', async () => {
  const entries = [{ slot: 2, record: record(2) }];
  const csv = await Codec.encodeCard(entries);
  assert.ok(csv.startsWith('﻿slot,line,data\n'));
  assert.deepEqual(await Codec.decodeCard(csv), entries);
});

test('encodeCard → decodeCard identity (3 slots), lines are 40 kana except last per slot', async () => {
  const entries = [1, 2, 3].map((s) => ({ slot: s, record: record(s) }));
  const csv = await Codec.encodeCard(entries);
  assert.deepEqual(await Codec.decodeCard(csv), entries);

  const lines = csv.slice(1).split('\n');
  assert.equal(lines[0], 'slot,line,data');
  assert.equal(lines[lines.length - 1], '');
  const body = lines.slice(1, -1);
  const perSlot = new Map();
  for (const l of body) {
    const m = /^([1-3]),(\d+),([^,]+)$/.exec(l);
    assert.ok(m, 'line shape: ' + l);
    const arr = perSlot.get(Number(m[1])) || [];
    assert.equal(Number(m[2]), arr.length, 'line numbers are sequential');
    assert.ok(Array.from(m[3]).every((c) => Codec.KANA.includes(c)), 'only table kana');
    arr.push(m[3]);
    perSlot.set(Number(m[1]), arr);
  }
  assert.deepEqual([...perSlot.keys()].sort(), [1, 2, 3]);
  for (const arr of perSlot.values()) {
    arr.slice(0, -1).forEach((d) => assert.equal(Array.from(d).length, 40));
    const last = Array.from(arr[arr.length - 1]).length;
    assert.ok(last >= 1 && last <= 40);
  }
});

test('each slot is independently decodable', async () => {
  const entries = [1, 3].map((s) => ({ slot: s, record: record(s) }));
  const csv = await Codec.encodeCard(entries);
  const only3 = csv.split('\n').filter((l) => !l.startsWith('1,')).join('\n');
  assert.deepEqual(await Codec.decodeCard(only3), [entries[1]]);
});

test('tamper (swap one kana) → auth or format', async () => {
  const csv = await Codec.encodeCard([{ slot: 1, record: record(1) }]);
  const lines = csv.split('\n');
  const i = Math.max(1, Math.floor(lines.length / 2));
  const cells = lines[i].split(',');
  const chars = Array.from(cells[2]);
  const k = Math.floor(chars.length / 2);
  chars[k] = chars[k] === 'あ' ? 'い' : 'あ';
  cells[2] = chars.join('');
  lines[i] = cells.join(',');
  await rejectsWith(Codec.decodeCard(lines.join('\n')), ['auth', 'format']);
});

test('password round trip; wrong/missing password → auth', async () => {
  const entries = [{ slot: 1, record: record(1) }, { slot: 2, record: record(2) }];
  const csv = await Codec.encodeCard(entries, { password: 'にゃんにゃん' });
  assert.deepEqual(await Codec.decodeCard(csv, { password: 'にゃんにゃん' }), entries);
  await rejectsWith(Codec.decodeCard(csv, { password: 'わんわん' }), ['auth']);
  await rejectsWith(Codec.decodeCard(csv), ['auth']);
  // 埋め込み鍵の blob に対してパスワードを渡しても無視される（鍵は flags で決まる）
  const plain = await Codec.encodeCard(entries);
  assert.deepEqual(await Codec.decodeCard(plain, { password: 'x' }), entries);
});

test('CSV with \\r\\n, BOM, blank lines, whitespace decodes', async () => {
  const entries = [{ slot: 3, record: record(3) }];
  const csv = await Codec.encodeCard(entries);
  const messy = '﻿\r\n\r\n' + csv.slice(1).split('\n')
    .map((l) => l ? '  ' + l.replace(/,/g, ' , ') + '  ' : l).join('\r\n\r\n') + '\r\n\r\n';
  assert.deepEqual(await Codec.decodeCard(messy), entries);
  // 行順が入れ替わっても line 番号で復元
  const lines = csv.slice(1).trim().split('\n');
  const shuffled = [lines[0], ...lines.slice(1).reverse()].join('\n');
  assert.deepEqual(await Codec.decodeCard(shuffled), entries);
});

test('header-only / empty / garbage CSV → format', async () => {
  await rejectsWith(Codec.decodeCard('﻿slot,line,data\n'), ['format']);
  await rejectsWith(Codec.decodeCard('slot,line,data\r\n\r\n'), ['format']);
  await rejectsWith(Codec.decodeCard(''), ['format']);
  await rejectsWith(Codec.decodeCard('1,0,あいうえ,extra'), ['format']);
  await rejectsWith(Codec.decodeCard('1,0,abcd'), ['format']);
  await rejectsWith(Codec.decodeCard('1,1,あいうえ'), ['format']); // 欠番 (line 0 がない)
  await rejectsWith(Codec.decodeCard('1,0,あいうえおか\n1,0,あいうえおか'), ['format']); // 重複
  await rejectsWith(Codec.decodeCard('1,0,あいうえおか'), ['format']); // magic 違い
  await rejectsWith(Codec.decodeCard(42), ['format']);
});

test('encodeCard rejects bad entries', async () => {
  await rejectsWith(Codec.encodeCard([]), ['format']);
  await rejectsWith(Codec.encodeCard([{ slot: 0, record: {} }]), ['format']);
  await rejectsWith(Codec.encodeCard([{ slot: 4, record: {} }]), ['format']);
  await rejectsWith(Codec.encodeCard([{ slot: 1, record: null }]), ['format']);
  await rejectsWith(Codec.encodeCard([{ slot: 1, record: {} }, { slot: 1, record: {} }]), ['format']);
});

test('version / unsupported flags detected', async () => {
  const bytes = new Uint8Array([0x4E, 0x4B, 0x54, 0x32, 0, ...new Uint8Array(40)]); // "NKT2"
  await rejectsWith(Codec.decodeCard('1,0,' + Codec.kanaEncode(bytes)), ['version']);
  const flags = new Uint8Array([0x4E, 0x4B, 0x54, 0x31, 0x80, ...new Uint8Array(40)]); // 未知の bit
  await rejectsWith(Codec.decodeCard('1,0,' + Codec.kanaEncode(flags)), ['unsupported']);
});

test('fileName format', () => {
  assert.equal(Codec.fileName(2, new Date(2026, 10, 6, 7, 15)), 'nekota-tower_card_20261106_slot2.csv');
  assert.equal(Codec.fileName(1, new Date(2027, 0, 1)), 'nekota-tower_card_20270101_slot1.csv');
  assert.match(Codec.fileName(3), /^nekota-tower_card_\d{8}_slot3\.csv$/);
});
