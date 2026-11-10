from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging

from app.database import get_db
from app.models import Order, ActivityLog, OrderStatusEnum
from app.schemas import OrderOut, OrderCreate, OrderUpdate, ActionItem

router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])
logger = logging.getLogger("voxflow.orders")


def _format_order(o: Order) -> OrderOut:
    items_raw = o.items or []
    items = [ActionItem(**i) if isinstance(i, dict) else i for i in items_raw]
    return OrderOut(
        id=o.id,
        orderNumber=o.order_number,
        createdAt=o.created_at.isoformat() if o.created_at else datetime.now(timezone.utc).isoformat(),
        sourceActionId=o.source_action_id,
        customerName=o.customer_name,
        customerPhone=o.customer_phone,
        items=items,
        totalAmount=o.total_amount,
        deliveryDate=o.delivery_date,
        status=o.status,
        paymentStatus=o.payment_status or "PENDING",
        notes=o.notes,
    )


@router.get("", response_model=Dict[str, Any])
async def list_orders(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Order).order_by(desc(Order.created_at))

    if status and status != "ALL":
        stmt = stmt.where(Order.status == status)

    result = await db.execute(stmt)
    orders = result.scalars().all()

    # Search filter in-memory for flexible case-insensitive matching across fields
    if search:
        q = search.lower().strip()
        filtered = []
        for o in orders:
            in_name = q in (o.customer_name or "").lower()
            in_num = q in (o.order_number or "").lower()
            in_phone = q in (o.customer_phone or "").lower()
            in_items = any(q in (i.get("productName", "") if isinstance(i, dict) else "").lower() for i in (o.items or []))
            if in_name or in_num or in_phone or in_items:
                filtered.append(o)
        orders = filtered

    formatted = [_format_order(o) for o in orders]
    return {"orders": formatted, "total": len(formatted)}


@router.post("", response_model=OrderOut)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(Order)
    c_res = await db.execute(count_stmt)
    total_existing = len(c_res.scalars().all())
    order_num = f"ORD-2026-{str(total_existing + 1).zfill(3)}"

    items_dump = [i.model_dump() for i in payload.items]

    new_order = Order(
        order_number=order_num,
        source_action_id=payload.sourceActionId,
        customer_name=payload.customerName,
        customer_phone=payload.customerPhone,
        items=items_dump,
        total_amount=payload.totalAmount,
        delivery_date=payload.deliveryDate,
        status=payload.status.value if hasattr(payload.status, 'value') else payload.status,
        payment_status=payload.paymentStatus,
        notes=payload.notes,
    )
    db.add(new_order)
    await db.flush()

    log = ActivityLog(
        type="ORDER_APPROVED",
        title=f"Order {order_num} created",
        description=f"{payload.customerName} · ₹{payload.totalAmount}",
        related_id=new_order.id,
    )
    db.add(log)
    await db.commit()
    await db.refresh(new_order)

    return _format_order(new_order)


@router.patch("/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: str,
    payload: OrderUpdate,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Order).where(Order.id == order_id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found",
        )

    if payload.status is not None:
        order.status = payload.status.value if hasattr(payload.status, 'value') else payload.status
    if payload.paymentStatus is not None:
        order.payment_status = payload.paymentStatus
    if payload.notes is not None:
        order.notes = payload.notes

    await db.commit()
    await db.refresh(order)
    return _format_order(order)

