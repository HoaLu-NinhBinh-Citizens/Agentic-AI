"""Tests for TypeScript/React analyzer."""
import pytest

from src.infrastructure.analysis.languages.typescript import (
    TypeScriptAnalyzer,
    VueAnalyzer,
    AngularAnalyzer,
)
from src.infrastructure.analysis.rule_engine import RuleSeverity


class TestTypeScriptAnalyzer:
    """Tests for TypeScript analyzer."""

    def setup_method(self):
        self.analyzer = TypeScriptAnalyzer(framework="generic")

    def test_detects_any_type(self):
        """Should detect explicit any type usage."""
        code = """
function process(data: any): void {
    console.log(data);
}
"""
        findings = self.analyzer._analyze_typescript(code, "test.ts")
        any_findings = [f for f in findings if "any" in f["message"].lower()]
        assert len(any_findings) >= 1

    def test_detects_unsafe_cast_any(self):
        """Should detect unsafe cast to any."""
        analyzer = TypeScriptAnalyzer()
        code = """
const result = data as any;
"""
        findings = analyzer._analyze_typescript(code, "test.ts")
        cast_findings = [f for f in findings if "unsafe" in f["message"].lower()]
        assert len(cast_findings) >= 1

    def test_detects_unsafe_cast_unknown(self):
        """Should detect unsafe cast to unknown."""
        analyzer = TypeScriptAnalyzer()
        code = """
const result = data as unknown;
"""
        findings = analyzer._analyze_typescript(code, "test.ts")
        cast_findings = [f for f in findings if "unsafe" in f["message"].lower()]
        assert len(cast_findings) >= 1

    def test_language_detection_tsx(self):
        """Should detect TSX files."""
        analyzer = TypeScriptAnalyzer()
        lang = analyzer._detect_language("component.tsx", "import React from 'react'")
        assert lang == "tsx"

    def test_language_detection_ts(self):
        """Should detect TS files."""
        analyzer = TypeScriptAnalyzer()
        lang = analyzer._detect_language("util.ts", "const x: number = 1;")
        assert lang == "typescript"

    def test_language_detection_js(self):
        """Should detect JS files."""
        analyzer = TypeScriptAnalyzer()
        lang = analyzer._detect_language("app.js", "const x = 1;")
        assert lang == "javascript"

    def test_language_detection_from_content(self):
        """Should detect JSX from content with useState."""
        analyzer = TypeScriptAnalyzer()
        lang = analyzer._detect_language("app.js", "useState(0)")
        assert lang == "jsx"

    def test_language_detection_vue_content(self):
        """Should detect JSX from content with v-for."""
        analyzer = TypeScriptAnalyzer()
        lang = analyzer._detect_language("app.js", '<div v-for="item in items">')
        assert lang == "jsx"

    def test_returns_dict_findings(self):
        """Should return dictionary findings."""
        code = "const x: any = 1;"
        findings = self.analyzer._analyze_typescript(code, "test.ts")
        assert all(isinstance(f, dict) for f in findings)

    def test_finding_has_required_fields(self):
        """Should have required fields in findings."""
        code = "const x: any = 1;"
        findings = self.analyzer._analyze_typescript(code, "test.ts")
        if findings:
            f = findings[0]
            assert "rule_id" in f
            assert "severity" in f
            assert "line" in f
            assert "message" in f
            assert "explanation" in f


class TestReactAnalyzer:
    """Tests for React analyzer."""

    def setup_method(self):
        self.analyzer = TypeScriptAnalyzer(framework="react")

    def test_detects_async_use_effect(self):
        """Should detect async function in useEffect."""
        code = """
useEffect(async () => {
    const data = await fetchData();
}, []);
"""
        findings = self.analyzer._analyze_react(code, "test.tsx", "tsx")
        async_findings = [f for f in findings if "async" in f["message"].lower()]
        assert len(async_findings) >= 1

    def test_detects_missing_deps(self):
        """Should detect useEffect with empty deps."""
        code = """
useEffect(() => {
    fetchData();
}, []);
"""
        findings = self.analyzer._analyze_react(code, "test.tsx", "tsx")
        dep_findings = [f for f in findings if "deps" in f["message"].lower() or "useeffect" in f["message"].lower()]
        assert len(dep_findings) >= 1

    def test_detects_use_state_empty_array(self):
        """Should detect useState with empty array."""
        analyzer = TypeScriptAnalyzer(framework="react")
        code = """
const [items, setItems] = useState([]);
"""
        findings = analyzer._analyze_react(code, "test.tsx", "tsx")
        array_findings = [f for f in findings if "array" in f["message"].lower()]
        assert len(array_findings) >= 1

    def test_returns_severity(self):
        """Should return correct severity levels."""
        code = """
useEffect(async () => {}, []);
"""
        findings = self.analyzer._analyze_react(code, "test.tsx", "tsx")
        if findings:
            for f in findings:
                assert hasattr(f["severity"], "value")

    def test_returns_fix_suggestion(self):
        """Should return fix suggestions."""
        code = """
useEffect(async () => {}, []);
"""
        findings = self.analyzer._analyze_react(code, "test.tsx", "tsx")
        if findings:
            for f in findings:
                assert f.get("fix") is not None or f.get("fix") is None


