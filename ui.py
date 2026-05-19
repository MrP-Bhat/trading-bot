import argparse

from bot.ui import run_ui


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run the Binance Futures Testnet Bot web UI"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8010, type=int)
    args = parser.parse_args()

    run_ui(host=args.host, port=args.port)
