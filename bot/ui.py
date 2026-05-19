import contextlib
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bot.client import create_client
from bot.market_data import (
    get_available_futures_balance,
    get_min_notional,
    get_symbol_price,
    to_decimal
)
from bot.orders import (
    place_limit_order,
    place_market_order,
    place_stop_limit_order
)
from bot.validators import (
    validate_order_type,
    validate_price,
    validate_quantity,
    validate_side,
    validate_symbol
)


HOST = "127.0.0.1"
PORT = 8010


def _format_decimal(value):
    if value is None:
        return "N/A"

    return format(value, "f")


def _json_response(handler, status_code, payload):
    body = json.dumps(payload, default=str).encode("utf-8")

    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler):
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw_body = handler.rfile.read(content_length)

    if not raw_body:
        return {}

    return json.loads(raw_body.decode("utf-8"))


def _get_market_info(symbol):
    client = create_client()
    current_price = get_symbol_price(symbol, client=client)
    available_balance = get_available_futures_balance(client=client)
    min_notional = get_min_notional(symbol, client=client)

    return {
        "symbol": symbol,
        "current_price": current_price,
        "available_balance": available_balance,
        "min_notional": min_notional
    }


def _build_order_estimate(order_type, quantity, price, market_info):
    order_price = to_decimal(price) if order_type != "MARKET" else market_info["current_price"]
    estimated_order_value = to_decimal(quantity) * order_price

    warnings = []

    if estimated_order_value > market_info["available_balance"]:
        warnings.append("Estimated order value exceeds available balance.")

    if (
        market_info["min_notional"] is not None
        and estimated_order_value < market_info["min_notional"]
    ):
        warnings.append("Estimated order value is below minimum notional.")

    return {
        "order_price": order_price,
        "estimated_order_value": estimated_order_value,
        "warnings": warnings
    }


def _capture_order_call(order_type, symbol, side, quantity, price, stop_price):
    output = io.StringIO()

    with contextlib.redirect_stdout(output):
        if order_type == "MARKET":
            response = place_market_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                show_preview=False
            )
        elif order_type == "LIMIT":
            response = place_limit_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                show_preview=False
            )
        else:
            response = place_stop_limit_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                stop_price=stop_price,
                show_preview=False
            )

    return response, output.getvalue()


class TradingBotUIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/", "/index.html"}:
            self.send_error(404)
            return

        body = HTML_PAGE.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            if self.path == "/api/market-info":
                self._handle_market_info()
                return

            if self.path == "/api/order":
                self._handle_order()
                return

            if self.path == "/api/cancel":
                self._handle_cancel()
                return
            self.send_error(404)
        except Exception as error:
            _json_response(self, 400, {"ok": False, "error": str(error)})

    def _handle_market_info(self):
        payload = _read_json(self)
        symbol = validate_symbol(payload.get("symbol"))
        market_info = _get_market_info(symbol)

        _json_response(self, 200, {
            "ok": True,
            "market": {
                "symbol": market_info["symbol"],
                "current_price": _format_decimal(market_info["current_price"]),
                "available_balance": _format_decimal(market_info["available_balance"]),
                "min_notional": _format_decimal(market_info["min_notional"])
            }
        })

    def _handle_order(self):
        payload = _read_json(self)
        symbol = validate_symbol(payload.get("symbol"))
        side = validate_side(payload.get("side"))
        order_type = validate_order_type(payload.get("type"))
        quantity = validate_quantity(payload.get("quantity"))
        price = None
        stop_price = None

        if order_type in {"LIMIT", "STOP_LIMIT"}:
            if payload.get("price") in {None, ""}:
                raise ValueError(f"{order_type} order requires price")
            price = validate_price(payload.get("price"))

        if order_type == "STOP_LIMIT":
            if payload.get("stop_price") in {None, ""}:
                raise ValueError("STOP_LIMIT order requires stop price")
            stop_price = validate_price(payload.get("stop_price"))

        market_info = _get_market_info(symbol)
        estimate = _build_order_estimate(order_type, quantity, price, market_info)

        if not payload.get("confirmed"):
            _json_response(self, 200, {
                "ok": True,
                "needs_confirmation": True,
                "market": {
                    "symbol": symbol,
                    "current_price": _format_decimal(market_info["current_price"]),
                    "available_balance": _format_decimal(market_info["available_balance"]),
                    "min_notional": _format_decimal(market_info["min_notional"])
                },
                "estimate": {
                    "order_price": _format_decimal(estimate["order_price"]),
                    "estimated_order_value": _format_decimal(estimate["estimated_order_value"]),
                    "warnings": estimate["warnings"]
                }
            })
            return

        response, output = _capture_order_call(
            order_type=order_type,
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            stop_price=stop_price
        )

        _json_response(self, 200, {
            "ok": response is not None,
            "response": response,
            "console_output": output
        })

    def _handle_cancel(self):
        payload = _read_json(self)
        symbol = validate_symbol(payload.get("symbol"))
        order_id = payload.get("order_id")
        algo_id = payload.get("algo_id")

        client = create_client()

        if algo_id:
            if hasattr(client, "futures_cancel_algo_order"):
                response = client.futures_cancel_algo_order(
                    symbol=symbol,
                    algoId=algo_id
                )
            else:
                response = client.futures_cancel_all_algo_open_orders(
                    symbol=symbol
                )
        else:
            response = client.futures_cancel_order(
                symbol=symbol,
                orderId=order_id
            )

        _json_response(self, 200, {
            "ok": True,
            "response": response
        })

    def log_message(self, format, *args):
        return


