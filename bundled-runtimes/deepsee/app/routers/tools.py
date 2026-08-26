from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.services.mac_tools import add_reminder

router = APIRouter(prefix="/api/tools", tags=["tools"])

class ReminderRequest(BaseModel):
    title: str
    notes: Optional[str] = ""
    due_date: Optional[str] = None

@router.post("/reminders/add")
async def create_reminder(req: ReminderRequest):
    success, message = add_reminder(req.title, req.notes, req.due_date)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return {"status": "success", "message": message}
