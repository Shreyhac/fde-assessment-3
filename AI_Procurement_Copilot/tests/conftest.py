# Shreyansh Arora | 24bcs10252. Unit tests never use paid inference by accident.
import pytest
@pytest.fixture(autouse=True)
def offline_default(monkeypatch):
    monkeypatch.setenv('COPILOT_MODE','offline')
