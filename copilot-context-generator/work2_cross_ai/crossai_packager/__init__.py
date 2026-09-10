"""AIサービス別コンテキストパッケージャ.

contextgen が生成する _AI_CONTEXT_DATA.jsonl（全チャンクの正規データ）を
入力に、Claude Projects / カスタムGPT / NotebookLM / M365 などの
サービス別制約（ファイル数上限・1ファイル容量・命名）に合わせた
アップロード用パッケージを生成する。
"""

__version__ = "1.0.0"
