from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
from typing import (
    Callable,
    Protocol,
    TypeVar,
    cast,
    List,
    Type,
    get_type_hints,
    Awaitable,
    Optional,
)
from aiosqlitepool import SQLiteConnectionPool
import asyncio
import inspect
import cronexpr
import logging
import uuid


TBaseModel = TypeVar("TBaseModel", bound=BaseModel)


class CronJobFunc(Protocol):
    async def __call__(
        self, job_id: str, schedule: str, input: TBaseModel
    ) -> Optional[TBaseModel]: ...

    function_id: str
    model_type: Type[BaseModel]


def cron_job(
    name: str, version: float
) -> Callable[
    [Callable[[str, str, TBaseModel], Awaitable[Optional[TBaseModel]]]], CronJobFunc
]:
    def decorator(func: Callable) -> CronJobFunc:
        # Validate function signature
        params = list(inspect.signature(func).parameters.keys())

        if params != ["job_id", "schedule", "input"]:
            raise ValueError(
                f"Function {func.__name__} must have exactly 3 parameters named 'job_id', 'schedule', 'input', got {params}"
            )

        func = cast(CronJobFunc, func)
        func.function_id = f"{name}-v{version}"

        # Extract the input model type from function annotations
        hints = get_type_hints(func)
        func.model_type = hints["input"]

        return func

    return decorator


class CronRunner:
    def __init__(
        self,
        func_pool: List[CronJobFunc],
        period: timedelta,
        db_pool: SQLiteConnectionPool,
        logger: logging.Logger,
    ) -> None:
        self.period = period
        self.db_pool = db_pool
        self.logger = logger
        self.functions = {func.function_id: func for func in func_pool}
        self.runner_id = str(uuid.uuid4())

    async def __aenter__(self) -> None:
        # initialize database
        async with self.db_pool.connection() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cronjobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    schedule TEXT NOT NULL,
                    function_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    fire_at TEXT NOT NULL,
                    runner TEXT
                ) 
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_fire_at
                ON cronjobs(fire_at)
            """)

            await db.commit()  # type: ignore

        # start background job runner
        self.job_queue = asyncio.Queue()

        async def job_runner() -> None:
            while True:
                try:
                    (
                        job_id,
                        task,
                        func,
                        schedule,
                        fired_at,
                        input,
                    ) = await self.job_queue.get()
                    try:
                        result = await task
                        # Delete the completed job
                        async with self.db_pool.connection() as db:
                            await db.execute(
                                "DELETE FROM cronjobs WHERE id = ?", (job_id,)
                            )
                            await db.commit()  # type: ignore

                        if result is not None:
                            await self.submit(func, result, schedule, fired_at)
                    except Exception as e:
                        self.logger.error(
                            f"Job {func.function_id} failed: {e}", exc_info=True
                        )
                        # Clear the runner field so job can be retried
                        async with self.db_pool.connection() as db:
                            await db.execute(
                                "UPDATE cronjobs SET runner = NULL WHERE id = ?",
                                (job_id,),
                            )
                            await db.commit()  # type: ignore
                except asyncio.QueueShutDown:
                    break

        async def db_reader() -> None:
            while True:
                wait = asyncio.create_task(asyncio.sleep(self.period.total_seconds()))

                now = datetime.now(timezone.utc)
                async with self.db_pool.connection() as db:
                    # Fetch ready jobs (only those not being processed by this runner)
                    cursor = await db.execute(
                        """
                        SELECT id, schedule, function_id, data, fire_at 
                        FROM cronjobs WHERE fire_at <= ? AND (runner IS NULL OR runner != ?) 
                        ORDER BY fire_at ASC
                        """,
                        (now, self.runner_id),
                    )
                    rows = await cursor.fetchall()

                    if rows:
                        # Mark the jobs we're about to process with our runner_id
                        job_ids = [row[0] for row in rows]
                        placeholders = ",".join("?" * len(job_ids))
                        await db.execute(
                            f"UPDATE cronjobs SET runner = ? WHERE id IN ({placeholders})",
                            [self.runner_id] + job_ids,
                        )
                        await db.commit()  # type: ignore

                # Process jobs outside the db connection
                for row in rows:
                    id, schedule, function_id, data, fired_at = row
                    func = self.functions[function_id]
                    input = func.model_type.model_validate_json(data)

                    task = asyncio.create_task(
                        func(job_id=str(id), schedule=schedule, input=input)
                    )
                    await self.job_queue.put(
                        (
                            id,
                            task,
                            func,
                            schedule,
                            datetime.fromisoformat(fired_at),
                            input,
                        )
                    )

                await wait

        self.job_runner = asyncio.create_task(job_runner())
        self.db_reader = asyncio.create_task(db_reader())

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # Cancel db_reader first
        self.db_reader.cancel()
        try:
            await asyncio.wait_for(self.db_reader, timeout=1.0)
        except asyncio.CancelledError:
            pass

        # Shutdown queue
        self.job_queue.shutdown()
        
        # Wait for job_runner with timeout too
        await asyncio.wait_for(self.job_runner, timeout=1.0)

    async def submit(
        self,
        job: CronJobFunc,
        initial_input: TBaseModel,
        schedule: str,
        last_fired_at: Optional[datetime] = None,
    ) -> None:
        fire_at = cronexpr.next_fire(schedule, last_fired_at)  # type: ignore

        async with self.db_pool.connection() as db:
            await db.execute(
                "INSERT INTO cronjobs (schedule, function_id, data, fire_at) VALUES (?, ?, ?, ?)",
                (
                    schedule,
                    job.function_id,
                    initial_input.model_dump_json(),
                    fire_at.isoformat(),
                ),
            )
            await db.commit()  # type: ignore
