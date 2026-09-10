"""単位変換。Presentation JSON は pt を正とする。

- EMU: OOXML の内部単位。914400 EMU = 1 inch、12700 EMU = 1 pt
- px : Web 側は 96dpi 換算（1 pt = 96/72 px）
"""
from __future__ import annotations

EMU_PER_PT = 12700
EMU_PER_INCH = 914400
PX_PER_PT = 96 / 72


def emu_to_pt(value: int | float | None) -> float:
    return 0.0 if value is None else float(value) / EMU_PER_PT


def pt_to_emu(value: float) -> int:
    return int(round(float(value) * EMU_PER_PT))


def pt_to_px(value: float) -> float:
    return float(value) * PX_PER_PT


def px_to_pt(value: float) -> float:
    return float(value) / PX_PER_PT


def inch_to_pt(value: float) -> float:
    return float(value) * 72.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
