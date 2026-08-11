"""Pytest bootstrap for academic-research-win.

Adds the skill root to sys.path so the `mappings` package and the
`workflows` directory are importable from tests regardless of where
pytest is invoked from.
"""
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))
