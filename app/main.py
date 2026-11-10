from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.database import init_db, engine, Base
from app.api.health import router as health_router
from app.api.voice import router as voice_router
from app.api.actions import router as actions_router
from app.api.orders import router as orders_router
from app.api.reminders import router as reminders_router
from app.api.dashboard import router as dashboard_router

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("voxflow.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Startup: Initialize database engine & create tables
    logger.info("Initializing database connection...")
    try:
        # Try configured database (PostgreSQL or SQLite)
        db_engine = init_db()
        async with db_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.warning(f"Primary database connection failed: {e}")
        if settings.USE_SQLITE_FALLBACK and "sqlite" not in settings.DATABASE_URL:
            logger.info("Falling back to local SQLite database...")
            db_engine = init_db(settings.SQLITE_URL)
            async with db_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("SQLite fallback tables initialized successfully.")
        else:
            raise

    # 2. Seed initial sample data if tables are brand new
    try:
        await seed_initial_records()
    except Exception as e:
        logger.warning(f"Could not seed sample data (tables may already contain data): {e}")

    yield

    # 3. Shutdown
    if engine:
        await engine.dispose()
        logger.info("Database connection closed.")


async def seed_initial_records():
    from app.database import AsyncSessionLocal
    from app.models import Order, PaymentReminder, PendingAction, ActivityLog
    from sqlalchemy import select
    from datetime import datetime, timezone, timedelta

    async with AsyncSessionLocal() as session:
        # Check if already seeded
        res = await session.execute(select(Order))
        if res.scalars().first():
            return  # Already has data

        now = datetime.now(timezone.utc)

        # 1. Sample Orders
        orders = [
            Order(
                order_number="ORD-2026-001",
                customer_name="Sharma Ji",
                customer_phone="+91 98112 34567",
                items=[{"productName": "Chakki Fresh Atta", "quantity": 5.0, "unit": "kg", "unitPrice": 44.0, "totalPrice": 220.0}],
                total_amount=220.0,
                delivery_date=(now + timedelta(days=1)).strftime("%Y-%m-%d"),
                status="PENDING",
                payment_status="PENDING",
                notes="Urgent morning delivery requested by customer",
            ),
            Order(
                order_number="ORD-2026-002",
                customer_name="Gupta Brothers",
                customer_phone="+91 98765 43210",
                items=[
                    {"productName": "Fortune Mustard Oil", "quantity": 2.0, "unit": "litre", "unitPrice": 165.0, "totalPrice": 330.0},
                    {"productName": "Tata Salt", "quantity": 1.0, "unit": "packet", "unitPrice": 28.0, "totalPrice": 28.0},
                ],
                total_amount=358.0,
                delivery_date=now.strftime("%Y-%m-%d"),
                status="OUT_FOR_DELIVERY",
                payment_status="PAID",
                notes="Leave at front porch if closed",
            ),
            Order(
                order_number="ORD-2026-003",
                customer_name="Pooja Verma",
                customer_phone="+91 94123 98765",
                items=[
                    {"productName": "Madhur Pure Sugar", "quantity": 3.0, "unit": "kg", "unitPrice": 48.0, "totalPrice": 144.0},
                    {"productName": "Taj Mahal Tea", "quantity": 1.0, "unit": "packet (500g)", "unitPrice": 240.0, "totalPrice": 240.0},
                ],
                total_amount=384.0,
                delivery_date=(now - timedelta(days=1)).strftime("%Y-%m-%d"),
                status="DELIVERED",
                payment_status="PAID",
            ),
        ]
        session.add_all(orders)

        # 2. Sample Reminders
        reminders = [
            PaymentReminder(
                reminder_number="REM-2026-001",
                customer_name="Ramesh Kumar",
                customer_phone="+91 98234 56789",
                amount=800.0,
                due_date=(now + timedelta(days=3)).strftime("%Y-%m-%d"),
                status="SCHEDULED",
                notes="Last month ration balance pending",
            ),
            PaymentReminder(
                reminder_number="REM-2026-002",
                customer_name="Anil Tyagi",
                customer_phone="+91 97123 45678",
                amount=1450.0,
                due_date=(now - timedelta(days=1)).strftime("%Y-%m-%d"),
                status="SENT",
                notes="Payment overdue by 1 day",
            ),
            PaymentReminder(
                reminder_number="REM-2026-003",
                customer_name="Sunita Mehra",
                customer_phone="+91 99887 76655",
                amount=520.0,
                due_date=(now - timedelta(days=2)).strftime("%Y-%m-%d"),
                status="PAID",
                notes="Settled via UPI on 6 Nov",
            ),
        ]
        session.add_all(reminders)

        # 3. Sample Pending Action
        pending = [
            PendingAction(
                id="act-301",
                original_transcript="Sharma ji ko kal 5 kilo atta deliver karna hai.",
                detected_language="hinglish",
                category="ORDER_CREATION",
                extracted_data={
                    "customerName": "Sharma Ji",
                    "phoneNumber": "+91 98112 34567",
                    "items": [{"productName": "Chakki Fresh Atta", "quantity": 5.0, "unit": "kg", "unitPrice": 44.0, "totalPrice": 220.0}],
                    "totalAmount": 220.0,
                    "deliveryDate": (now + timedelta(days=1)).strftime("%Y-%m-%d"),
                    "notes": "Voice input captured in Hinglish",
                },
                status="PENDING_APPROVAL",
                confidence_score=0.94,
                confidence_reason="Customer Sharma Ji matched existing contact. Product Chakki Atta identified with unit kg.",
            )
        ]
        session.add_all(pending)

        # 4. Sample Activity Logs
        logs = [
            ActivityLog(
                type="VOICE_TRANSCRIBED",
                title="Voice command transcribed",
                description='"Sharma ji ko kal 5 kilo atta deliver karna hai."',
            ),
            ActivityLog(
                type="ORDER_APPROVED",
                title="Order ORD-2026-001 confirmed",
                description="Sharma Ji · 5 kg Atta · ₹220",
            ),
        ]
        session.add_all(logs)

        await session.commit()
        logger.info("Sample Kirana business dataset seeded.")


# FastAPI App
app = FastAPI(
    title="VoxFlow Backend API",
    description="Multilingual Voice AI for Business Operations (FastAPI + PostgreSQL + Gnani AI)",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list + ["*"] if settings.DEBUG else settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(health_router)
app.include_router(voice_router)
app.include_router(actions_router)
app.include_router(orders_router)
app.include_router(reminders_router)
app.include_router(dashboard_router)

