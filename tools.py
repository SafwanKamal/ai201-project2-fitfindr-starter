"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

_GENERAL_STYLING_PREFIX = "General styling idea (no wardrobe items provided):"
_OWNERSHIP_CLAIM_PATTERN = re.compile(
    r"\b(?:i(?:\s+|['’])(?:paired|styled|wore|wear|rocked|matched|teamed|"
    r"am\s+wearing|m\s+wearing|have\s+paired|have\s+styled|ve\s+paired|"
    r"ve\s+styled)|(?:my|your)\s+(?:[a-z-]+\s+){0,3}(?:jeans|pants|"
    r"trousers|skirt|shorts|shoes|sneakers|boots|sandals|cardigan|jacket|hoodie|coat|"
    r"bag|belt|necklace))\b",
    re.IGNORECASE,
)


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key, timeout=20.0, max_retries=0)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
    query_terms = set(re.findall(r"[a-z0-9]+", description.lower()))
    if not query_terms:
        return []

    scored_listings: list[tuple[int, dict]] = []

    for listing in load_listings():
        if max_price is not None and listing["price"] > max_price:
            continue
        if size is not None and size.strip().lower() not in listing["size"].lower():
            continue

        searchable_values = [
            listing["title"],
            listing["description"],
            listing["category"],
            *listing["style_tags"],
            *listing["colors"],
            listing["brand"] or "",
            listing["platform"],
        ]
        searchable_terms = set(
            re.findall(r"[a-z0-9]+", " ".join(searchable_values).lower())
        )
        relevance = len(query_terms & searchable_terms)
        if relevance > 0:
            scored_listings.append((relevance, listing))

    scored_listings.sort(key=lambda result: result[0], reverse=True)
    return [listing for _, listing in scored_listings]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    wardrobe_items = wardrobe.get("items", [])
    item_summary = (
        f"{new_item.get('title', 'Unnamed item')} | "
        f"category: {new_item.get('category', 'unknown')} | "
        f"colors: {', '.join(new_item.get('colors', [])) or 'unknown'} | "
        f"style: {', '.join(new_item.get('style_tags', [])) or 'unspecified'}"
    )

    if wardrobe_items:
        formatted_wardrobe = "\n".join(
            (
                f"- {item.get('name', 'Unnamed piece')} "
                f"({item.get('category', 'unknown')}; "
                f"colors: {', '.join(item.get('colors', [])) or 'unknown'}; "
                f"style: {', '.join(item.get('style_tags', [])) or 'unspecified'}; "
                f"notes: {item.get('notes') or 'none'})"
            )
            for item in wardrobe_items
        )
        prompt = f"""You are FitFindr, a practical personal stylist.

New thrifted item:
{item_summary}

Pieces the user already owns:
{formatted_wardrobe}

Suggest one or two complete outfits that feature the new item and use specific
pieces from the wardrobe by their exact names. Explain briefly why the pieces
work together and include one concrete styling detail such as layering,
cuffing, or tucking. Keep the answer concise and do not invent wardrobe items."""
    else:
        prompt = f"""You are FitFindr, a practical personal stylist.

New thrifted item:
{item_summary}

The user has not added any wardrobe pieces yet. Give one or two concise,
general outfit ideas by naming the types, colors, and silhouettes of bottoms,
shoes, layers, or accessories that would pair well with the new item. Describe
the overall vibe and include one concrete styling detail. Do not imply that the
user already owns any of the suggested pieces. Use hypothetical language such
as "could pair," "would work with," or "I'd style it with." Never claim "I
paired it with," "I wore it with," or refer to "my jeans" or "my shoes."""

    client = _get_groq_client()
    messages = [{"role": "user", "content": prompt}]
    attempts = 1 if wardrobe_items else 2

    for attempt in range(attempts):
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=350,
        )
        suggestion = response.choices[0].message.content
        if not suggestion or not suggestion.strip():
            raise ValueError("Groq returned an empty outfit suggestion.")
        suggestion = suggestion.strip()

        if wardrobe_items:
            return suggestion
        if not _OWNERSHIP_CLAIM_PATTERN.search(suggestion):
            return f"{_GENERAL_STYLING_PREFIX}\n{suggestion}"

        if attempt == 0:
            messages.extend(
                [
                    {"role": "assistant", "content": suggestion},
                    {
                        "role": "user",
                        "content": (
                            "Rewrite this as a hypothetical styling idea. The "
                            "wardrobe is empty, so do not say I paired, wore, or "
                            "own any supporting clothes, and do not refer to my "
                            "or your jeans, shoes, layers, or accessories."
                        ),
                    },
                ]
            )

    raise ValueError("Outfit suggestion incorrectly implied wardrobe ownership.")


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if (
        not isinstance(outfit, str)
        or not outfit.strip()
        or not isinstance(new_item, dict)
        or not new_item.get("title")
        or new_item.get("price") is None
        or not new_item.get("platform")
    ):
        return (
            "Error: Cannot create fit card without a complete outfit, title, "
            "price, and platform."
        )

    general_styling = outfit.strip().startswith(_GENERAL_STYLING_PREFIX)
    wardrobe_context = (
        "The user provided an empty wardrobe. Every supporting garment in the "
        "outfit idea is hypothetical: use phrases such as 'I'd style it with' "
        "or 'would look great with.' Never say 'I paired it with,' 'I wore it "
        "with,' 'I'm wearing,' or call a supporting garment 'my jeans/shoes/etc.'"
        if general_styling
        else "The outfit uses pieces from the user's provided wardrobe."
    )
    prompt = f"""You write casual, authentic social captions for FitFindr.

Thrifted item: {new_item['title']}
Price: ${new_item['price']:g}
Platform: {new_item['platform']}
Outfit idea: {outfit.strip()}
Wardrobe context: {wardrobe_context}

Write one shareable Instagram or TikTok caption of 2 to 4 sentences. Mention
the exact item title, price, and platform naturally exactly once each. Capture
the outfit's specific vibe and styling details. Sound like a real OOTD post,
not an advertisement or product description. Do not claim the user has already
worn an outfit unless the wardrobe context explicitly supports that claim. A
restrained emoji is welcome.
Return only the caption with no heading, quotation marks, or explanation."""

    client = _get_groq_client()
    messages = [{"role": "user", "content": prompt}]
    attempts = 2 if general_styling else 1

    for attempt in range(attempts):
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=1.1,
            max_tokens=220,
        )
        caption = response.choices[0].message.content
        if not caption or not caption.strip():
            return "Error: The fit card generator returned an empty caption."
        caption = caption.strip()

        if not general_styling or not _OWNERSHIP_CLAIM_PATTERN.search(caption):
            return caption

        if attempt == 0:
            messages.extend(
                [
                    {"role": "assistant", "content": caption},
                    {
                        "role": "user",
                        "content": (
                            "Rewrite the caption. The wardrobe is empty, so the "
                            "supporting clothes are only suggestions. Use "
                            "hypothetical wording such as 'I'd style it with' and "
                            "remove every claim that I paired, wore, or own them."
                        ),
                    },
                ]
            )

    return "Error: The fit card incorrectly implied ownership of suggested items."
