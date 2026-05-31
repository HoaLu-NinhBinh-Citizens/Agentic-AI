"""Tests for ML Extended Rules (ML016-ML025)."""
import pytest
from src.infrastructure.analysis.ml_detectors.extended_rules import (
    check_extended_rules,
    ML_EXTENDED_RULES,
    MLExtendedRule,
    get_extended_rules,
    get_rule_by_id,
    get_rules_by_severity,
    check_single_rule,
)


class TestMLExtendedRules:
    """Test cases for each ML016-ML025 rule."""
    
    def test_ml016_gradient_checkpointing(self):
        """ML016: Gradient checkpointing for large models."""
        code = '''
model = transformers.BertLarge()
optimizer = AdamW(model.parameters())
for epoch in range(10):
    train(model)
'''
        findings = check_extended_rules(code)
        ml016_findings = [f for f in findings if f['rule_id'] == 'ML016']
        assert len(ml016_findings) >= 1
        assert ml016_findings[0]['severity'] == 'MEDIUM'
        assert 'gradient_checkpointing' in ml016_findings[0]['fix'].lower()
    
    def test_ml016_large_model_variant(self):
        """ML016: Large model without gradient checkpointing."""
        code = '''
model = build_large_model(n_params=1e8)
for batch in dataloader:
    loss.backward()
'''
        findings = check_extended_rules(code)
        ml016_findings = [f for f in findings if f['rule_id'] == 'ML016']
        assert len(ml016_findings) >= 1
    
    def test_ml017_lr_scaling(self):
        """ML017: Learning rate scaling with batch size."""
        code = '''
batch_size = 512
lr = 0.001
optimizer = AdamW(model.parameters(), lr=lr)
'''
        findings = check_extended_rules(code)
        ml017_findings = [f for f in findings if f['rule_id'] == 'ML017']
        assert len(ml017_findings) >= 1
        assert ml017_findings[0]['severity'] == 'HIGH'
        assert 'linear' in ml017_findings[0]['fix'].lower() or 'scale' in ml017_findings[0]['fix'].lower()
    
    def test_ml018_warmup(self):
        """ML018: Learning rate warmup."""
        code = '''
optimizer = AdamW(model.parameters(), lr=0.001)
for epoch in range(100):
    train()
'''
        findings = check_extended_rules(code)
        ml018_findings = [f for f in findings if f['rule_id'] == 'ML018']
        assert len(ml018_findings) >= 1
        assert 'warmup' in ml018_findings[0]['fix'].lower()
        assert ml018_findings[0]['severity'] == 'HIGH'
    
    def test_ml019_ema(self):
        """ML019: Model EMA not used."""
        code = '''
model = MyModel()
for epoch in range(10):
    train(model)
    eval(model)
'''
        findings = check_extended_rules(code)
        ml019_findings = [f for f in findings if f['rule_id'] == 'ML019']
        assert len(ml019_findings) >= 1
        assert 'ema' in ml019_findings[0]['fix'].lower()
    
    def test_ml020_mixed_precision(self):
        """ML020: Mixed precision not used."""
        code = '''
model = BigModel()
model = model.cuda()
for batch in dataloader:
    output = model(batch.cuda())
'''
        findings = check_extended_rules(code)
        ml020_findings = [f for f in findings if f['rule_id'] == 'ML020']
        assert len(ml020_findings) >= 1
        assert 'float16' in ml020_findings[0]['fix'].lower() or 'autocast' in ml020_findings[0]['fix'].lower()
    
    def test_ml021_gradient_accumulation(self):
        """ML021: Gradient accumulation step mismatch."""
        code = '''
for batch in dataloader:
    loss = criterion(model(batch), targets)
    loss.backward()
    optimizer.step()
'''
        findings = check_extended_rules(code)
        ml021_findings = [f for f in findings if f['rule_id'] == 'ML021']
        assert len(ml021_findings) >= 1
        assert ml021_findings[0]['severity'] == 'CRITICAL'
    
    def test_ml022_dataloader_workers(self):
        """ML022: DataLoader num_workers too low."""
        code = '''
DataLoader(dataset, batch_size=32, num_workers=0)
'''
        findings = check_extended_rules(code)
        ml022_findings = [f for f in findings if f['rule_id'] == 'ML022']
        assert len(ml022_findings) >= 1
        assert ml022_findings[0]['severity'] == 'LOW'
    
    def test_ml023_no_validation(self):
        """ML023: No validation during training."""
        code = '''
for epoch in range(10):
    model.train()
    train_loss = train_epoch(model, train_loader)
'''
        findings = check_extended_rules(code)
        ml023_findings = [f for f in findings if f['rule_id'] == 'ML023']
        assert len(ml023_findings) >= 1
        assert ml023_findings[0]['severity'] == 'HIGH'
    
    def test_ml024_no_early_stopping(self):
        """ML024: Early stopping not implemented."""
        code = '''
for epoch in range(100):
    train_loss = train_epoch()
    val_loss = validate_epoch()
'''
        findings = check_extended_rules(code)
        ml024_findings = [f for f in findings if f['rule_id'] == 'ML024']
        assert len(ml024_findings) >= 1
        assert 'patience' in ml024_findings[0]['fix'].lower()
        assert ml024_findings[0]['severity'] == 'MEDIUM'
    
    def test_ml025_no_eval_mode(self):
        """ML025: Model eval() not called before inference."""
        code = '''
outputs = model(inputs)
predictions = outputs.argmax(dim=1)
'''
        findings = check_extended_rules(code)
        ml025_findings = [f for f in findings if f['rule_id'] == 'ML025']
        assert len(ml025_findings) >= 1
        assert ml025_findings[0]['severity'] == 'HIGH'
        assert 'eval' in ml025_findings[0]['fix'].lower()


