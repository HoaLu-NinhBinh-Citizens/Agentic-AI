"""Unit tests for RuleEngine."""
import pytest
from pathlib import Path

from src.infrastructure.analysis.rule_engine import (
    RuleEngine,
    Rule,
    RuleSeverity,
    Finding,
)


class TestRule:
    def test_rule_compiles_patterns(self):
        rule = Rule(
            id="TEST001",
            name="test-rule",
            description="A test rule",
            severity=RuleSeverity.ERROR,
            languages=["python"],
            patterns=[r"def\s+\w+\(\):"],
        )
        matches = rule.match("def hello():\n    pass\n")
        assert len(matches) == 1

    def test_rule_no_match(self):
        rule = Rule(
            id="TEST001",
            name="test-rule",
            description="A test rule",
            severity=RuleSeverity.ERROR,
            languages=["python"],
            patterns=[r"def\s+\w+\(\):"],
        )
        matches = rule.match("class MyClass:\n    pass\n")
        assert len(matches) == 0

    def test_multiple_patterns(self):
        rule = Rule(
            id="TEST001",
            name="test-rule",
            description="A test rule",
            severity=RuleSeverity.WARNING,
            languages=["python"],
            patterns=[r"eval\s*\(", r"exec\s*\("],
        )
        matches = rule.match("eval('code')\nexec('stmt')")
        assert len(matches) == 2

    def test_rule_with_cwe_id(self):
        rule = Rule(
            id="SEC001",
            name="hardcoded-secret",
            description="Hardcoded secret",
            severity=RuleSeverity.ERROR,
            languages=["python"],
            cwe_id="CWE-798",
            tags=["security"],
        )
        assert rule.cwe_id == "CWE-798"
        assert "security" in rule.tags

    def test_rule_post_init_compiles(self):
        rule = Rule(
            id="TEST001",
            name="test",
            description="Test",
            severity=RuleSeverity.INFO,
            languages=["python"],
            patterns=[r"\d+"],
        )
        assert hasattr(rule, "_compiled_patterns")
        assert len(rule._compiled_patterns) == 1


class TestFinding:
    def test_finding_creation(self):
        f = Finding(
            rule_id="TEST001",
            rule_name="test",
            severity=RuleSeverity.ERROR,
            file="test.py",
            line=10,
            end_line=10,
        )
        assert f.rule_id == "TEST001"
        assert f.severity == RuleSeverity.ERROR
        assert f.line == 10

    def test_to_dict(self):
        f = Finding(
            rule_id="TEST001",
            rule_name="test",
            severity=RuleSeverity.ERROR,
            file="test.py",
            line=10,
            end_line=10,
            message="Test message",
        )
        d = f.to_dict()
        assert d["rule_id"] == "TEST001"
        assert d["severity"] == "error"
        assert d["message"] == "Test message"

    def test_finding_with_context(self):
        f = Finding(
            rule_id="SEC001",
            rule_name="hardcoded-secret",
            severity=RuleSeverity.ERROR,
            file="test.py",
            line=1,
            end_line=1,
            context="line1: secret = 'xxx'\n",
            confidence=0.95,
        )
        assert f.context == "line1: secret = 'xxx'\n"
        assert f.confidence == 0.95


class TestRuleSeverity:
    def test_to_numeric_error(self):
        assert RuleSeverity.ERROR.to_numeric() == 1.0

    def test_to_numeric_warning(self):
        assert RuleSeverity.WARNING.to_numeric() == 0.7

    def test_to_numeric_info(self):
        assert RuleSeverity.INFO.to_numeric() == 0.4

    def test_to_numeric_hint(self):
        assert RuleSeverity.HINT.to_numeric() == 0.2


