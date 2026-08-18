from v2.v3_telegram import currency, paginate_cards, percent, text, ticker


def test_html_and_ticker_are_safe_and_linked():
    assert text("A&B <test>") == "A&amp;B &lt;test&gt;"
    assert "NSE%3ARELIANCE" in ticker("reliance")
    assert "href=" not in ticker("bad symbol!")


def test_missing_and_indian_values():
    assert currency(125000) == "₹125,000.00"
    assert currency(None) == "N/A"
    assert percent(-2.5) == "-2.50%"


def test_card_pagination_never_splits_card():
    cards = ["A" * 1700, "B" * 1700, "C" * 1700]
    pages = paginate_cards("<b>HEADER</b>", cards)
    assert len(pages) == 3
    assert all(len(page) <= 3400 for page in pages)
