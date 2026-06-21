# FitFindr

FitFindr is a small shopping-and-styling agent for secondhand clothing. A user describes an item, optionally including size and budget; FitFindr searches a mock marketplace, styles the best match with either an example or empty wardrobe, and generates a shareable fit-card caption.

## Setup and Running the App

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `.env` in the project root:

```text
GROQ_API_KEY=your_actual_key_here
```

Run the tests and application:

```bash
pytest tests/ -v
python app.py
```

Open the local URL printed by Gradio. It is usually `http://127.0.0.1:7860`, but another port may be selected. The terminal must remain running while the page is open.

## Data and Wardrobes

`data/listings.json` contains 40 mock marketplace listings. Every listing has `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform` fields. `search_listings` loads this file through `load_listings()` rather than duplicating file-loading logic.

`data/wardrobe_schema.json` defines a wardrobe as `{"items": [...]}`. Each item has `id`, `name`, `category`, `colors`, `style_tags`, and optional `notes`. The Gradio radio control can load the ten-item example wardrobe or an empty wardrobe; an empty wardrobe produces general styling advice rather than claiming the user owns particular clothes.

## Tool Inventory

### `search_listings(description, size=None, max_price=None) -> list[dict]`

- `description` (`str`): Required words describing the desired item or style.
- `size` (`str | None`): Optional case-insensitive size filter. A value such as `"M"` can match a listing size such as `"S/M"`.
- `max_price` (`float | None`): Optional inclusive price ceiling.
- Purpose: Load the mock listings, apply size and price filters, score keyword overlap across the listing's searchable fields, remove zero-score records, and rank the remaining records by relevance.
- Output: A relevance-ordered list of complete listing dictionaries. Every returned dictionary retains all eleven dataset fields; no internal relevance score is exposed. No matches produce `[]`.

### `suggest_outfit(new_item, wardrobe) -> str`

- `new_item` (`dict`): The complete selected listing returned by `search_listings`.
- `wardrobe` (`dict`): A dictionary whose `items` list follows the wardrobe schema.
- Purpose: Ask Groq's `llama-3.3-70b-versatile` model for one or two outfits featuring the new item. With a populated wardrobe, the prompt requires exact names of owned pieces; with an empty wardrobe, it requests generic item types and explicitly forbids implying ownership.
- Output: A non-empty outfit suggestion string containing combinations, rationale, and a styling detail. Empty-wardrobe suggestions carry a visible `General styling idea (no wardrobe items provided)` label so that context survives the next tool handoff. An empty model response raises an error for the planning loop to handle.

### `create_fit_card(outfit, new_item) -> str`

- `outfit` (`str`): The non-empty outfit suggestion saved from `suggest_outfit`.
- `new_item` (`dict`): The same complete listing selected after search.
- Purpose: Ask `llama-3.3-70b-versatile` for a casual two-to-four-sentence social caption that mentions the exact item, price, and platform and reflects the outfit's styling. Its temperature is `1.1` to encourage variation.
- Output: A caption string. For an empty wardrobe it must use hypothetical wording such as “I'd style it with” rather than claiming the user owns or wore suggested pieces. Missing/blank outfit text or incomplete listing data returns a string beginning with `"Error:"` without calling Groq.

## Planning Loop

`run_agent(query, wardrobe)` does not call all tools unconditionally. It follows these branches:

1. Create a new session. If the query is blank, save an actionable error and return before calling any tool.
2. Parse the first shopping-request sentence with regular expressions. Extract `description`, optional `size`, and optional `max_price`, then save them in `session["parsed"]`. Later preference sentences such as “I mostly wear baggy jeans” are not treated as search keywords.
3. Call `search_listings(**session["parsed"])` and save the list in `session["search_results"]`.
4. If the list is empty, construct an error that repeats the attempted description and constraints, save it in `session["error"]`, and return immediately. `suggest_outfit` and `create_fit_card` are never called on this branch.
5. If matches exist, save `search_results[0]` as `session["selected_item"]`. Pass that exact dictionary and `session["wardrobe"]` to `suggest_outfit`, validate its response, and save it as `session["outfit_suggestion"]`.
6. Pass the saved outfit string and the same selected listing dictionary to `create_fit_card`. If it returns a valid caption, save it as `session["fit_card"]`; otherwise preserve the successful listing/outfit state, set `session["error"]`, and return.
7. A successful session has `error=None` and populated `selected_item`, `outfit_suggestion`, and `fit_card` fields.

This makes behavior input-dependent: a successful search executes all three tools, while a no-results search terminates after the first tool.

## State Management

A fresh dictionary created by `_new_session()` is the single source of truth for each interaction:

```python
{
    "query": "vintage graphic tee under $30",
    "parsed": {
        "description": "vintage graphic tee",
        "size": None,
        "max_price": 30.0,
    },
    "search_results": [...],
    "selected_item": {...},
    "wardrobe": {"items": [...]},
    "outfit_suggestion": "...",
    "fit_card": "...",
    "error": None,
}
```

Values are written only after their stage succeeds. Tests use spies to confirm that `selected_item` is the same dictionary passed to both LLM tools and that the saved `outfit_suggestion` is the exact value passed to `create_fit_card`. No global conversation state is reused between users or runs.

## Complete Interaction Walkthrough

**User query:** `vintage graphic tee under $30`, using **Example wardrobe**.

