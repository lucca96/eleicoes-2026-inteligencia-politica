from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_CAMARA_DIR = PROJECT_ROOT / "data" / "raw" / "camara"
RAW_SENADO_DIR = PROJECT_ROOT / "data" / "raw" / "senado"
RAW_TSE_DIR = PROJECT_ROOT / "data" / "raw" / "tse"
RAW_ALERJ_DIR = PROJECT_ROOT / "data" / "raw" / "alerj"
REPORTS_DIR = PROJECT_ROOT / "reports"
