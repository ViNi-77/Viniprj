/* 補完機 — ビルド。`node build.mjs` で completion-machine.html、`--light` で明テーマ、`--audit` で幾何の監査。
   幾何は parts.mjs、動きは live.js、数値は js/data.js と js/model.js（ビルド時の自己チェックにも使う）。 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "./vendor/anatomy/kit/iso-kit.mjs";
import * as G from "./vendor/anatomy/kit/lathe.mjs";
import * as A from "./vendor/anatomy/kit/audit.mjs";
import { kitScript } from "./vendor/anatomy/scripts/inline-kit.mjs";
import { makeParts } from "./parts.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const theme = process.argv.includes("--light") ? "light" : "dark";

/* モデルを読む（ブラウザと同じファイル） */
const dataSource = readFileSync(join(HERE, "js", "data.js"), "utf8");
const modelSource = readFileSync(join(HERE, "js", "model.js"), "utf8");
new Function(dataSource)();
new Function(modelSource)();
const { DATA, model } = globalThis.CM;

/* ---------- 世界座標（docs/02 §5） ---------- */
const PLATE = { x: -150, y: -95, w: 300, d: 190, r: 8 };
const W = {
  PLATE, PLATE_H: 12, FOOT_H: 5,
  TRAY: { x: -128, y: -18, w: 30, d: 36, r: 1.5 }, BINDER_TOP: 40, ARM_LEN: 18, STACK_MAX: 13, SHEET_T: 0.6,
  DESK: { x: -60, y: -45, w: 120, d: 90, r: 2 }, DESK_Z: 14, COLS: 5, ROWS: 4,
  SLOTS: ["intro", "intro", "ask", "sample", "sample", ...Array(4).fill("material"), ...Array(11).fill("history")],
  BIN: { x: -20, y: 50, w: 40, d: 30, r: 1.5 }, FALLEN_MAX: 3,
  PEN: { x: -64, y: 56, z: 3, len: 30 },
  GANTRY: { x0: -70, x1: 70, y: -54, z: 60 },
  DIAL: { x: 100, y: -38, r: 20, h: 10 },
  TAPE: { base: { x: 84, y: -8, w: 32, d: 16, r: 1.5 }, strip: { x: 92, y: 6, w: 12, d: 54, r: 0.5 }, z: 4, pitch: 6.2 }, WORDS: DATA.sentenceLen,
  METER: { x: 128, y: 64, r: 11, h: 5 },
  PINS: { block: { x: 82, y: 66, w: 30, d: 10, r: 1 }, count: DATA.stackedConditions, pitch: 5.5, up: 5 },
  LEVER: { x: -110, y: 60, z: 4, len: 16 },
};
const WIDTH = 760, HEIGHT = 440;
const P = k.fitProjection(
  [...k.boxCorners(PLATE, -W.PLATE_H - W.FOOT_H, 0), [W.GANTRY.x0, W.GANTRY.y, W.GANTRY.z + 7], [W.GANTRY.x1, W.GANTRY.y, W.GANTRY.z + 7], [W.DIAL.x + W.DIAL.r, W.DIAL.y, 20]],
  WIDTH, HEIGHT, { pad: 28, azimuth: 42, elevation: 30 },
);

/* ---------- 部品を記録しながら描く ---------- */
const R = A.recorder(P);
const back = [];
const parts = makeParts({ k, A, G, P, R, W, back });
parts.base();
parts.intake();
parts.desk();
parts.gantry();
parts.dialAndTape();
parts.meterAndLever();
A.settle(R, P);
R.items.sort((a, b) => a.key - b.key);
const groups = R.items.map((item) => `<g class="it" data-name="${item.name}"${item.attrs ?? ""}>${item.svg}</g>`);

const LABEL =
  "台の上の「補完機」。左に手紙の投入口と綴じ器、中央に20枠の机と、その上を走る読み取りヘッド、右に次の一語を選ぶ候補ダイヤルと答えを印字するテープ、手前に注意力メーターと条件ピン、机の奥に落ちた紙の受け皿、左奥に片付けレバー。ボタンで工程を1つずつ進めると、手紙が机に広がり、一語ずつ答えが印字され、往復を重ねると机から紙が落ちる。";
const svg = k.figureSvg({ width: WIDTH, height: HEIGHT, label: LABEL, body: [...back, `<g class="cm-machine">${groups.join("")}</g>`] });

