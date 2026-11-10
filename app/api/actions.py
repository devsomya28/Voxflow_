from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc
from typing import List, Dict, Any
from datetime import datetime, timezone
import logging

from app.database import get_db
from app.models import PendingAction, Order, PaymentReminder, ActivityLog, ActionStatusEnum, OrderStatusEnum, ReminderStatusEnum
from app.schemas import (
    ExtractActionRequest,
    ExtractActionResponse,
    StructuredAction,
    ActionConfirmRequest,
    ActionConfirmResponse,
    ActionRejectRequest,
    ExtractedEntities,
    ActionCategory,
    ActionStatus,
    LanguageCode,
)
from app.services.action_extractor import extract_action_from_transcript

router = APIRouter(prefix="/api/v1/actions", tags=["Actions"])
logger = logging.getLogger("voxflow.actions")


def _format_db_action(item: PendingAction) -> StructuredAction:
    entities_dict = item.extracted_data or {}
    return StructuredAction(
        id=item.id,
        createdAt=item.created_at.isoformat() if item.created_at else datetime.now(timezone.utc).isoformat(),
        originalTranscript=item.original_transcript,
        detectedLanguage=LanguageCode(item.detected_language) if item.detected_language in LanguageCode.__members__ else LanguageCode.hinglish,
        category=ActionCategory(item.category),
        status=ActionStatus(item.status),
        confidenceScore=item.confidence_score,
        confidenceReason=item.confidence_reason,
        rejectionReason=item.rejection_reason,
        confirmedAt=item.confirmed_at.isoformat() if item.confirmed_at else None,
        entities=ExtractedEntities(**entities_dict),
    )


@router.post("/extract", response_model=ExtractActionResponse)
async def extract_action(
    req: ExtractActionRequest,
    db: AsyncSession = Depends(get_db),
):
    if not req.transcript.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcript text cannot be empty.",
        )

    # 1. Run NLP extraction engine
    extracted = await extract_action_from_transcript(req.transcript, req.language)
    action = extracted.action

    # 2. Persist as PENDING_APPROVAL in the staging database table
    db_action = PendingAction(
        id=action.id,
        original_transcript=action.originalTranscript,
        detected_language=action.detectedLanguage.value,
        category=action.category.value,
        extracted_data=action.entities.model_dump(),
        status=ActionStatusEnum.PENDING_APPROVAL.value,
        confidence_score=action.confidenceScore,
        confidence_reason=action.confidenceReason,
    )
    db.add(db_action)

    # 3. Log activity
    log = ActivityLog(
        type="ACTION_CREATED",
        title=f"Staged {action.category.value.replace('_', ' ').title()}",
        description=f"Pending approval for {action.entities.customerName}: ₹{action.entities.totalAmount or 0}",
        related_id=action.id,
    )
    db.add(log)
    await db.commit()

    return extracted


@router.get("/pending", response_model=Dict[str, List[StructuredAction]])
async def get_pending_actions(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(PendingAction)
        .where(PendingAction.status == ActionStatusEnum.PENDING_APPROVAL.value)
        .order_by(desc(PendingAction.created_at))
    )
    result = await db.execute(stmt)
    records = result.scalars().all()
    actions = [_format_db_action(r) for r in records]
    return {"actions": actions}