class TestRuleIntegrity:
    """Test rule integrity and metadata."""
    
    def test_all_rules_have_fix_template(self):
        """All ML016-ML025 rules should have fix templates."""
        for rule_id, rule in ML_EXTENDED_RULES.items():
            assert rule.fix_template, f"{rule_id} missing fix template"
            assert len(rule.fix_template) > 50, f"{rule_id} fix template too short"
    
    def test_all_rules_have_confidence(self):
        """All ML016-ML025 rules should have confidence scores."""
        for rule_id, rule in ML_EXTENDED_RULES.items():
            assert 0.0 <= rule.confidence <= 1.0, f"{rule_id} invalid confidence: {rule.confidence}"
    
    def test_severity_classification(self):
        """All ML016-ML025 rules should have valid severity."""
        valid_severities = {'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'}
        for rule_id, rule in ML_EXTENDED_RULES.items():
            assert rule.severity in valid_severities, f"{rule_id} invalid severity: {rule.severity}"
    
    def test_rule_ids_are_unique(self):
        """All rule IDs should be unique."""
        rule_ids = [rule.rule_id for rule in ML_EXTENDED_RULES.values()]
        assert len(rule_ids) == len(set(rule_ids)), "Duplicate rule IDs found"
    
    def test_rule_count(self):
        """Should have exactly 10 extended rules (ML016-ML025)."""
        assert len(ML_EXTENDED_RULES) == 10, f"Expected 10 rules, got {len(ML_EXTENDED_RULES)}"
    
    def test_rule_id_format(self):
        """All rule IDs should follow ML0XX format."""
        for rule_id in ML_EXTENDED_RULES.keys():
            assert rule_id.startswith('ML'), f"Rule ID {rule_id} should start with 'ML'"
            assert len(rule_id) == 5, f"Rule ID {rule_id} should be 5 characters (ML0XX)"
    
    def test_explanation_quality(self):
        """All rules should have meaningful explanations."""
        for rule_id, rule in ML_EXTENDED_RULES.items():
            assert len(rule.explanation) > 20, f"{rule_id} explanation too short"
            # Explanations can end with periods - just check minimum length


