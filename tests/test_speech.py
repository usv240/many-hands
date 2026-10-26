"""The on-air voice reads only lines that passed the fairness check."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

os.environ["MANYHANDS_OFFLINE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.api.app import app  # noqa: E402
from services.api.speech import Voice, voice  # noqa: E402


def test_only_passing_lines_and_versions_become_speakable():
    v = Voice()
    v.approve_result(SimpleNamespace(status="ready", line="A fair line.", audit={"verdict": "fair"},
                                     variants=[{"text": "Kept.", "aired": True}, {"text": "Held.", "aired": False}]))
    assert v.allowed("A fair line.") and v.allowed("Kept.") and not v.allowed("Held.")
    v.approve_result(SimpleNamespace(status="ready", line="Number 8 cost them.", audit={"verdict": "unfair"}, variants=[]))
    v.approve_result(SimpleNamespace(status="held", line=None, audit=None, variants=[]))
    assert not v.allowed("Number 8 cost them.")


def test_the_api_refuses_to_read_a_line_that_did_not_pass():
    client = TestClient(app)
    r = client.post("/v1/speak", json={"text": "Number 8's howler cost them the goal."})
    assert r.status_code == 403 and "passed the fairness check" in r.json()["detail"]


def test_an_approved_line_offline_says_the_voice_is_hosted():
    voice.approve("A clearance in his own half by number 8 led to the goal.")
    r = TestClient(app).post("/v1/speak", json={"text": "A clearance in his own half by number 8 led to the goal."})
    assert r.status_code == 503
