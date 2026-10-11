"""Single-process admission for synchronous artifact jobs; cancellation is cooperative.

The local MVP runs one backend process. A cancelled HTTP request keeps its lease
until its current provider request returns. This is deliberately not a job queue.
"""
from contextlib import contextmanager
from threading import Lock
from fastapi import HTTPException
from .db import Session, Run
from .memory import require

_lock = Lock()
_workspaces = set()


def inline_active(wid):
    with _lock:
        return wid in _workspaces


@contextmanager
def artifact_lease(wid):
    with _lock:
        if wid in _workspaces:
            raise HTTPException(409, '当前工作区的产物任务仍在执行或停止，请稍后重试')
        _workspaces.add(wid)
    try:
        yield
    finally:
        with _lock:
            _workspaces.remove(wid)


def check_generation(rid, wid):
    with Session() as s:
        r = require(s, Run, rid, wid)
        if r.status != 'running':
            raise HTTPException(409, '简历生成已取消或中断，未保存产物；请等待当前请求结束后重新生成')
