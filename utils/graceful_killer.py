import signal

from typing import Callable


def install_graceful_killer(on_kill: Callable):
    signal.signal(signal.SIGTERM, on_kill)
