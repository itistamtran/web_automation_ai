# Web Automation AI Project

This project demonstrates three integrated components designed to showcase automation, AI planning, and API deployment skills.

1. **Required Core**: A Playwright-based bot that performs a fixed web automation task and prints a clear result.
2. **Optional Challenge 1 (AI Planner)**: An AI system that dynamically generates and executes structured steps based on a user’s goal and current webpage context.
3. **Optional Challenge 2 (Shareable API)**: A FastAPI service that exposes endpoints to trigger both the core bot and the AI planner remotely.

## Demo Task

This project uses the public demo e-commerce site: `https://webscraper.io/test-sites/e-commerce/allinone`.

The core task:

- Visit the site
- Navigate to Computers → Laptops
- Read the first product name and price
- Print a clear success message

---

## 1. Setup

```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install
```

For AI planner:

```bash
cp .env.example .env
# place OpenAI API key into .env
```

If an MCP server is not available, the AI planner automatically falls back to Playwright’s accessibility data. See `ai_mcp/mcp_client.py` for details.

---

## 2. Run the Core Bot from CLI

```bash
python main.py --product "wireless mouse"
```

Output looks like:

```
Starting search for 'wireless mouse' on Amazon...
Opening Amazon...
Success! Found 'Logitech M185 Wireless Mouse, 2.4GHz with USB Mini Receiver, 12-Month Battery Life, 1000 DPI Optical Tracking, Ambidextrous PC/Mac/Laptop - Swift Grey' for $14.70
```

Playwright will open a real browser window so you can watch everything happen live if you set headless=False

Example:

```bash
python main.py --product "laptop" --headless false
```

---

## 3. Run the AI MCP Module

The AI MCP module demonstrates the optional AI Planner component (Challenge 1).
It allows the AI to interpret a natural-language goal (e.g., “Find the cheapest MacBook on Amazon”) and execute the task automatically using Playwright.

Run the AI MCP Script:

```bash
python ai_mcp/ai_main.py
```

By default, the browser runs in visible (headed) mode, so you can watch the automation in real time.
If you prefer to run without opening a visible browser window, you can use a CLI flag

```bash
python ai_mcp/ai_main.py --headless
```

Example output:

```
What would you like me to do?
> find a pink shirt above $50

AI Goal: find a pink shirt above $50
- Extracting page context using Playwright MCP...
- Generating AI plan based on MCP context...
AI Plan received: 6 steps
   Step 1: goto → https://www.amazon.com
   Step 2: fill → #twotabsearchtextbox
   Step 3: click → #nav-search-submit-button
   Step 4: wait_for → div[data-component-type='s-search-result']
   Step 5: scroll → div[data-component-type='s-search-result']
   Step 6: extract → div[data-component-type='s-search-result']

Executing the plan...
> Extracted 102 products.
> Best match: $50.00 — Sportswear Women's Plus-Size Tamiami II Long Sleeve Shirt
> Link: https://www.amazon.com/Columbia-Womens-Tamiami-Sleeve-Shirt/dp/B0CLQYLJ9Z

Execution completed.
Full trace saved to ai_trace.json.
```

## 4. Run the API

Start the FastAPI server:

```bash
uvicorn api.app:app --reload
```

Then open:

```
http://127.0.0.1:8000/docs
```

This will open the interactive Swagger UI, where you can test both endpoints.

### Endpoints

- `POST /run-core`
  Runs the core Playwright automation for a fixed goal.
  Request Body:

  ```json
  {
    "goal": "laptop",
    "headless": true
  }
  ```

  - goal: the product or keyword to search for.
  - headless: if true, runs invisibly (no browser window). If false, shows the browser.

- `POST /run-ai`
  Triggers the AI planner and executes an intelligent plan based on the goal.
  Request Body:

  ```json
  {
    "goal": "find the pink wireless mouse under $40 on amazon",
    "headless": true
  }
  ```

  This returns both the AI plan and the execution result.
  You can modify the goal and toggle headless directly in Swagger, then click “Execute” to test.

---

## 4. Project Layout

```
web_automation_ai/
├── core/
│   ├── __init__.py         # Module initializer
│   ├── driver.py           # Core Playwright automation logic
│   └── utils.py            # Helper utilities (timeouts, retries, etc.)
│
├── ai_mcp/
│   ├── __init__.py         # Module initializer
│   ├── ai_main.py          # Entry point for running AI MCP from CLI
│   ├── browser_utils.py    # Browser and page interaction helpers
│   ├── executor.py         # Executes AI-generated steps using Playwright
│   ├── mcp_client.py       # Interface for extracting structured page context
│   └── planner.py          # Generates structured AI action plans
│
├── api/
│   ├── __init__.py         # Module initializer
│   └── app.py              # FastAPI app exposing /run-core and /run-ai endpoints
│
├── main.py                 # CLI entry point for the core automation
├── requirements.txt        # Dependencies list
├── .env                    # Environment variables (for OpenAI API key)
├── .gitignore              # Excludes sensitive and auto-generated files
└── README.md               # Project documentation
```

---

## 5. Notes for Evaluators

- Includes detailed error handling for navigation, timeouts, and missing elements.
- Logs show step-by-step progress and results clearly.
- The AI planner validates JSON safely and skips unsupported actions.
- The MCP layer is optional but ready. You can connect any Playwright MCP server by editing MCPClient.
- The .gitignore file ensures sensitive and generated files are not committed.

---
