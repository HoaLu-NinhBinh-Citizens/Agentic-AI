import pytest


def _first_divergence(a: list[str], b: list[str]) -> tuple[int, str, str]:
    limit = min(len(a), len(b))
    for i in range(limit):
        if a[i] != b[i]:
            return i, a[i], b[i]
    if len(a) != len(b):
        i = limit
        return i, a[i] if i < len(a) else "<end>", b[i] if i < len(b) else "<end>"
    return -1, "", ""


def test_conformance_replay_diff_smoke():
    original = ["cmd1", "cmd2", "cmd3"]
    replay = ["cmd1", "cmdX", "cmd3"]

    idx, left, right = _first_divergence(original, replay)
    assert idx == 1
    assert left == "cmd2"
    assert right == "cmdX"
