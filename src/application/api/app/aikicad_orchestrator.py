import json
import re
from pathlib import Path
from typing import Dict

from src.domains.eda.kicad import KiCadCliRunner, KiCadFileWriter, KiCadLibraryResolver, KiCadSkeletonGenerator, KiCadValidator
from src.domains.autonomy import AutonomyRunner
from src.domains.firmware import FirmwareCompileRunner, FirmwareGenerator, FirmwareSourceGenerator, FirmwareValidator
from src.domains.knowledge import AIKiCadKnowledgeAgent, KnowledgeCache
from src.domains.review import HumanReviewAudit
from src.domains.runtime import BoardProfileManager
from src.domains.safety import WriteBoundaryGuard
from src.domains.validation import CrossValidator
from src.domains.autonomy.planner import AutonomyPlanner
from src.core.multi_agent.pdf_knowledge_agent import PDFKnowledgeAgent


class AIKiCadOrchestrator:
    """Orchestrates AI KiCad Agent validation gates."""

    def __init__(self, workspace_root: str = "."):
        self.workspace_root = Path(workspace_root).resolve()
        self.knowledge_agent = AIKiCadKnowledgeAgent(str(self.workspace_root))
        self.cache = KnowledgeCache(str(self.workspace_root))
        self.firmware_compile_runner = FirmwareCompileRunner()
        self.firmware_generator = FirmwareGenerator()
        self.firmware_source_generator = FirmwareSourceGenerator()
        self.firmware_validator = FirmwareValidator()
        self.kicad_cli = KiCadCliRunner()
        self.kicad_file_writer = KiCadFileWriter()
        self.kicad_generator = KiCadSkeletonGenerator()
        self.kicad_library_resolver = KiCadLibraryResolver()
        self.kicad_validator = KiCadValidator()
        self.review_audit = HumanReviewAudit(str(self.workspace_root))
        self.board_profiles = BoardProfileManager(str(self.workspace_root))
        self.autonomy_planner = AutonomyPlanner()
        self.write_guard = WriteBoundaryGuard(str(self.workspace_root))
        self.cross_validator = CrossValidator()
        self.autonomy_runner = AutonomyRunner(self, str(self.workspace_root))

    def build_kb(self, **kwargs) -> Dict:
        return self.knowledge_agent.build_kb(**kwargs)

    def validate_kb(self, file_hash: str, require_kicad_fields: bool = False) -> Dict:
        return self.knowledge_agent.validate_cached_kb(file_hash, require_kicad_fields=require_kicad_fields)

    def generate_firmware(self, file_hash: str, user_requirement: str, target_platform: str, language: str) -> Dict:
        approved_kb = self.require_approved_kb(file_hash)
        project_id = self.safe_project_id(str(approved_kb.get("project_id", "default")) or "default")
        output_dir = self.project_output_dir(project_id) / "firmware"
        self.write_guard.require_write(str(output_dir))
        result = self.firmware_generator.generate(
            approved_kb,
            user_requirement=user_requirement,
            target_platform=target_platform,
            language=language,
            output_dir=output_dir,
        )
        result["firmware_output_path"] = str(output_dir / "firmware_output.json")
        result["firmware_validation_path"] = str(output_dir / "firmware_validation.json")
        return result

    def validate_firmware_file(self, file_hash: str, firmware_json_path: str) -> Dict:
        approved_kb = self.require_approved_kb(file_hash)
        firmware_output = self.read_json(firmware_json_path)
        return self.firmware_validator.validate(firmware_output, approved_kb)

    def generate_firmware_source(self, firmware_json_path: str, firmware_validation_json_path: str, output_dir: str = "") -> Dict:
        firmware_output = self.read_json(firmware_json_path)
        firmware_validation = self.read_json(firmware_validation_json_path)
        if not firmware_validation.get("valid", False):
            return {
                "status": "blocked",
                "reason": "firmware validation must pass before source generation",
                "validation": firmware_validation,
            }
        project_id = str(firmware_output.get("project_id", "default")) or "default"
        resolved_output_dir = self.resolve_path(output_dir) if output_dir else self.workspace_root / "AI_support" / "outputs" / "projects" / project_id / "firmware" / "src"
        self.write_guard.require_write(str(resolved_output_dir))
        generation = self.firmware_source_generator.generate(firmware_output, resolved_output_dir)
        compile_report = self.firmware_compile_runner.compile_directory(
            resolved_output_dir,
            str(firmware_output.get("target_platform", "")),
            str(firmware_output.get("language", "")),
        )
        report_path = resolved_output_dir / "compile_report.json"
        self.write_json_file(report_path, compile_report)
        return {
            "status": "pass" if compile_report.get("status") == "pass" else compile_report.get("status", "fail"),
            "source_generation": generation,
            "compile_report": compile_report,
            "compile_report_path": str(report_path),
        }

    def generate_kicad(self, file_hash: str, firmware_json_path: str, firmware_validation_json_path: str, hardware_requirement: str = "") -> Dict:
        approved_kb = self.require_approved_kb(file_hash)
        firmware_output = self.read_json(firmware_json_path)
        firmware_validation = self.read_json(firmware_validation_json_path)
        project_id = self.safe_project_id(str(approved_kb.get("project_id", "default")) or "default")
        output_dir = self.project_output_dir(project_id) / "kicad"
        self.write_guard.require_write(str(output_dir))
        result = self.kicad_generator.generate(
            approved_kb,
            firmware_output,
            firmware_validation,
            hardware_requirement=hardware_requirement,
            output_dir=output_dir,
        )
        result["kicad_output_path"] = str(output_dir / "kicad_output.json")
        result["kicad_validation_path"] = str(output_dir / "kicad_validation.json")
        return result

    def write_kicad_files(self, kicad_json_path: str, output_dir: str = "") -> Dict:
        kicad_output = self.read_json(kicad_json_path)
        project_id = self.safe_project_id(str(kicad_output.get("project_id", "default")) or "default")
        resolved_output_dir = self.resolve_path(output_dir) if output_dir else self.project_output_dir(project_id) / "kicad" / "project"
        self.write_guard.require_write(str(resolved_output_dir))
        files = self.kicad_file_writer.write_project(kicad_output, resolved_output_dir)
        return {"status": "written", "files": files}

    def validate_kicad_file(self, file_hash: str, firmware_json_path: str, firmware_validation_path: str, kicad_json_path: str) -> Dict:
        approved_kb = self.require_approved_kb(file_hash)
        firmware_output = self.read_json(firmware_json_path)
        firmware_validation = self.read_json(firmware_validation_path)
        kicad_output = self.read_json(kicad_json_path)
        return self.kicad_validator.validate(kicad_output, approved_kb, firmware_output, firmware_validation)

    def run_kicad_erc_drc(self, schematic_path: str, pcb_path: str, report_path: str = "") -> Dict:
        schematic = self.resolve_path(schematic_path)
        pcb = self.resolve_path(pcb_path)
        report = {
            "erc": self.kicad_cli.run_erc(schematic),
            "drc": self.kicad_cli.run_drc(pcb),
        }
        if report_path:
            resolved_report = self.resolve_path(report_path)
            self.write_guard.require_write(str(resolved_report))
            resolved_report.parent.mkdir(parents=True, exist_ok=True)
            self.write_json_file(resolved_report, report)
        return report

    def tool_status(self, target_platform: str = "STM32", language: str = "C") -> Dict:
        return {
            "kicad_cli": self.kicad_cli.status(),
            "firmware_compiler": self.firmware_compile_runner.status(target_platform, language),
            "ocr": self.knowledge_agent.ocr_status(),
            "paddleocr": self.knowledge_agent.ocr_status().get("backends", {}).get("paddleocr", {}),
            "serial_runtime": self.board_profiles.serial_status(),
            "board_profile": self.board_profiles.validate_profile(),
            "kicad_library": self.kicad_library_resolver.validate_maps(),
        }

    def diagnose_ocr(self, pdf_path: str, project_id: str = "") -> Dict:
        source = self.resolve_path(pdf_path)
        pdf_agent = self.knowledge_agent
        helper = PDFKnowledgeAgent(workspace_root=str(self.workspace_root))
        pages = helper.extract_pages(source)
        pages, ocr_pages = pdf_agent.add_ocr_fallback_pages(source, pages)
        report = pdf_agent.ocr_pipeline.diagnose_pdf(source, pages)
        report["project_id"] = project_id
        report["ocr_pages"] = ocr_pages
        output_dir = self.workspace_root / "AI_support" / "outputs" / "ocr"
        self.write_guard.require_write(str(output_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / "ocr_quality_report.json"
        self.write_json_file(report_path, report)
        report["report_path"] = str(report_path)
        return report

    def validate_board_profile(self, profile_path: str = "") -> Dict:
        report = self.board_profiles.validate_profile(profile_path)
        output_dir = self.workspace_root / "AI_support" / "outputs" / "runtime"
        self.write_guard.require_write(str(output_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "board_profile_validation.json"
        self.write_json_file(path, report)
        report["report_path"] = str(path)
        return report

    def validate_kicad_library(self) -> Dict:
        report = self.kicad_library_resolver.validate_maps()
        output_dir = self.workspace_root / "AI_support" / "outputs" / "kicad"
        self.write_guard.require_write(str(output_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "kicad_library_validation.json"
        self.write_json_file(path, report)
        report["report_path"] = str(path)
        return report

    def board_flash(self, profile_path: str = "") -> Dict:
        profile_report = self.board_profiles.validate_profile(profile_path)
        if not profile_report.get("valid", False):
            result = {
                "status": profile_report.get("status", "invalid"),
                "returncode": 1,
                "validation": profile_report,
                "stderr": "; ".join(profile_report.get("errors", [])),
            }
        else:
            result = self.board_profiles.run_flash(profile_report.get("profile", {}))
            result["validation"] = profile_report
        output_dir = self.workspace_root / "AI_support" / "outputs" / "runtime"
        self.write_guard.require_write(str(output_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "flash_result.json"
        self.write_json_file(path, result)
        result["report_path"] = str(path)
        return result

    def runtime_observe(self, profile_path: str = "") -> Dict:
        profile_report = self.board_profiles.validate_profile(profile_path)
        if not profile_report.get("valid", False):
            result = {
                "status": profile_report.get("status", "invalid"),
                "returncode": 1,
                "validation": profile_report,
                "observation": {},
                "stderr": "; ".join(profile_report.get("errors", [])),
            }
        else:
            result = self.board_profiles.read_serial_runtime(profile_report.get("profile", {}))
            result["validation"] = profile_report
        output_dir = self.workspace_root / "AI_support" / "outputs" / "runtime"
        self.write_guard.require_write(str(output_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "runtime_observation.json"
        self.write_json_file(path, result.get("observation", result))
        result["report_path"] = str(path)
        return result

    def benchmark_ocr(self, pdf_dir: str, expected_path: str = "") -> Dict:
        directory = self.resolve_path(pdf_dir)
        expected = self.read_json(expected_path) if expected_path else {}
        helper = PDFKnowledgeAgent(workspace_root=str(self.workspace_root))
        cases = []
        for pdf_path in sorted(directory.glob("*.pdf")):
            pages = helper.extract_pages(pdf_path)
            ocr_pages = []
            ocr_warning = ""
            try:
                pages, ocr_pages = self.knowledge_agent.add_ocr_fallback_pages(pdf_path, pages)
            except Exception as exc:
                ocr_warning = str(exc)
            report = self.knowledge_agent.ocr_pipeline.diagnose_pdf(pdf_path, pages)
            all_text = "\n".join(text for _, text in pages)
            expected_entry = expected.get(pdf_path.name, expected.get(str(pdf_path), [])) if isinstance(expected, dict) else []
            keywords = expected_entry.get("keywords", []) if isinstance(expected_entry, dict) else expected_entry
            recall = self.knowledge_agent.ocr_pipeline.keyword_recall(all_text, keywords if isinstance(keywords, list) else [])
            cases.append({
                "pdf": str(pdf_path),
                "word_count": sum(item.get("word_count", 0) for item in report.get("pages", [])),
                "backend_used": sorted({item.get("backend_used", "") for item in report.get("pages", []) if item.get("backend_used")}),
                "confidence": round(sum(item.get("confidence", 0) for item in report.get("pages", [])) / max(len(report.get("pages", [])), 1), 3),
                "keyword_recall": recall,
                "low_confidence_pages": report.get("low_confidence_pages", []),
                "ocr_pages": ocr_pages,
                "warning": ocr_warning,
            })
        report = {
            "pdf_dir": str(directory),
            "case_count": len(cases),
            "cases": cases,
            "needs_human_review": any(item.get("low_confidence_pages") for item in cases),
        }
        output_dir = self.workspace_root / "AI_support" / "outputs" / "ocr"
        self.write_guard.require_write(str(output_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "ocr_benchmark_report.json"
        self.write_json_file(path, report)
        report["report_path"] = str(path)
        return report

    def propose_plan(self, context_path: str, proposal_path: str = "") -> Dict:
        context = self.read_json(context_path)
        proposal_text = ""
        if proposal_path:
            proposal_text = self.resolve_path(proposal_path).read_text(encoding="utf-8")
        report = self.autonomy_planner.propose(context, proposal_text)
        output_dir = self.workspace_root / "AI_support" / "outputs" / "planner"
        self.write_guard.require_write(str(output_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        self.write_json_file(output_dir / "planner_proposal.json", report.get("proposal", {}))
        self.write_json_file(output_dir / "planner_validation_report.json", report.get("validation", {}))
        report["planner_proposal_path"] = str(output_dir / "planner_proposal.json")
        report["planner_validation_path"] = str(output_dir / "planner_validation_report.json")
        return report

    def planner_eval(self, cases_path: str, include_llm: bool = False) -> Dict:
        payload = self.read_json(cases_path)
        cases = payload.get("cases", payload) if isinstance(payload, dict) else payload
        if not isinstance(cases, list):
            cases = []
        report = self.autonomy_planner.evaluate_cases(cases, include_llm=include_llm)
        output_dir = self.workspace_root / "AI_support" / "outputs" / "planner"
        self.write_guard.require_write(str(output_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "planner_eval_report.json"
        self.write_json_file(path, report)
        report["report_path"] = str(path)
        return report

    def validate_write_path(self, path: str, mode: str = "target_project") -> Dict:
        return self.write_guard.validate_write(path, mode=mode)

    def validate_cross_files(self, file_hash: str, firmware_json_path: str, kicad_json_path: str) -> Dict:
        approved_kb = self.require_approved_kb(file_hash)
        firmware_output = self.read_json(firmware_json_path)
        kicad_output = self.read_json(kicad_json_path)
        return self.cross_validator.validate(approved_kb, firmware_output, kicad_output)

    def run_pipeline(
        self,
        pdf_path: str,
        project_id: str,
        user_requirement: str,
        hardware_requirement: str,
        target_platform: str,
        language: str,
        component_name: str = "",
        require_kicad_fields: bool = True,
        run_erc_drc: bool = True,
    ) -> Dict:
        safe_project_id = self.safe_project_id(project_id)
        project_root = self.project_output_dir(safe_project_id)
        reports_dir = project_root / "reports"
        self.write_guard.require_write(str(reports_dir))
        reports_dir.mkdir(parents=True, exist_ok=True)

        kb_result = self.build_kb(
            pdf_path=pdf_path,
            project_id=safe_project_id,
            component_name=component_name,
            require_kicad_fields=require_kicad_fields,
        )
        self.write_report(reports_dir / "kb_result.json", kb_result)
        if kb_result.get("status") != "approved":
            return self.pipeline_result("blocked", "kb", project_root, reports_dir, {"kb": kb_result})

        file_hash = kb_result["file_hash"]
        firmware_result = self.generate_firmware(file_hash, user_requirement, target_platform, language)
        self.write_report(reports_dir / "firmware_result.json", firmware_result)
        if firmware_result.get("status") != "pass":
            return self.pipeline_result("blocked", "firmware", project_root, reports_dir, {"kb": kb_result, "firmware": firmware_result})

        source_result = self.generate_firmware_source(
            firmware_result["firmware_output_path"],
            firmware_result["firmware_validation_path"],
        )
        self.write_report(reports_dir / "source_result.json", source_result)
        if source_result.get("status") not in {"pass", "tool_missing"}:
            return self.pipeline_result("blocked", "source", project_root, reports_dir, {"kb": kb_result, "firmware": firmware_result, "source": source_result})

        kicad_result = self.generate_kicad(
            file_hash,
            firmware_result["firmware_output_path"],
            firmware_result["firmware_validation_path"],
            hardware_requirement=hardware_requirement,
        )
        self.write_report(reports_dir / "kicad_result.json", kicad_result)
        if kicad_result.get("status") != "pass":
            return self.pipeline_result("blocked", "kicad", project_root, reports_dir, {"kb": kb_result, "firmware": firmware_result, "kicad": kicad_result})

        kicad_files = self.write_kicad_files(kicad_result["kicad_output_path"])
        self.write_report(reports_dir / "kicad_files.json", kicad_files)

        erc_drc_report = {"erc": {"status": "not_run"}, "drc": {"status": "not_run"}}
        if run_erc_drc:
            erc_drc_report = self.run_kicad_erc_drc(
                kicad_files["files"]["schematic"],
                kicad_files["files"]["pcb"],
                report_path=str(reports_dir / "erc_drc_report.json"),
            )
        self.write_report(reports_dir / "erc_drc_report.json", erc_drc_report)
        if run_erc_drc and not self.erc_drc_passed(erc_drc_report):
            return self.pipeline_result("blocked", "erc_drc", project_root, reports_dir, {
                "kb": kb_result,
                "firmware": firmware_result,
                "source": source_result,
                "kicad": kicad_result,
                "kicad_files": kicad_files,
                "erc_drc": erc_drc_report,
            })

        cross_report = self.validate_cross_files(file_hash, firmware_result["firmware_output_path"], kicad_result["kicad_output_path"])
        self.write_report(reports_dir / "cross_validation_report.json", cross_report)
        if not cross_report.get("valid", False):
            return self.pipeline_result("blocked", "cross_validation", project_root, reports_dir, {
                "kb": kb_result,
                "firmware": firmware_result,
                "source": source_result,
                "kicad": kicad_result,
                "erc_drc": erc_drc_report,
                "cross": cross_report,
            })
        return self.pipeline_result("final_approved", "final", project_root, reports_dir, {
            "kb": kb_result,
            "firmware": firmware_result,
            "source": source_result,
            "kicad": kicad_result,
            "kicad_files": kicad_files,
            "erc_drc": erc_drc_report,
            "cross": cross_report,
        })

    def run_autonomy(
        self,
        pdf_path: str,
        project_id: str,
        user_requirement: str,
        hardware_requirement: str,
        target_platform: str,
        language: str,
        component_name: str = "",
        max_retries: int = 2,
        stop_before_kicad: bool = False,
        run_erc_drc: bool = False,
        use_llm_planner: bool = False,
    ) -> Dict:
        return self.autonomy_runner.run(
            pdf_path=pdf_path,
            project_id=project_id,
            user_requirement=user_requirement,
            hardware_requirement=hardware_requirement,
            target_platform=target_platform,
            language=language,
            component_name=component_name,
            max_retries=max_retries,
            stop_before_kicad=stop_before_kicad,
            run_erc_drc=run_erc_drc,
            use_llm_planner=use_llm_planner,
        )

    def list_autonomy_learning(self):
        return self.autonomy_runner.learning_memory.list_proposals()

    def record_human_override(self, payload: Dict) -> Dict:
        return self.review_audit.record_override(payload)

    def list_human_overrides(self):
        return self.review_audit.list_overrides()

    def pipeline_result(self, status: str, stage: str, project_root: Path, reports_dir: Path, payload: Dict) -> Dict:
        result = {
            "status": status,
            "stage": stage,
            "project_output_path": str(project_root) if status == "final_approved" else None,
            "reports_path": str(reports_dir),
            "payload": payload,
        }
        self.write_report(reports_dir / "pipeline_result.json", result)
        return result

    def erc_drc_passed(self, report: Dict) -> bool:
        checks = [report.get("erc", {}), report.get("drc", {})]
        return all(isinstance(item, dict) and item.get("status") == "pass" for item in checks)

    def write_report(self, path: Path, payload: Dict) -> None:
        self.write_guard.require_write(str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.write_json_file(path, payload)

    def require_approved_kb(self, file_hash: str) -> Dict:
        if not self.cache.has_approved_kb(file_hash):
            raise FileNotFoundError(f"Approved KB not found for hash: {file_hash}")
        return self.cache.load_approved_kb(file_hash)

    def read_json(self, path: str) -> Dict:
        resolved = self.resolve_path(path)
        try:
            with resolved.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"JSON file not found: {resolved}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {resolved}: line {exc.lineno} column {exc.colno}: {exc.msg}") from exc

    def resolve_path(self, path: str) -> Path:
        if not str(path).strip():
            raise ValueError("path is required")
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = (self.workspace_root / resolved).resolve()
        return resolved

    def write_json_file(self, path: Path, payload) -> None:
        self.write_guard.require_write(str(path))
        tmp_path = path.with_name(f"{path.name}.tmp")
        self.write_guard.require_write(str(tmp_path))
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    def safe_project_id(self, project_id: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(project_id or "default")).strip("._-")
        cleaned = re.sub(r"_+", "_", cleaned)
        return cleaned[:80] or "default"

    def project_output_dir(self, project_id: str) -> Path:
        return self.workspace_root / "AI_support" / "outputs" / "projects" / self.safe_project_id(project_id)
