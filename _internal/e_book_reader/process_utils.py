from __future__ import annotations

import psutil


def terminate_process_tree(pid: int, *, include_parent: bool = True, grace_seconds: float = 4.0) -> None:
    """Terminate descendants before their parent so native helpers cannot be orphaned."""
    try:
        parent = psutil.Process(pid)
    except psutil.Error:
        return

    children = parent.children(recursive=True)
    for process in reversed(children):
        try:
            process.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(children, timeout=max(0.1, grace_seconds / 2))
    for process in alive:
        try:
            process.kill()
        except psutil.Error:
            pass
    if alive:
        psutil.wait_procs(alive, timeout=max(0.1, grace_seconds / 2))

    if not include_parent:
        return
    try:
        parent.terminate()
        parent.wait(timeout=max(0.1, grace_seconds / 2))
    except psutil.TimeoutExpired:
        try:
            parent.kill()
            parent.wait(timeout=max(0.1, grace_seconds / 2))
        except psutil.Error:
            pass
    except psutil.Error:
        pass
