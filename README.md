Binance Futures Testnet Trading Bot
===================================

A small Python CLI application for placing MARKET, LIMIT, and STOP_LIMIT orders
on Binance USDT-M Futures Testnet.

Setup
-----

1. Create and activate a virtual environment.

   ```cmd
   python -m venv venv
   venv\Scripts\activate
   ```

2. Install dependencies.

   ```cmd
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root.

   ```env
   BINANCE_API_KEY=your_testnet_api_key
   BINANCE_API_SECRET=your_testnet_api_secret
   ```

4. The default Futures Testnet base URL is:

   ```text
   https://testnet.binancefuture.com
   ```

   To override it, set:

   ```env
   BINANCE_FUTURES_BASE_URL=https://testnet.binancefuture.com
   ```

Run
---

Neubrutalism web UI:

```cmd
python ui.py
```

Then open:

```text
http://127.0.0.1:8010
```

Interactive mode:

```cmd
python main.py
```

Example interactive LIMIT order:

```text
Binance Futures Testnet Trading Bot
Enter order details below.

Symbol (e.g., BTCUSDT): solusdt

===== MARKET INFO =====
Symbol                : SOLUSDT
Current Symbol Price  : 85.17
Available Balance     : 1187.42664458 USDT
Minimum Notional      : 5 USDT

Side (BUY/SELL): sell
Order type (MARKET/LIMIT/STOP_LIMIT): limit
Price: 120
Quantity: 1

===== ORDER ESTIMATE =====
Estimated Order Value : 120.0 USDT
Available Balance     : 1187.42664458 USDT

Confirm order execution? (yes/no): yes
```

Example interactive STOP_LIMIT order:

```text
Symbol (e.g., BTCUSDT): btcusdt

===== MARKET INFO =====
Symbol                : BTCUSDT
Current Symbol Price  : 50000
Available Balance     : 1000 USDT
Minimum Notional      : 100 USDT

Side (BUY/SELL): buy
Order type (MARKET/LIMIT/STOP_LIMIT): stop_limit
Price: 50000
Stop price: 50500
Quantity: 0.001

Confirm order execution? (yes/no): yes
```

Single-command MARKET order:

```cmd
python main.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
```

Single-command LIMIT order:

```cmd
python main.py --symbol BTCUSDT --side BUY --type LIMIT --quantity 0.001 --price 50000
```

Single-command STOP_LIMIT order:

```cmd
python main.py --symbol BTCUSDT --side BUY --type STOP_LIMIT --quantity 0.001 --price 50000 --stop-price 50500
```

Notes
-----

- This bot is intended for Binance Futures Testnet only.
- The CLI validates symbol, side, order type, quantity, price, and stop price.
- Before order execution, the bot displays current price, estimated order value,
  available USDT futures balance, and minimum notional information.
- The lightweight web UI uses Python's standard library HTTP server and reuses
  the same validators, market data helpers, and order functions.
- Logs are written to `logs/trading.log`.
