"""
Official Retail Product Catalog configuration for VoxFlow.
Maps common Hindi, Devanagari, Hinglish and English keywords to catalog items
with their verified unit price and standard measurement unit.
"""
from typing import Optional, Tuple, Dict

# Structure: canonical_name -> (unit_price, default_unit, set_of_aliases)
CATALOG_ITEMS = {
    "Chawal": {
        "unit_price": 85.0,
        "unit": "kg",
        "aliases": {"chawal", "चावल", "rice", "चांवल"}
    },
    "Chakki Fresh Atta": {
        "unit_price": 44.0,
        "unit": "kg",
        "aliases": {"atta", "आटा", "aata", "flour", "gehu"}
    },
    "Refined Cooking Oil": {
        "unit_price": 150.0,
        "unit": "litre",
        "aliases": {"oil", "tel", "तेल", "refined", "refined oil"}
    },
    "Fortune Mustard Oil": {
        "unit_price": 165.0,
        "unit": "litre",
        "aliases": {"mustard oil", "sarson tel", "sarson ka tel", "सरसों का तेल", "सरसों तेल"}
    },
    "Madhur Pure Sugar": {
        "unit_price": 48.0,
        "unit": "kg",
        "aliases": {"sugar", "chini", "चीनी", "cheeni", "shakkar"}
    },
    "Tata Salt": {
        "unit_price": 28.0,
        "unit": "packet",
        "aliases": {"salt", "namak", "नमक", "tata salt"}
    },
    "Toor Dal Premium": {
        "unit_price": 135.0,
        "unit": "kg",
        "aliases": {"toor dal", "arhar dal", "अरहर दाल", "तूर दाल", "dal", "pulse", "दाल"}
    },
    "Taj Mahal Tea": {
        "unit_price": 240.0,
        "unit": "packet",
        "aliases": {"tea", "chai", "चाय", "chai patti", "चाय पत्ती"}
    },
    "Parle-G Biscuit": {
        "unit_price": 25.0,
        "unit": "packet",
        "aliases": {"biscuit", "biscuits", "बिस्कुट", "बिस्किट", "biskut", "parle-g", "parle g"}
    },
    "Classmate Notebook": {
        "unit_price": 45.0,
        "unit": "piece",
        "aliases": {"notebook", "notebooks", "नोटबुक", "copy", "कॉपी", "copies"}
    },
    "Lifebuoy Soap": {
        "unit_price": 35.0,
        "unit": "piece",
        "aliases": {"soap", "साबुन", "sabun"}
    }
}


def lookup_catalog_product(term: str) -> Optional[Tuple[str, float, str]]:
    """
    Given a spoken term or sentence snippet, finds the matching catalog product.
    Returns: (canonical_product_name, unit_price, default_unit) or None if not catalogued.
    """
    clean_term = term.strip().lower()
    
    # Direct match or alias match
    for prod_name, details in CATALOG_ITEMS.items():
        if clean_term == prod_name.lower():
            return prod_name, details["unit_price"], details["unit"]
        if clean_term in details["aliases"]:
            return prod_name, details["unit_price"], details["unit"]
            
    # Substring / word boundary match
    for prod_name, details in CATALOG_ITEMS.items():
        for alias in details["aliases"]:
            if f" {alias} " in f" {clean_term} ":
                return prod_name, details["unit_price"], details["unit"]
                
    return None

