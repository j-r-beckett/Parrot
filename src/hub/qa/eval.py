#!/usr/bin/env python3
"""
Evaluation script for parrot-hub.

Runs evaluations against a local parrot-hub instance by making requests
to the /webhook/sms-proxy/received endpoint and displaying results.
Uses a producer/consumer pattern to run evals concurrently while displaying
results in order.
"""

import json
import asyncio
import httpx
from pathlib import Path
from typing import List, Dict, Any, Tuple


class EvalRunner:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.endpoint = f"{base_url}/webhook/sms-proxy/received"
        
    async def load_evals(self) -> List[Dict[str, Any]]:
        """Load evaluations from eval.json."""
        eval_file = Path(__file__).parent / "eval.json"
        with open(eval_file, 'r') as f:
            return json.load(f)
    
    def create_sms_payload(self, message: str, phone_number: str = "+1234567890") -> Dict[str, Any]:
        """Create SMS received payload for the webhook."""
        return {
            "deviceId": "test-device",
            "id": "test-webhook-id", 
            "payload": {
                "message": message,
                "receivedAt": "2025-08-31T12:00:00Z",
                "messageId": "test-message-id",
                "phoneNumber": phone_number
            }
        }
    
    async def send_request(self, message: str, phone_number: str = "+1234567890") -> Tuple[str, str]:
        """Send a request to the webhook endpoint."""
        payload = self.create_sms_payload(message, phone_number)
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.endpoint,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            correlation_id = response.headers.get("X-Correlation-ID", "unknown")
            return response.text, correlation_id
    
    async def execute_eval(self, eval_data: Dict[str, Any]) -> Tuple[str, List[Tuple[str, str, str]], Exception | None]:
        """Execute a single evaluation and return results."""
        eval_id = eval_data["id"]
        prompts = eval_data["prompts"]
        results = []
        error = None
        
        phone_number = f"+123456{hash(eval_id) % 10000:04d}"  # Unique phone per eval
        
        try:
            for i, prompt in enumerate(prompts, 1):
                # Add "! " prefix for continuation prompts (except the first)
                message = f"! {prompt}" if i > 1 else prompt
                response, correlation_id = await self.send_request(message, phone_number)
                results.append((prompt, response, correlation_id))
        except Exception as e:
            error = e
        
        return eval_id, results, error
    
    async def producer(self, task_queue: asyncio.Queue) -> None:
        """Producer: creates eval tasks and adds them to the queue."""
        evals = await self.load_evals()
        
        for i, eval_data in enumerate(evals):
            task = asyncio.create_task(self.execute_eval(eval_data))
            await task_queue.put((i, task))
        
        # Signal that no more tasks will be added
        task_queue.shutdown()
    
    async def consumer(self, task_queue: asyncio.Queue) -> None:
        """Consumer: processes tasks from queue and displays results in order."""
        completed_results = {}
        next_order = 0
        
        try:
            while True:
                order, task = await task_queue.get()
                result = await task
                
                # Store the result
                completed_results[order] = result
                
                # Display all consecutive results starting from next_order
                while next_order in completed_results:
                    self._display_result(completed_results[next_order])
                    del completed_results[next_order]
                    next_order += 1
        
        except asyncio.QueueShutDown:
            # Queue is shut down and empty, we're done
            pass
    
    def _display_result(self, result: Tuple[str, List[Tuple[str, str, str]], Exception | None]) -> None:
        """Display the result of a single evaluation."""
        eval_id, results, error = result
        
        print(f"\n{'='*60}")
        print(f"Running eval: {eval_id}")
        print(f"{'='*60}")
        
        if error:
            print(f"Error: {error}")
            return
        
        for i, (prompt, response, correlation_id) in enumerate(results, 1):
            print(f"\nPrompt {i}/{len(results)}: {prompt}")
            print(f"Correlation ID: {correlation_id}")
            print("-" * 40)
            print(f"Response: {response}")
    
    async def run_all_evals(self) -> None:
        """Run all evaluations concurrently using producer/consumer pattern."""
        evals = await self.load_evals()
        print(f"Starting evaluation run with {len(evals)} evaluations...")
        
        task_queue = asyncio.Queue()
        
        # Start producer and consumer
        producer_task = asyncio.create_task(self.producer(task_queue))
        consumer_task = asyncio.create_task(self.consumer(task_queue))
        
        # Wait for both to complete
        await asyncio.gather(producer_task, consumer_task)
        
        print(f"\n{'='*60}")
        print("All evaluations completed!")
        print(f"{'='*60}")


async def main():
    runner = EvalRunner()
    await runner.run_all_evals()


if __name__ == "__main__":
    asyncio.run(main())