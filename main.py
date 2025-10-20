import argparse
import os
from dotenv import load_dotenv
from core.driver import search_product_price

def parse_args():
    """
    Parse command-line arguments for product search and headless mode.
    """
    ap = argparse.ArgumentParser(description="Run the core web automation task.")
    ap.add_argument(
        "--product",
        default="laptop",
        help="Product keyword to search on Amazon."
    )
    ap.add_argument(
        "--headless",
        default=None,
        help="true or false to override .env HEADLESS setting."
    )
    return ap.parse_args()

def get_headless_flag(arg_flag):
    """
    Determine whether to run Playwright in headless mode based on CLI or .env.
    """
    load_dotenv()
    env_val = os.getenv("HEADLESS", "true").lower()
    if arg_flag is not None:
        env_val = str(arg_flag).lower()
    return env_val in ("1", "true", "yes")

if __name__ == "__main__":
    args = parse_args()
    headless = get_headless_flag(args.headless)

    print(f"Starting search for '{args.product}' on Amazon...")
    result = search_product_price(product_keyword=args.product, headless=headless)
    print(result)
