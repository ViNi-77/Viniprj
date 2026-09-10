"""定数・設定・実行コンフィグ.

定数値は復元版 (restored/box_copy_gui_direct_context_mode_fixed.py) と同一。
新機能のオプションは RunConfig に集約し、既定値は従来挙動互換とする。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# ---- 原本由来の定数（変更しない） ----
TARGET_EXTENSIONS = ['.doc', '.docx', '.txt', '.pdf', '.xlsx', '.xlsm', '.pptx', '.pptm', '.zip']
ZIP_READABLE_EXTENSIONS = [ext for ext in TARGET_EXTENSIONS if ext != '.zip']
EXCLUDE_DIRS = ['ChatGPT用コンテキストファイル生成', '収集データ', '生成コンテキスト', '管理']

MAX_TEXT_CHARS_PER_CONTEXT_RECORD = 12000
MAX_MARKDOWN_CHARS_PER_FILE = 120000
COPYRIGHT_TEXT = 'Copyright (c) 2026 第２ユニット生技部アルミ加工開発室. All rights reserved.'
M365_CONTEXT_BASENAME = 'M365AgentContext'
M365_CONTEXT_TARGET_CHARS_PER_FILE = 30000
M365_CONTEXT_MAX_BODY_FILES = 19
M365_CONTEXT_ARCHIVE_DIR_NAME = 'Archive'
MAX_SUMMARY_CHARS = 1200
MAX_ZIP_FILES = 300
MAX_ZIP_ENTRY_BYTES = 52428800
MAX_ZIP_TOTAL_BYTES = 314572800

SEARCH_ROOT_DEFAULT = Path(
    r"C:\BoxDrive\Box\第2ユニット生技部_全員\002_室運営\2026年\NZB00_アルミ開発室"
)
CONTEXT_OUTPUT_DIR_DEFAULT = Path(
    r"C:\BoxDrive\Box\第2ユニット生技部_全員\002_室運営\2026年\NZB00_アルミ開発室\2G\401_内製ソフト\ChatGPT用コンテキストファイル生成\生成コンテキスト"
)
BASE_DIR_DEFAULT = Path(
    r"C:\BoxDrive\Box\第2ユニット生技部_全員\002_室運営\2026年\NZB00_アルミ開発室\2G\401_内製ソフト\ChatGPT用コンテキストファイル生成\管理"
)

LOG_FILENAME = 'box_copy_gui_log.txt'
SETTINGS_FILENAME = 'box_copy_gui_settings.json'
CACHE_DB_FILENAME = 'extract_cache.db'
REPORT_FILENAME = '_AI_CONTEXT_REPORT.md'

# 日本語テキストのトークン数推定係数（文字数 / この値 ≒ トークン数）
TOKEN_CHARS_PER_TOKEN_DEFAULT = 1.4
# トークン基準の容量管理を選んだ場合の1ファイル目標トークン数
M365_CONTEXT_TARGET_TOKENS_PER_FILE = 21000


@dataclass
class RunConfig:
    """1回の生成実行の設定。既定値はすべて従来挙動互換。"""

    search_root: Path
    context_output_dir: Path
    base_dir: Path | None = None

    # 改善①: インクリメンタル更新
    use_cache: bool = True
    full_rescan: bool = False

    # v2.1 F2: ドライラン（見積のみ・ファイル書き出しなし）
    dry_run: bool = False

    # v2.1 F1: 再アップロード指示書 (_AI_CONTEXT_UPLOAD.md)
    write_upload_note: bool = True

    # v3 柱3: 文書健康診断 (_AI_CONTEXT_HEALTH.md)
    write_health: bool = True

    # v3 柱2: 人間向け読解キット (_HUMAN_DIGEST/*.md)
    human_digest: bool = False
    # v3: Word の見出しスタイル・章番号を構造マーカーとして残す
    # （目次抽出とセマンティック分割の精度が上がる）
    mark_docx_headings: bool = True

    # v3 B5: 1ファイルの解析タイムアウト（秒）。0 で無効
    extract_timeout_seconds: int = 60
    # v3 B6: JSONL の text_excerpt に本文全体を複製するか（原本互換用）
    jsonl_full_excerpt: bool = False
    jsonl_excerpt_chars: int = 300

    # v3 柱0: 原子的公開。完全成功時のみ既存ナレッジを差し替える
    force_publish: bool = False        # サニティチェックを無視して公開する
    publish_min_ratio: float = 0.5     # 前回比でこの割合を下回ったら公開を保留
    # ステージングへ書き出す間も、生成物の本文には本来の公開先を記載するために使う
    final_output_dir: Path | None = None

    # v2.1 F3: Teams Incoming Webhook 通知（空なら無効）
    teams_webhook_url: str = ''

    # v2.1 F4: Box Drive オンラインオンリーの扱い
    cloud_only_mode: str = 'download'     # 'download'(従来) | 'skip' | 'warn'

    # v2.1 F5: 機密情報スキャン
    sensitive_scan: str = 'warn'          # 'off' | 'warn' | 'mask' | 'block'

    # v2.1 F6: 重複・類似文書検出
    dedupe_mode: str = 'warn'             # 'off' | 'warn' | 'exclude'
    dedupe_threshold: float = 0.90

    # v2.1 F7: OCR（needs_ocr のPDFに実行）
    ocr_mode: str = 'off'                 # 'off' | 'auto'
    ocr_max_pages: int = 30

    # 改善②: 抽出カバレッジと透明性
    skip_temp_files: bool = True          # ~$ や .~ のロック/一時ファイルを除外
    enable_doc_conversion: bool = True    # .doc の変換プラグインを試す
    write_report: bool = True             # _AI_CONTEXT_REPORT.md を出力
    text_encoding_mode: str = 'auto'      # 'auto'(charset判定) | 'legacy'(utf-8 ignore)

    # 改善③: チャンクとトークン
    chunk_mode: str = 'semantic'          # 'semantic' | 'legacy'
    chunk_overlap_ratio: float = 0.12
    summary_mode: str = 'headings'        # 'headings' | 'legacy'
    token_chars_per_token: float = TOKEN_CHARS_PER_TOKEN_DEFAULT
    m365_capacity_mode: str = 'chars'     # 'chars' | 'tokens'

    # 改善⑤: 収録優先度・分割
    sort_mode: str = 'path'               # 'path' | 'mtime_desc'
    priority_folders: list[str] = field(default_factory=list)
    split_by_subfolder: bool = False      # サブフォルダごとに別パッケージを生成
    m365_packing: str = 'sequential'      # 'sequential' | 'bestfit'
    index_enriched: bool = True           # INDEXにファイル別要約・差分・未収録理由を追記

    max_chars_per_record: int = MAX_TEXT_CHARS_PER_CONTEXT_RECORD

    def __post_init__(self):
        self.search_root = Path(self.search_root)
        self.context_output_dir = Path(self.context_output_dir)
        if self.base_dir is None:
            self.base_dir = self.context_output_dir.parent / '管理'
        self.base_dir = Path(self.base_dir)

    @property
    def display_output_dir(self) -> Path:
        """生成物の本文に記載する公開先（ステージング中も本来の公開先を指す）."""
        return self.final_output_dir or self.context_output_dir

    @property
    def log_path(self) -> Path:
        return self.base_dir / LOG_FILENAME

    @property
    def settings_path(self) -> Path:
        return self.base_dir / SETTINGS_FILENAME

    @property
    def cache_db_path(self) -> Path:
        return self.base_dir / CACHE_DB_FILENAME

    @property
    def context_md_path(self) -> Path:
        return self.context_output_dir / '_AI_CONTEXT_SUMMARY.md'

    @property
    def context_jsonl_path(self) -> Path:
        return self.context_output_dir / '_AI_CONTEXT_DATA.jsonl'

    @property
    def report_path(self) -> Path:
        return self.context_output_dir / REPORT_FILENAME

    @property
    def m365_target_chars(self) -> int:
        return M365_CONTEXT_TARGET_CHARS_PER_FILE

    @property
    def m365_target_tokens(self) -> int:
        return M365_CONTEXT_TARGET_TOKENS_PER_FILE

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, round(len(text) / self.token_chars_per_token))

    def legacy(self) -> "RunConfig":
        """従来挙動（restored 版と同一出力）の設定を返す。パリティテスト用。"""
        import dataclasses
        return dataclasses.replace(
            self,
            use_cache=False,
            skip_temp_files=False,
            enable_doc_conversion=False,
            write_report=False,
            text_encoding_mode='legacy',
            dry_run=False,
            write_upload_note=False,
            force_publish=True,   # 原本は常に上書きしていたため
            extract_timeout_seconds=0,
            jsonl_full_excerpt=True,
            human_digest=False,
            mark_docx_headings=False,
            write_health=False,

            teams_webhook_url='',
            cloud_only_mode='download',
            sensitive_scan='off',
            dedupe_mode='off',
            ocr_mode='off',
            chunk_mode='legacy',
            summary_mode='legacy',
            m365_capacity_mode='chars',
            sort_mode='path',
            priority_folders=[],
            split_by_subfolder=False,
            m365_packing='sequential',
            index_enriched=False,
        )


def load_settings(settings_path: Path) -> dict:
    """設定 JSON を読む。原本互換 + 追加キーはそのまま保持。"""
    try:
        if settings_path.exists():
            with open(settings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_settings(settings_path: Path, data: dict) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