@router.post("/confirm", response_model=ActionConfirmResponse)
async def confirm_action(
    req: ActionConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(PendingAction).where(PendingAction.id == req.actionId)
    res = await db.execute(stmt)
    action_record = res.scalar_one_or_none()

    if not action_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending action {req.actionId} not found.",
        )

    if action_record.status != ActionStatusEnum.PENDING_APPROVAL.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Action is already marked as {action_record.status}.",
        )

    # Use updated action data from client if provided, else database extracted data
    action_data = req.actionData
    entities_dict = action_data.entities.model_dump() if action_data else action_record.extracted_data
    category = action_data.category.value if action_data else action_record.category

    now_utc = datetime.now(timezone.utc)
    action_record.status = ActionStatusEnum.APPROVED.value
    action_record.confirmed_at = now_utc
    action_record.extracted_data = entities_dict

    created_order_id = None
    created_reminder_id = None

    if category == ActionCategory.ORDER_CREATION.value:
        # Generate order number
        count_stmt = select(Order)
        c_res = await db.execute(count_stmt)
        total_existing = len(c_res.scalars().all())
        order_num = f"ORD-2026-{str(total_existing + 1).padStart(3, '0') if hasattr(str, 'padStart') else str(total_existing + 1).zfill(3)}"

        customer_name = entities_dict.get("customerName", "Customer")
        total_amount = float(entities_dict.get("totalAmount") or 0.0)
        items = entities_dict.get("items", [])
        delivery_date = entities_dict.get("deliveryDate") or now_utc.strftime("%Y-%m-%d")

        new_order = Order(
            order_number=order_num,
            source_action_id=action_record.id,
            customer_name=customer_name,
            customer_phone=entities_dict.get("phoneNumber"),
            items=items,
            total_amount=total_amount,
            delivery_date=delivery_date,
            status=OrderStatusEnum.PENDING.value,
            payment_status="PENDING",
            notes=entities_dict.get("notes"),
        )
        db.add(new_order)
        await db.flush()
        created_order_id = new_order.id

        # Log activity
        log = ActivityLog(
            type="ORDER_APPROVED",
            title=f"Order {order_num} confirmed",
            description=f"{customer_name} · ₹{total_amount}",
            related_id=new_order.id,
        )
        db.add(log)

        message = f"Order {order_num} approved and saved successfully."
    else:
        # Reminder creation
        count_stmt = select(PaymentReminder)
        c_res = await db.execute(count_stmt)
        total_reminders = len(c_res.scalars().all())
        rem_num = f"REM-2026-{str(total_reminders + 1).zfill(3)}"

        customer_name = entities_dict.get("customerName", "Customer")
        amount = float(entities_dict.get("totalAmount") or 0.0)
        due_date = entities_dict.get("dueDate") or now_utc.strftime("%Y-%m-%d")

        new_reminder = PaymentReminder(
            reminder_number=rem_num,
            source_action_id=action_record.id,
            customer_name=customer_name,
            customer_phone=entities_dict.get("phoneNumber") or "",
            amount=amount,
            due_date=due_date,
            status=ReminderStatusEnum.SCHEDULED.value,
            notes=entities_dict.get("notes"),
        )
        db.add(new_reminder)
        await db.flush()
        created_reminder_id = new_reminder.id

        log = ActivityLog(
            type="ORDER_APPROVED",
            title=f"Reminder {rem_num} scheduled",
            description=f"₹{amount} for {customer_name} due {due_date}",
            related_id=new_reminder.id,
        )
        db.add(log)

        message = f"Payment reminder {rem_num} scheduled successfully."

    await db.commit()

    return ActionConfirmResponse(
        success=True,
        message=message,
        orderId=created_order_id,
        reminderId=created_reminder_id,
    )


@router.post("/{action_id}/reject")
async def reject_action(
    action_id: str,
    body: ActionRejectRequest = ActionRejectRequest(),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(PendingAction).where(PendingAction.id == action_id)
    res = await db.execute(stmt)
    action_record = res.scalar_one_or_none()

    if not action_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending action {action_id} not found.",
        )

    action_record.status = ActionStatusEnum.REJECTED.value
    action_record.rejection_reason = body.reason or "Rejected by user during review"

    log = ActivityLog(
        type="ACTION_REJECTED",
        title="Action rejected by user",
        description=f"Discarded {action_record.category} item.",
        related_id=action_id,
    )
    db.add(log)
    await db.commit()

    return {"success": True, "message": "Action rejected and removed from pending queue."}

