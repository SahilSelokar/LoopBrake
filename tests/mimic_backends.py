"""Stand-ins for the tools LoopBrake exports to (research R9), so export is tested without vendor accounts.

Each one is a stdlib HTTP server on 127.0.0.1 that checks the generic OTLP JSON rules (R8), plus that
tool's published intake rules as of 2026-10-02. They can't catch undocumented behavior or later changes.
"""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_KEY = re.compile(r"[a-z][A-Za-z0-9]*")
_INT64 = {"startTimeUnixNano", "endTimeUnixNano", "timeUnixNano", "asInt", "intValue"}
_ENUMS = {"kind", "code", "aggregationTemporality"}
_IDS = {"traceId": 32, "spanId": 16, "parentSpanId": 16}


def otlp_problems(body):
    """What breaks the OTLP JSON encoding rules: hex ids, 64-bit integers as strings, integer enums,
    lowerCamelCase keys. An empty list means the body is fine."""
    out = []

    def walk(x):
        if isinstance(x, list):
            for y in x:
                walk(y)
        elif isinstance(x, dict):
            for k, v in x.items():
                if not _KEY.fullmatch(k):
                    out.append(f"key {k!r} isn't lowerCamelCase")
                if k in _IDS and not (isinstance(v, str) and re.fullmatch(f"[0-9a-f]{{{_IDS[k]}}}", v) and set(v) != {"0"}):
                    out.append(f"{k} {v!r} isn't {_IDS[k]} lowercase hex")
                if k in _INT64 and not (isinstance(v, str) and v.isdigit()):
                    out.append(f"{k} {v!r} isn't a decimal string")
                if k in _ENUMS and not isinstance(v, int):
                    out.append(f"{k} {v!r} isn't an integer")
                walk(v)
    walk(body)
    return out


def _temporalities(body):
    return {m["sum"]["aggregationTemporality"] for r in body.get("resourceMetrics", []) for s in r["scopeMetrics"]
            for m in s["metrics"] if "sum" in m}


# Each tool's rules: (path, headers, body) -> (status, reply) to refuse, or None to accept.

def _collector(path, headers, body):
    return None if path in ("/v1/traces", "/v1/metrics") else (404, "not found")


def _datadog(path, headers, body):
    if not headers.get("dd-api-key"):
        return 403, "missing API key"
    if 2 in _temporalities(body):
        return 400, "cumulative monotonic sums are not supported; use delta temporality"
    return _collector(path, headers, body)


def _grafana(path, headers, body):
    if not (headers.get("authorization") or "").startswith("Basic "):
        return 401, "authentication required"
    if 1 in _temporalities(body):
        return 400, "delta temporality is not supported; use cumulative"
    return _collector(path, headers, body)


def _honeycomb(path, headers, body):
    return (401, "missing x-honeycomb-team") if not headers.get("x-honeycomb-team") else _collector(path, headers, body)


def _langfuse(path, headers, body):
    if path != "/api/public/otel/v1/traces":
        return 404, "not found"
    return (401, "authentication required") if not (headers.get("authorization") or "").startswith("Basic ") else None


def _jaeger(path, headers, body):
    return None if path == "/v1/traces" else (404, "not found")


def _phoenix(path, headers, body):
    return 415, "unsupported content type; send application/x-protobuf"


RULES = {"collector": _collector, "datadog": _datadog, "grafana": _grafana, "honeycomb": _honeycomb,
         "langfuse": _langfuse, "jaeger": _jaeger, "phoenix": _phoenix}


class Backend:
    """A running stand-in. `requests` holds (path, headers, parsed body, status) for everything received.
    `replies` is a queue of (status, body, headers) the tests can push to force an answer."""

    def __init__(self, tool="collector"):
        self.rule, self.requests, self.replies = RULES[tool], [], []
        backend = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                headers = {k.lower(): v for k, v in self.headers.items()}
                status, reply, extra = backend._answer(self.path, headers, raw)
                backend.requests.append((self.path, headers, _parse(raw), status))
                data = reply.encode() if isinstance(reply, str) else json.dumps(reply).encode()
                self.send_response(status)
                for k, v in extra.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def _answer(self, path, headers, raw):
        if self.replies:
            return self.replies.pop(0)
        if headers.get("content-type") != "application/json" and self.rule is not _phoenix:
            return 415, "send application/json", {}
        body = _parse(raw)
        if body is None:
            return 400, "not JSON", {}
        problems = otlp_problems(body)
        if problems:
            return 400, "; ".join(problems), {}
        refused = self.rule(path, headers, body)
        return (*refused, {}) if refused else (200, {"partialSuccess": {}}, {})

    def bodies(self, path_end):
        return [b for p, _, b, _ in self.requests if p.endswith(path_end)]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def _parse(raw):
    try:
        return json.loads(raw)
    except ValueError:
        return None