HTML_PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Binance Futures Testnet Bot</title>
  <style>
    :root {
      --ink: #101010;
      --paper: #fff8e8;
      --panel: #ffffff;
      --yellow: #ffe45c;
      --pink: #ff6bb5;
      --cyan: #48dbe8;
      --green: #7df37d;
      --red: #ff5a5f;
      --shadow: 8px 8px 0 var(--ink);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        linear-gradient(90deg, rgba(16, 16, 16, 0.08) 1px, transparent 1px),
        linear-gradient(rgba(16, 16, 16, 0.08) 1px, transparent 1px),
        var(--paper);
      background-size: 28px 28px;
      font-family: Arial, Helvetica, sans-serif;
    }

    button,
    input,
    select {
      font: inherit;
    }

    .shell {
      width: min(1180px, calc(100% - 32px));
      margin: 24px auto;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 14px 18px;
      border: 3px solid var(--ink);
      background: var(--yellow);
      box-shadow: var(--shadow);
      margin-bottom: 24px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: 0;
      font-size: clamp(18px, 3vw, 30px);
    }

    .mark {
      display: grid;
      place-items: center;
      width: 44px;
      height: 44px;
      border: 3px solid var(--ink);
      background: var(--cyan);
      box-shadow: 4px 4px 0 var(--ink);
      font-weight: 900;
    }

    .badge {
      border: 3px solid var(--ink);
      background: var(--panel);
      padding: 8px 12px;
      box-shadow: 4px 4px 0 var(--ink);
      font-weight: 800;
      white-space: nowrap;
    }

    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(320px, 420px);
      gap: 24px;
      align-items: start;
    }

    .panel {
      border: 3px solid var(--ink);
      background: var(--panel);
      box-shadow: var(--shadow);
      padding: 18px;
    }

    .panel h2 {
      margin: 0 0 16px;
      font-size: 22px;
      text-transform: uppercase;
    }

    .panel h3 {
      margin: 0;
      font-size: 18px;
      text-transform: uppercase;
    }

    .form-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    label {
      display: grid;
      gap: 8px;
      font-weight: 800;
      text-transform: uppercase;
      font-size: 12px;
      letter-spacing: 0.04em;
    }

    input,
    select {
      width: 100%;
      min-height: 48px;
      border: 3px solid var(--ink);
      background: #fff;
      padding: 10px 12px;
      box-shadow: 4px 4px 0 var(--ink);
      outline: none;
    }

    input:focus,
    select:focus {
      background: var(--cyan);
    }

    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 18px;
    }

    .btn {
      min-height: 48px;
      border: 3px solid var(--ink);
      padding: 10px 16px;
      font-weight: 900;
      text-transform: uppercase;
      color: var(--ink);
      background: var(--green);
      box-shadow: 5px 5px 0 var(--ink);
      cursor: pointer;
    }

    .btn.secondary {
      background: var(--cyan);
    }

    .btn.danger {
      background: var(--red);
    }

    .btn:active {
      transform: translate(3px, 3px);
      box-shadow: 2px 2px 0 var(--ink);
    }

    .stats {
      display: grid;
      gap: 12px;
    }

    .stat {
      border: 3px solid var(--ink);
      padding: 12px;
      background: var(--yellow);
      box-shadow: 4px 4px 0 var(--ink);
    }

    .stat:nth-child(2) {
      background: var(--cyan);
    }

    .stat:nth-child(3) {
      background: var(--pink);
    }

    .stat span {
      display: block;
      font-size: 12px;
      font-weight: 900;
      text-transform: uppercase;
      margin-bottom: 6px;
    }

    .stat strong {
      display: block;
      overflow-wrap: anywhere;
      font-size: 22px;
    }

    .chart {
      height: 92px;
      border: 3px solid var(--ink);
      background: #fff;
      box-shadow: 4px 4px 0 var(--ink);
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 6px;
      align-items: end;
      padding: 8px;
      margin-bottom: 16px;
    }

    .bar {
      border: 2px solid var(--ink);
      background: var(--green);
    }

    .bar:nth-child(3n) {
      background: var(--pink);
    }

    .bar:nth-child(4n) {
      background: var(--cyan);
    }

    .notice,
    .result-panel,
    .estimate-panel {
      margin-top: 18px;
      border: 3px solid var(--ink);
      background: #fff;
      box-shadow: 5px 5px 0 var(--ink);
      padding: 14px;
    }

    .notice.warning {
      background: var(--yellow);
    }

    .notice.error {
      background: var(--red);
    }

    .estimate-panel {
      background: var(--panel);
    }

    .estimate-panel.warning {
      background: var(--yellow);
    }

    .estimate-label {
      font-size: 12px;
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .estimate-value {
      font-size: 28px;
      font-weight: 900;
      margin: 6px 0 4px;
    }

    .estimate-sub {
      font-size: 13px;
      font-weight: 700;
    }

    .estimate-warnings {
      margin-top: 10px;
      display: grid;
      gap: 4px;
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }

    .result-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }

    .result-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    .result-item span {
      display: block;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 800;
      opacity: 0.8;
    }

    .result-item strong {
      display: block;
      font-size: 18px;
      font-weight: 900;
      overflow-wrap: anywhere;
    }

    .status-chip {
      border: 3px solid var(--ink);
      padding: 6px 10px;
      font-weight: 900;
      text-transform: uppercase;
      box-shadow: 3px 3px 0 var(--ink);
      background: var(--yellow);
    }

    .status-filled {
      background: var(--green);
    }

    .status-pending {
      background: var(--yellow);
    }

    .status-error {
      background: var(--red);
    }

    .status-detail {
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      margin-top: 6px;
    }

    .raw-json {
      margin-top: 14px;
      border-top: 2px solid var(--ink);
      padding-top: 12px;
    }

    .raw-json summary {
      cursor: pointer;
      font-weight: 900;
      text-transform: uppercase;
      font-size: 12px;
    }

    .raw-json pre {
      margin: 12px 0 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #fff;
      border: 2px solid var(--ink);
      padding: 10px;
    }

    .result-actions {
      margin-top: 14px;
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    .hidden {
      display: none;
    }

    @media (max-width: 860px) {
      .grid,
      .form-grid,
      .result-grid {
        grid-template-columns: 1fr;
      }

      .topbar {
        align-items: flex-start;
        flex-direction: column;
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand">
        <div class="mark">BT</div>
        <div>Futures Testnet Bot</div>
      </div>
      <div class="badge">Local UI / Testnet</div>
    </header>

    <section class="grid">
      <form class="panel" id="orderForm">
        <h2>Place Order</h2>

        <div class="form-grid">
          <label>
            Symbol
            <input id="symbol" name="symbol" value="SOLUSDT" placeholder="BTCUSDT" autocomplete="off">
          </label>

          <label>
            Side
            <select id="side" name="side">
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
            </select>
          </label>

          <label>
            Type
            <select id="type" name="type">
              <option value="MARKET">MARKET</option>
              <option value="LIMIT">LIMIT</option>
              <option value="STOP_LIMIT">STOP_LIMIT</option>
            </select>
          </label>

          <label>
            Quantity
            <input id="quantity" name="quantity" value="1" inputmode="decimal">
          </label>

          <label id="priceWrap">
            Price
            <input id="price" name="price" placeholder="Required for LIMIT / STOP_LIMIT" inputmode="decimal">
          </label>

          <label id="stopPriceWrap">
            Stop Price
            <input id="stopPrice" name="stop_price" placeholder="Required for STOP_LIMIT" inputmode="decimal">
          </label>
        </div>

        <div class="actions">
          <button class="btn secondary" type="button" id="loadMarket">Refresh Market</button>
          <button class="btn" type="button" id="estimateOrder">Estimate</button>
          <button class="btn danger" type="submit" id="executeOrder" disabled>Execute</button>
        </div>

        <div id="message" class="notice hidden"></div>
        <section id="estimatePanel" class="estimate-panel hidden">
          <div class="estimate-label">Estimated Order Value</div>
          <div class="estimate-value" id="estimateValue">--</div>
          <div class="estimate-sub" id="estimateDetails">Order Price: --</div>
          <div class="estimate-warnings" id="estimateWarnings"></div>
        </section>

        <section id="resultPanel" class="result-panel hidden">
          <div class="result-header">
            <h3>Order Result</h3>
            <div>
              <span id="statusChip" class="status-chip status-pending">NEW</span>
              <div id="statusDetail" class="status-detail">Pending in Order Book</div>
            </div>
          </div>

          <div class="result-grid">
            <div class="result-item"><span>Status</span><strong id="resultStatus">--</strong></div>
            <div class="result-item"><span>Symbol</span><strong id="resultSymbol">--</strong></div>
            <div class="result-item"><span>Order Type</span><strong id="resultType">--</strong></div>
            <div class="result-item"><span>Side</span><strong id="resultSide">--</strong></div>
            <div class="result-item"><span>Executed Quantity</span><strong id="resultQty">--</strong></div>
            <div class="result-item"><span>Average Price</span><strong id="resultAvg">--</strong></div>
            <div class="result-item"><span>Total Value / Cum Quote</span><strong id="resultTotal">--</strong></div>
            <div class="result-item" id="resultLimitWrap"><span>Limit Price</span><strong id="resultLimit">--</strong></div>
            <div class="result-item" id="resultStopWrap"><span>Stop Price</span><strong id="resultStop">--</strong></div>
          </div>

          <div class="result-actions">
            <button class="btn danger hidden" type="button" id="cancelOrder">Cancel Order</button>
          </div>

          <details class="raw-json">
            <summary>Show Raw JSON</summary>
            <pre id="rawJson">--</pre>
          </details>
        </section>
      </form>

      <aside class="panel">
        <h2>Market Snapshot</h2>
        <div class="chart" aria-hidden="true">
          <div class="bar" style="height: 42%"></div>
          <div class="bar" style="height: 68%"></div>
          <div class="bar" style="height: 55%"></div>
          <div class="bar" style="height: 82%"></div>
          <div class="bar" style="height: 44%"></div>
          <div class="bar" style="height: 74%"></div>
          <div class="bar" style="height: 61%"></div>
          <div class="bar" style="height: 90%"></div>
          <div class="bar" style="height: 49%"></div>
          <div class="bar" style="height: 70%"></div>
          <div class="bar" style="height: 58%"></div>
          <div class="bar" style="height: 78%"></div>
        </div>
        <div class="stats">
          <div class="stat"><span>Symbol</span><strong id="marketSymbol">--</strong></div>
          <div class="stat"><span>Current Price</span><strong id="currentPrice">--</strong></div>
          <div class="stat"><span>Available Balance</span><strong id="availableBalance">--</strong></div>
          <div class="stat"><span>Minimum Notional</span><strong id="minNotional">--</strong></div>
        </div>
      </aside>
    </section>
  </main>

  <script>
    const form = document.querySelector("#orderForm");
    const message = document.querySelector("#message");
    const estimatePanel = document.querySelector("#estimatePanel");
    const estimateValue = document.querySelector("#estimateValue");
    const estimateDetails = document.querySelector("#estimateDetails");
    const estimateWarnings = document.querySelector("#estimateWarnings");
    const resultPanel = document.querySelector("#resultPanel");
    const statusChip = document.querySelector("#statusChip");
    const statusDetail = document.querySelector("#statusDetail");
    const cancelButton = document.querySelector("#cancelOrder");
    const typeInput = document.querySelector("#type");
    const symbolInput = document.querySelector("#symbol");
    const executeButton = document.querySelector("#executeOrder");
    let lastEstimate = null;
    let marketRefreshTimer = null;
    let lastOrderPayload = null;
    let lastOrderResponse = null;

    function orderPayload(confirmed = false) {
      return {
        symbol: document.querySelector("#symbol").value.trim().toUpperCase(),
        side: document.querySelector("#side").value,
        type: document.querySelector("#type").value,
        quantity: document.querySelector("#quantity").value,
        price: document.querySelector("#price").value,
        stop_price: document.querySelector("#stopPrice").value,
        confirmed
      };
    }

    function showMessage(text, mode = "") {
      message.textContent = text;
      message.className = `notice ${mode}`.trim();
      message.classList.remove("hidden");
    }

    function clearMessage() {
      message.classList.add("hidden");
    }

    function updateTypeFields() {
      const type = typeInput.value;
      document.querySelector("#priceWrap").classList.toggle("hidden", type === "MARKET");
      document.querySelector("#stopPriceWrap").classList.toggle("hidden", type !== "STOP_LIMIT");
      executeButton.disabled = true;
      lastEstimate = null;
    }

    function parseNumber(value) {
      const parsed = Number.parseFloat(value);
      return Number.isFinite(parsed) ? parsed : null;
    }

    function formatValue(value, suffix = "") {
      if (value === null || value === undefined || value === "") return "--";
      return `${value}${suffix}`.trim();
    }

    async function postJson(path, payload) {
      const response = await fetch(path, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      return response.json();
    }

    function renderMarket(market) {
      document.querySelector("#marketSymbol").textContent = market.symbol;
      document.querySelector("#currentPrice").textContent = `${market.current_price} USDT`;
      document.querySelector("#availableBalance").textContent = `${market.available_balance} USDT`;
      document.querySelector("#minNotional").textContent = `${market.min_notional} USDT`;
    }

    async function refreshMarket(symbol, showFeedback = false) {
      if (!symbol) return;
      try {
        const data = await postJson("/api/market-info", {symbol});
        if (!data.ok) throw new Error(data.error);
        renderMarket(data.market);
        if (showFeedback) {
          showMessage("Market info refreshed.", "");
        } else {
          clearMessage();
        }
      } catch (error) {
        showMessage(error.message, "error");
      }
    }

    function updateStatusChip(status, orderType) {
      const normalized = (status || "UNKNOWN").toUpperCase();
      let chipClass = "status-pending";
      let label = "Pending";

      if (normalized === "FILLED") {
        chipClass = "status-filled";
        label = "Filled";
      } else if (["REJECTED", "CANCELED", "EXPIRED", "ERROR"].includes(normalized)) {
        chipClass = "status-error";
        label = normalized === "REJECTED" ? "Rejected" : "Cancelled";
      } else if (normalized === "PARTIALLY_FILLED") {
        label = "Partially Filled";
      }

      statusChip.className = `status-chip ${chipClass}`.trim();
      statusChip.textContent = normalized;

      if (["NEW", "PENDING_NEW", "PENDING", "TRIGGER_PENDING", "WAITING"].includes(normalized)) {
        statusDetail.textContent = orderType === "STOP_LIMIT"
          ? "Waiting for Trigger"
          : "Pending in Order Book";
      } else {
        statusDetail.textContent = "";
      }

      return label;
    }

    function isPendingStatus(status) {
      const normalized = (status || "").toUpperCase();
      return ["NEW", "PENDING_NEW", "PENDING", "TRIGGER_PENDING", "WAITING"].includes(normalized);
    }

    function renderResult(orderResponse, payload) {
      const response = orderResponse || {};
      const orderType = payload.type || response.type || "UNKNOWN";
      const status = response.status || response.algoStatus || "UNKNOWN";
      let statusLabel = updateStatusChip(status, orderType);
      const pending = isPendingStatus(status);

      if (orderType === "STOP_LIMIT" && pending) {
        statusLabel = "Waiting for Trigger";
      }

      document.querySelector("#resultStatus").textContent = statusLabel;
      document.querySelector("#resultSymbol").textContent = response.symbol || payload.symbol;
      document.querySelector("#resultType").textContent = orderType;
      document.querySelector("#resultSide").textContent = response.side || payload.side;

      const executedQty = response.executedQty || response.executedQuantity || response.origQty || "--";
      const averagePrice = response.avgPrice || response.averagePrice || "--";
      const totalValue = response.cumQuote || response.cumQuoteQty || response.cumQuoteValue || "--";

      const showExecutionDetails = orderType === "MARKET"
        ? true
        : orderType === "LIMIT"
          ? ["FILLED", "PARTIALLY_FILLED"].includes(status.toUpperCase())
          : orderType === "STOP_LIMIT"
            ? ["FILLED", "PARTIALLY_FILLED"].includes(status.toUpperCase())
            : false;

      document.querySelector("#resultQty").textContent = showExecutionDetails ? executedQty : "--";
      document.querySelector("#resultAvg").textContent = showExecutionDetails ? averagePrice : "--";
      document.querySelector("#resultTotal").textContent = showExecutionDetails ? totalValue : "--";

      const limitWrap = document.querySelector("#resultLimitWrap");
      const stopWrap = document.querySelector("#resultStopWrap");
      const limitValue = response.price || payload.price || "--";
      const stopValue = response.stopPrice || response.triggerPrice || payload.stop_price || "--";

      limitWrap.classList.toggle("hidden", orderType === "MARKET");
      stopWrap.classList.toggle("hidden", orderType !== "STOP_LIMIT");

      document.querySelector("#resultLimit").textContent = limitValue;
      document.querySelector("#resultStop").textContent = stopValue;

      document.querySelector("#rawJson").textContent = JSON.stringify(response, null, 2);
      resultPanel.classList.remove("hidden");

      const canCancelLimit = orderType === "LIMIT" && pending;
      const canCancelStop = orderType === "STOP_LIMIT" && pending;
      cancelButton.classList.toggle("hidden", !(canCancelLimit || canCancelStop));
    }

    document.querySelector("#loadMarket").addEventListener("click", async () => {
      await refreshMarket(symbolInput.value.trim(), true);
    });

    document.querySelector("#estimateOrder").addEventListener("click", async () => {
      try {
        const data = await postJson("/api/order", orderPayload(false));
        if (!data.ok) throw new Error(data.error);
        lastEstimate = data;
        renderMarket(data.market);
        executeButton.disabled = false;

        const warnings = [...data.estimate.warnings];
        const estimatedValue = parseNumber(data.estimate.estimated_order_value);
        const availableBalance = parseNumber(data.market.available_balance);

        if (estimatedValue !== null && availableBalance !== null && estimatedValue >= availableBalance * 0.75) {
          warnings.push("Estimated exposure is very large relative to available balance.");
        }

        estimatePanel.classList.toggle("warning", warnings.length > 0);
        estimatePanel.classList.remove("hidden");
        estimateValue.textContent = formatValue(data.estimate.estimated_order_value, " USDT");
        estimateDetails.textContent = `Order Price: ${data.estimate.order_price} USDT`;
        estimateWarnings.textContent = warnings.join("\n");
        clearMessage();
      } catch (error) {
        executeButton.disabled = true;
        showMessage(error.message, "error");
      }
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!lastEstimate) {
        showMessage("Estimate the order before execution.", "error");
        return;
      }

      const accepted = window.confirm("Execute this Testnet order?");
      if (!accepted) return;

      try {
        const payload = orderPayload(true);
        const data = await postJson("/api/order", payload);
        if (!data.ok) throw new Error(data.console_output || "Order failed.");
        showMessage("Order submitted.", "");
        lastOrderPayload = payload;
        lastOrderResponse = data.response;
        renderResult(data.response, payload);
      } catch (error) {
        showMessage(error.message, "error");
      }
    });

    cancelButton.addEventListener("click", async () => {
      if (!lastOrderPayload || !lastOrderResponse) {
        showMessage("No cancellable order found.", "error");
        return;
      }

      const accepted = window.confirm("Cancel this order?");
      if (!accepted) return;

      try {
        const payload = {
          symbol: lastOrderPayload.symbol,
          order_id: lastOrderResponse.orderId,
          algo_id: lastOrderResponse.algoId
        };
        const data = await postJson("/api/cancel", payload);
        if (!data.ok) throw new Error(data.error || "Cancel failed.");
        lastOrderResponse = {
          ...lastOrderResponse,
          status: "CANCELED",
          algoStatus: "CANCELED"
        };
        showMessage("Order cancelled.", "");
        renderResult(lastOrderResponse, lastOrderPayload);
      } catch (error) {
        showMessage(error.message, "error");
      }
    });

    typeInput.addEventListener("change", updateTypeFields);
    symbolInput.addEventListener("input", (event) => {
      event.target.value = event.target.value.toUpperCase();
      if (marketRefreshTimer) {
        window.clearTimeout(marketRefreshTimer);
      }
      marketRefreshTimer = window.setTimeout(() => {
        refreshMarket(symbolInput.value.trim(), false);
      }, 450);
    });

    updateTypeFields();
    refreshMarket(symbolInput.value.trim(), false);
  </script>
</body>
</html>"""


def run_ui(host=HOST, port=PORT):
    server = ThreadingHTTPServer((host, port), TradingBotUIHandler)
    print(f"UI running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()
