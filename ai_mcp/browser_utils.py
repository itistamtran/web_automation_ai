from typing import Tuple
from playwright.async_api import async_playwright
import random

async def launch_stealth_browser(headless: bool = False):
    """
    Launch Playwright Chromium browser with stealthy defaults (async version).
    Returns (playwright, browser, context, page).
    """
    p = await async_playwright().start()

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    ]
    ua = random.choice(user_agents)

    browser = await p.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ],
    )

    context = await browser.new_context(
        user_agent=ua,
        viewport={"width": 1366, "height": 768},
        locale="en-US",
        timezone_id="America/Los_Angeles",
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )

    page = await context.new_page()

    await page.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
        window.chrome = { runtime: {} };
        """
    )

    return p, browser, context, page


async def extract_mcp_context(page):
    """Return list of element samples asynchronously."""
    elements = await page.query_selector_all("input, button, a, div[role], span, img")
    samples = []
    for el in elements[:200]:
        try:
            role = await el.get_attribute("role") or "none"
            aria = await el.get_attribute("aria-label")
            text = (await el.inner_text() or "").strip()[:80]
            tag = await el.evaluate("el => el.tagName.toLowerCase()")
            samples.append({"tag": tag, "role": role, "text": text, "aria": aria})
        except Exception:
            continue
    return samples


async def extract_mcp_context_payload(page):
    """
    Build a compact MCP context from the CURRENT page.
    Async-safe: all Playwright calls are awaited.
    """
    context = {"element_samples": []}
    try:
        title = await page.title()
        url = page.url  # property
        context["title"] = title
        context["url"] = url

        # Collect a small sample of visible-ish elements
        elements = await page.query_selector_all("*")
        for el in elements[:100]:
            try:
                tag = await el.evaluate("n => n.tagName.toLowerCase()")
                role = await el.get_attribute("role")
                aria = await el.get_attribute("aria-label")
                # inner_text can be expensive; check visibility first
                txt = (await el.inner_text()) if await el.is_visible() else ""
                txt = (txt or "").strip()[:80]
                if txt or aria or role:
                    context["element_samples"].append(
                        {"tag": tag, "role": role or "none", "aria": aria, "text": txt}
                    )
            except Exception:
                continue
    except Exception:
        pass
    return context
