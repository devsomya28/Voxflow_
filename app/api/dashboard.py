from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, timezone
import logging

from app.database import get_db
from app.models import Order, PaymentReminder, PendingAction, ActivityLog, ActionStatusEnum
from app.schemas import (
    DashboardResponse,
    DashboardMetrics,
    OrderOut,
    ActivityLogOut,
    ActionItem,
)

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])
logger = logging.getLogger("voxflow.dashboard")


@router.get("", response_model=DashboardResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    # 1. Fetch Orders
    orders_stmt = select(Order).order_by(desc(Order.created_at))
    orders_res = await db.execute(orders_stmt)
    orders = orders_res.scalars().all()

    # 2. Fetch Reminders
    reminders_stmt = select(PaymentReminder).order_by(desc(PaymentReminder.created_at))
    reminders_res = await db.execute(reminders_stmt)
    reminders = reminders_res.scalars().all()

    # 3. Fetch Pending Actions count
    pending_stmt = select(PendingAction).where(PendingAction.status == ActionStatusEnum.PENDING_APPROVAL.value)
    pending_res = await db.execute(pending_stmt)
    pending_actions = pending_res.scalars().all()

    # 4. Fetch Recent Activity
    act_stmt = select(ActivityLog).order_by(desc(ActivityLog.timestamp)).limit(6)
    act_res = await db.execute(act_stmt)
    activities = act_res.scalars().all()

    # Calculate metrics
    total_orders = len(orders)
    pending_orders = sum(1 for o in orders if o.status in ["PENDING", "OUT_FOR_DELIVERY"])
    delivered_orders = sum(1 for o in orders if o.status == "DELIVERED")

    active_reminders = [r for r in reminders if r.status in ["SCHEDULED", "SENT"]]
    total_pending_payments = sum(r.amount for r in active_reminders)
    pending_payments_count = len(active_reminders)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_sales = sum(
        o.total_amount for o in orders
        if (o.created_at and o.created_at.strftime("%Y-%m-%d") == today_str) or (o.delivery_date == today_str)
    )

    metrics = DashboardMetrics(
        totalOrders=total_orders,
        pendingOrdersCount=pending_orders,
        deliveredOrdersCount=delivered_orders,
        totalPendingPaymentsAmount=round(total_pending_payments, 2),
        pendingPaymentsCount=pending_payments_count,
        activeRemindersCount=len(active_reminders),
        pendingActionsCount=len(pending_actions),
        todaySalesAmount=round(today_sales, 2),
    )

    # Format recent orders (top 5)
    recent_orders = []
    for o in orders[:5]:
        items_raw = o.items or []
        items = [ActionItem(**i) if isinstance(i, dict) else i for i in items_raw]
        recent_orders.append(
            OrderOut(
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
        )

    # Format activity logs
    recent_activities = [
        ActivityLogOut(
            id=a.id,
            timestamp=a.timestamp.isoformat() if a.timestamp else datetime.now(timezone.utc).isoformat(),
            type=a.type,
            title=a.title,
            description=a.description,
            relatedId=a.related_id,
        )
        for a in activities
    ]

    return DashboardResponse(
        metrics=metrics,
        recentOrders=recent_orders,
        recentActivity=recent_activities,
    )

