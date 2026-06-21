from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from tools import create_fit_card, search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe, load_listings


def _fake_client(*responses: str) -> MagicMock:
    client = MagicMock()
    completions = [
        SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=response))]
        )
        for response in responses
    ]
    client.chat.completions.create.side_effect = completions
    return client


def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)

    assert isinstance(results, list)
    assert len(results) > 0
    assert all(item["price"] <= 50 for item in results)
    assert set(results[0]) == {
        "id",
        "title",
        "description",
        "category",
        "style_tags",
        "size",
        "condition",
        "price",
        "colors",
        "brand",
        "platform",
    }


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)

    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)

    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter_is_case_insensitive():
    results = search_listings("butterfly tee", size="m", max_price=30)

    assert results
    assert all("m" in item["size"].lower() for item in results)


def test_suggest_outfit_uses_named_wardrobe_items():
    client = _fake_client(
        "Pair it with the Baggy straight-leg jeans, dark wash and Chunky white "
        "sneakers for an easy streetwear look."
    )

    with patch("tools._get_groq_client", return_value=client):
        result = suggest_outfit(load_listings()[5], get_example_wardrobe())

    assert "Baggy straight-leg jeans" in result
    request = client.chat.completions.create.call_args.kwargs
    assert request["model"] == "llama-3.3-70b-versatile"
    assert "Baggy straight-leg jeans, dark wash" in request["messages"][0]["content"]


def test_suggest_outfit_handles_empty_wardrobe():
    client = _fake_client(
        "Try loose dark denim and chunky sneakers for a 90s grunge outfit."
    )

    with patch("tools._get_groq_client", return_value=client):
        result = suggest_outfit(load_listings()[5], get_empty_wardrobe())

    assert result.startswith("General styling idea (no wardrobe items provided):")
    prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "not added any wardrobe pieces" in prompt
    assert "Do not imply" in prompt
    assert "hypothetical language" in prompt


def test_suggest_outfit_rejects_empty_llm_response():
    client = _fake_client("   ")

    with patch("tools._get_groq_client", return_value=client):
        with pytest.raises(ValueError, match="empty outfit suggestion"):
            suggest_outfit(load_listings()[5], get_example_wardrobe())


def test_empty_wardrobe_outfit_rewrites_false_ownership_claim():
    client = _fake_client(
        "Pair it with your white sneakers and cardigan.",
        "It could work with white sneakers and a neutral cardigan.",
    )

    with patch("tools._get_groq_client", return_value=client):
        result = suggest_outfit(load_listings()[5], get_empty_wardrobe())

    assert result.startswith("General styling idea")
    assert "your white sneakers" not in result
    assert "could work with" in result
    assert client.chat.completions.create.call_count == 2


def test_empty_wardrobe_outfit_rejects_repeated_ownership_claims():
    client = _fake_client(
        "Pair it with your white sneakers.",
        "Wear it with my black cardigan.",
    )

    with patch("tools._get_groq_client", return_value=client):
        with pytest.raises(ValueError, match="wardrobe ownership"):
            suggest_outfit(load_listings()[5], get_empty_wardrobe())


def test_create_fit_card_returns_caption_and_uses_high_temperature():
    client = _fake_client(
        "The Graphic Tee — 2003 Tour Bootleg Style was a $24 Depop find. "
        "The faded graphic with loose denim is pure grunge energy 🖤"
    )
    outfit = "Wear it with loose dark jeans and chunky white sneakers."

    with patch("tools._get_groq_client", return_value=client):
        result = create_fit_card(outfit, load_listings()[5])

    assert "Graphic Tee — 2003 Tour Bootleg Style" in result
    request = client.chat.completions.create.call_args.kwargs
    assert request["model"] == "llama-3.3-70b-versatile"
    assert request["temperature"] >= 1.0


@pytest.mark.parametrize("outfit", ["", "   ", None])
def test_create_fit_card_guards_empty_outfit_without_calling_llm(outfit):
    with patch("tools._get_groq_client") as get_client:
        result = create_fit_card(outfit, load_listings()[5])

    assert result.startswith("Error:")
    get_client.assert_not_called()


def test_create_fit_card_guards_incomplete_item_without_calling_llm():
    with patch("tools._get_groq_client") as get_client:
        result = create_fit_card("A complete outfit", {"title": "Mystery tee"})

    assert result.startswith("Error:")
    get_client.assert_not_called()


def test_create_fit_card_empty_llm_response_returns_error():
    client = _fake_client("  ")

    with patch("tools._get_groq_client", return_value=client):
        result = create_fit_card("Wear it with loose jeans.", load_listings()[5])

    assert result.startswith("Error:")


def test_empty_wardrobe_fit_card_rewrites_false_ownership_claim():
    client = _fake_client(
        "This would look great with my white sneakers.",
        "I'd style it with high-waisted jeans and white sneakers for a playful look.",
    )
    outfit = (
        "General styling idea (no wardrobe items provided):\n"
        "High-waisted jeans and white sneakers would work well."
    )

    with patch("tools._get_groq_client", return_value=client):
        result = create_fit_card(outfit, load_listings()[1])

    assert result.startswith("I'd style it with")
    assert "my white sneakers" not in result
    assert client.chat.completions.create.call_count == 2
    first_prompt = client.chat.completions.create.call_args_list[0].kwargs[
        "messages"
    ][0]["content"]
    assert "empty wardrobe" in first_prompt
    assert "hypothetical" in first_prompt


def test_empty_wardrobe_fit_card_rejects_repeated_ownership_claims():
    client = _fake_client(
        "I’m wearing it with high-waisted jeans.",
        "This works with your favorite white sneakers.",
    )
    outfit = (
        "General styling idea (no wardrobe items provided):\n"
        "High-waisted jeans and white sneakers would work well."
    )

    with patch("tools._get_groq_client", return_value=client):
        result = create_fit_card(outfit, load_listings()[1])

    assert result == (
        "Error: The fit card incorrectly implied ownership of suggested items."
    )


def test_create_fit_card_can_return_varied_captions_for_same_input():
    client = _fake_client(
        "Found this tour tee on Depop for $24. Baggy denim makes it feel perfectly 90s.",
        "This $24 Depop tour tee belongs with loose jeans. The whole look is grunge in the best way.",
        "A faded tour tee, chunky sneakers, and loose denim—my $24 Depop find understood the assignment.",
    )
    item = load_listings()[5]
    outfit = "Wear it with loose jeans and chunky sneakers."

    with patch("tools._get_groq_client", return_value=client):
        captions = {create_fit_card(outfit, item) for _ in range(3)}

    assert len(captions) == 3
    assert all(
        call.kwargs["temperature"] >= 1.0
        for call in client.chat.completions.create.call_args_list
    )
