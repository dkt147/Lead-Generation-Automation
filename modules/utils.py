"""
Utility module with shared helpers.
Provides retry logic with exponential backoff for API calls.
"""

import time
import logging
import functools
from typing import Callable, Tuple, Type

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    Decorator that retries a function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay cap in seconds
        backoff_factor: Multiplier applied to delay each retry
        retryable_exceptions: Tuple of exception types that trigger a retry
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
                        raise
                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)

            raise last_exception

        return wrapper
    return decorator


class ProgressTracker:
    """Tracks and displays real-time progress for pipeline steps."""

    def __init__(self, total_steps: int = 4):
        self.total_steps = total_steps
        self.current_step = 0
        self.step_results = {}

    def start_step(self, step_name: str, step_number: int, total_items: int = 0):
        """Signal the start of a pipeline step."""
        self.current_step = step_number
        print(f"\n{'='*60}")
        print(f"  Step {step_number}/{self.total_steps}: {step_name}")
        print(f"{'='*60}")
        if total_items > 0:
            print(f"  Processing {total_items} items...")

    def update_item(self, current: int, total: int, item_name: str, status: str = "processing"):
        """Update progress for an individual item within a step."""
        bar_width = 30
        filled = int(bar_width * current / total) if total > 0 else 0
        bar = '#' * filled + '-' * (bar_width - filled)
        pct = (current / total * 100) if total > 0 else 0
        print(f"  [{bar}] {pct:5.1f}% ({current}/{total}) - {status}: {item_name}")

    def complete_step(self, step_number: int, summary: str):
        """Mark a step as complete with a summary."""
        self.step_results[step_number] = summary
        print(f"  >> {summary}")

    def print_summary(self, extra_stats: dict = None):
        """Print final pipeline summary."""
        print(f"\n{'='*60}")
        print(f"  PIPELINE COMPLETE - Summary")
        print(f"{'='*60}")
        for step_num in sorted(self.step_results):
            print(f"  Step {step_num}: {self.step_results[step_num]}")
        if extra_stats:
            print(f"  {'-'*40}")
            for key, value in extra_stats.items():
                print(f"  {key}: {value}")
        print(f"{'='*60}\n")
