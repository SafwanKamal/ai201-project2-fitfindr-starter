from unittest.mock import patch

from app import handle_query
from utils.data_loader import load_listings


def test_handle_query_maps_successful_session_to_three_panels():
    item = load_listings()[5]
    session = {
        "selected_item": item,
        "outfit_suggestion": "Wear it with loose jeans.",
        "fit_card": "A casual fit-card caption.",
        "error": None,
    }

    with patch("app.run_agent", return_value=session) as run:
        listing, outfit, fit_card = handle_query(
            "graphic tee under $30", "Example wardrobe"
        )

    run.assert_called_once()
    assert "Graphic Tee — 2003 Tour Bootleg Style" in listing
    assert "$24 on depop" in listing
    assert outfit == session["outfit_suggestion"]
    assert fit_card == session["fit_card"]


def test_handle_query_maps_agent_error_to_first_panel_only():
    session = {
        "selected_item": None,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": "No listings matched. Try a broader description.",
    }

    with patch("app.run_agent", return_value=session):
        panels = handle_query(
            "designer ballgown size XXS under $5", "Example wardrobe"
        )

    assert panels == (session["error"], "", "")


def test_handle_query_rejects_empty_input_without_running_agent():
    with patch("app.run_agent") as run:
        panels = handle_query("  ", "Example wardrobe")

    run.assert_not_called()
    assert panels[0].startswith("Tell me what item")
    assert panels[1:] == ("", "")


def test_handle_query_uses_empty_wardrobe_selection():
    empty_wardrobe = {"items": []}
    session = {
        "selected_item": None,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": "No listings matched.",
    }

    with (
        patch("app.get_empty_wardrobe", return_value=empty_wardrobe),
        patch("app.run_agent", return_value=session) as run,
    ):
        handle_query("graphic tee", "Empty wardrobe (new user)")

    assert run.call_args.args[1] is empty_wardrobe
