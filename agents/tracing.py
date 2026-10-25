"""OpenTelemetry tracing for the agents.

Microsoft Agent Framework emits spans for every workflow run, every executor and every model call
(GenAI semantic conventions: model, tokens, duration). Here we collect them in memory so the dashboard's
trace panel can show the workflow tree live (`GET /api/spans`), and, when OTEL_EXPORTER_OTLP_ENDPOINT
is set, also send them to any OTLP backend.

Needs the OpenTelemetry SDK. Without it, tracing is simply off and everything else runs the same.
Prompts and replies are never recorded (sensitive data stays off).
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Any

log = logging.getLogger("gameday.tracing")

MAX_SPANS = 600
_collector: Any = None


def setup() -> bool:
    """Turn tracing on once at startup. Returns whether spans are being collected."""
    global _collector
    if _collector is not None:
        return True
    try:
        from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

        from agent_framework.observability import configure_otel_providers
    except ImportError:
        log.info("OpenTelemetry SDK not installed: agent tracing is off")
        return False

    class Collector(SpanExporter):
        def __init__(self) -> None:
            self.spans: deque[dict[str, Any]] = deque(maxlen=MAX_SPANS)
            self.lock = threading.Lock()

        def export(self, spans: Any) -> Any:
            with self.lock:
                for s in spans:
                    self.spans.append(_row(s))
            return SpanExportResult.SUCCESS

        def shutdown(self) -> None:
            return None

    _collector = Collector()
    try:
        configure_otel_providers(service_name="gameday-intelligence", exporters=[_collector],
                                 enable_sensitive_data=False)
    except Exception as e:  # tracing must never stop the app
        log.warning("could not configure OpenTelemetry: %s", e)
        _collector = None
        return False
    return True


KEEP = ("gen_ai.operation.name", "gen_ai.request.model", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
        "gen_ai.agent.name", "executor.id", "executor.type", "workflow.name", "workflow.id", "message.type")


def _row(span: Any) -> dict[str, Any]:
    ctx, parent = span.get_span_context(), span.parent
    attrs = {k: v for k, v in (span.attributes or {}).items()
             if (k in KEEP or k.startswith(("workflow", "executor"))) and not k.endswith("definition")}
    return {
        "trace": f"{ctx.trace_id:032x}", "id": f"{ctx.span_id:016x}",
        "parent": f"{parent.span_id:016x}" if parent else None,
        "name": span.name, "start": span.start_time / 1e9 if span.start_time else None,
        "ms": round((span.end_time - span.start_time) / 1e6, 1) if span.end_time and span.start_time else None,
        "status": span.status.status_code.name if span.status else "UNSET",
        "attrs": {k: v if isinstance(v, (int, float, str, bool)) else str(v) for k, v in attrs.items()},
    }


def recent(limit: int = 200) -> dict[str, Any]:
    """The latest spans, newest last, for the trace panel."""
    if _collector is None:
        return {"enabled": False, "spans": []}
    with _collector.lock:
        spans = list(_collector.spans)[-limit:]
    return {"enabled": True, "spans": spans}