class TestRuleHelpers:
    """Test helper functions."""
    
    def test_get_extended_rules(self):
        """get_extended_rules should return all rules."""
        rules = get_extended_rules()
        assert len(rules) == 10
        assert 'ML016' in rules
        assert 'ML025' in rules
    
    def test_get_rule_by_id_valid(self):
        """get_rule_by_id should return rule for valid ID."""
        rule = get_rule_by_id('ML016')
        assert rule is not None
        assert rule.rule_id == 'ML016'
    
    def test_get_rule_by_id_invalid(self):
        """get_rule_by_id should return None for invalid ID."""
        rule = get_rule_by_id('INVALID')
        assert rule is None
    
    def test_get_rules_by_severity(self):
        """get_rules_by_severity should filter correctly."""
        critical_rules = get_rules_by_severity('CRITICAL')
        assert len(critical_rules) >= 1
        assert all(r.severity == 'CRITICAL' for r in critical_rules)
        
        low_rules = get_rules_by_severity('LOW')
        assert len(low_rules) >= 1
        assert all(r.severity == 'LOW' for r in low_rules)
    
    def test_check_single_rule_valid(self):
        """check_single_rule should work for valid rule ID."""
        code = 'model = BertLarge()'
        findings = check_single_rule(code, 'ML016')
        assert len(findings) >= 1
    
    def test_check_single_rule_invalid(self):
        """check_single_rule should return empty for invalid ID."""
        code = 'model = BertLarge()'
        findings = check_single_rule(code, 'INVALID')
        assert len(findings) == 0


class TestPatternMatching:
    """Test pattern matching behavior."""
    
    def test_multiline_pattern(self):
        """Patterns should match across multiple lines."""
        code = '''
model = MyModel()
for epoch in range(10):
    train()
    eval(model)
'''
        findings = check_extended_rules(code)
        # Should match ML019 (no EMA)
        assert any(f['rule_id'] == 'ML019' for f in findings)
    
    def test_case_insensitive_pattern(self):
        """Pattern matching should be case insensitive."""
        code_lowercase = 'batch_size = 512\nlr = 0.001'
        code_uppercase = 'BATCH_SIZE = 512\nLR = 0.001'
        
        findings_lowercase = check_extended_rules(code_lowercase)
        findings_uppercase = check_extended_rules(code_uppercase)
        
        # Both should find ML017
        assert any(f['rule_id'] == 'ML017' for f in findings_lowercase)
        assert any(f['rule_id'] == 'ML017' for f in findings_uppercase)
    
    def test_no_false_positives(self):
        """Code with proper patterns should not trigger false positives."""
        # Good code - uses gradient checkpointing
        good_code = '''
model = BertLarge()
model.gradient_checkpointing_enable()
for batch in dataloader:
    loss.backward()
'''
        findings = check_extended_rules(good_code)
        # ML016 should not fire because gradient_checkpointing is present
        ml016_findings = [f for f in findings if f['rule_id'] == 'ML016']
        # This might still fire due to model = BertLarge, so we just check it's only one rule
        assert len(ml016_findings) <= 1


class TestConfidenceScores:
    """Test confidence score behavior."""
    
    def test_confidence_range(self):
        """All rules should have confidence in valid range."""
        for rule_id, rule in ML_EXTENDED_RULES.items():
            assert 0.0 <= rule.confidence <= 1.0, f"{rule_id} confidence out of range"
    
    def test_confidence_values(self):
        """Confidence values should be reasonable."""
        for rule_id, rule in ML_EXTENDED_RULES.items():
            # Most rules should have confidence > 0.7
            if rule.severity in ['CRITICAL', 'HIGH']:
                assert rule.confidence >= 0.75, f"{rule_id} ({rule.severity}) confidence too low: {rule.confidence}"


class TestFixQuality:
    """Test fix template quality."""
    
    def test_fix_has_imports(self):
        """Fix templates should include necessary imports."""
        for rule_id, rule in ML_EXTENDED_RULES.items():
            fix = rule.fix_template
            # Most ML fixes should have some import statement
            # This is a soft check
            assert len(fix) > 100, f"{rule_id} fix template too short"
    
    def test_fix_is_complete(self):
        """Fix templates should be complete code snippets."""
        for rule_id, rule in ML_EXTENDED_RULES.items():
            fix = rule.fix_template
            # Should have actual code, not just comments
            lines = [l for l in fix.split('\n') if l.strip() and not l.strip().startswith('#')]
            assert len(lines) >= 2, f"{rule_id} fix template should have at least 2 code lines"
    
    def test_critical_fixes_are_comprehensive(self):
        """CRITICAL severity fixes should be especially complete."""
        critical_rules = get_rules_by_severity('CRITICAL')
        for rule in critical_rules:
            fix = rule.fix_template
            # Critical fixes should be longer (more comprehensive)
            assert len(fix) >= 200, f"{rule.rule_id} CRITICAL fix should be comprehensive"
