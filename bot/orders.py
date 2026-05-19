import time
from decimal import Decimal, InvalidOperation

from binance.exceptions import BinanceAPIException
from bot.client import create_client
from bot.logging_config import logger
from bot.market_data import (
    get_available_futures_balance,
    get_min_notional,
    get_symbol_price,
    to_decimal
)


FINAL_ORDER_STATUSES = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}


def _decimal(value, default="0"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return Decimal(default)


def _fetch_order_trades(client, symbol, order_id):
    try:
        return client.futures_account_trades(
            symbol=symbol,
            orderId=order_id
        )
    except BinanceAPIException as e:
        logger.warning(
            f"Unable to fetch trades for order {order_id}: {e.message}"
        )
        return []


def _apply_trade_summary(order, trades):
    if not trades:
        return order

    executed_qty = sum(_decimal(trade.get("qty")) for trade in trades)
    quote_qty = sum(_decimal(trade.get("quoteQty")) for trade in trades)

    if executed_qty > 0:
        order["executedQty"] = format(executed_qty, "f")
        order["cumQuote"] = format(quote_qty, "f")
        order["avgPrice"] = format(quote_qty / executed_qty, "f")
        order["fills"] = trades

        if order.get("status") == "NEW":
            order["status"] = "FILLED"

    return order


def _wait_for_final_order_status(
    client,
    symbol,
    order_id,
    timeout_seconds=5,
    poll_interval_seconds=0.5
):
    deadline = time.monotonic() + timeout_seconds
    latest_order = None

    while time.monotonic() <= deadline:
        latest_order = client.futures_get_order(
            symbol=symbol,
            orderId=order_id
        )

        logger.info(f"Polled order status: {latest_order}")

        if latest_order.get("status") in FINAL_ORDER_STATUSES:
            return latest_order

        time.sleep(poll_interval_seconds)

    return latest_order


def _resolve_market_order_result(client, response):
    symbol = response.get("symbol")
    order_id = response.get("orderId")

    if not symbol or not order_id:
        return response

    final_order = response

    if response.get("status") not in FINAL_ORDER_STATUSES:
        final_order = _wait_for_final_order_status(
            client=client,
            symbol=symbol,
            order_id=order_id
        ) or response

    executed_qty = _decimal(final_order.get("executedQty"))
    avg_price = _decimal(final_order.get("avgPrice"))

    if final_order.get("status") != "FILLED" or executed_qty == 0 or avg_price == 0:
        trades = _fetch_order_trades(
            client=client,
            symbol=symbol,
            order_id=order_id
        )
        final_order = _apply_trade_summary(final_order, trades)

    return final_order


def _format_decimal(value):
    if value is None:
        return "N/A"

    return format(value, "f")


def _print_order_preview(client, symbol, side, order_type, quantity, price=None):
    current_price = get_symbol_price(symbol, client=client)
    available_balance = get_available_futures_balance(client=client)
    min_notional = get_min_notional(symbol, client=client)
    order_price = to_decimal(price) if price is not None else current_price
    estimated_order_value = to_decimal(quantity) * order_price

    logger.info(
        f"Order preview | Symbol={symbol}, Side={side}, Type={order_type}, "
        f"Quantity={quantity}, CurrentPrice={current_price}, "
        f"EstimatedOrderValue={estimated_order_value}, "
        f"AvailableBalance={available_balance}, MinNotional={min_notional}"
    )

    print("\n===== ORDER REQUEST SUMMARY =====")
    print(f"Symbol                : {symbol}")
    print(f"Side                  : {side}")
    print(f"Order Type            : {order_type}")
    print(f"Quantity              : {quantity}")
    print(f"Current Symbol Price  : {_format_decimal(current_price)}")
    print(f"Estimated Order Value : {_format_decimal(estimated_order_value)} USDT")
    print(f"Available Balance     : {_format_decimal(available_balance)} USDT")
    print(f"Minimum Notional      : {_format_decimal(min_notional)} USDT")

    if estimated_order_value > available_balance:
        print("\n[WARNING] Estimated order value exceeds available balance.")

    if min_notional is not None and estimated_order_value < min_notional:
        print("\n[WARNING] Estimated order value is below minimum notional.")

    return {
        "current_price": current_price,
        "estimated_order_value": estimated_order_value,
        "available_balance": available_balance,
        "min_notional": min_notional
    }


def place_market_order(symbol, side, quantity, show_preview=True):
    """
    Place a MARKET order on Binance Futures Testnet
    """
    
    try:
        logger.info(
            f"Placing MARKET order | "
            f"Symbol={symbol}, Side={side}, Quantity={quantity}"
        )

        client = create_client()

        if show_preview:
            _print_order_preview(
                client=client,
                symbol=symbol,
                side=side,
                order_type="MARKET",
                quantity=quantity
            )

        response = client.futures_create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=quantity,
            newOrderRespType="RESULT"
        )

        logger.info(f"MARKET order response: {response}")

        response = _resolve_market_order_result(
            client=client,
            response=response
        )

        logger.info(f"Resolved MARKET order response: {response}")

        print("\n[OK] MARKET Order Placed Successfully")

        print("\n===== ORDER RESPONSE =====")
        print(f"Symbol          : {response.get('symbol')}")
        print(f"Order ID        : {response.get('orderId')}")
        print(f"Side            : {response.get('side')}")
        print(f"Status          : {response.get('status')}")
        print(f"Executed Qty    : {response.get('executedQty')}")
        print(f"Average Price   : {response.get('avgPrice')}")
        print(f"Cum Quote       : {response.get('cumQuote')}")

        print("\n===== RAW RESPONSE =====")
        print(response)

        return response

    except BinanceAPIException as e:
        logger.error(f"Binance API Error: {e}")

        print("\n[ERROR] Binance API Error")
        print(f"Code    : {e.code}")
        print(f"Message : {e.message}")

    except Exception as e:
        logger.error(f"Unexpected Error: {str(e)}")

        print("\n[ERROR] Failed to Place MARKET Order")
        print(f"Error : {str(e)}")


