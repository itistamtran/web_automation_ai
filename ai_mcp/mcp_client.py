import time
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright
from ai_mcp.browser_utils import launch_stealth_browser


async def async_extract_page_context(headless: bool = True, query: str = None):
    """
    Uses Playwright (async) to open Amazon (U.S. region) and capture detailed page context.
    Returns metadata + accessibility info for the MCP planner.
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                ],
            )

            context = await browser.new_context(
                locale="en-US",
                timezone_id="America/Los_Angeles",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                extra_http_headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.google.com/",
                },
                viewport={"width": 1440, "height": 900},
            )

            page = await context.new_page()

            # Anti-bot stealth setup
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4]});
                Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
                Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                window.chrome = { runtime: {} };
            """)

            # Open Amazon directly
            print("Opening Amazon search page...")
            base_url = "https://www.amazon.com"
            search_url = f"{base_url}/s?k={query.replace(' ', '+')}&language=en_US" if query else base_url
            await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(1500)

            # Handle cookie or location popups
            for sel in ["#sp-cc-accept", "input[name='accept']", "#glowDoneButton"]:
                try:
                    await page.click(sel, timeout=3000)
                    print(f"Closed popup {sel}")
                except Exception:
                    pass

            # Wait for at least some product elements
            try:
                await page.wait_for_selector("div.s-main-slot div.s-result-item[data-asin]", timeout=10000)
            except Exception:
                print("Product grid not found, continuing anyway...")

            # Collect minimal metadata for LLM planner
            title = await page.title()
            url = page.url
            element_data = []

            elements = await page.query_selector_all("*")
            for el in elements[:50]:
                try:
                    tag = await el.evaluate("el => el.tagName.toLowerCase()")
                    aria = await el.get_attribute("aria-label")
                    text = (await el.inner_text())[:60].strip()
                    if text:
                        element_data.append({
                            "tag": tag,
                            "aria": aria,
                            "text": text
                        })
                except Exception:
                    continue

            await browser.close()
            return {
                "title": title,
                "url": url,
                "element_samples": element_data,
                "source": "Amazon (US)",
                "timestamp": time.time()
            }

    except Exception as e:
        print(f"❌ async_extract_page_context error: {e}")
        return {"error": str(e)}


async def extract_page_context(headless=False, query=None):
    """
    Uses Playwright (async) to extract HTML context from an Amazon search page.
    Works safely within an asyncio loop.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()

        if query:
            url = f"https://www.amazon.com/s?k={query.replace(' ', '+')}&language=en_US"
        else:
            url = "https://www.amazon.com/"
        print(f" Navigating to: {url}")

        try:
            await page.goto(url, timeout=60000)
            await page.wait_for_selector(".s-main-slot", timeout=15000)
        except Exception as e:
            print(f"Page load warning: {e}")

        html = await page.content()
        await browser.close()

        return {"url": url, "html": html}
