"""Codex-Style Agent Evaluation Package.

This package provides comprehensive agent evaluation framework:

Quick Start:
```python
from tests.evaluation import get_all_scenarios, EvaluationFramework

# Register scenarios
framework = EvaluationFramework()
framework.register_scenarios(get_all_scenarios())

# Run evaluation
result = await framework.run_suite(
    suite_name="Codex Evaluation",
    agent_executor=your_agent_executor,
)

# Generate report
print(framework.generate_report(result))
```

Components:
- framework.py: Core evaluation framework and metrics
- scenarios_levels_1_3.py: Level 1-3 test scenarios
- scenarios_levels_4_7.py: Level 4-7 test scenarios
- harness_evaluator.py: AgentHarness integration
- test_codex_evaluation.py: Pytest integration
"""

from tests.evaluation.framework import (
    EvaluationFramework,
    EvaluationLevel,
    EvaluationMetric,
    EvaluationMetrics,
    EvaluationSuiteResult,
    FailureInjector,
    MetricsCollector,
    TestResult,
    TestScenario,
    TestScenarioType,
    Tracer,
    TrapScenario,
    VerificationResult,
    get_evaluation_framework,
)

from tests.evaluation.scenarios_levels_1_3 import (
    get_all_early_scenarios,
    get_all_level_1_scenarios,
    get_all_level_2_scenarios,
    get_all_level_3_scenarios,
)

from tests.evaluation.scenarios_levels_4_7 import (
    get_all_advanced_scenarios,
    get_all_level_4_scenarios,
    get_all_level_5_scenarios,
    get_all_level_6_scenarios,
    get_all_level_7_scenarios,
    get_all_scenarios,
)

from tests.evaluation.harness_evaluator import (
    HarnessEvaluator,
    HarnessEvaluationResult,
    MockAgentExecutor,
)


__all__ = [
    # Framework
    "EvaluationFramework",
    "EvaluationLevel",
    "EvaluationMetric",
    "EvaluationMetrics",
    "EvaluationSuiteResult",
    "FailureInjector",
    "MetricsCollector",
    "TestResult",
    "TestScenario",
    "TestScenarioType",
    "Tracer",
    "TrapScenario",
    "VerificationResult",
    "get_evaluation_framework",
    # Harness
    "HarnessEvaluator",
    "HarnessEvaluationResult",
    "MockAgentExecutor",
    # Scenarios
    "get_all_scenarios",
    "get_all_early_scenarios",
    "get_all_advanced_scenarios",
    "get_all_level_1_scenarios",
    "get_all_level_2_scenarios",
    "get_all_level_3_scenarios",
    "get_all_level_4_scenarios",
    "get_all_level_5_scenarios",
    "get_all_level_6_scenarios",
    "get_all_level_7_scenarios",
]
