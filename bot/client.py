import os
from dotenv import load_dotenv
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Load environment variables
load_dotenv()

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

FUTURES_BASE_URL = os.getenv(
    "BINANCE_FUTURES_BASE_URL",
    "https://testnet.binancefuture.com"
)


def create_client():
    """
    Create and return Binance Futures Testnet client
    """

    if not API_KEY or not API_SECRET:
        raise ValueError("API keys not found in .env file")

    client = Client(API_KEY, API_SECRET, ping=False)

    # Override base URL to USD-M Futures Testnet
    client.FUTURES_URL = FUTURES_BASE_URL.rstrip("/") + "/fapi"

    return client


def test_connection():
    """
    Test authenticated connection to Binance Futures Testnet
    """

    try:
        client = create_client()

        # Authenticated request
        account_info = client.futures_account()

        print("\n[OK] Connected to Binance Futures Testnet Successfully")

        # Print small useful info
        print(f"Assets Found: {len(account_info.get('assets', []))}")

        return client

    except BinanceAPIException as e:
        print("\n[ERROR] Binance API Error")
        print(f"Code: {e.code}")
        print(f"Message: {e.message}")

    except Exception as e:
        print("\n[ERROR] Connection Failed")
        print(f"Error: {str(e)}")