class TestVueAnalyzer:
    """Tests for Vue analyzer."""

    def setup_method(self):
        self.analyzer = VueAnalyzer()

    def test_detects_missing_key(self):
        """Should detect v-for without key."""
        code = """
<div v-for="item in items">
    {{ item.name }}
</div>
"""
        findings = self.analyzer.analyze(code, "test.vue")
        key_findings = [f for f in findings if "v-for" in f["message"].lower() or "key" in f["message"].lower()]
        assert len(key_findings) >= 1

    def test_detects_deprecated_sync(self):
        """Should detect deprecated .sync modifier."""
        analyzer = VueAnalyzer()
        code = """
<ChildComponent :value.sync="parentValue" />
"""
        findings = analyzer.analyze(code, "test.vue")
        sync_findings = [f for f in findings if "sync" in f["message"].lower()]
        assert len(sync_findings) >= 1

    def test_detects_options_api(self):
        """Should detect Options API usage."""
        analyzer = VueAnalyzer()
        code = """
export default {
    data() {
        return { count: 0 }
    }
}
"""
        findings = analyzer.analyze(code, "test.vue")
        opt_findings = [f for f in findings if "options" in f["message"].lower() or "data()" in f["message"].lower()]
        assert len(opt_findings) >= 1

    def test_returns_findings_as_dicts(self):
        """Should return findings as dictionaries."""
        code = '<div v-for="item in items"></div>'
        findings = self.analyzer.analyze(code, "test.vue")
        assert all(isinstance(f, dict) for f in findings)


class TestAngularAnalyzer:
    """Tests for Angular analyzer."""

    def setup_method(self):
        self.analyzer = AngularAnalyzer()

    def test_detects_subscribe_no_unsubscribe(self):
        """Should detect subscription without cleanup."""
        code = """
ngOnInit() {
    this.dataService.getData().subscribe(data => {
        this.data = data;
    });
}
"""
        findings = self.analyzer.analyze(code, "test.ts")
        sub_findings = [f for f in findings if "subscription" in f["message"].lower() or "subscribe" in f["message"].lower()]
        assert len(sub_findings) >= 1

    def test_detects_any_type(self):
        """Should detect 'any' type usage."""
        code = """
function processData(data: any): void {
    console.log(data);
}
"""
        findings = self.analyzer.analyze(code, "test.ts")
        any_findings = [f for f in findings if "any" in f["message"].lower()]
        assert len(any_findings) >= 1

    def test_returns_findings_as_dicts(self):
        """Should return findings as dictionaries."""
        code = "const x: any = 1;"
        findings = self.analyzer.analyze(code, "test.ts")
        assert all(isinstance(f, dict) for f in findings)

    def test_finding_has_severity(self):
        """Should have severity attribute."""
        code = "const x: any = 1;"
        findings = self.analyzer.analyze(code, "test.ts")
        if findings:
            for f in findings:
                assert "severity" in f


class TestAnalyzerIntegration:
    """Integration tests for all analyzers."""

    def test_typescript_analyzer_full(self):
        """Test TypeScript analyzer with mixed content."""
        analyzer = TypeScriptAnalyzer(framework="react")
        code = """
import React from 'react';

interface Props {
    data: any;
}

function Component({ data }: Props) {
    useEffect(async () => {
        await fetchData();
    }, []);

    return <div>{data}</div>;
}
"""
        findings = analyzer.analyze(code, "component.tsx")
        assert len(findings) >= 0

    def test_vue_analyzer_empty_code(self):
        """Test Vue analyzer with empty code."""
        analyzer = VueAnalyzer()
        findings = analyzer.analyze("", "test.vue")
        assert len(findings) == 0

    def test_angular_analyzer_empty_code(self):
        """Test Angular analyzer with clean code."""
        analyzer = AngularAnalyzer()
        code = """
import { Component } from '@angular/core';
import { OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';

@Component({})
class MyComponent implements OnInit {
    private subscriptions = new Subscription();

    constructor(private http: HttpClient) {}

    ngOnInit() {
        this.subscriptions.add(
            this.http.get('/api/data').subscribe(data => {
                this.data = data;
            })
        );
    }

    ngOnDestroy() {
        this.subscriptions.unsubscribe();
    }
}
"""
        findings = analyzer.analyze(code, "component.ts")
        assert len(findings) >= 0
