from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from core.driver import search_product_price
from ai_mcp.mcp_client import extract_page_context  
from ai_mcp.planner import generate_ai_plan
from ai_mcp.executor import execute_plan
from playwright.async_api import async_playwright
import asyncio
import time
import traceback

app = FastAPI(title="Web Automation AI Service")

class RunRequest(BaseModel):
    goal: str
    headless: Optional[bool] = True


@app.post("/run-core")
async def run_core(req: RunRequest):
    # Wrap sync function safely in threadpool if it’s blocking
    from fastapi.concurrency import run_in_threadpool
    result = await run_in_threadpool(search_product_price, req.goal, req.headless)
    return {"status": "completed", "result": result}


@app.post("/run-ai")
async def run_ai(req: RunRequest):
    trace = {"goal": req.goal, "timestamps": {}, "errors": []}

    try:
        start = time.time()
        context_data = await extract_page_context(headless=req.headless)
        trace["timestamps"]["context_extraction"] = round(time.time() - start, 2)

        if not context_data:
            return {"status": "error", "message": "MCP did not return context data."}

        start = time.time()
        plan = generate_ai_plan(req.goal, context_data)
        trace["timestamps"]["plan_generation"] = round(time.time() - start, 2)

        if not plan.get("steps"):
            return {"status": "planned", "plan": [], "result": "Planner returned no steps."}

        start = time.time()
        result = await execute_plan(plan["steps"], goal=req.goal, headless=req.headless, llm_fn=generate_ai_plan)
        trace["timestamps"]["execution"] = round(time.time() - start, 2)
        trace["result"] = result

        return {
            "status": "completed",
            "plan": plan["steps"],
            "result": result,
            "trace": trace
        }

    except Exception as e:
        error_msg = f"Fatal error: {str(e)}"
        trace["errors"].append(error_msg)
        trace["traceback"] = traceback.format_exc()
        return {"status": "error", "trace": trace, "message": error_msg}
