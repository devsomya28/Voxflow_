from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class LanguageCode(str, Enum):
    hi = "hi"
    hinglish = "hinglish"
    en = "en"


class ActionCategory(str, Enum):
    ORDER_CREATION = "ORDER_CREATION"
    PAYMENT_REMINDER = "PAYMENT_REMINDER"
    INVENTORY_UPDATE = "INVENTORY_UPDATE"


class ActionStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PREPARING = "PREPARING"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class ReminderStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    PAID = "PAID"
    SNOOZED = "SNOOZED"


class ActionItem(BaseModel):
    id: Optional[str] = None
    productName: str
    quantity: float
    unit: str = "piece"
    unitPrice: Optional[float] = None
    totalPrice: Optional[float] = None


class ExtractedEntities(BaseModel):
    customerName: Optional[str] = None
    phoneNumber: Optional[str] = None
    items: List[ActionItem] = []
    totalAmount: Optional[float] = None
    deliveryDate: Optional[str] = None
    dueDate: Optional[str] = None
    deliveryTimeSlot: Optional[str] = None
    notes: Optional[str] = None


class StructuredAction(BaseModel):
    id: str
    createdAt: str
    originalTranscript: str
    detectedLanguage: LanguageCode
    category: ActionCategory
    entities: ExtractedEntities
    status: ActionStatus = ActionStatus.PENDING_APPROVAL
    confidenceScore: Optional[float] = None
    confidenceReason: Optional[str] = None
    rejectionReason: Optional[str] = None
    confirmedAt: Optional[str] = None


class TranscribeResponse(BaseModel):
    transcript: str
    detectedLanguage: LanguageCode
    confidenceScore: Optional[float] = None
    durationSeconds: Optional[float] = None


class ExtractActionRequest(BaseModel):
    transcript: str
    language: LanguageCode = LanguageCode.hinglish


class ExtractActionResponse(BaseModel):
    action: StructuredAction
    confidenceScore: Optional[float] = None
    processingTimeMs: Optional[float] = None


class ActionConfirmRequest(BaseModel):
    actionId: str
    actionData: Optional[StructuredAction] = None


class ActionConfirmResponse(BaseModel):
    success: bool
    message: str
    orderId: Optional[str] = None
    reminderId: Optional[str] = None


class ActionRejectRequest(BaseModel):
    reason: Optional[str] = None


class OrderBase(BaseModel):
    customerName: str
    customerPhone: Optional[str] = None
    items: List[ActionItem] = []
    totalAmount: float = 0.0
    deliveryDate: str
    status: OrderStatus = OrderStatus.PENDING
    paymentStatus: str = "PENDING"
    notes: Optional[str] = None


class OrderCreate(OrderBase):
    sourceActionId: Optional[str] = None


class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    paymentStatus: Optional[str] = None
    notes: Optional[str] = None


class OrderOut(OrderBase):
    id: str
    orderNumber: str
    createdAt: str
    sourceActionId: Optional[str] = None

    class Config:
        from_attributes = True


class ReminderBase(BaseModel):
    customerName: str
    customerPhone: str
    amount: float
    dueDate: str
    status: ReminderStatus = ReminderStatus.SCHEDULED
    notes: Optional[str] = None


class ReminderCreate(ReminderBase):
    sourceActionId: Optional[str] = None


class ReminderUpdate(BaseModel):
    status: Optional[ReminderStatus] = None
    notes: Optional[str] = None


class ReminderOut(ReminderBase):
    id: str
    reminderNumber: str
    createdAt: str
    sourceActionId: Optional[str] = None
    lastReminderSentAt: Optional[str] = None

    class Config:
        from_attributes = True


class DashboardMetrics(BaseModel):
    totalOrders: int
    pendingOrdersCount: int
    deliveredOrdersCount: int
    totalPendingPaymentsAmount: float
    pendingPaymentsCount: int
    activeRemindersCount: int
    pendingActionsCount: int
    todaySalesAmount: float


class ActivityLogOut(BaseModel):
    id: str
    timestamp: str
    type: str
    title: str
    description: str
    relatedId: Optional[str] = None


class DashboardResponse(BaseModel):
    metrics: DashboardMetrics
    recentOrders: List[OrderOut]
    recentActivity: List[ActivityLogOut]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    database: str = "connected"
    timestamp: str

