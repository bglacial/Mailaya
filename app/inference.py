from __future__ import annotations

import multiprocessing
import threading
import time
from dataclasses import replace
from typing import Any

from .classifier import ClassifierLoadError, build_classifier
from .config import Settings


class InferenceCancelled(Exception):
    """The current message stays pending when its worker is stopped."""


def _serve(connection, settings: Settings, factory) -> None:
    # Spawn imports this module, never the API/database or IMAP credentials.
    try:
        classifier = factory(settings)
        while True:
            email = connection.recv()
            if email is None:
                return
            try:
                connection.send(("result", classifier.classify(email)))
            except ClassifierLoadError as exc:
                connection.send(("load_error", str(exc)))
                return
            except Exception as exc:
                connection.send(("error", str(exc)))
    except (EOFError, BrokenPipeError, ConnectionResetError):
        pass
    finally:
        connection.close()


class ProcessClassifier:
    """One spawned model process per batch; no model weights in the API."""

    def __init__(self, settings: Settings, *, factory=build_classifier):
        metadata = build_classifier(settings)
        self.name, self.model = metadata.name, metadata.model
        self.settings = settings
        self._factory = factory
        self._context = multiprocessing.get_context("spawn")
        self._process = None
        self._connection = None
        self._cancelled = threading.Event()

    def begin_run(self) -> None:
        self._cancelled.clear()

    def cancel(self) -> None:
        # Only the owning analysis thread handles the pipe and reaps the child.
        self._cancelled.set()

    def _start(self) -> None:
        parent, child = self._context.Pipe()
        process = self._context.Process(target=_serve, args=(child, self.settings, self._factory),
                                        daemon=True, name="mailaya-inference")
        try:
            process.start()
        except BaseException:
            parent.close()
            raise
        finally:
            child.close()
        self._connection, self._process = parent, process

    def classify(self, email: dict[str, Any]) -> dict[str, Any]:
        if self._cancelled.is_set():
            raise InferenceCancelled()
        if self._process is None:
            self._start()
        # Send only model inputs, never user/account IDs or IMAP secrets.
        inputs = {key: email[key] for key in
                  ("graph_id", "sender_name", "sender_address", "subject", "body_preview")}
        deadline = time.monotonic() + 900
        try:
            self._connection.send(inputs)
            while True:
                if self._cancelled.is_set():
                    raise InferenceCancelled()
                if self._connection.poll(0.1):
                    kind, value = self._connection.recv()
                    if self._cancelled.is_set():
                        raise InferenceCancelled()
                    if kind == "result":
                        return value
                    if kind == "load_error":
                        raise ClassifierLoadError(value)
                    raise RuntimeError(value)
                if not self._process.is_alive():
                    raise ClassifierLoadError(f"Le processus d’inférence s’est arrêté (code {self._process.exitcode}). Relancez l’analyse.")
                if time.monotonic() >= deadline:
                    raise ClassifierLoadError("Le processus d’inférence ne répond plus après 15 minutes. Relancez l’analyse.")
        except (EOFError, BrokenPipeError, ConnectionResetError, OSError) as exc:
            raise ClassifierLoadError("Le processus d’inférence s’est arrêté. Relancez l’analyse.") from exc

    def unload(self) -> None:
        process, connection = self._process, self._connection
        if process is None:
            return
        try:
            if not self._cancelled.is_set() and process.is_alive():
                try:
                    connection.send(None)
                except (BrokenPipeError, EOFError, OSError):
                    pass
                process.join(timeout=0.5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join()
        finally:
            connection.close()
            process.close()
            self._process = self._connection = None


def build_process_classifier(settings: Settings, backend: str | None = None):
    selected = replace(settings, laya_backend=backend) if backend else settings
    if selected.laya_backend == "demo":
        return build_classifier(selected)
    return ProcessClassifier(selected)
