from app.data.schemas import BookLevel, MarketQuote, OrderBook
from app.signals.arbitrage import ArbitrageDetector


def _mk_book(bid: float, ask: float, size: float = 1000) -> OrderBook:
    return OrderBook(
        bids=[BookLevel(bid, size)],
        asks=[BookLevel(ask, size)],
    )


def _mk_quote(yes_bid, yes_ask, no_bid, no_ask) -> MarketQuote:
    return MarketQuote(
        condition_id="0xabc",
        slug="test-market",
        question="q",
        yes_token_id="1",
        no_token_id="2",
        yes_book=_mk_book(yes_bid, yes_ask),
        no_book=_mk_book(no_bid, no_ask),
        volume_24h=100000,
    )


def test_arbitrage_detects_buy_both():
    quote = _mk_quote(yes_bid=0.48, yes_ask=0.48, no_bid=0.40, no_ask=0.41)
    # asks sum = 0.89 → 0.11 profit per bond
    signals = ArbitrageDetector().scan([quote])
    assert len(signals) == 1
    s = signals[0]
    assert s.context["kind"] == "buy_both"
    assert s.edge.ev > 0


def test_arbitrage_no_edge_when_prices_sum_to_one():
    quote = _mk_quote(yes_bid=0.50, yes_ask=0.51, no_bid=0.49, no_ask=0.50)
    signals = ArbitrageDetector().scan([quote])
    # ask_sum = 1.01 → no buy arb; bid_sum = 0.99 → no sell arb
    assert signals == []


def test_arbitrage_detects_sell_both():
    quote = _mk_quote(yes_bid=0.55, yes_ask=0.56, no_bid=0.52, no_ask=0.53)
    # bid_sum = 1.07 → overpriced, profit 0.07
    signals = ArbitrageDetector().scan([quote])
    assert any(s.context["kind"] == "sell_both" for s in signals)
