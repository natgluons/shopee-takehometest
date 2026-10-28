from __future__ import annotations

import receipt_ai


def test_package_imports() -> None:
    assert receipt_ai.__version__ == "0.1.0"
