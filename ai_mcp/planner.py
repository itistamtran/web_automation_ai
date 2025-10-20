import json
import os
from typing import Any, Dict
from dotenv import load_dotenv
from openai import OpenAI

SYSTEM = (
    "You are a web automation planner. "
    "Given a user's plain English goal and structured webpage context (from MCP), "
    "determine the user's intent (search, filter, extract, buy, click, etc.), "
    "and output ONLY a valid JSON array of step-by-step actions to achieve that goal. "
    "Each object must include 'action' and 'selector' or 'target'. "
    "Supported actions: 'goto', 'wait_for', 'fill', 'click', 'scroll', 'extract'. "
    "If the action is 'fill', include a 'value'. "
    "Prefer simple, stable CSS selectors that match the context. "
    "If the goal refers to Amazon, use these selectors where possible: "
    "#twotabsearchtextbox (search box), #nav-search-submit-button (search button), "
    "div[data-component-type='s-search-result'] (product container). "
    "For tasks involving 'buy' or 'add to cart', click the first visible 'Add to Cart' button. "
    "For tasks involving filtering by price, simulate sorting or include a comment in 'value'. "
    "No explanations, markdown, or natural text — output pure JSON only."
)


def get_openai_client() -> OpenAI:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Missing OPENAI_API_KEY in environment variables.")
    return OpenAI(api_key=api_key)


def generate_ai_plan(goal: str, page_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates a web automation plan using GPT. Falls back to a
    reliable Amazon plan if the model returns invalid output.
    """
    try:
        client = get_openai_client()
    except Exception as e:
        print(f"⚠️ Skipping OpenAI (missing key): {e}")
        client = None

    user_prompt = {
        "role": "user",
        "content": (
            f"User Goal: {goal}\n\n"
            "Webpage Context (simplified elements):\n"
            f"{json.dumps(page_context.get('element_samples', []), indent=2)}\n\n"
            "Output a JSON array of actions using only these keys: action, selector, target, value."
        ),
    }

    steps = []
    if client:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": SYSTEM}, user_prompt],
                temperature=0.3,
            )

            text = response.choices[0].message.content.strip()
            if not text:
                print("Model returned empty response.")
            else:
                if text.startswith("```"):
                    text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:].strip()

                print("\n--- Raw AI Response ---")
                print(text)
                print("-----------------------\n")

                try:
                    steps = json.loads(text)
                except json.JSONDecodeError:
                    print("Attempting to fix malformed JSON...")
                    start, end = text.find("["), text.rfind("]")
                    if start != -1 and end != -1:
                        steps = json.loads(text[start:end + 1])
                    else:
                        print("Could not recover valid JSON.")
                        steps = []

        except Exception as e:
            print(f"OpenAI API error: {e}")

    # Fallback plan for Amazon
    if not steps or not isinstance(steps, list):
        print("Falling back to intelligent default plan...")
        steps = [
            {"action": "goto", "selector": "https://www.amazon.com"},
            {"action": "wait_for", "selector": "#twotabsearchtextbox"},
            {"action": "fill", "selector": "#twotabsearchtextbox", "value": goal},
            {"action": "click", "selector": "#nav-search-submit-button"},
            {"action": "wait_for", "selector": "div[data-component-type='s-search-result']"},
            {"action": "extract", "selector": "div[data-component-type='s-search-result']"}
        ]

    # Normalize keys
    normalized = []
    for step in steps:
        if "target" in step:
            step["selector"] = step.pop("target")
        if step.get("action") == "fill" and not step.get("value"):
            step["value"] = goal
        normalized.append(step)

    return {"steps": normalized}
