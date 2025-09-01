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
        is_continuation: bool = False
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[int]]:
        """
        Send a single prompt to the server.
        
        Returns: (response_text, correlation_id, error_message, status_code)
        """
        # Add "! " prefix for conversation continuation
        message = f"! {prompt}" if is_continuation else prompt
        
        payload = self.create_sms_payload(message, phone_number)
        
        try:
            response = await self.client.post(
                f"{self.base_url}/webhook/sms-proxy/received",
                json=payload
            )
            
            correlation_id = response.headers.get("X-Correlation-ID", "N/A")
            
            if response.status_code >= 400:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                return None, correlation_id, error_msg, response.status_code
            
            return response.text, correlation_id, None, response.status_code
            
        except httpx.RequestError as e:
            return None, "N/A", str(e), None
    
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
        
        result = {
            "index": index,
            "id": scenario_id,
            "phone_number": phone_number,
            "stages": [],
            "error": None
        }
        
        for stage_idx, prompt in enumerate(prompts):
            is_continuation = stage_idx > 0
            
            response_text, correlation_id, error_msg, status_code = await self.send_prompt(
                prompt, 
                phone_number, 
                is_continuation
            )
            
            stage_result = {
                "stage": stage_idx + 1,
                "prompt": prompt,
                "correlation_id": correlation_id,
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


def format_result(result: Dict[str, Any]) -> str:
    """Format a scenario result for display."""
    lines = []
    
    # Header
    lines.append("=" * 80)
    lines.append(f"Scenario: {result['id']} (Index: {result['index']})")
    lines.append(f"Phone: {result['phone_number']}")
    
    if result.get("error"):
        lines.append(f"Status: FAILED - {result['error']}")
    else:
        lines.append(f"Status: COMPLETED all stages")
    
    lines.append("-" * 80)
    
    # Stages
    for stage in result["stages"]:
        lines.append(f"\nStage {stage['stage']}:")
        lines.append(f"  Prompt: {stage['prompt']}")
        lines.append(f"  Correlation ID: {stage['correlation_id']}")
        
        if stage['error']:
            lines.append(f"  Status: FAILED")
            lines.append(f"  Error: {stage['error']}")
        else:
            lines.append(f"  Status: SUCCESS (HTTP {stage['status_code']})")
            if stage['response']:
                # Truncate long responses
                response = stage['response']
                if len(response) > 200:
                    response = response[:197] + "..."
                lines.append(f"  Response: {response}")
    
    return "\n".join(lines)


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
    
    print(f"Loaded {len(scenarios)} scenario(s)")
    print()
    
    async with ScenarioRunner() as runner:
        # Health check
        print("Checking server health...")
        if not await runner.check_health():
            print("Server is not healthy. Please ensure the server is running on http://127.0.0.1:8000")
            sys.exit(1)
        print("Server is healthy")
        print()
        
        # Run all scenarios concurrently
        print(f"Running {len(scenarios)} scenario(s) concurrently...")
        print()
        
        # Create tasks for all scenarios
        tasks = [
            runner.run_scenario(scenario, idx) 
            for idx, scenario in enumerate(scenarios)
        ]
        
        # Run concurrently and collect results
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results in order
        print("\n" + "=" * 80)
        print("RESULTS (displayed in scenario order)")
        print("=" * 80 + "\n")
        
        success_count = 0
        failure_count = 0
        
        for result in results:
            if isinstance(result, Exception):
                print(f"Unexpected error: {result}")
                failure_count += 1
            else:
                print(format_result(result))
                if result.get("error"):
                    failure_count += 1
                else:
                    success_count += 1
        
        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Successful scenarios: {success_count}")
        print(f"Failed scenarios: {failure_count}")
        print(f"Total scenarios: {len(scenarios)}")
        
        # Exit with error code if any scenarios failed
        if failure_count > 0:
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())