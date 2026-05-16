import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from src.application.api.app.aikicad_orchestrator import AIKiCadOrchestrator
from src.core.memory import AgentMemory
from src.domains.knowledge import KnowledgeCache
from src.domains.review import HumanReviewAudit
from src.application.services.path_finder_service import PathFinderService

try:
    import fitz
except ImportError:  # pragma: no cover - optional dependency guard
    fitz = None


class ReviewUIServer:
    """Small stdlib-only local review UI for KB and controlled memory."""

    def __init__(self, workspace_root: str = ".", port: int = 8765):
        self.workspace_root = Path(workspace_root).resolve()
        self.port = int(port)
        self.memory = AgentMemory(str(self.workspace_root))
        self.cache = KnowledgeCache(str(self.workspace_root))
        self.audit = HumanReviewAudit(str(self.workspace_root))
        self.orchestrator = AIKiCadOrchestrator(str(self.workspace_root))
        self.path_finder = PathFinderService(str(self.workspace_root))

    def serve(self):
        server_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                server_ref.handle_get(self)

            def do_POST(self):  # noqa: N802
                server_ref.handle_post(self)

            def log_message(self, format, *args):  # noqa: A002
                return

        httpd = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        print(f"Review UI: http://127.0.0.1:{self.port}")
        httpd.serve_forever()

    def handle_get(self, handler: BaseHTTPRequestHandler):
        parsed = urlparse(handler.path)
        if parsed.path == "/export":
            return self.send_json(handler, self.review_report())
        if parsed.path == "/kb.json":
            query = parse_qs(parsed.query)
            file_hash = query.get("file_hash", [""])[0]
            return self.send_json(handler, self.kb_view(file_hash))
        if parsed.path == "/path-search":
            query = parse_qs(parsed.query)
            return self.send_json(handler, self.path_search(
                self.form_value({key: values[0] for key, values in query.items()}, "q"),
                kind=self.form_value({key: values[0] for key, values in query.items()}, "kind", "all"),
            ))
        if parsed.path == "/path-finder":
            return self.send_file(handler, self.workspace_root / "AI_support" / "app" / "path_finder.html")
        if parsed.path == "/open-pdf":
            query = parse_qs(parsed.query)
            result = self.workspace_pdf(self.form_value({key: values[0] for key, values in query.items()}, "path"))
            if result.get("status") == "success":
                return self.send_pdf(handler, result["path"])
            return self.send_json(handler, result, status=404 if result.get("status") == "missing_pdf" else 400)
        if parsed.path == "/kb":
            query = parse_qs(parsed.query)
            file_hash = query.get("file_hash", [""])[0]
            return self.send_html(handler, self.render_kb(file_hash))
        if parsed.path == "/pdf-page":
            query = parse_qs(parsed.query)
            file_hash = query.get("file_hash", [""])[0]
            page = self.safe_page_number(query.get("page", ["1"])[0])
            bboxes = self.parse_bbox_query(query.get("bbox", []))
            result = self.render_pdf_page_png(file_hash, page, bboxes)
            if result.get("status") == "success":
                return self.send_png(handler, result["png"])
            return self.send_json(handler, result, status=404)
        return self.send_html(handler, self.render_home())

    def handle_post(self, handler: BaseHTTPRequestHandler):
        try:
            length = int(handler.headers.get("Content-Length", "0") or 0)
        except ValueError:
            return self.send_json(handler, {"status": "bad_request", "error": "invalid Content-Length"}, status=400)
        if length > 64 * 1024:
            return self.send_json(handler, {"status": "bad_request", "error": "request body too large"}, status=413)
        body = handler.rfile.read(length).decode("utf-8") if length else ""
        fields = {key: values[0] for key, values in parse_qs(body).items()}
        parsed = urlparse(handler.path)
        if parsed.path == "/approve":
            result = self.memory.approve_learning_proposal(
                fields.get("proposal_id", ""),
                reviewer=fields.get("reviewer", "review-ui"),
                reason=fields.get("reason", "approved from review UI"),
                evidence=fields.get("evidence", ""),
            )
            return self.send_json(handler, result)
        if parsed.path == "/reject":
            result = self.memory.reject_learning_proposal(
                fields.get("proposal_id", ""),
                reviewer=fields.get("reviewer", "review-ui"),
                reason=fields.get("reason", "rejected from review UI"),
            )
            return self.send_json(handler, result)
        workflow_routes = {
            "/tool-status": ("Tool Status", self.workflow_tool_status),
            "/kb-build": ("Build KB", self.workflow_kb_build),
            "/firmware-generate": ("Generate Firmware", self.workflow_firmware_generate),
            "/kicad-generate": ("Generate KiCad", self.workflow_kicad_generate),
            "/kicad-write": ("Write KiCad Files", self.workflow_kicad_write),
            "/pipeline-run": ("Run Pipeline", self.workflow_pipeline_run),
        }
        if parsed.path in workflow_routes:
            title, action = workflow_routes[parsed.path]
            result = self.run_workflow_action(action, fields)
            if self.is_async_request(handler):
                return self.send_json(handler, result, status=200 if result.get("status") not in {"failed", "bad_request"} else 400)
            return self.send_html(handler, self.render_result(title, result), status=200 if result.get("status") not in {"failed", "bad_request"} else 400)
        return self.send_json(handler, {"status": "not_found"}, status=404)

    def _load_template(self, name: str) -> str:
        """Load HTML template from file."""
        template_dir = Path(__file__).parent / "templates"
        template_path = template_dir / f"{name}.html"
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        return ""

    def review_report(self) -> dict:
        """Generate the review report for the home page."""
        return {
            "learning": self.memory.review_learning_proposals(limit=100),
            "memory_conflicts": self.memory.detect_memory_conflicts(),
            "human_overrides": self.audit.list_overrides(),
            "kb_cache_root": str(self.cache.root),
            "workspace_root": str(self.workspace_root),
        }

    def run_workflow_action(self, action, fields: dict) -> dict:
        try:
            return action(fields)
        except (OSError, ValueError, PermissionError, FileNotFoundError) as exc:
            return {"status": "failed", "error": str(exc)}

    def workflow_tool_status(self, fields: dict) -> dict:
        return self.orchestrator.tool_status(
            target_platform=self.form_value(fields, "target_platform", "STM32"),
            language=self.form_value(fields, "language", "C"),
        )

    def workflow_kb_build(self, fields: dict) -> dict:
        pdf_path = self.form_value(fields, "pdf")
        project_id = self.form_value(fields, "project_id")
        if not pdf_path or not project_id:
            return {"status": "bad_request", "error": "pdf and project_id are required"}
        return self.orchestrator.build_kb(
            pdf_path=pdf_path,
            project_id=project_id,
            component_name=self.form_value(fields, "component_name"),
            document_scope_id=self.form_value(fields, "document_scope_id"),
            require_kicad_fields=self.form_checked(fields, "require_kicad_fields"),
        )

    def workflow_firmware_generate(self, fields: dict) -> dict:
        required = self.require_fields(fields, ("file_hash", "requirement", "target_platform", "language"))
        if required:
            return required
        return self.orchestrator.generate_firmware(
            self.form_value(fields, "file_hash"),
            self.form_value(fields, "requirement"),
            self.form_value(fields, "target_platform"),
            self.form_value(fields, "language"),
        )

    def workflow_kicad_generate(self, fields: dict) -> dict:
        required = self.require_fields(fields, ("file_hash", "firmware_json", "firmware_validation_json"))
        if required:
            return required
        return self.orchestrator.generate_kicad(
            self.form_value(fields, "file_hash"),
            self.form_value(fields, "firmware_json"),
            self.form_value(fields, "firmware_validation_json"),
            hardware_requirement=self.form_value(fields, "hardware_requirement"),
        )

    def workflow_kicad_write(self, fields: dict) -> dict:
        kicad_json = self.form_value(fields, "kicad_json")
        if not kicad_json:
            return {"status": "bad_request", "error": "kicad_json is required"}
        return self.orchestrator.write_kicad_files(
            kicad_json,
            output_dir=self.form_value(fields, "output_dir"),
        )

    def workflow_pipeline_run(self, fields: dict) -> dict:
        required = self.require_fields(fields, ("pdf", "project_id", "requirement", "hardware_requirement", "target_platform", "language"))
        if required:
            return required
        return self.orchestrator.run_pipeline(
            pdf_path=self.form_value(fields, "pdf"),
            project_id=self.form_value(fields, "project_id"),
            user_requirement=self.form_value(fields, "requirement"),
            hardware_requirement=self.form_value(fields, "hardware_requirement"),
            target_platform=self.form_value(fields, "target_platform"),
            language=self.form_value(fields, "language"),
            component_name=self.form_value(fields, "component_name"),
            require_kicad_fields=self.form_checked(fields, "require_kicad_fields"),
            run_erc_drc=not self.form_checked(fields, "skip_erc_drc"),
        )

    def form_value(self, fields: dict, key: str, default: str = "") -> str:
        return str(fields.get(key, default) or default).strip()

    def form_checked(self, fields: dict, key: str) -> bool:
        return str(fields.get(key, "")).lower() in {"1", "true", "yes", "on"}

    def require_fields(self, fields: dict, names) -> dict:
        missing = [name for name in names if not self.form_value(fields, name)]
        return {"status": "bad_request", "error": f"missing required fields: {', '.join(missing)}"} if missing else {}

    def is_async_request(self, handler: BaseHTTPRequestHandler) -> bool:
        return str(handler.headers.get("X-Requested-With", "")).lower() == "fetch"

    def path_search(self, query: str = "", kind: str = "all", limit: int = 60) -> dict:
        return self.path_finder.search(query=query, kind=kind, limit=limit).to_dict()

    def workspace_path(self, raw_path: str) -> Path:
        raw_path = str(raw_path or "").strip()
        if not raw_path:
            raise ValueError("path is required")
        candidate = Path(raw_path)
        resolved = candidate.resolve() if candidate.is_absolute() else (self.workspace_root / candidate).resolve()
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as exc:
            raise PermissionError("path must stay inside workspace") from exc
        return resolved

    def workspace_pdf(self, raw_path: str) -> dict:
        try:
            path = self.workspace_path(raw_path)
        except (ValueError, PermissionError) as exc:
            return {"status": "bad_request", "error": str(exc)}
        if not path.exists():
            return {"status": "missing_pdf", "path": str(path)}
        if not path.is_file() or path.suffix.lower() != ".pdf":
            return {"status": "bad_request", "error": "path must point to a PDF file"}
        return {"status": "success", "path": path}

    def kb_view(self, file_hash: str):
        if not file_hash:
            return {"status": "missing_file_hash"}
        try:
            cache_dir = self.cache.cache_dir(file_hash)
        except ValueError as exc:
            return {"status": "invalid_file_hash", "error": str(exc)}
        payload = {"file_hash": file_hash, "cache_dir": str(cache_dir)}
        for name in ("approved_kb.json", "structured_kb.json", "kb_validation_report.json", "raw_evidence.json"):
            path = cache_dir / name
            if path.exists():
                try:
                    payload[name] = self.cache.read_json(path)
                except (OSError, ValueError) as exc:
                    payload[name] = {"error": str(exc)}
        return payload

    def render_home(self) -> str:
        """Render the home page HTML."""
        report = self.review_report()
        proposals = report["learning"].get("proposals", [])

        # Build proposals rows
        rows = []
        for proposal in proposals:
            pid = html.escape(str(proposal.get("proposal_id", "")))
            rows.append(
                "<tr>"
                f"<td>{pid}</td>"
                f"<td>{html.escape(str(proposal.get('risk', '')))}</td>"
                f"<td>{html.escape(str(proposal.get('field', '')))}</td>"
                f"<td>{html.escape(str(proposal.get('value', '')))}</td>"
                "<td>"
                f"<form method='post' action='/approve'><input name='proposal_id' value='{pid}' type='hidden'>"
                "<input name='reviewer' value='review-ui'><input name='reason' value='human reviewed'>"
                "<input name='evidence' placeholder='evidence/citation'><button>Approve</button></form>"
                f"<form method='post' action='/reject'><input name='proposal_id' value='{pid}' type='hidden'>"
                "<input name='reviewer' value='review-ui'><input name='reason' value='not grounded'><button>Reject</button></form>"
                "</td></tr>"
            )

        template = self._load_template("review_home")
        if template:
            return template.replace("{{PROPOSALS_ROWS}}", "".join(rows)) \
                          .replace("{{HUMAN_OVERRIDES}}", html.escape(json.dumps(report.get("human_overrides", []), indent=2))) \
                          .replace("{{MEMORY_CONFLICTS}}", html.escape(json.dumps(report.get("memory_conflicts", {}), indent=2)))

        # Fallback inline template (if template file not found)
        return self._fallback_home_template(report, rows)

    def _fallback_home_template(self, report: dict, rows: list) -> str:
        """Fallback inline home template when template file is missing."""
        return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>AI KiCad Review UI</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;color:#1f2933;background:#f7f8fa}}
