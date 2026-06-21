from unittest.mock import patch

from agent import run_agent
from utils.data_loader import get_example_wardrobe, load_listings


def test_complete_query_passes_session_state_between_tools():
    selected_item = load_listings()[5]
    wardrobe = get_example_wardrobe()
    expected_outfit = "Use the dark baggy jeans and chunky white sneakers."
    expected_card = "This $24 Depop tee was made for a baggy grunge fit."

    def outfit_spy(new_item, received_wardrobe):
        assert new_item is selected_item
        assert received_wardrobe is wardrobe
        return expected_outfit

    def fit_card_spy(outfit, new_item):
        assert outfit is expected_outfit
        assert new_item is selected_item
        return expected_card

    with (
        patch("agent.search_listings", return_value=[selected_item]) as search,
        patch("agent.suggest_outfit", side_effect=outfit_spy) as suggest,
        patch("agent.create_fit_card", side_effect=fit_card_spy) as create,
    ):
        session = run_agent(
            "I'm looking for a vintage graphic tee under $30, size L. "
            "I mostly wear baggy jeans and chunky sneakers.",
            wardrobe,
        )

    search.assert_called_once_with(
        description="vintage graphic tee", size="L", max_price=30.0
    )
    suggest.assert_called_once()
    create.assert_called_once()
    assert session == {
        "query": (
            "I'm looking for a vintage graphic tee under $30, size L. "
            "I mostly wear baggy jeans and chunky sneakers."
        ),
        "parsed": {
            "description": "vintage graphic tee",
            "size": "L",
            "max_price": 30.0,
        },
        "search_results": [selected_item],
        "selected_item": selected_item,
        "wardrobe": wardrobe,
        "outfit_suggestion": expected_outfit,
        "fit_card": expected_card,
        "error": None,
    }
    assert session["selected_item"] is selected_item


def test_no_results_returns_early_without_calling_later_tools():
    wardrobe = get_example_wardrobe()

    with (
        patch("agent.search_listings", return_value=[]) as search,
        patch("agent.suggest_outfit") as suggest,
        patch("agent.create_fit_card") as create,
    ):
        session = run_agent(
            "designer ballgown size XXS under $5",
            wardrobe,
        )

    search.assert_called_once_with(
        description="designer ballgown", size="XXS", max_price=5.0
    )
    suggest.assert_not_called()
    create.assert_not_called()
    assert session["search_results"] == []
    assert session["selected_item"] is None
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None
    assert "Try a broader description" in session["error"]


def test_empty_query_returns_before_calling_any_tool():
    with (
        patch("agent.search_listings") as search,
        patch("agent.suggest_outfit") as suggest,
        patch("agent.create_fit_card") as create,
    ):
        session = run_agent("   ", get_example_wardrobe())

    search.assert_not_called()
    suggest.assert_not_called()
    create.assert_not_called()
    assert session["error"].startswith("Tell me what item")


def test_outfit_failure_preserves_selected_item_and_skips_fit_card():
    selected_item = load_listings()[5]

    with (
        patch("agent.search_listings", return_value=[selected_item]),
        patch("agent.suggest_outfit", return_value="   "),
        patch("agent.create_fit_card") as create,
    ):
        session = run_agent("graphic tee", get_example_wardrobe())

    create.assert_not_called()
    assert session["selected_item"] is selected_item
    assert session["outfit_suggestion"] is None
    assert session["fit_card"] is None
    assert "couldn't create an outfit suggestion" in session["error"]


def test_fit_card_failure_preserves_completed_outfit_state():
    selected_item = load_listings()[5]
    outfit = "Wear it with loose jeans."

    with (
        patch("agent.search_listings", return_value=[selected_item]),
        patch("agent.suggest_outfit", return_value=outfit),
        patch("agent.create_fit_card", return_value="Error: missing input"),
    ):
        session = run_agent("graphic tee", get_example_wardrobe())

    assert session["selected_item"] is selected_item
    assert session["outfit_suggestion"] == outfit
    assert session["fit_card"] is None
    assert "couldn't create the fit card" in session["error"]


def test_different_queries_produce_different_search_arguments():
    selected_item = load_listings()[5]

    with (
        patch("agent.search_listings", return_value=[selected_item]) as search,
        patch("agent.suggest_outfit", return_value="An outfit"),
        patch("agent.create_fit_card", return_value="A fit card"),
    ):
        run_agent("graphic tee under $30", get_example_wardrobe())
        run_agent("combat boots size 8", get_example_wardrobe())

    assert search.call_args_list[0].kwargs == {
        "description": "graphic tee",
        "size": None,
        "max_price": 30.0,
    }
    assert search.call_args_list[1].kwargs == {
        "description": "combat boots",
        "size": "8",
        "max_price": None,
    }
