from decimal import Decimal, InvalidOperation

from bot.client import create_client


def _get_client(client=None):
    return client or create_client()


def to_decimal(value, default="0"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return Decimal(default)


def get_symbol_price(symbol, client=None):
    client = _get_client(client)

    ticker = client.futures_symbol_ticker(symbol=symbol)

    return to_decimal(ticker["price"])


def get_available_futures_balance(asset="USDT", client=None):
    client = _get_client(client)

    balances = client.futures_account_balance()

    for balance in balances:
        if balance.get("asset") == asset:
            return to_decimal(balance.get("availableBalance"))

    return Decimal("0")


def get_min_notional(symbol, client=None):
    client = _get_client(client)

    exchange_info = client.futures_exchange_info()

    for symbol_info in exchange_info.get("symbols", []):
        if symbol_info.get("symbol") != symbol:
            continue

        for order_filter in symbol_info.get("filters", []):
            filter_type = order_filter.get("filterType")

            if filter_type == "MIN_NOTIONAL":
                return to_decimal(order_filter.get("notional"))

            if filter_type == "NOTIONAL":
                return to_decimal(order_filter.get("minNotional"))

    return None
