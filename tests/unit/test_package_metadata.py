from __future__ import annotations

import re

import molvault


def test_package_exposes_semantic_version() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", molvault.__version__)