class TestRuleEngine:
    def setup_method(self):
        self.engine = RuleEngine()

    def test_builtin_rules_count(self):
        assert len(self.engine._rules) >= 28

    def test_get_rule(self):
        rule = self.engine.get_rule("SEC001")
        assert rule is not None
        assert rule.id == "SEC001"

    def test_get_rule_not_found(self):
        rule = self.engine.get_rule("NONEXISTENT")
        assert rule is None

    def test_get_rules_by_language(self):
        rules = self.engine.get_rules_by_language("python")
        assert len(rules) > 0

    def test_get_rules_by_language_js(self):
        rules = self.engine.get_rules_by_language("javascript")
        assert len(rules) > 0

    def test_get_rules_by_severity(self):
        rules = self.engine.get_rules_by_severity(RuleSeverity.ERROR)
        assert all(r.severity == RuleSeverity.ERROR for r in rules)

    def test_get_rules_by_tag(self):
        rules = self.engine.get_rules_by_tag("security")
        assert all("security" in r.tags for r in rules)

    def test_get_rules_by_tag_python(self):
        rules = self.engine.get_rules_by_tag("python")
        assert all("python" in r.languages for r in rules)

    def test_register_custom_rule(self):
        rule = Rule(
            id="CUSTOM001",
            name="custom-rule",
            description="Custom test rule",
            severity=RuleSeverity.HINT,
            languages=["python"],
            patterns=[r"test_pattern"],
        )
        self.engine.register(rule)
        assert self.engine.get_rule("CUSTOM001") is not None

    def test_register_duplicate_rule_raises(self):
        rule = Rule(
            id="SEC001",
            name="duplicate",
            description="Duplicate",
            severity=RuleSeverity.INFO,
            languages=["python"],
        )
        with pytest.raises(ValueError):
            self.engine.register(rule)

    def test_unregister_rule(self):
        result = self.engine.unregister("SEC001")
        assert result is True
        assert self.engine.get_rule("SEC001") is None

    def test_unregister_nonexistent(self):
        result = self.engine.unregister("NONEXISTENT")
        assert result is False

    def test_detect_hardcoded_secret(self, tmp_path):
        code = 'api_key = "sk-1234567890abcdefghijklmnopqrstuvwxyz"\n'
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        findings = self.engine.detect(str(tmp_path / "test.py"), "python")
        assert len(findings) >= 1
        assert any(f.rule_id == "SEC001" for f in findings)

    def test_detect_sql_injection(self, tmp_path):
        code = 'cursor.execute("SELECT * FROM users WHERE id = %s" % user_id)\n'
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        findings = self.engine.detect(str(tmp_path / "test.py"), "python")
        assert len(findings) >= 1
        assert any(f.rule_id == "SEC002" for f in findings)

    def test_detect_eval_usage(self, tmp_path):
        code = "result = eval('2 + 2')\n"
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        findings = self.engine.detect(str(tmp_path / "test.py"), "python")
        assert len(findings) >= 1

    def test_detect_exec_usage(self, tmp_path):
        code = "exec('print(1)')\n"
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        findings = self.engine.detect(str(tmp_path / "test.py"), "python")
        assert len(findings) >= 1
        assert any(f.rule_id == "SEC005" for f in findings)

    def test_detect_shell_injection(self, tmp_path):
        code = "subprocess.run('ls', shell=True)\n"
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        findings = self.engine.detect(str(tmp_path / "test.py"), "python")
        assert len(findings) >= 1

    def test_detect_unsupported_language(self):
        findings = self.engine.detect("file.unknown", "unknown_lang")
        assert len(findings) == 0

    def test_detect_missing_file(self):
        findings = self.engine.detect("/nonexistent/file.py", "python")
        assert len(findings) == 0

    def test_detect_all(self, tmp_path):
        (tmp_path / "a.py").write_text("eval('1')\n")
        (tmp_path / "b.py").write_text("exec('2')\n")
        findings = self.engine.detect_all(str(tmp_path))
        assert len(findings) > 0

    def test_deduplication(self, tmp_path):
        code = "def func():\n    print(1)\n    print(2)\n"
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        findings = self.engine.detect(str(tmp_path / "test.py"), "python")
        seen = set()
        for f in findings:
            key = (f.rule_id, f.file, f.line, f.end_line)
            seen.add(key)
        assert len(findings) == len(seen)

    def test_get_stats(self, tmp_path):
        code = 'api_key = "sk-test1234567890abcdefghijklmn"\n'
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        findings = self.engine.detect(str(tmp_path / "test.py"), "python")
        stats = self.engine.get_stats(findings)
        assert stats["total"] >= 1
        assert "error" in stats["by_severity"]

    def test_get_stats_empty(self):
        stats = self.engine.get_stats([])
        assert stats["total"] == 0
        assert stats["files_with_issues"] == 0

    def test_merge_findings(self):
        f1 = Finding(
            rule_id="SEC001", rule_name="sec", severity=RuleSeverity.ERROR,
            file="a.py", line=1, end_line=1,
        )
        f2 = Finding(
            rule_id="SEC002", rule_name="sec2", severity=RuleSeverity.WARNING,
            file="b.py", line=5, end_line=5,
        )
        merged = self.engine.merge_findings([[f1], [f2]])
        assert len(merged) == 2

    def test_context_lines(self):
        lines = ["line0", "line1", "line2", "line3", "line4", "line5"]
        ctx = self.engine._get_context_lines(lines, 3)
        assert isinstance(ctx, str)

    def test_skip_path(self):
        assert self.engine._should_skip_path(Path("node_modules/test.py"))
        assert self.engine._should_skip_path(Path("venv/lib/test.py"))
        assert self.engine._should_skip_path(Path(".git/test.py"))
        assert self.engine._should_skip_path(Path("dist/test.py"))
        assert not self.engine._should_skip_path(Path("src/test.py"))
        assert not self.engine._should_skip_path(Path("tests/test.py"))

    def test_detect_language(self):
        assert self.engine._detect_language(Path("test.py")) == "python"
        assert self.engine._detect_language(Path("test.js")) == "javascript"
        assert self.engine._detect_language(Path("test.ts")) == "typescript"
        assert self.engine._detect_language(Path("test.tsx")) == "typescript"
        assert self.engine._detect_language(Path("test.c")) == "c"
        assert self.engine._detect_language(Path("test.cpp")) == "cpp"
        assert self.engine._detect_language(Path("test.h")) == "c"
        assert self.engine._detect_language(Path("test.rs")) == "rust"
        assert self.engine._detect_language(Path("test.go")) == "go"
        assert self.engine._detect_language(Path("test.java")) == "java"

    def test_apply_fix(self, tmp_path):
        code = 'api_key = "sk-test"\n'
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        findings = self.engine.detect(str(tmp_path / "test.py"), "python")
        assert len(findings) > 0
        fix = self.engine.apply_fix(findings[0])
        assert isinstance(fix, str)

    def test_format_finding_message(self):
        rule = Rule(
            id="TEST001",
            name="test",
            description="Test description",
            severity=RuleSeverity.ERROR,
            languages=["python"],
        )
        msg = self.engine._format_finding_message(rule, "matched_text")
        assert "TEST001" in msg
        assert "test" in msg

    def test_format_finding_message_truncates_long_match(self):
        rule = Rule(
            id="TEST001",
            name="test",
            description="Test",
            severity=RuleSeverity.ERROR,
            languages=["python"],
        )
        long_text = "x" * 100
        msg = self.engine._format_finding_message(rule, long_text)
        assert len(msg) < len(long_text) + 50

    def test_format_finding_message_with_cwe(self):
        rule = Rule(
            id="SEC001",
            name="hardcoded-secret",
            description="Secret detected",
            severity=RuleSeverity.ERROR,
            languages=["python"],
            cwe_id="CWE-798",
        )
        msg = self.engine._format_finding_message(rule, "secret")
        assert "CWE-798" in msg

    def test_external_linter_unknown(self):
        findings = self.engine.run_external_linter("unknown_linter", "test.py")
        assert len(findings) == 0

    def test_format_summary(self, tmp_path):
        code = 'api_key = "sk-1234567890abcdefghijklmnopqrstuvwxyz"\n'
        (tmp_path / "test.py").write_text(code, encoding="utf-8")
        findings = self.engine.detect(str(tmp_path / "test.py"), "python")
        assert len(findings) > 0
        summary = self.engine.get_stats(findings)
        assert "total" in summary
        assert "by_severity" in summary
