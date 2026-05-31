"""Documentation analysis rules."""

from .missing_docstring import MissingDocstringRule
from .outdated_docstring import OutdatedDocstringRule
from .missing_type_hints import MissingTypeHintsRule
from .broken_link import BrokenLinkRule
from .missing_example import MissingExampleRule

__all__ = [
    "MissingDocstringRule",
    "OutdatedDocstringRule",
    "MissingTypeHintsRule",
    "BrokenLinkRule",
    "MissingExampleRule",
]