main{{max-width:1380px;margin:0 auto;padding:20px}}
section{{background:#fff;border:1px solid #d8dee8;border-radius:8px;padding:16px;margin:16px 0}}
table{{border-collapse:collapse;width:100%;background:#fff}}td,th{{border:1px solid #ccd4df;padding:6px;vertical-align:top}}
input,textarea,select{{box-sizing:border-box;margin:3px 0;padding:6px;border:1px solid #b8c2cf;border-radius:4px;font:inherit;width:100%}}
textarea{{min-height:64px}}button{{padding:7px 10px;border:1px solid #2f5f8f;background:#315f8d;color:#fff;border-radius:4px;cursor:pointer}}
.layout{{display:grid;grid-template-columns:minmax(0,1fr) 420px;gap:16px;align-items:start}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}}.field{{margin:6px 0}}.inline{{display:flex;gap:8px;align-items:center}}.inline input{{width:auto}}
.path-input-row{{display:flex;gap:6px;align-items:center}}.path-input-row input{{flex:1;min-width:0}}.path-input-row button{{flex:0 0 auto;margin:3px 0;white-space:nowrap}}
pre{{white-space:pre-wrap;overflow:auto;background:#0f1720;color:#e6edf3;padding:12px;border-radius:6px;max-height:520px}}
.sticky{{position:sticky;top:12px}}.muted{{color:#627083}}.path-results{{display:grid;gap:6px;margin-top:8px}}.path-item{{display:flex;gap:6px;align-items:center;border:1px solid #d8dee8;border-radius:6px;padding:6px;background:#fbfcfe}}.path-item code{{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}.statusline{{min-height:22px;color:#315f8d}}
@media(max-width:980px){{.layout{{grid-template-columns:1fr}}.sticky{{position:static}}}}
</style></head>
<body>
<main>
<h1>AI KiCad Review UI</h1>
<p><a href="/export">Export review JSON</a> | <a href="/path-finder" target="_blank">Open Path Finder (standalone)</a></p>
<div class="layout">
<div>
<section>
<h2>Learning Proposals</h2>
<table><tr><th>ID</th><th>Risk</th><th>Field</th><th>Proposal</th><th>Action</th></tr>{''.join(rows)}</table>
</section>
</div>
</div>
</main>
</body></html>"""

    def render_result(self, title: str, result: dict) -> str:
        """Render a result page."""
        template = self._load_template("review_result")
        if template:
            return template.replace("{{TITLE}}", html.escape(title)) \
                          .replace("{{STATUS}}", html.escape(str(result.get("status", "ok")))) \
                          .replace("{{BODY}}", html.escape(json.dumps(result, indent=2, ensure_ascii=False)))

        # Fallback inline
        return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;background:#f7f8fa;color:#1f2933}}main{{max-width:1100px;margin:0 auto}}pre{{white-space:pre-wrap;overflow:auto;background:#0f1720;color:#e6edf3;padding:12px;border-radius:6px}}a{{color:#315f8d}}</style></head>
<body><main>
<p><a href="/">Back to UI</a></p>
<h1>{html.escape(title)}</h1>
<p>Status: <b>{html.escape(str(result.get('status', 'ok')))}</b></p>
<pre>{html.escape(json.dumps(result, indent=2, ensure_ascii=False))}</pre>
</main></body></html>"""

    def render_kb(self, file_hash: str) -> str:
        payload = self.kb_view(file_hash)
        if payload.get("status") == "missing_file_hash":
            return "<html><body><h1>Missing file_hash</h1></body></html>"
        kb = payload.get("approved_kb.json") or payload.get("structured_kb.json") or {}
        raw = payload.get("raw_evidence.json", {}) if isinstance(payload.get("raw_evidence.json", {}), dict) else {}
        component = kb.get("component", {}) if isinstance(kb, dict) else {}
        electrical = kb.get("electrical", {}) if isinstance(kb, dict) else {}
        package = kb.get("package", {}) if isinstance(kb, dict) else {}
        pin_rows = []
        for pin in kb.get("pinout", []) if isinstance(kb.get("pinout", []), list) else []:
            citations = pin.get("citations", []) if isinstance(pin, dict) else []
            pin_rows.append(
                "<tr>"
                f"<td>{html.escape(str(pin.get('pin_name', '')))}</td>"
                f"<td>{html.escape(str(pin.get('pin_number', '')))}</td>"
                f"<td>{html.escape(', '.join(str(item) for item in pin.get('functions', [])))}</td>"
                f"<td><pre>{html.escape(json.dumps(citations[:2], indent=2))}</pre></td>"
                "</tr>"
            )
        citation_blocks = []
        for source in [
            component.get("citations", []),
            electrical.get("operating_voltage", {}).get("citations", []) if isinstance(electrical.get("operating_voltage", {}), dict) else [],
            package.get("citations", []) if isinstance(package, dict) else [],
        ]:
            for citation in source if isinstance(source, list) else []:
                preview = self.citation_preview_link(file_hash, citation)
                citation_blocks.append(f"{preview}<pre>{html.escape(json.dumps(citation, indent=2))}</pre>")
        ocr_quality = raw.get("ocr_quality", {})
        return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>KB Review</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:32px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:6px;vertical-align:top}}pre{{white-space:pre-wrap}}</style></head>
<body>
<p><a href="/">Back</a> | <a href="/kb.json?file_hash={html.escape(file_hash)}">JSON</a></p>
<h1>KB Review: {html.escape(file_hash[:12])}</h1>
<h2>Component</h2>
<p><b>Part:</b> {html.escape(str(component.get('part_number', '')))} | <b>Package:</b> {html.escape(str(package.get('name') or package.get('recommended_land_pattern') or ''))}</p>
<h2>Voltage</h2>
<pre>{html.escape(json.dumps(electrical.get('operating_voltage', {}), indent=2))}</pre>
<h2>Pinout</h2>
<table><tr><th>Name</th><th>Number</th><th>Functions</th><th>Citations page/table/row/cell</th></tr>{''.join(pin_rows)}</table>
<h2>Citation Browser</h2>
{''.join(citation_blocks) or '<p>No citations found.</p>'}
<h2>OCR Quality</h2>
<pre>{html.escape(json.dumps(ocr_quality, indent=2))}</pre>
</body></html>"""

    def citation_preview_link(self, file_hash: str, citation: dict) -> str:
        page = citation.get("page_number") or citation.get("page")
        bbox = citation.get("cell_bbox") or citation.get("row_bbox") or citation.get("table_bbox") or citation.get("bbox")
        if not page or not isinstance(bbox, list) or len(bbox) != 4:
            return ""
        bbox_text = ",".join(str(item) for item in bbox)
        return f"<p><a href=\"/pdf-page?file_hash={html.escape(file_hash)}&page={html.escape(str(page))}&bbox={html.escape(bbox_text)}\">Preview page {html.escape(str(page))} bbox</a></p>"

    def parse_bbox_query(self, bbox_values):
        boxes = []
        for raw in bbox_values:
            try:
                coords = [float(part) for part in str(raw).split(",")]
            except ValueError:
                continue
            if len(coords) == 4 and all(abs(value) < 1_000_000 for value in coords):
                boxes.append(coords)
        return boxes

    def safe_page_number(self, value) -> int:
        try:
            page = int(value or 1)
        except (TypeError, ValueError):
            return 1
        return max(page, 1)

    def source_pdf_for_hash(self, file_hash: str) -> Path:
        payload = self.kb_view(file_hash)
        for key in ("raw_evidence.json", "approved_kb.json", "structured_kb.json"):
            data = payload.get(key, {})
            if isinstance(data, dict):
                source = str(data.get("source_file", "")).strip()
                if source:
                    path = Path(source)
                    resolved = path if path.is_absolute() else (self.workspace_root / path).resolve()
                    try:
                        resolved.resolve().relative_to(self.workspace_root)
                    except ValueError:
                        return self.workspace_root / "__missing_source_pdf__"
                    return resolved
        return self.workspace_root / "__missing_source_pdf__"

    def render_pdf_page_png(self, file_hash: str, page_number: int, bboxes=None):
        if fitz is None:
            return {"status": "tool_missing", "error": "PyMuPDF/fitz is not installed"}
        source = self.source_pdf_for_hash(file_hash)
        if not source.exists():
            return {"status": "missing_pdf", "source_file": str(source)}
        doc = None
        try:
            doc = fitz.open(str(source))
            page = doc[max(min(int(page_number), len(doc)), 1) - 1]
            for bbox in bboxes or []:
                shape = page.new_shape()
                shape.draw_rect(fitz.Rect(*bbox))
                shape.finish(color=(1, 0, 0), width=2)
                shape.commit()
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            png = pix.tobytes("png")
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "source_file": str(source)}
        finally:
            if doc is not None:
                doc.close()
        return {"status": "success", "png": png, "source_file": str(source), "page_number": page_number}

    def send_html(self, handler: BaseHTTPRequestHandler, body: str, status: int = 200):
        payload = body.encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)

    def send_file(self, handler: BaseHTTPRequestHandler, path: Path, status: int = 200):
        """Send a file as response."""
        if not path.exists() or not path.is_file():
            return self.send_json(handler, {"status": "not_found", "error": "file not found"}, status=404)
        try:
            payload = path.read_bytes()
            suffix = path.suffix.lower()
            content_types = {
                ".html": "text/html; charset=utf-8",
                ".json": "application/json",
                ".css": "text/css",
                ".js": "application/javascript",
            }
            content_type = content_types.get(suffix, "application/octet-stream")
            handler.send_response(status)
            handler.send_header("Content-Type", content_type)
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            handler.wfile.write(payload)
        except OSError as exc:
            return self.send_json(handler, {"status": "error", "error": str(exc)}, status=500)

    def send_json(self, handler: BaseHTTPRequestHandler, payload, status: int = 200):
        body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def send_png(self, handler: BaseHTTPRequestHandler, payload: bytes, status: int = 200):
        handler.send_response(status)
        handler.send_header("Content-Type", "image/png")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)

    def send_pdf(self, handler: BaseHTTPRequestHandler, path: Path, status: int = 200):
        size = path.stat().st_size
        handler.send_response(status)
        handler.send_header("Content-Type", "application/pdf")
        handler.send_header("Content-Disposition", f'inline; filename="{path.name}"')
        handler.send_header("Content-Length", str(size))
        handler.end_headers()
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(256 * 1024)
                if not chunk:
                    break
                handler.wfile.write(chunk)