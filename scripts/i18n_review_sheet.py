# scripts/i18n_review_sheet.py
"""One markdown table per language for a partner reviewer (design I§5.4).

    micromamba run -n shiny python scripts/i18n_review_sheet.py de > review-de.md

Merges the three catalogues with the English beside each row. A convenience for the
reviewer, not a source of truth: the YAML files are. Never writes back.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from app.i18n import APP_LOCALES, PARAMS_LOCALES, params_reference_keys  # noqa: E402
from seagarden_dst.i18n import CORE_LOCALES  # noqa: E402


def _messages(root: Path, language: str) -> dict[str, str]:
    path = root / f"{language}.yaml"
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8"))["messages"]


def sheet(language: str) -> str:
    rows = [
        f"# Review sheet — {language}",
        "",
        "| Key | English | " + language + " |",
        "|---|---|---|",
    ]
    for _owner, root in (("core", CORE_LOCALES), ("app", APP_LOCALES)):
        english = _messages(root, "en")
        other = _messages(root, language)
        for key in sorted(english):
            rows.append(f"| `{key}` | {_cell(english[key])} | {_cell(other.get(key, ''))} |")
    other = _messages(PARAMS_LOCALES, language)
    for key, english_text in sorted(params_reference_keys().items()):
        rows.append(f"| `{key}` | {_cell(english_text)} | {_cell(other.get(key, ''))} |")
    return "\n".join(rows) + "\n"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: i18n_review_sheet.py <language>")
    sys.stdout.write(sheet(sys.argv[1]))
