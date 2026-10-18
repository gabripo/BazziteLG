import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Keep tests independent of a real install in /etc/lgtvcontrol."""
    import lgtv
    for name in ("INPUT_FILE", "MAC_FILE", "DISABLED_FILE"):
        monkeypatch.setattr(lgtv, name, tmp_path / f"_isolated_{name.lower()}")
