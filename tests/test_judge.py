import importlib.util
import io
import json
import urllib.error
from pathlib import Path

import pytest

from loopbrake.signals import Step

spec = importlib.util.spec_from_file_location("judge", Path(__file__).parents[1] / "eval" / "judge.py")
jd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jd)

KEY = "test-key-not-real"


def steps(n, obs="out"):
    return [Step(f"bash {{\"command\": \"cmd {i}\"}}", obs, False, 10) for i in range(n)]


# ---------- the state the judge sees ----------


def test_state_limits_and_cut_marks():
    long = [Step("a" * 900, "r" * 5000, False, 1)] * 5
    state, cut = jd.build_state("t" * 4000, long, 4)
    assert cut
    assert len(state["task"]) == 1500 and state["task"].endswith("…")
    assert len(state["earlier_actions"]) == 3 and all(len(a) <= 200 for a in state["earlier_actions"])
    assert len(state["action"]) == 600 and state["action"].endswith("…")
    assert state["result"] == "r" * 1200 + "…" + "r" * 800
    short, cut = jd.build_state("fix it", steps(2), 0)
    assert not cut and short["earlier_actions"] == [] and "…" not in json.dumps(short, ensure_ascii=False)
    assert jd.build_state("fix it", steps(5), 4)[0]["earlier_actions"] == [s.action for s in steps(5)[1:4]]


def test_key_is_stable_and_never_holds_the_access_key(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", KEY)
    body = jd.request_body(jd.build_state("fix it", steps(3), 2)[0])
    assert jd.judgment_key(body) == jd.judgment_key(json.loads(json.dumps(body)))
    assert KEY not in json.dumps(body) and body["model"] == "jev-1.13.0"
    assert set(body["questions"]) == {"progress", "kind"}


# ---------- reading answers ----------


def answer(noul=0.2, choice="repeated", p=0.8):
    return {"answers": {"progress": {"type": "noul", "noul": noul},
                        "kind": {"type": "choice", "choice": choice, "probabilities": {choice: p}}},
            "usage": {"input_tokens": 300, "output_tokens": 20}}


def test_parse_answer():
    got = jd.parse_answer(answer())
    assert (got["progress"], got["kind"], got["kind_p"], got["tokens"], got["status"]) == (0.2, "repeated", 0.8, 320, "ok")
    assert jd.parse_answer({"answers": {}, "usage": {}})["status"] == "unreadable"
    bad = jd.parse_answer(answer(noul=1.7))
    assert bad["status"] == "unreadable" and bad["progress"] is None


# ---------- calling Jev, with a fake network ----------


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_opener(script):
    calls = []

    def opener(req, timeout=None):
        calls.append(req)
        item = script[min(len(calls) - 1, len(script) - 1)]
        if isinstance(item, int):
            raise urllib.error.HTTPError(req.full_url, item, "err", {"Retry-After": "3"} if item == 429 else {}, io.BytesIO(b"{}"))
        if isinstance(item, Exception):
            raise item
        return FakeResponse(json.dumps(item).encode())

    return opener, calls


def test_retry_then_success_honours_retry_after():
    opener, calls = fake_opener([429, answer()])
    waits = []
    got = jd.call_jev({"x": 1}, KEY, opener=opener, sleep=waits.append)
    assert got["status"] == "ok" and len(calls) == 2 and waits == [3.0]
    assert calls[0].get_header("Authorization") == f"Bearer {KEY}"


def test_service_error_after_six_tries_and_422_unreadable():
    opener, calls = fake_opener([529])
    waits = []
    assert jd.call_jev({"x": 1}, KEY, opener=opener, sleep=waits.append)["status"] == "service_error"
    assert len(calls) == 6 and waits == [1, 2, 4, 8, 16]
    opener, calls = fake_opener([TimeoutError("slow")] * 6)
    assert jd.call_jev({"x": 1}, KEY, opener=opener, sleep=lambda s: None)["status"] == "service_error"
    opener, calls = fake_opener([422])
    assert jd.call_jev({"x": 1}, KEY, opener=opener, sleep=lambda s: None)["status"] == "unreadable" and len(calls) == 1


def test_401_stops_without_showing_the_key():
    opener, _ = fake_opener([401])
    with pytest.raises(jd.StopJudging) as err:
        jd.call_jev({"x": 1}, KEY, opener=opener, sleep=lambda s: None)
    assert "TYPESAFE_API_KEY" in str(err.value) and KEY not in str(err.value)


# ---------- refusals ----------


def test_refusals(monkeypatch, tmp_path):
    monkeypatch.setattr(jd, "candidate_committed", lambda: False)
    assert jd.main(["--group", "local-1"]) == 2
    assert jd.main(["--group", "made-up"]) == 2
    assert jd.main(["--group", "swe-gpt5mini"]) == 3  # holdout before the choice is committed
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(jd, "KEY_FILE", tmp_path / "no-key")
    assert jd.main(["--group", "swe-devstral"]) == 4