/* ---------- 自己チェック（docs/03 §3） ---------- */
const check = model.selfCheck();
console.log("self-check", JSON.stringify(check));
const expect = { usageAtStep3: 75, roundsToOverflow: 2, droppedAtStep6: 1, shareAtStep7: 20 };
for (const [key, value] of Object.entries(expect)) if (check[key] !== value) throw new Error(`self-check ${key}: ${check[key]} != ${value} (docs/03 と不一致)`);

/* ---------- 実行時へ渡す定数 ---------- */
const LIVE_DATA = {
  P,
  W: { TRAY: W.TRAY, BINDER_TOP: W.BINDER_TOP, ARM_LEN: W.ARM_LEN, STACK_MAX: W.STACK_MAX, SHEET_T: W.SHEET_T, DESK: W.DESK, DESK_Z: W.DESK_Z, COLS: W.COLS, ROWS: W.ROWS, SLOTS: W.SLOTS, BIN: W.BIN, FALLEN_MAX: W.FALLEN_MAX, GANTRY: W.GANTRY, DIAL: W.DIAL, TAPE: W.TAPE, WORDS: W.WORDS, METER: W.METER, PINS: W.PINS, LEVER: W.LEVER },
  theme,
};
const CSS = readFileSync(join(HERE, "cm.css"), "utf8");
const LIVE = readFileSync(join(HERE, "live.js"), "utf8").replace("__DATA__", JSON.stringify(LIVE_DATA));

/* ---------- カードとページ ---------- */
const stepButtons = DATA.steps.map((s) => `<li><button type="button" class="cm-step" data-step="${s.n}" data-state="${s.n === 1 ? "next" : "locked"}"${s.n === 1 ? "" : " disabled"}><span class="cm-num">${s.n}</span><span class="cm-name">${s.name}</span></button></li>`).join("");
const nav = `<nav class="cm-steps" aria-label="工程">
<div class="cm-mode" role="group" aria-label="進め方"><button type="button" data-mode="manual" aria-pressed="true">手動</button><button type="button" data-mode="auto" aria-pressed="false">自動</button></div>
<ol>${stepButtons}</ol>
<button type="button" class="cm-restart">最初から</button>
</nav>`;
const plate = k.plateHtml({
  fig: "Fig 1",
  title: "補完機",
  hint: "ボタンで進む · Space で次へ",
  readout: model.readout(model.initial()),
  keys: [
    { mark: "lit", label: "読み取りヘッドのレンズ: 机の紙を読む" },
    { mark: "raised", label: "机の20枠: 一度に見えるのは、ここに載った紙だけ" },
    { mark: "flat", label: "印字テープ: 一語ずつ埋めた答え" },
  ],
  caption: "台の上の補完機。手紙が投入口から机に広がり、読み取りヘッドが読み、候補ダイヤルが次の一語を選んでテープに印字する。往復を重ねると机から古い紙が落ち、条件を積むと注意力メーターの針が下がる。",
  body: `<div class="iso-stage" tabindex="0" role="group" aria-label="補完機。Space か Enter で次の工程へ、Home で最初から。">${svg}<span class="cm-sr" role="status" aria-live="polite" data-status></span></div>`,
});
const app = `<style>${CSS}</style><div class="cm-app" id="cm-app">${nav}<div class="cm-main">${plate}
<p class="cm-hint"><span class="cm-hint-text" data-hint>①を押すと、手紙を書くところから始まります。</span> <span class="cm-sound" data-sound></span></p>
<p class="cm-idea">${DATA.bigIdea}</p>
<p class="cm-tags"><span class="cm-tag" data-tag="example">例示値</span><span>机の枚数・手紙の枚数・条件の数は、説明のための架空の量。${DATA.scaleNote}</span><span class="cm-tag" data-tag="public">公開値</span><span>本物の机の広さは公開資料の値（docs/03）。</span></p>
<div class="cm-cursor" data-cursor aria-hidden="true"></div>
</div></div>`;

const page = k
  .pageHtml({ title: "補完機 — 生成AIの中身を、動く機械で見る", theme, body: app, script: kitScript() + "\n" + dataSource + "\n" + modelSource + "\n" + LIVE, width: 980 })
  .replace('<html lang="en">', '<html lang="ja">');
const name = theme === "light" ? "completion-machine-light.html" : "completion-machine.html";
writeFileSync(join(HERE, name), page);
console.log("wrote", name, `${(page.length / 1024).toFixed(0)} KB`, `${R.items.length} items`);

A.auditOrExit(R, P, { crowd: [] });
