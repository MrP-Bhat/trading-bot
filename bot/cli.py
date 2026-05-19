import argparse
import sys

from bot.client import create_client
from bot.logging_config import logger
from bot.market_data import (
    get_available_futures_balance,
    get_min_notional,
    get_symbol_price,
    to_decimal
)
from bot.orders import (
    place_market_order,
    place_limit_order,
    place_stop_limit_order
)

from bot.validators import (
    validate_symbol,
    validate_side,
    validate_order_type,
    validate_quantity,
    validate_price
)


def _format_decimal(value):
    if value is None:
        return "N/A"

    return format(value, "f")


def _show_market_info(symbol, client):
    current_price = get_symbol_price(symbol, client=client)
    available_balance = get_available_futures_balance(client=client)
    min_notional = get_min_notional(symbol, client=client)

    print("\n===== MARKET INFO =====")
    print(f"Symbol                : {symbol}")
    print(f"Current Symbol Price  : {_format_decimal(current_price)}")
    print(f"Available Balance     : {_format_decimal(available_balance)} USDT")
    print(f"Minimum Notional      : {_format_decimal(min_notional)} USDT")

    return {
        "current_price": current_price,
        "available_balance": available_balance,
        "min_notional": min_notional
    }


def _confirm_order():
    confirmation = input("\nConfirm order execution? (yes/no): ")
    return confirmation.strip().lower() in {"yes", "y"}


def _run_interactive_cli():
    print("\nBinance Futures Testnet Trading Bot")
    print("Enter order details below.\n")

    symbol = validate_symbol(
        _get_required_arg(input("Symbol (e.g., BTCUSDT): "), "--symbol")
    )

    client = create_client()
    market_info = _show_market_info(symbol, client)

    side = validate_side(
        _get_required_arg(input("\nSide (BUY/SELL): "), "--side")
    )
    order_type = validate_order_type(
        _get_required_arg(input("Order type (MARKET/LIMIT/STOP_LIMIT): "), "--type")
    )
    price = None
    stop_price = None

    if order_type in {"LIMIT", "STOP_LIMIT"}:
        price = validate_price(
            _get_required_arg(input("Price: "), "--price")
        )

    if order_type == "STOP_LIMIT":
        stop_price = validate_price(
            _get_required_arg(input("Stop price: "), "--stop-price")
        )

    quantity = validate_quantity(
        _get_required_arg(input("Quantity: "), "--quantity")
    )

    order_price = to_decimal(price) if price is not None else market_info["current_price"]
    estimated_order_value = to_decimal(quantity) * order_price

    print("\n===== ORDER ESTIMATE =====")
    print(f"Estimated Order Value : {_format_decimal(estimated_order_value)} USDT")
    print(f"Available Balance     : {_format_decimal(market_info['available_balance'])} USDT")

    if estimated_order_value > market_info["available_balance"]:
        print("\n[WARNING] Estimated order value exceeds available balance.")

    if (
        market_info["min_notional"] is not None
        and estimated_order_value < market_info["min_notional"]
    ):
        print("\n[WARNING] Estimated order value is below minimum notional.")

    logger.info(
        f"Interactive order estimate | Symbol={symbol}, Side={side}, "
        f"Type={order_type}, Quantity={quantity}, Price={price}, "
        f"StopPrice={stop_price}, "
        f"EstimatedOrderValue={estimated_order_value}, "
        f"AvailableBalance={market_info['available_balance']}, "
        f"MinNotional={market_info['min_notional']}"
    )

    if not _confirm_order():
        print("\n[OK] Order cancelled by user.")
        return

    if order_type == "MARKET":
        place_market_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            show_preview=False
        )

    elif order_type == "LIMIT":
        place_limit_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            show_preview=False
        )

    elif order_type == "STOP_LIMIT":
        place_stop_limit_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            show_preview=False
        )


def _get_required_arg(value, name):
    if value is None or str(value).strip() == "":
        raise ValueError(f"{name} is required")

    return value


def run_cli():

    parser = argparse.ArgumentParser(
        description="Binance Futures Testnet Trading Bot"
    )

    parser.add_argument(
        "--symbol",
        help="Trading pair symbol (e.g., BTCUSDT)"
    )

    parser.add_argument(
        "--side",
        help="BUY or SELL"
    )

    parser.add_argument(
        "--type",
        help="MARKET, LIMIT, or STOP_LIMIT"
    )

    parser.add_argument(
        "--quantity",
        help="Order quantity"
    )

    parser.add_argument(
        "--price",
        type=float,
        help="Price required for LIMIT and STOP_LIMIT orders"
    )

    parser.add_argument(
        "--stop-price",
        type=float,
        help="Stop trigger price required for STOP_LIMIT orders"
    )

    try:
        if len(sys.argv) == 1:
            _run_interactive_cli()
            return

        args = parser.parse_args()

        symbol = validate_symbol(_get_required_arg(args.symbol, "--symbol"))
        side = validate_side(_get_required_arg(args.side, "--side"))
        order_type = validate_order_type(_get_required_arg(args.type, "--type"))
        quantity = validate_quantity(_get_required_arg(args.quantity, "--quantity"))

        if order_type == "MARKET":

            place_market_order(
                symbol=symbol,
                side=side,
                quantity=quantity
            )

        elif order_type == "LIMIT":

            if args.price is None:
                raise ValueError(
                    "LIMIT order requires --price"
                )

            price = validate_price(args.price)

            place_limit_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price
            )

        elif order_type == "STOP_LIMIT":

            if args.price is None:
                raise ValueError(
                    "STOP_LIMIT order requires --price"
                )

            if args.stop_price is None:
                raise ValueError(
                    "STOP_LIMIT order requires --stop-price"
                )

            price = validate_price(args.price)
            stop_price = validate_price(args.stop_price)

            place_stop_limit_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                stop_price=stop_price
            )

    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        sys.exit(1)
