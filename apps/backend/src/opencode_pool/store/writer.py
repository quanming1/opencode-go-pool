"""单写线程 SQLite 落库队列（G7 FR1）。

转发热路径零阻塞：事件/用量记录只入队（submit 非阻塞返回），由专属
写线程串行执行落库；flush 阻塞到队列清空（测试/关停），close 优雅停止。

线程安全：唯一写线程独占 execute；读路径（stats/events 查询）经
asyncio.to_thread 与写线程共享同一 sqlite3 连接——GIL + sqlite3 模块
内部锁保证串行安全，WAL 模式读写并行。
"""

import logging
import queue
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("opencode_pool.store.writer")

_SENTINEL: Any = None


class SQLiteWriter:
    """把 store 写调用转成队列 + 单写线程异步执行。"""

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[Callable[..., Any], tuple[Any, ...]] | None] = (
            queue.Queue()
        )
        self._thread = threading.Thread(
            target=self._worker, name="store-writer", daemon=True
        )
        self._thread.start()

    def submit(self, fn: Callable[..., Any], *args: Any) -> None:
        """非阻塞入队（队列无限大，不抛）。"""
        self._queue.put((fn, args))

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                break
            fn, args = item
            try:
                fn(*args)
            except Exception:  # noqa: BLE001 - 落库失败降级，不中断写线程
                logger.warning("[store] 异步落库失败（降级忽略）")
            finally:
                self._queue.task_done()

    def flush(self) -> None:
        """阻塞直到队列清空（含正在执行的任务）。"""
        self._queue.join()

    def close(self, timeout: float = 5.0) -> None:
        """发送停止哨兵并等待写线程退出（幂等）。"""
        self._queue.put(None)
        self._thread.join(timeout)