import asyncio
import pytest
from datetime import timedelta
from pydantic import BaseModel
from aiosqlitepool import SQLiteConnectionPool
import aiosqlite
import logging
from clients.cron_runner import CronRunner, cron_job


class CounterInput(BaseModel):
    value: int


@pytest.mark.asyncio
async def test_cron_runner_happy_path():
    # Setup
    # Use shared cache so all connections see the same in-memory database
    db_pool = SQLiteConnectionPool(
        lambda: aiosqlite.connect("file::memory:?cache=shared", uri=True)
    )
    logger = logging.getLogger(__name__)

    results = []

    @cron_job("increment", 1.0)
    async def increment_job(
        job_id: str, schedule: str, input: CounterInput
    ) -> CounterInput:
        new_value = input.value + 1
        results.append(new_value)
        if new_value >= 3:
            return None  # Terminate the job
        return CounterInput(value=new_value)

    runner = CronRunner(
        func_pool=[increment_job],
        period=timedelta(milliseconds=100),  # Check every 100ms for faster testing
        db_pool=db_pool,
        logger=logger,
    )

    async def run_full_test():
        async with runner:
            # Submit initial job
            await runner.submit(
                increment_job, CounterInput(value=0), "* * * * * *"
            )  # Every second

            # Run for 3 seconds
            await asyncio.sleep(3.2)

        # Assertions inside the timeout scope so cleanup hangs are caught
        assert results == [1, 2, 3], f"Expected [1, 2, 3] but got {results}"

    try:
        # Wrap EVERYTHING including cleanup in timeout
        await asyncio.wait_for(run_full_test(), timeout=5.0)
    except asyncio.TimeoutError:
        pytest.fail("Test timed out - likely deadlock during CronRunner cleanup")
    except Exception as e:
        pytest.fail(f"Test failed: {e}")
    finally:
        await db_pool.close()


if __name__ == "__main__":
    asyncio.run(test_cron_runner_happy_path())
