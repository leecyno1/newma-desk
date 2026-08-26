from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Task
from ..schemas import TaskOut


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=list[TaskOut])
def list_tasks(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    items = db.execute(select(Task).order_by(Task.id.desc()).limit(limit)).scalars().all()
    return [TaskOut(id=t.id, type=t.type, status=t.status, result=t.result) for t in items]


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "task not found")
    return TaskOut(id=task.id, type=task.type, status=task.status, result=task.result)

