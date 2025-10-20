from typing import List, Dict, Any, Callable
import asyncio, re, math
import inspect
import time
from matplotlib.pyplot import step
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from ai_mcp.browser_utils import extract_mcp_context_payload
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

SEARCH_INPUTS = [
    "input#twotabsearchtextbox",
    "input[name='field-keywords']",
]
SEARCH_SUBMITS = [
    "input#nav-search-submit-button",
    "input[type='submit'][value]",
    "input[type='submit']",
]


# ------------------------- Utility Helpers -------------------------
async def _wait_ready(page):
    """Ensure DOM is ready before interacting."""
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        pass


async def _click_with_fallbacks(page, selector: str):
    """Try main and fallback click selectors."""
    candidates = [selector] + [s for s in SEARCH_SUBMITS if s != selector and s]
    for sel in candidates:
        try:
            await page.wait_for_selector(sel, state="visible", timeout=10000)
            await page.click(sel)
            return True
        except Exception:
            continue

    # Fallback: press Enter in the search box
    for si in SEARCH_INPUTS:
        try:
            await page.wait_for_selector(si, state="visible", timeout=3000)
            await page.focus(si)
            await page.keyboard.press("Enter")
            return True
        except Exception:
            continue
    return False


async def _fill_with_fallbacks(page, selector: str, value: str):
    """Try main and fallback fill selectors."""
    candidates = [selector] + [s for s in SEARCH_INPUTS if s != selector and s]
    for sel in candidates:
        try:
            await page.wait_for_selector(sel, state="attached", timeout=8000)
            await asyncio.sleep(1)  # let Amazon's UI hydrate
            await page.wait_for_selector(sel, state="visible", timeout=8000)
            await page.fill(sel, value)
            return True
        except Exception:
            continue
    return False


async def call_llm_fn(llm_fn, goal, context):
    if llm_fn is None:
        return None
    result = llm_fn(goal, context) 
    if inspect.isawaitable(result):
        result = await result
    return result

# ------------------------- Price Parsing -------------------------

PRICE_RE = re.compile(r'(?P<op>above|over|under|below|less\s+than|more\s+than|at\s+least|>=|>|<=|<)?\s*\$?\s*(?P<val>\d+(?:\.\d{1,2})?)', re.I)
RANGE_RE = re.compile(r'\$?\s*(?P<lo>\d+(?:\.\d{1,2})?)\s*[-–to]+\s*\$?\s*(?P<hi>\d+(?:\.\d{1,2})?)', re.I)


def parse_price_filters(goal: str):
    """Return (min_price, max_price, cleaned_query)."""
    g = goal.strip()
    # Range like: 50-100 or $50 to $100
    m = RANGE_RE.search(g)
    if m:
        lo = float(m.group("lo"))
        hi = float(m.group("hi"))
        cleaned = RANGE_RE.sub("", g).strip()
        return lo, hi, cleaned

    # Single sided like: above $50, under 30
    m = PRICE_RE.search(g)
    if m:
        op = (m.group("op") or "").lower()
        val = float(m.group("val"))
        cleaned = PRICE_RE.sub("", g).strip()
        if op in ("above", "over", "more than", "at least", ">", ">="):
            return val, None, cleaned
        if op in ("under", "below", "less than", "<", "<="):
            return None, val, cleaned

    return None, None, g  # no constraint found

def build_amazon_search_url(goal: str):
    """Build Amazon URL with price filter when possible."""
    min_p, max_p, cleaned = parse_price_filters(goal)
    # remove generic verbs like 'cheapest' or 'find'
    query = cleaned
    for word in ("cheapest", "find", "show", "get", "buy"):
        query = re.sub(rf"\b{word}\b", "", query, flags=re.I)
    query = re.sub(r"\s+", " ", query).strip()
    if not query:
        query = "shirt"

    rh = ""
    # Amazon price filter uses cents in p_36
    # min only: p_36:{min_cents}-
    # max only: p_36:-{max_cents}
    # range:    p_36:{min_cents}-{max_cents}
    if min_p is not None or max_p is not None:
        lo = f"{int(round(min_p * 100))}" if min_p is not None else ""
        hi = f"{int(round(max_p * 100))}" if max_p is not None else ""
        if min_p is not None and max_p is not None:
            rh_val = f"{lo}-{hi}"
        elif min_p is not None:
            rh_val = f"{lo}-"
        else:
            rh_val = f"-{hi}"
        rh = f"&rh=p_36%3A{quote_plus(rh_val)}"

    # Sort ascending so the first valid item is the cheapest within the constraint
    return f"https://www.amazon.com/s?k={quote_plus(query)}{rh}&s=price-asc-rank", min_p, max_p

