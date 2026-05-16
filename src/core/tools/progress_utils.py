"""
Progress bar utilities using tqdm.

Provides:
- Context managers for long-running operations
- Progress wrappers for async operations
- Rich console output with ETA
"""

import asyncio
import logging
import sys
import time
from typing import Any, Callable, Iterable, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def get_progress_bar(*args, **kwargs):
    """
    Create a tqdm progress bar, falling back to a no-op wrapper if tqdm is unavailable.

    Usage:
        pbar = get_progress_bar(iterable, total=100, desc="Indexing PDFs")
        for item in pbar:
            process(item)
        pbar.close()
    """
    try:
        from tqdm import tqdm as _tqdm
        return _tqdm(*args, **kwargs)
    except ImportError:
        return NoOpProgressBar()


class NoOpProgressBar:
    """No-op fallback when tqdm is not installed."""

    def __init__(self, iterable: Optional[Iterable] = None, total: Optional[int] = None, **kwargs):
        self.iterable = iterable
        self.total = total
        self.n = 0
        self._closed = False

    def __iter__(self):
        if self.iterable is not None:
            yield from self.iterable

    def update(self, n: int = 1):
        self.n += n

    def set_description(self, desc: str):
        pass

    def set_postfix(self, **kwargs):
        pass

    def close(self):
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


async def progress_async(
    iterable: Iterable[T],
    desc: str = "",
    total: Optional[int] = None,
    show_progress: bool = True,
) -> List[T]:
    """
    Async wrapper that collects items from an async iterator with optional progress bar.

    For truly async iterables, use progress_async_iter instead.
    """
    if not show_progress:
        return list(iterable)

    try:
        from tqdm import tqdm as _tqdm
        results = []
        pbar = _tqdm(iterable, desc=desc, total=total, unit="item")
        for item in pbar:
            results.append(item)
        pbar.close()
        return results
    except ImportError:
        return list(iterable)


async def progress_async_iter(
    async_iter,
    desc: str = "",
    total: Optional[int] = None,
    show_progress: bool = True,
):
    """
    Wrap an async iterator with a tqdm progress bar.

    Usage:
        async for item in progress_async_iter(generate_items(), desc="Processing"):
            await process(item)
    """
    if not show_progress:
        async for item in async_iter:
            yield item
        return

    try:
        from tqdm import tqdm as _tqdm
        import aiostream
    except ImportError:
        async for item in async_iter:
            yield item
        return

    pbar = _tqdm(total=total, desc=desc, unit="item")
    try:
        async with aiostream.streamlist(async_iter).stream() as streamer:
            async for item in streamer:
                pbar.update(1)
                yield item
    finally:
        pbar.close()


def make_progress_callback(total: int, desc: str = "", unit: str = "step") -> Callable[[int], None]:
    """
    Create a simple progress callback for tqdm.

    Usage:
        callback = make_progress_callback(total=10, desc="Building")
        for step in range(10):
            do_work()
            callback(1)
    """
    try:
        from tqdm import tqdm as _tqdm
        pbar = _tqdm(total=total, desc=desc, unit=unit)
        return pbar.update
    except ImportError:
        count = [0]

        def noop_update(n: int = 1):
            count[0] += n

        return noop_update


class Spinner:
    """Simple spinner for CLI feedback during long operations."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = "", interval_ms: int = 80):
        self.message = message
        self.interval_ms = interval_ms
        self._running = False
        self._task = None
        self._count = 0

    async def __aenter__(self):
        self._running = True
        self._task = asyncio.create_task(self._spin())
        return self

    async def __aexit__(self, *args):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _spin(self):
        """Async spinner task."""
        import sys
        while self._running:
            frame = self.FRAMES[self._count % len(self.FRAMES)]
            print(f"\r{frame} {self.message}", end="", flush=True)
            self._count += 1
            await asyncio.sleep(self.interval_ms / 1000.0)
        # Clear line
        print(f"\r{' ' * (len(self.message) + 3)}\r", end="", flush=True)

    def set_message(self, message: str):
        self.message = message


def print_progress_table(headers: List[str], rows: List[List[Any]], title: str = ""):
    """
    Print a formatted ASCII table with progress-style formatting.

    Usage:
        print_progress_table(
            ["Step", "Status", "Time"],
            [["Configure", "OK", "2.1s"], ["Build", "FAIL", "1.0s"]],
            title="Build Results"
        )
    """
    if not rows:
        return

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    total_width = sum(col_widths) + len(headers) * 3 + 1
    separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    if title:
        print(f"\n{title}")
        print("=" * total_width)

    print(separator)
    header_row = "|" + "|".join(f" {h:<{col_widths[i]}} " for i, h in enumerate(headers)) + "|"
    print(header_row)
    print(separator)
    for row in rows:
        row_str = "|" + "|".join(f" {str(cell):<{col_widths[i]}} " for i, cell in enumerate(row)) + "|"
        print(row_str)
    print(separator)


class RichProgressDisplay:
    """
    Multi-line progress display that updates in place.

    Shows a list of items with their current status, e.g.:
        [1/5] Indexing PDF 1 ...  8.2s
        [2/5] Indexing PDF 2 OK    3.1s
        [3/5] Indexing PDF 3 FAIL  0.5s
        [4/5] Indexing PDF 4 ...  12.0s
        [5/5] Indexing PDF 5 ...
    """

    def __init__(self, total: int, prefix: str = "", width: int = 60):
        self.total = total
        self.prefix = prefix
        self.width = width
        self.items: List[dict] = [{"status": "pending", "elapsed": 0} for _ in range(total)]
        self._started = False

    def start(self):
        self._started = True
        self._print()

    def update_status(self, index: int, status: str, elapsed: float = 0):
        if 0 <= index < self.total:
            self.items[index]["status"] = status
            self.items[index]["elapsed"] = elapsed
            self._print()

    def update(self, index: int, **kwargs):
        if 0 <= index < self.total:
            self.items[index].update(kwargs)
            self._print()

    def _print(self):
        if not self._started:
            return
        lines = []
        for i, item in enumerate(self.items, start=1):
            status_icon = {"pending": "...", "running": "...", "ok": "OK  ", "fail": "FAIL", "skip": "SKIP"}.get(
                item.get("status", "pending"), "...."
            )
            label = item.get("label", f"Step {i}/{self.total}")
            elapsed = item.get("elapsed", 0)
            lines.append(f"[{i}/{self.total}] {label} {status_icon} {elapsed:.1f}s")

        # Move cursor up and redraw
        cursor_up = f"\033[{len(lines)}A" if lines else ""
        print(cursor_up, end="")
        for line in lines[-min(len(lines), 10):]:  # Show max 10 lines
            print(f"\r{line[:self.width]:<{self.width}}")
        print("\033[J", end="")  # Clear to end of screen

    def finish(self):
        self._started = False
        print()  # newline
