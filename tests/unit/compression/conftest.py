"""Pytest configuration for compression tests."""

import pytest
import sys
from pathlib import Path

src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


@pytest.fixture(scope="session")
def anyio_backend():
    """Configure anyio backend for pytest-asyncio."""
    return "asyncio"


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "chaos: mark test as chaos test"
    )
