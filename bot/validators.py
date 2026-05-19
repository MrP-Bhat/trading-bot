import math
import re


VALID_SIDES = ["BUY", "SELL"]
VALID_ORDER_TYPES = ["MARKET", "LIMIT", "STOP_LIMIT"]
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{5,20}$")


def validate_symbol(symbol):
    if not symbol or not isinstance(symbol, str):
        raise ValueError("Symbol must be a non-empty string")

    symbol = symbol.strip().upper()

    if not symbol:
        raise ValueError("Symbol must be a non-empty string")

    if not SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError("Symbol must contain only letters and numbers")

    return symbol


def validate_side(side):
    if not side or not isinstance(side, str):
        raise ValueError("Side must be BUY or SELL")

    side = side.upper()

    if side not in VALID_SIDES:
        raise ValueError(
            f"Invalid side. Allowed values: {VALID_SIDES}"
        )

    return side


def validate_order_type(order_type):
    if not order_type or not isinstance(order_type, str):
        raise ValueError("Order type must be MARKET, LIMIT, or STOP_LIMIT")

    order_type = order_type.upper()

    if order_type not in VALID_ORDER_TYPES:
        raise ValueError(
            f"Invalid order type. Allowed values: {VALID_ORDER_TYPES}"
        )

    return order_type


def validate_quantity(quantity):
    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        raise ValueError("Quantity must be a finite number greater than 0")

    if not math.isfinite(quantity) or quantity <= 0:
        raise ValueError("Quantity must be a finite number greater than 0")

    return quantity


def validate_price(price):
    try:
        price = float(price)
    except (TypeError, ValueError):
        raise ValueError("Price must be a finite number greater than 0")

    if not math.isfinite(price) or price <= 0:
        raise ValueError("Price must be a finite number greater than 0")

    return price
