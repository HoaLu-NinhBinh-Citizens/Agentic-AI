"""Tests for security rules."""

import pytest
from src.infrastructure.analysis.rules.security.sql_injection import SQLInjectionRule
from src.infrastructure.analysis.rules.security.hardcoded_secret import HardcodedSecretRule
from src.infrastructure.analysis.rules.security.command_injection import CommandInjectionRule
from src.infrastructure.analysis.rules.security.xss import XSSRule
from src.infrastructure.analysis.rules.security.path_traversal import PathTraversalRule
from src.infrastructure.analysis.rules.security.insecure_hash import InsecureHashRule
from src.infrastructure.analysis.rules.security.insecure_random import InsecureRandomRule


class TestSQLInjectionRule:
    """Tests for SQL injection detection."""

    def test_detects_cursor_execute_fstring(self):
        """Should detect cursor.execute with f-string."""
        rule = SQLInjectionRule()
        code = '''cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "SEC001"

    def test_allows_parameterized(self):
        """Should not flag parameterized queries."""
        rule = SQLInjectionRule()
        code = '''cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))'''
        findings = rule.detect(code, "test.py")
        assert len(findings) == 0

    def test_detects_string_concatenation(self):
        """Should detect SQL with string concatenation."""
        rule = SQLInjectionRule()
        code = '''query = "SELECT * FROM " + table_name'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1


class TestHardcodedSecretRule:
    """Tests for hardcoded secret detection."""

    def test_detects_password(self):
        """Should detect hardcoded password."""
        rule = HardcodedSecretRule()
        code = '''password = "secret123"'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "SEC002"

    def test_allows_placeholder(self):
        """Should not flag placeholders."""
        rule = HardcodedSecretRule()
        code = '''password = "xxx"'''
        findings = rule.detect(code, "test.py")
        assert len(findings) == 0

    def test_detects_api_key(self):
        """Should detect hardcoded API key."""
        rule = HardcodedSecretRule()
        code = '''api_key = "sk_live_abcdefghijklmnopqrst"'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1


class TestCommandInjectionRule:
    """Tests for command injection detection."""

    def test_detects_os_system_percent(self):
        """Should detect os.system with % formatting."""
        rule = CommandInjectionRule()
        code = '''os.system("ls %s" % user_input)'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "SEC003"

    def test_detects_subprocess_shell_true(self):
        """Should detect subprocess with shell=True."""
        rule = CommandInjectionRule()
        code = '''subprocess.run(cmd, shell=True)'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1


class TestXSSRule:
    """Tests for XSS detection."""

    def test_detects_render_template_string_with_brace(self):
        """Should detect render_template_string with brace."""
        rule = XSSRule()
        code = '''render_template_string("Hello {name}")'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "SEC004"


class TestPathTraversalRule:
    """Tests for path traversal detection."""

    def test_detects_open_with_user_input(self):
        """Should detect open with user input."""
        rule = PathTraversalRule()
        code = '''open("/files/" + request.args.get("filename"))'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "SEC005"


class TestInsecureHashRule:
    """Tests for insecure hash detection."""

    def test_detects_md5(self):
        """Should detect hashlib.md5 usage."""
        rule = InsecureHashRule()
        code = '''hash = hashlib.md5(data)'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "SEC006"

    def test_detects_sha1(self):
        """Should detect hashlib.sha1 usage."""
        rule = InsecureHashRule()
        code = '''hash = hashlib.sha1(data)'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1


class TestInsecureRandomRule:
    """Tests for insecure random detection."""

    def test_detects_random_random(self):
        """Should detect random.random usage."""
        rule = InsecureRandomRule()
        code = '''value = random.random()'''
        findings = rule.detect(code, "test.py")
        assert len(findings) >= 1
        assert findings[0]["rule_id"] == "SEC007"
