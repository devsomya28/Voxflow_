from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, Enum as SQLEnum
from datetime import datetime, timezone
import enum
import uuid

from app.database import Base


def generate_uuid():
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc)


class ActionCategoryEnum(str, enum.Enum):
    ORDER_CREATION = "ORDER_CREATION"
    PAYMENT_REMINDER = "PAYMENT_REMINDER"
    INVENTORY_UPDATE = "INVENTORY_UPDATE"


class ActionStatusEnum(str, enum.Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class OrderStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    PREPARING = "PREPARING"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class ReminderStatusEnum(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    PAID = "PAID"
    SNOOZED = "SNOOZED"


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    original_transcript = Column(Text, nullable=False)
    detected_language = Column(String(16), default="hinglish")
    category = Column(String(32), default=ActionCategoryEnum.ORDER_CREATION.value)
    extracted_data = Column(JSON, nullable=False)  # Stores ExtractedEntities as JSON
    status = Column(String(32), default=ActionStatusEnum.PENDING_APPROVAL.value)
    confidence_score = Column(Float, nullable=True)
    confidence_reason = Column(String(255), nullable=True)
    rejection_reason = Column(String(255), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)


class Order(Base):
    __tablename__ = "orders"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    order_number = Column(String(32), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    source_action_id = Column(String(64), nullable=True)
    customer_name = Column(String(128), nullable=False)
    customer_phone = Column(String(32), nullable=True)
    items = Column(JSON, nullable=False, default=list)  # List of ActionItem dicts
    total_amount = Column(Float, nullable=False, default=0.0)
    delivery_date = Column(String(32), nullable=False)
    status = Column(String(32), default=OrderStatusEnum.PENDING.value)
    payment_status = Column(String(32), default="PENDING")
    notes = Column(Text, nullable=True)


class PaymentReminder(Base):
    __tablename__ = "reminders"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    reminder_number = Column(String(32), unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    source_action_id = Column(String(64), nullable=True)
    customer_name = Column(String(128), nullable=False)
    customer_phone = Column(String(32), nullable=False)
    amount = Column(Float, nullable=False)
    due_date = Column(String(32), nullable=False)
    status = Column(String(32), default=ReminderStatusEnum.SCHEDULED.value)
    last_reminder_sent_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    timestamp = Column(DateTime(timezone=True), default=utc_now)
    type = Column(String(32), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    related_id = Column(String(64), nullable=True)

