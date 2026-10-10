"""One monotonic deadline for every subprocess, retry and HTTP probe in an operation."""
from contextlib import contextmanager
from contextvars import ContextVar
import time

_end = ContextVar("onprem_deadline", default=None)


def remaining(limit=30):
    end = _end.get()
    value = limit if end is None else min(limit, end - time.monotonic())
    if value <= 0:
        raise RuntimeError("operation deadline exceeded")
    return value


@contextmanager
def budget(seconds):
    previous = _end.get()
    end = time.monotonic() + seconds
    token = _end.set(min(previous, end) if previous is not None else end)
    try:
        yield
    finally:
        _end.reset(token)


def pause(seconds=5):
    time.sleep(remaining(seconds))
