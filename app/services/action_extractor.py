import re
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple

from app.schemas import (
    LanguageCode,
    ActionCategory,
    ActionStatus,
    ActionItem,
    ExtractedEntities,
    StructuredAction,
    ExtractActionResponse,
)
from app.services.catalog import lookup_catalog_product

logger = logging.getLogger("voxflow.action_extractor")


async def extract_action_from_transcript(
    transcript: str,
    language: LanguageCode = LanguageCode.hinglish,
) -> ExtractActionResponse:
    start_time = datetime.now()
    action = parse_multilingual_retail_transcript(transcript, language)
    elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000

    return ExtractActionResponse(
        action=action,
        confidenceScore=action.confidenceScore,
        processingTimeMs=round(elapsed_ms, 2),
    )


# Unit normalization mapping supporting Hindi Devanagari, Hinglish and English
UNIT_MAP = {
    # Kilogram
    "kilo": "kg",
    "kg": "kg",
    "kgs": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "किलो": "kg",
    "किलोग्राम": "kg",
    "केजी": "kg",

    # Packet
    "packet": "packet",
    "packets": "packet",
    "pack": "packet",
    "packs": "packet",
    "पैकेट": "packet",
    "पैक": "packet",

    # Litre
    "litre": "litre",
    "litres": "litre",
    "liter": "litre",
    "liters": "litre",
    "लीटर": "litre",
    "ली": "litre",

    # Carton / Box
    "carton": "carton",
    "cartons": "carton",
    "box": "carton",
    "boxes": "carton",
    "कार्टन": "carton",
    "बॉक्स": "carton",
    "पेटी": "carton",
    "बोरी": "carton",
    "bora": "carton",
    "bori": "carton",

    # Gram
    "g": "gram",
    "gm": "gram",
    "gms": "gram",
    "gram": "gram",
    "grams": "gram",
    "ग्राम": "gram",

    # Piece
    "piece": "piece",
    "pieces": "piece",
    "pc": "piece",
    "pcs": "piece",
    "पीस": "piece",
    "नग": "piece",
    "दर्जन": "dozen",
    "darjan": "dozen",
    "dozen": "dozen",
}

# Stopwords that must never be treated as customer or product names
STOPWORDS = {
    "kal", "aaj", "parso", "today", "tomorrow", "yesterday",
    "कल", "आज", "परसों",
    "deliver", "order", "shop", "stock", "supplier", "phone", "hello", "hi",
    "karo", "karna", "hai", "hain", "kar", "do", "kripya", "please",
    "bech", "becho", "bhejo", "bhejna", "de", "dena", "deni", "dene",
    "बेच", "बेचो", "भेजो", "भेजना", "देना", "देनी", "देने", "करो", "करना", "है", "हैं", "कर", "दो",
    "रुपये", "रुपया", "rupaye", "rupees", "rs", "inr",
}


