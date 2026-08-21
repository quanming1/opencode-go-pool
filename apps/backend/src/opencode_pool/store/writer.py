"""单写线程 SQLite 落库队列（G7 FR1 + G8 FR3 有界化）。

转发热路径零阻塞：事件/用量记录只入队（submit 非阻塞返回），由专属
写线程串行执行落库；flush 阻塞到队列清空（测试/关停），close 优雅停止。

G8 资源上限（PRD-G8 FR3）：
- 队列有界（maxsize 默认 2000），满载时 submit **绝不阻塞**；
- 满载丢弃策略按 droppable 标记：新任务是可重建的成功快照（droppable）
  直接丢弃并计数；不可丢任务（失败/状态事件）驱逐队列中最旧一个
  droppable 任务腾位（无 droppable 则丢弃新任务并计数）——保证高价值
  事件优先落库，同时内存/队列不无限增长。

线程安全：唯一写线程独占 execute；读路径（stats/events 查询）经
asyncio.to_thread 与写线程共享同一 sqlite3 连接——GIL + sqlite3 模块
内部锁保证串行安全，WAL 模式读写并行。
"""

import logging
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("opencode_pool.store.writer")

_Item = tuple[Callable[..., Any], tuple[Any, ...], bool]


class SQLiteWriter:
    """把 store 写调用转成有界队列 + 单写线程异步执行（满载非阻塞丢弃）。"""

    def __init__(self, maxsize: int = 2000) -> None:
        self._maxsize = maxsize
        # 队列项：(fn, args, droppable) —— droppable 表示可重建的成功快照
        self._items: deque[_Item] = deque()
        self._cond = threading.Condition()
        self._closed = False
        self._dropped = 0
        # 队列中 + 执行中的任务数（flush 等待其归零）
        self._pending = 0
        self._thread = threading.Thread(
            target=self._worker, name="store-writer", daemon=True
        )
        self._thread.start()

    @property
    def dropped(self) -> int:
        """满载丢弃的任务总数（droppable 被丢 + 不可丢被拒），测试/日志用。"""
        with self._cond:
            return self._dropped

    def submit(self, fn: Callable[..., Any], *args: Any, droppable: bool = False) -> None:
        """非阻塞入队；满载时按 droppable 策略丢弃/驱逐，绝不阻塞调用方。"""
        with self._cond:
            if self._closed:
                # 收尾后提交：放弃（进程退出窗口，数据不保证）
                self._dropped += 1
                return
            if len(self._items) >= self._maxsize:
                if droppable:
                    self._dropped += 1
                    return
                # 不可丢任务：驱逐最旧一个 droppable 腾位（保高价值事件）
                evicted: int | None = None
                for idx, item in enumerate(self._items):
                    if item[2]:
                        evicted = idx
                        break
                if evicted is None:
                    self._dropped += 1
                    return
                del self._items[evicted]
                self._dropped += 1
                # 被驱逐任务不再执行，同步递减 pending（否则 flush 永不归零）
                self._pending -= 1
            self._items.append((fn, args, droppable))
            self._pending += 1
            self._cond.notify()

    def _worker(self) -> None:
        while True:
            with self._cond:
                while not self._items and not self._closed:
                    self._cond.wait()
                if not self._items and self._closed:
                    break
                item = self._items.popleft()
            fn, args, _ = item
            try:
                fn(*args)
            except Exception:  # noqa: BLE001 - 落库失败降级，不中断写线程
                logger.warning("[store] 异步落库失败（降级忽略）")
            finally:
                with self._cond:
                    self._pending -= 1
                    self._cond.notify_all()

    def flush(self) -> None:
        """阻塞直到队列清空（含正在执行的任务）。"""
        with self._cond:
            while self._pending > 0:
                self._cond.wait()

    def close(self, timeout: float = 5.0) -> None:
        """标记关闭并等待写线程退出（幂等；残留任务仍会被消费完）。"""
        with self._cond:
            self._closed = True
            self._cond.notify_all()
        self._thread.join(timeout)