from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Optional

AMAZON_URL = "https://www.amazon.com/"

def search_product_price(product_keyword: str = "laptop", headless: bool = True) -> str:
    """
    Navigate to Amazon, search for a product, and return the first result's name and price.
    Handles slow pages, missing elements, and provides a clear final output message.
    """

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            page = browser.new_page()
            page.set_default_timeout(60000)

            print("Opening Amazon...")
            page.goto(AMAZON_URL, timeout=60000)

            # Accept cookies if prompted
            try:
                page.locator("input#sp-cc-accept").click(timeout=3000)
            except Exception:
                pass  # ignore if no cookie popup

            # Type the product name into the search bar
            page.fill("input#twotabsearchtextbox", product_keyword)
            page.click("input#nav-search-submit-button")

            # Wait for search results to appear
            page.wait_for_selector("div.s-main-slot div[data-component-type='s-search-result']", timeout=60000)

            # Select the first product in the list
            first_product = page.query_selector("div.s-main-slot div[data-component-type='s-search-result']")
            if not first_product:
                return f"No search results found for '{product_keyword}'."

            # Extract product title
            title_el = (
                first_product.query_selector("h2 a span") or
                first_product.query_selector("h2 span") or
                first_product.query_selector("span.a-text-normal")
            )

            # Extract price elements
            price_whole_el = first_product.query_selector("span.a-price-whole")
            price_fraction_el = first_product.query_selector("span.a-price-fraction")

            name = title_el.inner_text().strip() if title_el else "Unknown Product"

            # Build and clean price safely
            if price_whole_el:
                price_whole = price_whole_el.inner_text().strip().replace(",", "")
                price_fraction = price_fraction_el.inner_text().strip() if price_fraction_el else "00"

                # Join whole and fraction without any newline issues
                price = f"{price_whole}.{price_fraction}"
                price = price.replace("\n", "").replace(" ", "")
            else:
                price = "Price not available"
            # Final clean formatting
            price = price.replace("..", ".").replace("$", "").strip()

            msg = f"Success! Found '{name}' for ${price}"
            browser.close()
            return msg

    except PlaywrightTimeoutError:
        return "Timeout: The page took too long to load or respond. Try again."
    except Exception as e:
        return f"Error: Unexpected failure occurred - {e}"
