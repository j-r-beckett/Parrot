#!/usr/bin/env python3
"""
Evaluation script for running scenarios against the parrot hub server.

This script:
1. Checks server health before running
2. Executes all scenarios concurrently from scenarios.json
3. Displays results in the order they appear in the JSON
4. Shows correlation IDs for all requests
5. Handles errors gracefully, stopping multi-stage scenarios on first error
"""

import asyncio
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import httpx


class ScenarioRunner:
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def check_health(self) -> bool:
        """Check if the server is healthy."""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except httpx.RequestError as e:
            print(f"Health check failed: {e}")
            return False
    
    def generate_phone_number(self) -> str:
        """Generate a random phone number for testing."""
        # Format: +1555XXXXXXX (US format with fake 555 area code)
        return f"+1555{random.randint(1000000, 9999999)}"
    
    def create_sms_payload(self, message: str, phone_number: str) -> Dict[str, Any]:
        """Create an SMS received webhook payload."""
        return {
            "deviceId": "test-device",
            "id": str(uuid4()),
            "payload": {
                "message": message,
                "receivedAt": datetime.now().isoformat() + "Z",
                "messageId": str(uuid4()),
                "phoneNumber": phone_number
            }
        }
    
    async def send_prompt(
        self, 
        prompt: str, 
        phone_number: str, 
        correlation_id: str,
        is_continuation: bool = False
    ) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """
        Send a single prompt to the server.
        
        Returns: (response_text, error_message, status_code)
        """
        # Add "! " prefix for conversation continuation
        message = f"! {prompt}" if is_continuation else prompt
        
        payload = self.create_sms_payload(message, phone_number)
        
        try:
            response = await self.client.post(
                f"{self.base_url}/webhook/sms-proxy/received",
                json=payload,
                headers={"X-Correlation-ID": correlation_id}
            )
            
            if response.status_code >= 400:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                return None, error_msg, response.status_code
            
            return response.text, None, response.status_code
            
        except httpx.RequestError as e:
            return None, str(e), None
    
    async def run_scenario(
        self, 
        scenario: Dict[str, Any], 
        index: int
    ) -> Dict[str, Any]:
        """
        Run a single scenario with all its prompts.
        
        Returns a result dictionary with scenario info and stage results.
        """
        scenario_id = scenario.get("id", f"scenario-{index}")
        prompts = scenario.get("prompts", [])
        phone_number = self.generate_phone_number()
        correlation_id = str(uuid4())
        
        result = {
            "index": index,
            "id": scenario_id,
            "correlation_id": correlation_id,
            "stages": [],
            "error": None
        }
        
        for stage_idx, prompt in enumerate(prompts):
            is_continuation = stage_idx > 0
            
            response_text, error_msg, status_code = await self.send_prompt(
                prompt, 
                phone_number, 
                correlation_id,
                is_continuation
            )
            
            stage_result = {
                "stage": stage_idx + 1,
                "prompt": prompt,
                "response": response_text,
                "error": error_msg,
                "status_code": status_code
            }
            
            result["stages"].append(stage_result)
            
            # Stop processing remaining stages if this one failed
            if error_msg:
                result["error"] = f"Failed at stage {stage_idx + 1}"
                break
        
        return result


def wrap_text(text: str, width: int) -> List[str]:
    """Wrap text to specified width, preserving words."""
    if not text:
        return [""]
    
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        if not current_line:
            current_line = word
        elif len(current_line) + 1 + len(word) <= width:
            current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word
    
    if current_line:
        lines.append(current_line)
    
    return lines


def format_user_message(text: str) -> str:
    """Format user message: blue, right-aligned with 10 char offset."""
    lines = wrap_text(text, 50)  # Full 50 char width for wrapping
    formatted_lines = []
    
    for line in lines:
        # Right-justify within 50 chars, then add 10 char offset
        right_justified = line.rjust(50)
        shifted = " " * 10 + right_justified
        colored = f"\033[94m{shifted}\033[0m"
        formatted_lines.append(colored)
    
    return "\n".join(formatted_lines)


def format_ai_message(text: str, is_error: bool = False) -> str:
    """Format AI message: grey (or red for errors), left-aligned."""
    if not text:
        text = "Empty response"
        is_error = True
    
    # For errors, remove newlines and truncate to 160 characters
    if is_error:
        text = text.replace('\n', ' ').replace('\r', ' ')
        if len(text) > 160:
            text = text[:160] + "..."
    
    # For errors, don't respect word boundaries when wrapping
    if is_error:
        lines = []
        for i in range(0, len(text), 50):
            lines.append(text[i:i+50])
    else:
        lines = wrap_text(text, 50)
    
    formatted_lines = []
    color_code = "\033[91m" if is_error else "\033[32m"  # red or standard green
    
    for line in lines:
        colored = f"{color_code}{line}\033[0m"
        formatted_lines.append(colored)
    
    return "\n".join(formatted_lines)


def format_result(result: Dict[str, Any]) -> str:
    """Format a scenario result as SMS conversation."""
    lines = []
    
    # Header with clean divider
    lines.append(f"── {result['id']} ── {result['correlation_id']} ──")
    
    # SMS conversation
    for stage in result["stages"]:
        # Add some spacing between message pairs
        lines.append("")
        
        # User message (right-aligned, blue)
        user_msg = format_user_message(stage['prompt'])
        lines.append(user_msg)
        
        # Small gap between user and AI message
        lines.append("")
        
        # AI response (left-aligned, grey or red for errors)
        if stage['error']:
            ai_msg = format_ai_message(stage['error'], is_error=True)
        else:
            ai_msg = format_ai_message(stage.get('response', ''), is_error=False)
        
        lines.append(ai_msg)
    
    return "\n".join(lines) + "\n"


async def main():
    """Main evaluation function."""
    # Load scenarios
    scenarios_path = Path(__file__).parent / "scenarios.json"
    
    if not scenarios_path.exists():
        print(f"Error: scenarios.json not found at {scenarios_path}")
        sys.exit(1)
    
    try:
        with open(scenarios_path) as f:
            scenarios = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error parsing scenarios.json: {e}")
        sys.exit(1)
    
    if not scenarios:
        print("No scenarios found in scenarios.json")
        sys.exit(0)
    
    async with ScenarioRunner() as runner:
        # Health check
        if not await runner.check_health():
            print("Server is not healthy. Please ensure the server is running on http://127.0.0.1:8000")
            sys.exit(1)
        
        # Run all scenarios concurrently
        print(f"Running {len(scenarios)} scenario(s)...")
        
        # Create tasks for all scenarios
        tasks = [
            runner.run_scenario(scenario, idx) 
            for idx, scenario in enumerate(scenarios)
        ]
        
        # Run concurrently and collect results
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results in order
        print()
        
        failure_count = 0
        
        for result in results:
            if isinstance(result, Exception):
                print(f"Unexpected error: {result}")
                failure_count += 1
            else:
                print(format_result(result))
                if result.get("error"):
                    failure_count += 1
        
        print("All scenarios completed.")
        
        # Exit with error code if any scenarios failed
        if failure_count > 0:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())