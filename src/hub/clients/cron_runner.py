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
    """
    Async cron job executor with persistent storage and crash recovery.

    CronRunner provides reliable, at-least-once execution of scheduled jobs. Jobs are
    responsible for their own error handling, retry logic, and state management across executions.
    A job may be ran multiple times if CronRunner crashes while the job is executing.

    Job Lifecycle:
        1. Jobs are scheduled with a cron expression and initial input state
        2. Initializer polls DB for due jobs, marks them with runner_id, starts async tasks
        3. Tasks execute concurrently while flowing through the execution queue
        4. Finalizer awaits completion, schedules next execution based on job's return value
        5. Jobs return new state for next execution, or None to cancel themselves

    Error Handling:
        The system guarantees execution; jobs handle errors. If a job fails with an
        exception TODO. Jobs should:
        - Track error counts and implement backoff strategies in their state
        - Handle different error types appropriately (timeouts, auth, rate limits, etc.)
        - Return None to permanently cancel themselves when appropriate
        - Use state continuity for sophisticated retry patterns

    Thread Safety:
        Single CronRunner per process. Multiple runners will conflict due to runner_id
        optimistic locking. Use external coordination for multi-process deployments.
    """

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

        # Only one CronRunner should be active at a time, this is used to recover from
        # crashes by differentiating between the old CronRunner and the new CronRunner
        self.runner_id = str(uuid.uuid4())

    async def __aenter__(self) -> None:
        # Initialize database
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

        # The initializer reads jobs from disk and starts them, the finalizer awaits the jobs
        # then writes them back to disk. Jobs flow from the initializer to the finalizer via
        # a queue. Jobs execute while they're in the queue.
        self.executing_jobs = asyncio.Queue()
        self.job_initializer_task = asyncio.create_task(self._initialize_jobs())
        self.job_finalizer_task = asyncio.create_task(self._finalize_jobs())

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # Shut down the initializer before we shut down the finalizer so no jobs are droppped
        self.job_initializer_task.cancel()
        try:
            await asyncio.wait_for(self.job_initializer_task, timeout=1.0)
        except asyncio.CancelledError:
            pass

        # All jobs in executing_jobs are processed before QueueShutDown is raised. This is
        # because QueueShutDown is thrown only when the queue is in the shutdown state and
        # the queue is empty (or forceful shutdown is requested, but we don't request it).

        # The initializer has already been stopped, so once executing_jobs is empty we know
        # that no more jobs will ever be written to it and we can safely shut down.
        self.executing_jobs.shutdown()
        try:
            await asyncio.wait_for(self.job_finalizer_task, timeout=1.0)
        except asyncio.QueueShutDown:
            pass

        # Note that __aexit__ does NOT close the db_pool. That is the responsiblity of the calling code

    async def _finalize_jobs(self) -> None:
        """Reads executing jobs from the queue, awaits their completion, then schedules the next execution and writes the job back to disk."""
        while True:
            (
                job_id,
                task,
                func,
                schedule,
                fired_at,
                input,
            ) = await self.executing_jobs.get()

            has_result = False
            try:
                # Jobs are finalized sequentially, but they execute concurrently in the execution queue
                result: TBaseModel = await task
                has_result = True
            except Exception as e:
                self.logger.error(f"Job {func.function_id} failed: {e}", exc_info=True)
                # Job failed - delete it and let the job's next scheduled execution handle retry logic

            if has_result:
                # Delete the completed job
                async with self.db_pool.connection() as db:
                    await db.execute("DELETE FROM cronjobs WHERE id = ?", (job_id,))
                    await db.commit()  # type: ignore

                # Schedule the next job
                if result is not None:
                    await self.submit(func, result, schedule, fired_at)

    async def _initialize_jobs(self) -> None:
        """Reads job specifications from disk, starts the jobs as tasks, and writes the tasks to the execution queue."""
        while True:
            wait = asyncio.create_task(asyncio.sleep(self.period.total_seconds()))

            now = datetime.now(timezone.utc)
            async with self.db_pool.connection() as db:
                # Fetch jobs that are due to be processed and are not already being processed
                cursor = await db.execute(
                    """
                    SELECT id, schedule, function_id, data, fire_at 
                    FROM cronjobs WHERE fire_at <= ? AND (runner IS NULL OR runner != ?) 
                    ORDER BY fire_at ASC
                    """,
                    (now.isoformat(), self.runner_id),
                )
                rows = await cursor.fetchall()

                if rows:
                    # Mark the jobs we're about to process with our runner_id
                    job_ids: List[str] = [row[0] for row in rows]
                    placeholders = ",".join("?" * len(job_ids))
                    await db.execute(
                        f"UPDATE cronjobs SET runner = ? WHERE id IN ({placeholders})",
                        [self.runner_id] + job_ids,
                    )
                    await db.commit()  # type: ignore

            # Start jobs as task and write them to the execution queue
            for row in rows:
                id, schedule, function_id, data, fired_at = row
                func = self.functions[function_id]
                input = func.model_type.model_validate_json(data)

                task = asyncio.create_task(
                    func(job_id=str(id), schedule=schedule, input=input)
                )
                await self.executing_jobs.put(
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