def place_limit_order(symbol, side, quantity, price, show_preview=True):
    """
    Place a LIMIT order on Binance Futures Testnet
    """

    try:
        logger.info(
            f"Placing LIMIT order | "
            f"Symbol={symbol}, Side={side}, "
            f"Quantity={quantity}, Price={price}"
        )

        client = create_client()

        if show_preview:
            _print_order_preview(
                client=client,
                symbol=symbol,
                side=side,
                order_type="LIMIT",
                quantity=quantity,
                price=price
            )

        response = client.futures_create_order(
            symbol=symbol,
            side=side,
            type="LIMIT",
            quantity=quantity,
            price=price,
            timeInForce="GTC"
        )

        logger.info(f"LIMIT order response: {response}")

        print("\n[OK] LIMIT Order Placed Successfully")

        print("\n===== ORDER RESPONSE =====")
        print(f"Symbol          : {response.get('symbol')}")
        print(f"Order ID        : {response.get('orderId')}")
        print(f"Side            : {response.get('side')}")
        print(f"Status          : {response.get('status')}")
        print(f"Price           : {response.get('price')}")
        print(f"Original Qty    : {response.get('origQty')}")

        print("\n===== RAW RESPONSE =====")
        print(response)

        return response

    except BinanceAPIException as e:
        logger.error(f"Binance API Error: {e}")

        print("\n[ERROR] Binance API Error")
        print(f"Code    : {e.code}")
        print(f"Message : {e.message}")

    except Exception as e:
        logger.error(f"Unexpected Error: {str(e)}")

        print("\n[ERROR] Failed to Place LIMIT Order")
        print(f"Error : {str(e)}")


def place_stop_limit_order(symbol, side, quantity, price, stop_price, show_preview=True):
    """
    Place a STOP_LIMIT order on Binance Futures Testnet.
    Binance Futures uses order type STOP for stop-limit orders.
    """

    try:
        logger.info(
            f"Placing STOP_LIMIT order | "
            f"Symbol={symbol}, Side={side}, Quantity={quantity}, "
            f"Price={price}, StopPrice={stop_price}"
        )

        client = create_client()

        if show_preview:
            _print_order_preview(
                client=client,
                symbol=symbol,
                side=side,
                order_type="STOP_LIMIT",
                quantity=quantity,
                price=price
            )

        response = client.futures_create_order(
            symbol=symbol,
            side=side,
            type="STOP",
            quantity=quantity,
            price=price,
            stopPrice=stop_price,
            timeInForce="GTC"
        )

        logger.info(f"STOP_LIMIT order response: {response}")

        print("\n[OK] STOP_LIMIT Order Placed Successfully")

        print("\n===== ORDER RESPONSE =====")
        print(f"Symbol          : {response.get('symbol')}")
        print(f"Order ID        : {response.get('orderId') or 'N/A'}")
        print(f"Algo ID         : {response.get('algoId') or 'N/A'}")
        print(f"Side            : {response.get('side')}")
        print(f"Status          : {response.get('status') or response.get('algoStatus')}")
        print(f"Price           : {response.get('price')}")
        print(f"Stop Price      : {response.get('stopPrice') or response.get('triggerPrice')}")
        print(f"Original Qty    : {response.get('origQty') or response.get('quantity')}")

        print("\n===== RAW RESPONSE =====")
        print(response)

        return response

    except BinanceAPIException as e:
        logger.error(f"Binance API Error: {e}")

        print("\n[ERROR] Binance API Error")
        print(f"Code    : {e.code}")
        print(f"Message : {e.message}")

    except Exception as e:
        logger.error(f"Unexpected Error: {str(e)}")

        print("\n[ERROR] Failed to Place STOP_LIMIT Order")
        print(f"Error : {str(e)}")


def cancel_all_orders(symbol):

    try:
        client = create_client()

        response = client.futures_cancel_all_open_orders(
            symbol=symbol
        )

        algo_response = client.futures_cancel_all_algo_open_orders(
            symbol=symbol
        )

        logger.info(
            f"Cancelled all open orders for {symbol}. "
            f"OrderResponse={response}, AlgoResponse={algo_response}"
        )

        print("\n[OK] All Open Orders Cancelled")
        print(response)
        print(algo_response)

    except BinanceAPIException as e:
        logger.error(f"Binance API Error: {e}")

        print("\n[ERROR] Binance API Error")
        print(f"Code    : {e.code}")
        print(f"Message : {e.message}")

    except Exception as e:
        logger.error(f"Unexpected Error: {str(e)}")

        print("\n[ERROR] Failed to Cancel Orders")
        print(f"Error : {str(e)}")
