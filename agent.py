"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

_PRICE_PATTERN = re.compile(
    r"\b(?:under|below|less\s+than|max(?:imum)?(?:\s+price)?(?:\s+of)?)"
    r"\s*\$?\s*(\d+(?:\.\d{1,2})?)\b",
    re.IGNORECASE,
)
_SIZE_PATTERN = re.compile(
    r"(?:\bin\s+)?\bsize\s+"
    r"((?:US|UK|EU)\s*\d+(?:\.\d+)?|XXS|XS|S|M|L|XL|XXL|"
    r"\d+(?:\.\d+)?)\b",
    re.IGNORECASE,
)
_REQUEST_PREFIX_PATTERN = re.compile(
    r"^(?:(?:i['’]?m|i\s+am)\s+)?(?:looking|searching)\s+for\s+"
    r"(?:(?:a|an|some)\s+)?|^find\s+me\s+(?:(?:a|an|some)\s+)?",
    re.IGNORECASE,
)


def _parse_query(query: str) -> dict:
    """Extract search arguments from the first shopping-request sentence."""
    search_clause = re.split(r"[.!?](?:\s+|$)", query.strip(), maxsplit=1)[0]

    price_match = _PRICE_PATTERN.search(search_clause)
    max_price = float(price_match.group(1)) if price_match else None

    size_match = _SIZE_PATTERN.search(search_clause)
    size = re.sub(r"\s+", " ", size_match.group(1)).upper() if size_match else None

    description = _PRICE_PATTERN.sub(" ", search_clause)
    description = _SIZE_PATTERN.sub(" ", description)
    description = _REQUEST_PREFIX_PATTERN.sub("", description)
    description = re.sub(r"\s+", " ", description).strip(" ,;:-")

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


def _no_results_message(parsed: dict) -> str:
    """Build an actionable no-results message from the attempted filters."""
    constraints = []
    if parsed["size"] is not None:
        constraints.append(f"in size {parsed['size']}")
    if parsed["max_price"] is not None:
        constraints.append(f"under ${parsed['max_price']:g}")
    attempted_filters = f" {' '.join(constraints)}" if constraints else ""
    return (
        f"No listings matched '{parsed['description']}'{attempted_filters}. "
        "Try a broader description, another size, or a higher price limit."
    )

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    session = _new_session(query, wardrobe)

    if not isinstance(query, str) or not query.strip():
        session["error"] = (
            "Tell me what item you're looking for—for example, "
            "'vintage graphic tee under $30, size M'."
        )
        return session

    session["parsed"] = _parse_query(query)
    if not session["parsed"]["description"]:
        session["error"] = (
            "Tell me what kind of item you want, such as 'graphic tee' or "
            "'combat boots'."
        )
        return session

    try:
        session["search_results"] = search_listings(**session["parsed"])
    except Exception:
        session["error"] = (
            "I couldn't search the listings right now. Please try again."
        )
        return session

    if not session["search_results"]:
        session["error"] = _no_results_message(session["parsed"])
        return session

    session["selected_item"] = session["search_results"][0]

    try:
        outfit = suggest_outfit(session["selected_item"], session["wardrobe"])
    except Exception:
        session["error"] = (
            "I found a listing, but couldn't create an outfit suggestion. "
            "Try again, or add a few wardrobe pieces with colors and categories."
        )
        return session

    if not isinstance(outfit, str) or not outfit.strip():
        session["error"] = (
            "I found a listing, but couldn't create an outfit suggestion. "
            "Try again, or add a few wardrobe pieces with colors and categories."
        )
        return session
    session["outfit_suggestion"] = outfit.strip()

    try:
        fit_card = create_fit_card(
            session["outfit_suggestion"], session["selected_item"]
        )
    except Exception:
        fit_card = ""

    if (
        not isinstance(fit_card, str)
        or not fit_card.strip()
        or fit_card.strip().lower().startswith("error:")
    ):
        session["error"] = (
            "Your outfit idea is ready, but I couldn't create the fit card because "
            "the outfit or listing details were incomplete. You can still use the "
            "outfit suggestion above, or try generating the card again."
        )
        return session

    session["fit_card"] = fit_card.strip()
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
    print(f"Fit card: {session2['fit_card']}")
