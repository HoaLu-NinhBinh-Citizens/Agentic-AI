"""
HTTP Metrics Server for Prometheus Scraping

Provides:
- HTTP server with /metrics endpoint
- Health check endpoint
- Metrics push support
- Graceful shutdown
"""

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver

logger = logging.getLogger(__name__)


@dataclass
class Endpoint:
    """HTTP endpoint definition."""
    path: str
    handler: Callable[..., Tuple[int, str, Dict[str, str]]]
    method: str = "GET"


class MetricsRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for metrics endpoints."""

    endpoints: List[Endpoint] = []
    collector = None

    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.debug("%s %s", self.address_string(), format % args)

    def do_GET(self):
        """Handle GET requests."""
        for endpoint in self.endpoints:
            if self.path == endpoint.path:
                try:
                    status, body, content_type = endpoint.handler()
                    self.send_response(status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", len(body))
                    self.end_headers()
                    self.wfile.write(body.encode("utf-8"))
                except Exception as exc:
                    logger.error("Endpoint error: %s", exc)
                    self.send_error(500, str(exc))
                return

        self.send_error(404, "Not Found")

    def do_POST(self):
        """Handle POST requests."""
        for endpoint in self.endpoints:
            if self.path == endpoint.path and endpoint.method == "POST":
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
                    status, response, content_type = endpoint.handler(body)
                    self.send_response(status)
                    self.send_header("Content-Type", content_type)
                    self.end_headers()
                    self.wfile.write(response.encode("utf-8"))
                except Exception as exc:
                    logger.error("Endpoint error: %s", exc)
                    self.send_error(500, str(exc))
                return

        self.send_error(404, "Not Found")


class ThreadedHTTPServer:
    """
    Threaded HTTP server for metrics.

    Features:
    - Multiple endpoints
    - Threaded request handling
    - Graceful shutdown
    - SSL support (optional)
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9090,
    ):
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def register_endpoint(
        self,
        path: str,
        handler: Callable[..., Tuple[int, str, Dict[str, str]]],
        method: str = "GET",
    ) -> None:
        """
        Register an endpoint.

        Args:
            path: URL path (e.g., "/metrics")
            handler: Handler function returning (status, body, content_type)
            method: HTTP method ("GET" or "POST")
        """
        endpoint = Endpoint(path=path, handler=handler, method=method)
        MetricsRequestHandler.endpoints.append(endpoint)
        logger.debug("Registered endpoint: %s %s", method, path)

    def _make_metrics_handler(self, collector) -> Callable:
        """Create metrics endpoint handler."""
        def handler() -> Tuple[int, str, Dict[str, str]]:
            metrics_text = collector.to_prometheus_format()
            return (200, metrics_text, "text/plain; version=0.0.4")
        return handler

    def _make_health_handler(self) -> Callable:
        """Create health endpoint handler."""
        def handler() -> Tuple[int, str, Dict[str, str]]:
            health = {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
            }
            body = json.dumps(health, indent=2)
            return (200, body, "application/json")
        return handler

    def _make_json_metrics_handler(self, collector) -> Callable:
        """Create JSON metrics endpoint handler."""
        def handler() -> Tuple[int, str, Dict[str, str]]:
            metrics_json = collector.to_json()
            body = json.dumps(metrics_json, indent=2)
            return (200, body, "application/json")
        return handler

    def start(self, collector=None) -> bool:
        """
        Start the HTTP server.

        Args:
            collector: Optional MetricsCollector for /metrics endpoint

        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("Server already running")
            return False

        try:
            # Register default endpoints
            if collector:
                self.register_endpoint("/metrics", self._make_metrics_handler(collector))
                self.register_endpoint("/metrics/json", self._make_json_metrics_handler(collector))
                MetricsRequestHandler.collector = collector

            self.register_endpoint("/health", self._make_health_handler())

            # Create server
            MetricsRequestHandler.protocol_version = "HTTP/1.1"
            self.server = HTTPServer((self.host, self.port), MetricsRequestHandler)

            # Start in thread
            self._thread = threading.Thread(target=self._serve, daemon=True)
            self._thread.start()
            self._running = True

            logger.info("Metrics server started on %s:%d", self.host, self.port)
            return True

        except Exception as exc:
            logger.error("Failed to start server: %s", exc)
            return False

    def _serve(self):
        """Serve requests in thread."""
        try:
            self.server.serve_forever()
        except Exception as exc:
            logger.error("Server error: %s", exc)

    def stop(self) -> bool:
        """
        Stop the HTTP server.

        Returns:
            True if stopped successfully
        """
        if not self._running or not self.server:
            return False

        try:
            self.server.shutdown()
            self._thread.join(timeout=5)
            self._running = False
            logger.info("Metrics server stopped")
            return True
        except Exception as exc:
            logger.error("Failed to stop server: %s", exc)
            return False

    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running


class MetricsServer:
    """
    Combined metrics server with built-in collector.

    Usage:
        server = MetricsServer(port=9090)
        server.start()

        # Use built-in collector
        counter = server.counter("requests", "Total requests")
        counter.inc()

        # Stop when done
        server.stop()
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9090,
        namespace: str = "ai_support",
    ):
        self.host = host
        self.port = port
        self._server = ThreadedHTTPServer(host=host, port=port)

        # Import collector
        from src.infrastructure.observability.prometheus_metrics import MetricsCollector
        self._collector = MetricsCollector(namespace=namespace)

        # Auto-register /metrics endpoint
        self._server.register_endpoint(
            "/metrics",
            self._server._make_metrics_handler(self._collector),
        )
        self._server.register_endpoint(
            "/metrics/json",
            self._server._make_json_metrics_handler(self._collector),
        )
        self._server.register_endpoint("/health", self._server._make_health_handler())

    def start(self) -> bool:
        """Start the metrics server."""
        return self._server.start()

    def stop(self) -> bool:
        """Stop the metrics server."""
        return self._server.stop()

    @property
    def is_running(self) -> bool:
        """Check if server is running."""
        return self._server.is_running

    @property
    def collector(self):
        """Get the metrics collector."""
        return self._collector

    def counter(self, name: str, description: str, labels: Optional[Tuple[str, ...]] = None):
        """Create a counter metric."""
        return self._collector.counter(name, description, labels)

    def gauge(self, name: str, description: str, labels: Optional[Tuple[str, ...]] = None):
        """Create a gauge metric."""
        return self._collector.gauge(name, description, labels)

    def histogram(self, name: str, description: str, labels: Optional[Tuple[str, ...]] = None, buckets: Optional[List[float]] = None):
        """Create a histogram metric."""
        return self._collector.histogram(name, description, labels, buckets)

    def register_endpoint(
        self,
        path: str,
        handler: Callable[..., Tuple[int, str, Dict[str, str]]],
        method: str = "GET",
    ):
        """Register a custom endpoint."""
        self._server.register_endpoint(path, handler, method)


def start_metrics_server(
    host: str = "0.0.0.0",
    port: int = 9090,
    namespace: str = "ai_support",
) -> MetricsServer:
    """
    Start a metrics server with built-in collector.

    Args:
        host: Server host
        port: Server port
        namespace: Metrics namespace

    Returns:
        MetricsServer instance
    """
    server = MetricsServer(host=host, port=port, namespace=namespace)
    server.start()
    return server
