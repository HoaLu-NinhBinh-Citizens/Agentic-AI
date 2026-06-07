"""Language-specific rule sets for the Universal Rule Engine.

Each language module exports a `get_rules()` function returning
a list of UniversalRule instances.

Rule modules are loaded dynamically by the UniversalRuleEngine
based on detected project languages.
"""
