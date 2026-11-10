from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging

from app.database import get_db
from app.models import PaymentReminder, ActivityLog, ReminderStatusEnum
from app.schemas import ReminderOut, ReminderCreate, ReminderUpdate

router = APIRouter(prefix="/api/v1/reminders", tags=["Reminders"])
logger = logging.getLogger("voxflow.reminders")


def _format_reminder(r: PaymentReminder) -> ReminderOut:
    return ReminderOut(
        id=r.id,
        reminderNumber=r.reminder_number,
        createdAt=r.created_at.isoformat() if r.created_at else datetime.now(timezone.utc).isoformat(),
        sourceActionId=r.source_action_id,
        customerName=r.customer_name,
        customerPhone=r.customer_phone,
        amount=r.amount,
        dueDate=r.due_date,
        status=r.status,
        lastReminderSentAt=r.last_reminder_sent_at.isoformat() if r.last_reminder_sent_at else None,
        notes=r.notes,
    )


@router.get("", response_model=Dict[str, Any])
async def list_reminders(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(PaymentReminder).order_by(desc(PaymentReminder.created_at))

    if status and status != "ALL":
        stmt = stmt.where(PaymentReminder.status == status)

    result = await db.execute(stmt)
    reminders = result.scalars().all()

    if search:
        q = search.lower().strip()
        reminders = [
            r for r in reminders
            if q in (r.customer_name or "").lower()
            or q in (r.reminder_number or "").lower()
            or q in (r.customer_phone or "").lower()
        ]

    formatted = [_format_reminder(r) for r in reminders]
    return {"reminders": formatted, "total": len(formatted)}


@router.post("", response_model=ReminderOut)
async def create_reminder(
    payload: ReminderCreate,
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(PaymentReminder)
    c_res = await db.execute(count_stmt)
    total_existing = len(c_res.scalars().all())
    rem_num = f"REM-2026-{str(total_existing + 1).zfill(3)}"

    new_rem = PaymentReminder(
        reminder_number=rem_num,
        source_action_id=payload.sourceActionId,
        customer_name=payload.customerName,
        customer_phone=payload.customerPhone,
        amount=payload.amount,
        due_date=payload.dueDate,
        status=payload.status.value if hasattr(payload.status, 'value') else payload.status,
        notes=payload.notes,
    )
    db.add(new_rem)
    await db.flush()

    log = ActivityLog(
        type="ORDER_APPROVED",
        title=f"Reminder {rem_num} scheduled",
        description=f"₹{payload.amount} for {payload.customerName}",
        related_id=new_rem.id,
    )
    db.add(log)
    await db.commit()
    await db.refresh(new_rem)

    return _format_reminder(new_rem)


@router.patch("/{reminder_id}/status", response_model=ReminderOut)
async def update_reminder_status(
    reminder_id: str,
    payload: ReminderUpdate,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(PaymentReminder).where(PaymentReminder.id == reminder_id)
    res = await db.execute(stmt)
    reminder = res.scalar_one_or_none()

    if not reminder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment reminder {reminder_id} not found",
        )

    if payload.status is not None:
        new_status = payload.status.value if hasattr(payload.status, 'value') else payload.status
        reminder.status = new_status
        if new_status == ReminderStatusEnum.SENT.value:
            reminder.last_reminder_sent_at = datetime.now(timezone.utc)
    if payload.notes is not None:
        reminder.notes = payload.notes

    await db.commit()
    await db.refresh(reminder)
    return _format_reminder(reminder)