1. The parser saves `{"description": "vintage graphic tee", "size": None, "max_price": 30.0}`. `search_listings` uses those exact values and returns ranked complete records; in the tested run the first result was `Y2K Baby Tee — Butterfly Print`, priced at `$18` on Depop.
2. The planning loop saves that record as `selected_item` and calls `suggest_outfit(selected_item, wardrobe)`. The returned suggestion used actual example-wardrobe names such as `Baggy straight-leg jeans, dark wash`, `Chunky white sneakers`, `Wide-leg khaki trousers`, and `Black combat boots`.
3. The loop saves the suggestion and calls `create_fit_card(outfit_suggestion, selected_item)`. The returned caption correctly mentioned the Y2K Baby Tee, `$18`, Depop, and the styling details.
4. `handle_query` formats the selected listing into the first Gradio panel and maps the two saved strings to the outfit and fit-card panels.

## Error Handling and Tested Failures

| Component | Failure mode | Agent response |
|---|---|---|
| Query parser | Empty query or no item description | Returns before search with an example of a usable request. The other panels remain empty. |
| `search_listings` | No record matches all supplied constraints | Saves an actionable constraint-aware error and returns before either LLM tool. Tested with `designer ballgown size XXS under $5`: `search_results=[]`, `selected_item=None`, `outfit_suggestion=None`, and `fit_card=None`. |
| `search_listings` | Dataset/search exception | Returns `I couldn't search the listings right now. Please try again.` |
| `suggest_outfit` | Empty wardrobe | This is supported, not fatal: the tool asks for hypothetical general silhouettes/colors, labels the result as general styling, and does not invent owned pieces. |
| `suggest_outfit` | Model exception or empty response | Preserves the selected listing, tells the user it could not create an outfit, and skips `create_fit_card`. |
| `create_fit_card` | Empty outfit or missing title/price/platform | Returns an `Error:` string without calling Groq. The loop preserves the listing and outfit and offers a retry rather than displaying a fabricated caption. |
| `create_fit_card` | Empty-wardrobe caption falsely says “I paired/wore it with” or “my jeans/shoes” | Detects the ownership claim and asks Groq to rewrite once using hypothetical language. If the rewrite repeats the claim, it returns an `Error:` string instead of displaying false information. |
| Groq service | Missing key, connection failure, or timeout | The planning loop catches the tool exception and returns the stage-specific message. The Groq client has a 20-second timeout and no automatic retries. |

The automated suite contains 28 tests covering individual tools, prompt branches, semantic ownership guards, planning decisions, object-identity state passing, UI mapping, and early returns:

```bash
pytest tests/ -v
```

## Gradio Interface

`handle_query(user_query, wardrobe_choice)` validates the textbox, loads either `get_example_wardrobe()` or `get_empty_wardrobe()`, runs the agent once, and maps the returned session into three panels. On success all panels contain the selected listing, outfit idea, and fit card. On an agent error, the first panel shows the message and the two downstream panels remain blank.

## AI Usage

### Instance 1 — Individual tool implementations

I gave ChatGPT/Codex one tool specification at a time from the **Tools** section of `planning.md`, including exact parameters, return fields, and failure behavior, plus the relevant `tools.py` stub and `utils/data_loader.py` helper signature. It produced implementations for deterministic listing scoring and the two Groq prompts. Before using them, I kept the existing signatures, reviewed every dataset field, changed the prompts to explicitly forbid invented wardrobe ownership, added empty-response validation, set the fit-card temperature to `1.1`, and added a bounded Groq client timeout.

I verified each function independently before connecting them. The tests mock only the Groq transport while inspecting the real prompt/model/temperature arguments, and they exercise real listing data for search filtering and ranking.

### Instance 2 — Planning loop and state flow

I gave ChatGPT/Codex the complete **Planning Loop** and **State Management** sections from `planning.md`, the Mermaid architecture diagram, and the existing `_new_session()`/`run_agent()` stubs. It produced the orchestration structure and conditional early returns. I replaced vague query interpretation with deterministic regular-expression parsing, added stage-specific exception handling, and wrote spy tests that assert object identity between `selected_item` and the arguments received by both later tools.

I also overrode any unconditional pipeline behavior: an empty `search_results` list now returns immediately. A dedicated test asserts that both `suggest_outfit` and `create_fit_card` have zero calls on that branch.

### Instance 3 — Correcting an empty-wardrobe ownership error

During live Gradio testing, the empty-wardrobe outfit suggestion correctly gave general advice, but the AI-generated fit card changed that advice into `I paired it with high-waisted light-wash jeans, white sneakers, and a neutral cardigan.` That wording falsely implied the user owned and had worn items that were never present in the empty wardrobe. I gave ChatGPT/Codex the screenshot, the actual output, and the `suggest_outfit`/`create_fit_card` handoff and asked it to identify where the wardrobe context was lost.

The proposed prompt-only correction was not strong enough by itself, so I added deterministic safeguards before accepting it: empty-wardrobe suggestions now carry a general-styling marker into `create_fit_card`, both prompts require hypothetical wording, and both stages detect ownership claims such as `I paired`, `I'm wearing`, `my sneakers`, or `your cardigan`. The tool requests one rewrite and returns an error instead of displaying false information if the rewrite still claims ownership. I added regression tests reproducing the original failure and related wording variants; the complete suite now has 28 passing tests.

## Spec Reflection

**One way `planning.md` helped during implementation:** The tool contracts made state boundaries concrete before coding: search returns complete listing dictionaries, outfit generation consumes one of those exact dictionaries plus the wardrobe, and fit-card generation consumes the saved outfit plus that same listing. The error diagram made the most important control-flow constraint visible—an empty search must terminate before either LLM tool—which translated directly into an early return and a mock assertion.

**One divergence from the spec, and why:** The walkthrough's illustrative `Faded Band Tee` result does not exist under that exact title/price/size combination in the supplied dataset, so the live run correctly selected the highest-scoring real record (`Y2K Baby Tee — Butterfly Print`) instead of hardcoding the example. I also made incomplete fit-card input use a recognizable `Error:` prefix so the string-returning tool and planning loop can distinguish validation failure from a caption without changing the required function signature.