def parse_multilingual_retail_transcript(
    raw_transcript: str,
    language: LanguageCode,
) -> StructuredAction:
    text = raw_transcript.strip()
    lower = text.lower()
    action_id = f"act-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    # 1. Intent Detection
    # Casual conversation or general greeting check
    greetings = ["hello", "hi", "how are you", "kya haal", "namaste", "good morning", "kaise ho", "नमस्ते", "हेलो"]
    if any(lower == g or lower.startswith(g + " ") for g in greetings) and len(text.split()) <= 4:
        return StructuredAction(
            id=action_id,
            createdAt=now.isoformat(),
            originalTranscript=raw_transcript,
            detectedLanguage=language,
            category=ActionCategory.INVENTORY_UPDATE,
            status=ActionStatus.PENDING_APPROVAL,
            confidenceScore=None,
            confidenceReason="Casual greeting detected; no commercial transaction requested.",
            entities=ExtractedEntities(
                customerName=None,
                phoneNumber=None,
                items=[],
                totalAmount=None,
                deliveryDate=None,
                dueDate=None,
                notes="General conversation — no business action required.",
            ),
        )

    reminder_indicators = [
        "reminder", "bhejna", "pending", "rupaye", "rupees", "rs", "inr",
        "baaki", "udhar", "udhaar", "vasool", "khata", "balance", "yaad dilana", "overdue", "dene hain",
        "उधार", "बाकी", "रिमाइंडर", "याद दिलाना", "पेंडिंग", "खाता", "वसूल",
    ]
    is_reminder = any(kw in lower for kw in reminder_indicators)

    # Check for payment reminder vs order creation
    if "udhar" in lower or "udhaar" in lower or "उधार" in text or "yaad dilana" in lower or "याद दिलाना" in text:
        category = ActionCategory.PAYMENT_REMINDER
    elif is_reminder and not any(w in lower for w in ["bech", "deliver", "bhejo", "बेच", "डिलीवर"]):
        category = ActionCategory.PAYMENT_REMINDER
    else:
        category = ActionCategory.ORDER_CREATION

    # 2. Customer Name Extraction
    customer_name: Optional[str] = None

    # Devanagari + Latin regex matching name immediately preceding postpositions (को / ko / ने / ne / के / ke / का / ka / से / se / जी / ji)
    postposition_match = re.search(
        r"\b([A-Za-z\u0900-\u097F]+(?:\s+[A-Za-z\u0900-\u097F]+)?)\s+(?:ko|ne|ke|ka|se|ji|bhai|को|ने|के|का|से|जी|भाई)\b",
        text,
        re.IGNORECASE,
    )
    if postposition_match:
        cand = postposition_match.group(1).strip()
        tokens = [w for w in cand.split() if w.lower() not in STOPWORDS]
        if tokens:
            customer_name = " ".join(w.capitalize() for w in tokens)
            if ("ji" in lower or "जी" in text) and not customer_name.lower().endswith("ji") and not customer_name.endswith("जी"):
                customer_name += " Ji"

    # Direct name detection fallback if postposition pattern didn't catch it
    if not customer_name:
        known_names = [
            ("Amit", ["amit", "अमित"]),
            ("Rahul", ["rahul", "राहुल"]),
            ("Priya", ["priya", "प्रिया"]),
            ("Sharma", ["sharma", "शर्मा"]),
            ("Verma", ["verma", "वर्मा"]),
            ("Gupta", ["gupta", "गुप्ता"]),
            ("Ramesh", ["ramesh", "रमेश"]),
            ("Sunita", ["sunita", "सुनीता"]),
            ("Anil", ["anil", "अनिल"]),
            ("Pooja", ["pooja", "पूजा"]),
            ("Vikram", ["vikram", "विक्रम"]),
            ("Suresh", ["suresh", "सुरेश"]),
        ]
        for canon_name, aliases in known_names:
            for al in aliases:
                if re.search(rf"\b{al}\b", text, re.IGNORECASE):
                    customer_name = canon_name
                    if ("ji" in lower or "जी" in text) and not customer_name.endswith("Ji") and not customer_name.endswith("जी"):
                        customer_name += " Ji"
                    break
            if customer_name:
                break

    # 3. Phone Number Extraction (Strictly from speech; NEVER invented)
    phone_match = re.search(r"(\+?91[\s-]?)?[6-9]\d{9}", text)
    phone_number: Optional[str] = phone_match.group(0) if phone_match else None

    # 4. Spoken Amount Extraction (e.g., 500 rupaye / 500 रुपये)
    total_amount: Optional[float] = None
    amt_match = (
        re.search(r"(\d+(?:\.\d+)?)\s*(?:rupaye|rupees|rs|inr|₹|रुपये|रुपया)\b", lower)
        or re.search(r"(?:rupaye|rupees|₹|rs\.?|रुपये|रुपया)\s*(\d+(?:\.\d+)?)\b", lower)
    )
    if amt_match:
        try:
            total_amount = float(amt_match.group(1))
        except (ValueError, IndexError):
            total_amount = None

    # 5. Quantity & Unit Extraction
    quantity: Optional[float] = None
    unit: str = "piece"

    # Regex matching number + unit in Hindi or English
    unit_pattern = r"(kilo|kg|kgs|kilogram|kilograms|packet|packets|pack|packs|carton|cartons|box|boxes|litre|litres|liter|liters|piece|pieces|notebook|notebooks|copy|bora|bori|g|gm|किलो|किलोग्राम|केजी|पैकेट|पैक|लीटर|ली|कार्टन|बॉक्स|पेटी|बोरी|ग्राम|पीस|नग|दर्जन)"
    qty_unit_match = re.search(rf"(\d+(?:\.\d+)?)\s*{unit_pattern}\b", lower)

    if qty_unit_match:
        quantity = float(qty_unit_match.group(1))
        raw_u = qty_unit_match.group(2).lower()
        unit = UNIT_MAP.get(raw_u, "piece")
    else:
        # Bare number matching for quantity (e.g. 5 chawal, 2 biscuit)
        bare_num_match = re.search(r"\b(\d+)\s+([A-Za-z\u0900-\u097F]+)", text)
        if bare_num_match:
            cand_num = float(bare_num_match.group(1))
            cand_word = bare_num_match.group(2).lower()
            if cand_word not in STOPWORDS and cand_word not in UNIT_MAP:
                quantity = cand_num
                unit = "piece"

    # 6. Spoken Product Extraction & Catalog Pricing Lookup
    product_name: Optional[str] = None
    unit_price: Optional[float] = None
    total_calculated: Optional[float] = None

    # Search for known products / aliases in the spoken text
    # Candidate product search terms
    known_product_matches = [
        ("Chawal", ["chawal", "चावल", "rice", "चांवल"]),
        ("Chakki Fresh Atta", ["atta", "आटा", "aata", "flour"]),
        ("Refined Cooking Oil", ["refined oil", "refined", "oil", "tel", "तेल"]),
        ("Fortune Mustard Oil", ["mustard oil", "sarson tel", "सरसों तेल", "सरसों का तेल"]),
        ("Madhur Pure Sugar", ["sugar", "chini", "चीनी", "cheeni", "shakkar"]),
        ("Tata Salt", ["salt", "namak", "नमक", "tata salt"]),
        ("Toor Dal Premium", ["toor dal", "arhar dal", "अरहर दाल", "तूर दाल", "dal", "दाल"]),
        ("Taj Mahal Tea", ["tea", "chai", "चाय", "chai patti"]),
        ("Parle-G Biscuit", ["biscuit", "biscuits", "बिस्कुट", "बिस्किट", "biskut"]),
        ("Classmate Notebook", ["notebook", "notebooks", "नोटबुक", "copy", "कॉपी"]),
        ("Lifebuoy Soap", ["soap", "साबुन", "sabun"]),
    ]

    for canon_name, aliases in known_product_matches:
        for al in aliases:
            if re.search(rf"\b{al}\b", lower):
                # Verify from configured product catalog
                cat_match = lookup_catalog_product(al)
                if cat_match:
                    product_name = cat_match[0]
                    unit_price = cat_match[1]
                    # If unit was piece but catalog specifies kg/packet, use catalog standard
                    if not qty_unit_match:
                        unit = cat_match[2]
                else:
                    product_name = canon_name
                break
        if product_name:
            break

    # If the user mentioned a product not in standard catalog
    if not product_name and quantity is not None:
        # Check word immediately following the quantity and unit, e.g. "5 kilo chawal" -> chawal
        after_unit_match = re.search(rf"\d+\s*{unit_pattern}?\s*([A-Za-z\u0900-\u097F]+)", text, re.IGNORECASE)
        if after_unit_match:
            potential_prod = after_unit_match.group(2).strip() if after_unit_match.lastindex and after_unit_match.lastindex >= 2 else after_unit_match.group(1).strip()
            # Ensure the potential product is NOT a unit name like "किलो" or a stopword
            if potential_prod.lower() not in UNIT_MAP and potential_prod.lower() not in STOPWORDS:
                cat_match = lookup_catalog_product(potential_prod)
                if cat_match:
                    product_name = cat_match[0]
                    unit_price = cat_match[1]
                else:
                    product_name = potential_prod.capitalize()

    # Calculate total if unit price is verified from catalog and quantity is known
    if quantity is not None and unit_price is not None:
        total_calculated = round(quantity * unit_price, 2)
    elif total_amount is not None:
        total_calculated = total_amount

    # Build items list
    items: List[ActionItem] = []
    if category == ActionCategory.ORDER_CREATION and product_name:
        items = [
            ActionItem(
                productName=product_name,
                quantity=quantity if quantity is not None else 1.0,
                unit=unit,
                unitPrice=unit_price,  # Looked up from catalog, or None
                totalPrice=total_calculated,  # Calculated or None
            )
        ]

    # 7. Date Resolution (Relative to Current Server Date)
    delivery_date: Optional[str] = None
    due_date: Optional[str] = None

    if any(w in lower for w in ["parso", "day after tomorrow", "परसों"]):
        resolved_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")
    elif any(w in lower for w in ["kal", "tomorrow", "कल"]):
        resolved_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    elif any(w in lower for w in ["aaj", "today", "आज"]):
        resolved_date = now.strftime("%Y-%m-%d")
    elif any(w in lower for w in ["friday", "shukrawar", "शुक्रवार"]):
        days_ahead = (4 - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        resolved_date = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    elif any(w in lower for w in ["monday", "somwar", "सोमवार"]):
        days_ahead = (0 - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        resolved_date = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    else:
        # Default order delivery to today if action is immediate sell ("bech / बेच") or unspecified
        if "bech" in lower or "बेच" in text:
            resolved_date = now.strftime("%Y-%m-%d")
        else:
            resolved_date = None

    if category == ActionCategory.ORDER_CREATION:
        delivery_date = resolved_date
    else:
        due_date = resolved_date

    # 8. Missing Fields & Honest Heuristic Confidence
    missing_fields: List[str] = []
    if not customer_name:
        missing_fields.append("customer")
    if category == ActionCategory.ORDER_CREATION:
        if not product_name:
            missing_fields.append("product")
        if quantity is None:
            missing_fields.append("quantity")
        if unit_price is None:
            missing_fields.append("price")
        if not delivery_date:
            missing_fields.append("delivery_date")
    else:
        if total_amount is None:
            missing_fields.append("amount")
        if not due_date:
            missing_fields.append("due_date")

    if not customer_name and not product_name:
        confidence_score = 0.30
        confidence_reason = f"Ambiguous command: missing {', '.join(missing_fields)}. Manual input required."
    elif missing_fields:
        confidence_score = round(max(0.40, 0.90 - (0.12 * len(missing_fields))), 2)
        confidence_reason = f"Extracted {category.value} with pending manual input: {', '.join(missing_fields)}."
    else:
        confidence_score = 0.92
        confidence_reason = f"Verified {category.value} for {customer_name}: {product_name} ({quantity} {unit}) at ₹{unit_price}/unit."

    notes = None
    if missing_fields:
        notes = f"Notice: Missing or uncatalogued fields: {', '.join(missing_fields)}"

    entities = ExtractedEntities(
        customerName=customer_name,
        phoneNumber=phone_number,
        items=items,
        totalAmount=total_calculated,
        deliveryDate=delivery_date,
        dueDate=due_date,
        notes=notes,
    )

    return StructuredAction(
        id=action_id,
        createdAt=now.isoformat(),
        originalTranscript=raw_transcript,
        detectedLanguage=language,
        category=category,
        entities=entities,
        status=ActionStatus.PENDING_APPROVAL,
        confidenceScore=confidence_score,
        confidenceReason=confidence_reason,
    )
