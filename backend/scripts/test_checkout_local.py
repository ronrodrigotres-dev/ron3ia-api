"""Quick local test: calls /create-checkout-session and prints the Stripe URL."""
import json
import sys

import requests

BASE_URL = "http://localhost:8000"


def main():
    payload = {
        "email": "test@example.com",
        "reportId": "rep_test_001",
        "amount": 9900,
        "currency": "clp",
    }

    print(f"POST {BASE_URL}/create-checkout-session")
    print("Payload:", json.dumps(payload, indent=2))

    try:
        response = requests.post(
            f"{BASE_URL}/create-checkout-session",
            json=payload,
            timeout=15,
        )
    except requests.ConnectionError:
        print(
            "\n[ERROR] Could not connect to the server. "
            "Make sure the backend is running:\n"
            "  uvicorn main:app --reload\n",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Status: {response.status_code}")
    data = response.json()
    print("Response:", json.dumps(data, indent=2))

    if "url" in data:
        print(f"\nCheckout URL:\n{data['url']}")
    else:
        print("\n[WARNING] No 'url' key in response.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
