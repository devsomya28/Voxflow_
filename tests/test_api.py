import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone, timedelta

from app.main import app
from app.database import Base, get_db
from app.schemas import TranscribeResponse, LanguageCode

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_hindi_devanagari_amit_chawal_extraction():
    """
    Test reported bug: 'आज अमित को 5 किलो चावल बेच'
    Expected:
    - Customer: Amit
    - Product: Chawal (from catalog)
    - Quantity: 5.0
    - Unit: kg (not piece, and product is NOT किलो)
    - Price: 85.0 (from verified catalog)
    - Total: 425.0 (5 * 85.0)
    - Delivery Date: today's date (due to 'आज' and immediate 'बेच')
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/actions/extract",
            json={"transcript": "आज अमित को 5 किलो चावल बेच", "language": "hi"},
        )
        assert res.status_code == 200
        action = res.json()["action"]
        entities = action["entities"]

        assert action["category"] == "ORDER_CREATION"
        assert entities["customerName"] == "Amit"
        assert len(entities["items"]) == 1
        item = entities["items"][0]
        assert item["productName"] == "Chawal"
        assert item["quantity"] == 5.0
        assert item["unit"] == "kg"
        assert item["unitPrice"] == 85.0
        assert item["totalPrice"] == 425.0
        assert entities["totalAmount"] == 425.0

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert entities["deliveryDate"] == today_str


@pytest.mark.asyncio
async def test_hinglish_amit_chawal():
    """Hinglish phrase: 'Amit ko kal 3 kilo chawal deliver karna hai.'"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/actions/extract",
            json={"transcript": "Amit ko kal 3 kilo chawal deliver karna hai.", "language": "hinglish"},
        )
        assert res.status_code == 200
        entities = res.json()["action"]["entities"]
        assert entities["customerName"] == "Amit"
        item = entities["items"][0]
        assert item["productName"] == "Chawal"
        assert item["quantity"] == 3.0
        assert item["unit"] == "kg"
        assert item["unitPrice"] == 85.0
        assert item["totalPrice"] == 255.0
        expected_date = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        assert entities["deliveryDate"] == expected_date


@pytest.mark.asyncio
async def test_english_command():
    """English phrase: 'Deliver 2 packets of tea to Rahul tomorrow'"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/actions/extract",
            json={"transcript": "Deliver 2 packets of tea to Rahul tomorrow", "language": "en"},
        )
        assert res.status_code == 200
        entities = res.json()["action"]["entities"]
        assert "Rahul" in entities["customerName"]
        item = entities["items"][0]
        assert "Tea" in item["productName"]
        assert item["quantity"] == 2.0
        assert item["unit"] == "packet"
        assert item["unitPrice"] == 240.0
        assert item["totalPrice"] == 480.0


@pytest.mark.asyncio
async def test_missing_customer():
    """Order with no customer specified: '5 kilo atta pack kar do'"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/actions/extract",
            json={"transcript": "5 kilo atta pack kar do", "language": "hi"},
        )
        assert res.status_code == 200
        action = res.json()["action"]
        entities = action["entities"]
        assert entities["customerName"] is None
        assert "Atta" in entities["items"][0]["productName"]
        assert "customer" in entities["notes"].lower()


@pytest.mark.asyncio
async def test_unknown_product_uncatalogued_price():
    """Unknown product not in catalog: 'Rahul ko 2 umbrella deliver karna hai'"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/actions/extract",
            json={"transcript": "Rahul ko 2 umbrella deliver karna hai", "language": "en"},
        )
        assert res.status_code == 200
        entities = res.json()["action"]["entities"]
        assert entities["customerName"] == "Rahul"
        item = entities["items"][0]
        assert item["productName"] == "Umbrella"
        assert item["unitPrice"] is None
        assert item["totalPrice"] is None
        assert entities["totalAmount"] is None
        assert "price" in entities["notes"].lower()


@pytest.mark.asyncio
async def test_hindi_payment_reminder():
    """Hindi reminder: 'रमेश को 500 रुपये का रिमाइंडर भेजना'"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/actions/extract",
            json={"transcript": "रमेश को 500 रुपये का रिमाइंडर भेजना", "language": "hi"},
        )
        assert res.status_code == 200
        action = res.json()["action"]
        assert action["category"] == "PAYMENT_REMINDER"
        assert action["entities"]["customerName"] == "Ramesh"
        assert action["entities"]["totalAmount"] == 500.0
