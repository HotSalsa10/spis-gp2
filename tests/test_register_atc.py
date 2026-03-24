"""
tests/test_register_atc.py
---------------------------
Unit tests for helper functions in scripts/register_atc.py.

Covers _infer_levels() — the pure function that derives WHO ATC level codes
from a full ATC code string.  The main() entrypoint is a CLI wrapper and is
not tested here.
"""

import sys
from pathlib import Path

import pytest

# Make scripts/ importable without installing it as a package.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from register_atc import _infer_levels  # noqa: E402


# ---------------------------------------------------------------------------
# Tests: _infer_levels
# ---------------------------------------------------------------------------

def test_infer_levels_standard_code():
    """A 5-char level-4 ATC code (e.g. A10BA) should give level1='A', level2='A10'."""
    level1, level2 = _infer_levels("A10BA")
    assert level1 == "A"
    assert level2 == "A10"


def test_infer_levels_level5_code():
    """A 7-char level-5 substance code should still return the first letter and first 3 chars."""
    level1, level2 = _infer_levels("A10BA02")
    assert level1 == "A"
    assert level2 == "A10"


def test_infer_levels_single_letter():
    """A single-character code (top-level anatomical group) should map to itself for both levels."""
    level1, level2 = _infer_levels("A")
    assert level1 == "A"
    assert level2 == "A"


def test_infer_levels_lowercase_input():
    """Input is lowercased — function must normalise to uppercase before slicing."""
    level1, level2 = _infer_levels("a10ba")
    assert level1 == "A"
    assert level2 == "A10"


def test_infer_levels_two_char_code():
    """A 2-char code that is shorter than 3 chars should return the code itself as level2."""
    level1, level2 = _infer_levels("A1")
    assert level1 == "A"
    assert level2 == "A1"


def test_infer_levels_whitespace_stripped():
    """Leading/trailing whitespace in the input must be stripped before processing."""
    level1, level2 = _infer_levels("  N02BE  ")
    assert level1 == "N"
    assert level2 == "N02"
