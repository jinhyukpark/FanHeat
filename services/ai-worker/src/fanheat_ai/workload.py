from contextlib import contextmanager
from threading import Condition


class LLMWorkCoordinator:
    """Serialize LLM workloads and let waiting manual work outrank automation."""

    def __init__(self) -> None:
        self._condition = Condition()
        self._manual_waiting = 0
        self._active = False

    @contextmanager
    def manual(self):
        with self._condition:
            self._manual_waiting += 1
            try:
                while self._active:
                    self._condition.wait()
                self._active = True
            finally:
                self._manual_waiting -= 1
        try:
            yield
        finally:
            with self._condition:
                self._active = False
                self._condition.notify_all()

    @contextmanager
    def background(self):
        with self._condition:
            acquired = not self._active and self._manual_waiting == 0
            if acquired:
                self._active = True
        try:
            yield acquired
        finally:
            if acquired:
                with self._condition:
                    self._active = False
                    self._condition.notify_all()
