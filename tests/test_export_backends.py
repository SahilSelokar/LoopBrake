"""Each tool's README settings against a stand-in that enforces its published rules (research R9).

The stand-ins encode the documented rules as of 2026-10-02; a real Collector and Jaeger are checked by
hand (quickstart scenario 7).
"""
import os

import pytest

from loopbrake import otlp, records
from mimic_backends import Backend
from test_otlp import task, write

BASIC = "Authorization=Basic%20aW5zdGFuY2U6dG9rZW4="
# tool -> the settings the README shows (contracts/otlp.md, "Settings per tool"), with the base path
RIGHT = {
    "collector": ("", {}),
    "datadog": ("", {"OTEL_EXPORTER_OTLP_HEADERS": "dd-api-key=0123456789abcdef"}),
    "grafana": ("", {"OTEL_EXPORTER_OTLP_HEADERS": BASIC, "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "cumulative"}),
    "honeycomb": ("", {"OTEL_EXPORTER_OTLP_HEADERS": "x-honeycomb-team=0123456789abcdef"}),
    "langfuse": ("/api/public/otel", {"OTEL_EXPORTER_OTLP_HEADERS": BASIC, "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "none"}),
    "jaeger": ("", {"OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "none"}),
}
# tool -> (a wrong setting, the path that refuses it, the status)
WRONG = {
    "datadog": ({"OTEL_EXPORTER_OTLP_HEADERS": "dd-api-key=0123456789abcdef",
                 "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "cumulative"}, "/v1/metrics", 400),
    "grafana": ({"OTEL_EXPORTER_OTLP_HEADERS": BASIC}, "/v1/metrics", 400),  # delta, the default
    "langfuse": ({"OTEL_EXPORTER_OTLP_HEADERS": BASIC}, "/api/public/otel/v1/metrics", 404),
    "jaeger": ({}, "/v1/metrics", 404),
    "phoenix": ({}, "/v1/traces", 415),
}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for k in list(os.environ):
        if k.startswith(("OTEL_", "LOOPBRAKE_EXPORT")):
            monkeypatch.delenv(k)
    monkeypatch.setenv("LOOPBRAKE_HOME", str(tmp_path / "lb"))
    monkeypatch.setenv("LOOPBRAKE_EXPORT", "otlp")
    made = []

    def start(tool, base, env):
        backend = Backend(tool)
        made.append(backend)
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", backend.url + base)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        home = records.home()
        otlp.begin(home)
        write(home, "s1", task("a", tokens=10))
        write(home, "s1", task("b", calls=4, stop_at=4, t0=10))
        return home, backend
    yield start
    for b in made:
        b.close()


@pytest.mark.parametrize("tool", RIGHT)
def test_readme_settings_are_accepted(setup, tool):
    base, env = RIGHT[tool]
    home, backend = setup(tool, base, env)
    r = otlp.export_pending()
    assert r["ok"], (tool, r)
    paths = {p for p, *_ in backend.requests}
    wants_metrics = env.get("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT") != "none"
    assert paths == {f"{base}/v1/traces"} | ({f"{base}/v1/metrics"} if wants_metrics else set())
    assert all(status == 200 for *_, status in backend.requests)


@pytest.mark.parametrize("tool", WRONG)
def test_wrong_settings_are_refused_recorded_and_not_retried(setup, tool):
    env, path, status = WRONG[tool]
    home, backend = setup(tool, "/api/public/otel" if tool == "langfuse" else "", env)
    r = otlp.export_pending()
    assert not r["ok"] and r["status"] == status, (tool, r)
    assert otlp.load_state(home)["last"]["status"] == status
    assert [p for p, *_ in backend.requests].count(path) == 1
