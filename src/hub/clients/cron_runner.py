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
        self.instance_id = str(uuid.uuid4())

    async def __aenter__(self) -> None:
        # initialize database
        async with self.db_pool.connection() as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cronjobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    schedule TEXT NOT NULL,
                    function_id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    FIRE_AT TEXT NOT NULL
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
                    coro, func, schedule, fire_at, input = await self.job_queue.get()
                    try:
                        result = await coro
                        if result is not None:
                            await self.submit(func, result, schedule, fire_at)
                    except Exception as e:
                        self.logger.error(
                            f"Job {func.function_id} failed: {e}", exc_info=True
                        )
                        # Reschedule the job with original input on failure
                        await self.submit(func, input, schedule, fire_at)
                except asyncio.QueueShutDown:
                    break

        async def db_reader() -> None:
            while True:
                wait = asyncio.create_task(asyncio.sleep(self.period.total_seconds()))

                now = datetime.now(timezone.utc)
                async with self.db_pool.connection() as db:
                    # Fetch ready jobs
                    cursor = await db.execute(
                        "SELECT id, schedule, function_id, data, fire_at FROM cronjobs WHERE fire_at <= ? ORDER BY fire_at ASC",
                        (now,),
                    )
                    rows = await cursor.fetchall()

                    if rows:
                        # Delete the jobs we're about to process
                        job_ids = [str(row[0]) for row in rows]
                        placeholders = ",".join("?" * len(job_ids))
                        await db.execute(
                            f"DELETE FROM cronjobs WHERE id IN ({placeholders})",
                            job_ids,
                        )
                        await db.commit()  # type: ignore

                # Process jobs outside the db connection
                for row in rows:
                    id, schedule, function_id, data, fire_at = row
                    func = self.functions[function_id]
                    input = func.model_type.model_validate_json(data)

                    coro = func(job_id=str(id), schedule=schedule, input=input)
                    await self.job_queue.put(
                        (coro, func, schedule, datetime.fromisoformat(fire_at), input)
                    )

                await wait

        self.job_runner = asyncio.create_task(job_runner())
        self.db_reader = asyncio.create_task(db_reader())

    async def __aexit__(self) -> None:
        self.db_reader.cancel()
        try:
            await self.db_reader
        except asyncio.CancelledError:
            pass

        self.job_queue.shutdown()
        await self.job_runner

    async def submit(
        self,
        job: CronJobFunc,
        initial_input: TBaseModel,
        schedule: str,
        last_ran_at: Optional[datetime] = None,
    ) -> None:
        fire_at = cronexpr.next_fire(schedule, last_ran_at)  # type: ignore

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