# ------------------------- Product Extraction -------------------------
async def extract_products(page, goal="cheapest hat", debug_html_path="debug_amazon_item.html"):
    """Open an Amazon search for the goal, wait for real results, then return [{title, link, price}, ...]."""
    try:
        print("Starting extraction...")

        # Anti-bot hints
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        await page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
        await page.set_viewport_size({"width": 1366, "height": 900})

        # Build proper search URL
        url, min_price, max_price = build_amazon_search_url(goal)
        print(f"Navigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)

        # CAPTCHA check
        html = await page.content()
        block_markers = ("captcha", "robot check", "enter the characters you see", "/errors/validateCaptcha")
        if any(b in html.lower() for b in block_markers):
            print("CAPTCHA detected.")
            await page.screenshot(path="debug_captcha.png", full_page=True)
            with open(debug_html_path, "w", encoding="utf-8") as f:
                f.write(html)
            return []

        # Close location/cookie popups
        for sel in ("input#sp-cc-accept", "button[name='glowDoneButton']", "input[name='glowDoneButton']"):
            try:
                await page.locator(sel).click(timeout=1500)
                print(f"Closed popup: {sel}")
            except Exception:
                pass

        # Wait for main container
        await page.wait_for_selector("div.s-main-slot", timeout=30000)

        # Scroll to load content
        print("Scrolling to load products...")
        for _ in range(12):
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(1.0)

        # Wait for prices to render before querying products
        await asyncio.sleep(3)
        await page.wait_for_selector(
            ".a-price .a-offscreen, span[data-a-color='price'] .a-offscreen, div.s-widget-container",
            timeout=25000
        )

        # Retry loop
        items = []
        for i in range(5):
            items = await page.query_selector_all(
                "div.s-main-slot div[data-asin]:not([data-asin='']), div.s-widget-container"
            )
            if items:
                print(f"> Found {len(items)} product containers on attempt {i+1}.")
                break
            print(f"Waiting for results... attempt {i+1}")
            await page.mouse.wheel(0, 2500)
            await asyncio.sleep(1.5)

        if not items:
            print("No visible product cards after multiple attempts.")
            html = await page.content()
            with open(debug_html_path, "w", encoding="utf-8") as f:
                f.write(html)
            await page.screenshot(path="debug_no_cards.png", full_page=True)
            return []

        # Main extraction logic
        products = await page.eval_on_selector_all(
            "div.s-main-slot div[data-asin]:not([data-asin='']), div.s-card-container, div.sg-col-inner",
            """
            (cards) => {
                const money = (s) => {
                    if (!s) return NaN;
                    const clean = s.replace(/[^0-9.,-]/g, "").split(/-|–/)[0].replace(/,/g, "");
                    const v = parseFloat(clean);
                    return Number.isNaN(v) ? NaN : v;
                };

                const isSponsored = (el) => {
                    return !!(
                        el.querySelector("[aria-label='Sponsored']") ||
                        el.querySelector(".s-sponsored-label-text") ||
                        el.querySelector(".puis-sponsored-label-text")
                    );
                };

                return cards.map(card => {
                    let titleEl =
                        card.querySelector("h2 a span") ||
                        card.querySelector(".a-size-medium.a-color-base.a-text-normal") ||
                        card.querySelector(".a-size-base-plus.a-color-base.a-text-normal");

                    const linkEl =
                        card.querySelector("h2 a[href]") ||
                        card.querySelector("a.a-link-normal.s-underline-text") ||
                        card.querySelector("a.a-link-normal");

                    const offscreen =
                        card.querySelector(".a-price .a-offscreen") ||
                        card.querySelector(".a-text-price .a-offscreen") ||
                        card.querySelector("span[data-a-color='price'] .a-offscreen") ||
                        card.querySelector("span[data-a-color='base'] .a-offscreen") ||  
                        card.querySelector("span.a-price[data-a-size] .a-offscreen") ||
                        card.querySelector(".a-price .a-price-range .a-offscreen") ||
                        card.querySelector(".a-price-whole"); 

                    const symbol = card.querySelector(".a-price-symbol");
                    let priceText = offscreen ? offscreen.textContent : null;

                    if (!priceText) {
                        const whole = card.querySelector(".a-price .a-price-whole")?.textContent || "";
                        const frac  = card.querySelector(".a-price .a-price-fraction")?.textContent || "00";
                        if (whole.trim()) priceText = `${whole}.${frac}`;
                    }

                    if (!priceText && symbol) priceText = symbol.textContent;

                    const title = titleEl ? titleEl.textContent.trim() : null;
                    const href  = linkEl ? linkEl.getAttribute("href") : null;
                    const link  = href ? (href.startsWith("http") ? href : "https://www.amazon.com" + href) : null;
                    const price = money(priceText);

                    if (!title || !link || !Number.isFinite(price) || price <= 0 || isSponsored(card)) return null;
                    return { title, link, price };
                }).filter(Boolean);
            }
            """
        )

        # Fallback layout
        if not products or len(products) == 0:
            products = await page.eval_on_selector_all(
                "div.s-card-container",
                """
                (cards) => cards.map(c => {
                    const title = c.querySelector("h2 a span")?.textContent?.trim() || null;
                    const href  = c.querySelector("h2 a[href]")?.getAttribute("href") || null;
                    const link  = href ? (href.startsWith("http") ? href : "https://www.amazon.com" + href) : null;
                    const priceText = c.querySelector(".a-price .a-offscreen")?.textContent
                                   || c.querySelector(".a-color-price")?.textContent
                                   || null;
                    const money = (s) => {
                        if (!s) return NaN;
                        const m = s.replace(/[^0-9.,-]/g, "").split(/-|–/)[0].replace(/,/g, "");
                        const v = parseFloat(m);
                        return Number.isNaN(v) ? NaN : v;
                    };
                    const price = money(priceText);
                    const sponsored = !!(c.querySelector("[aria-label='Sponsored']") || c.querySelector(".s-sponsored-label-text") || c.querySelector(".puis-sponsored-label-text"));
                    if (!title || !link || !Number.isFinite(price) || price <= 0 || sponsored) return null;
                    return { title, link, price };
                }).filter(Boolean)
                """
            )

        # Apply price filters (above, below, range)
        def within_bounds(p):
            if min_price is not None and p["price"] < min_price:
                return False
            if max_price is not None and p["price"] > max_price:
                return False
            return True

        products = [p for p in products if within_bounds(p) and math.isfinite(p["price"]) and p["price"] > 0] 

        if not products:
            print("No valid products extracted after rendering.")
            html = await page.content()
            with open(debug_html_path, "w", encoding="utf-8") as f:
                f.write(html)
            await page.screenshot(path="debug_no_products.png", full_page=True)
            return []

        # Sort by price ascending (cheapest first)
        products.sort(key=lambda x: x["price"])
        selected = products[0]
        print(f"> Extracted {len(products)} products.")
        print(f"\nBest match: ${selected['price']:.2f} — {selected['title']}")
        print(f"\nLink product: {selected['link']}")
        return products

    except Exception as e:
        print(f"Error extracting products: {e}")
        try:
            html = await page.content()
            with open(debug_html_path, "w", encoding="utf-8") as f:
                f.write(html)
            await page.screenshot(path="debug_exception.png", full_page=True)
        except Exception:
            pass
        return []


# ------------------------- Plan Execution -------------------------
async def execute_plan(
    steps: List[Dict[str, Any]],
    goal: str = "",
    headless: bool = True,
    llm_fn: Callable[[str, Dict[str, Any]], Dict[str, Any]] | None = None
) -> Dict[str, Any]:
    """Executes AI plan steps with async Playwright."""
    results = {"data": [], "errors": []}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            color_scheme="light",
        )
        page = await context.new_page()


        print("Starting automation...")
        await _wait_ready(page)

        # Apply anti-bot settings once
        await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        await page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
        await page.set_viewport_size({"width": 1366, "height": 900})

        try:
            step_idx = 0
            while step_idx < len(steps):
                step = steps[step_idx]
                action = step.get("action", "")
                selector = (step.get("selector") or "").strip()
                value = step.get("value") or goal
                print(f"Step {step_idx + 1}: {action} {selector}")

                try:
                    if action == "goto":
                        print(f"\nNavigating to {selector}")
                        await page.goto(selector, timeout=60000)
                        await _wait_ready(page)
                        await page.wait_for_timeout(2000)

                    elif action == "wait_for":
                        print(f"Waiting for {selector}")
                        await page.wait_for_selector(selector, state="visible", timeout=30000)

                    elif action == "fill":
                        await _fill_with_fallbacks(page, selector, value)

                    elif action == "click":
                        await _click_with_fallbacks(page, selector)

                    elif action == "scroll":
                        print("Scrolling down...")
                        await page.mouse.wheel(0, 2000)
                        await asyncio.sleep(2)

                    elif action == "extract":
                        # pass the user's goal so the extractor searches for the right thing
                        products = await extract_products(page, goal=goal)
                        if not products:
                            print("No products were extracted. Check debug_amazon_item.html for details.")
                            raise RuntimeError("Extraction failed.")
                        results["data"] = products
                        selected = min(products, key=lambda x: x["price"])
                        results["selected"] = selected
                        print(f"\nBest match: ${selected['price']:.2f} — {selected['title']}")
                        print(f"\nLink product: {selected.get('link')}")

                    else:
                        print(f"Unknown action: {action}")

                    step_idx += 1

                except Exception as e:
                    print(f"Step failed: {e}")
                    if llm_fn:
                        print("Replanning based on updated MCP context...")
                        page_context = await extract_mcp_context_payload(page)
                        plan_obj = await call_llm_fn(llm_fn, goal, page_context) or {}
                        new_steps = plan_obj.get("steps", [])
                        if new_steps:
                            print("New AI plan received")
                            steps = new_steps
                            step_idx = 0
                            continue
                        else:
                            print("LLM returned no steps during replan")
                            results["errors"].append("No steps generated during replan.")
                            break
                    else:
                        print("No llm_fn provided — skipping replan fallback.")
                        results["errors"].append(str(e))
                        break
            return results

        finally:
            await context.close()
            await browser.close()
