import asyncio
from contextlib import asynccontextmanager


class RWLock:
    """
    An async reader-writer lock with writer priority.

    Properties:
    - Multiple readers can hold the lock simultaneously
    - Only one writer can hold the lock at a time
    - When a writer is waiting, new readers are blocked
    - Existing readers can finish before writer takes over
    """

    def __init__(self):
        # Turnstile lock -- used for timing, not necessary for correctness
        self.read_ready = asyncio.Lock()

        # Write lock
        self.write_ready = asyncio.Lock()

        # Counter locks
        self.readers_lock = asyncio.Lock()
        self.writers_lock = asyncio.Lock()

        # Counters
        self.reader_count = 0
        self.writer_count = 0

    # Reader methods
    async def r_acquire(self):
        # Wait if any writers are waiting
        async with self.read_ready:
            pass

        # Register as a reader
        async with self.readers_lock:
            self.reader_count += 1
            if self.reader_count == 1:
                # First reader blocks writers from starting
                await self.write_ready.acquire()

    async def r_release(self):
        async with self.readers_lock:
            self.reader_count -= 1
            if self.reader_count == 0:
                # Last reader allows writers to proceed
                self.write_ready.release()

    @asynccontextmanager
    async def r_locked(self):
        """Async reader context manager for use with 'async with' statement."""
        try:
            await self.r_acquire()
            yield
        finally:
            await self.r_release()

    # Writer methods
    async def w_acquire(self):
        # Register as a waiting writer
        async with self.writers_lock:
            self.writer_count += 1
            if self.writer_count == 1:
                # First writer blocks new readers
                await self.read_ready.acquire()

        # Wait for existing readers to finish
        await self.write_ready.acquire()

    async def w_release(self):
        # Release the write lock
        self.write_ready.release()

        # Unregister as a writer
        async with self.writers_lock:
            self.writer_count -= 1
            if self.writer_count == 0:
                # Last writer allows new readers
                self.read_ready.release()

    @asynccontextmanager
    async def w_locked(self):
        """Async writer context manager for use with 'async with' statement."""
        try:
            await self.w_acquire()
            yield
        finally:
            await self.w_release()
