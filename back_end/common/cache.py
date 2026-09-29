"""服务端内存缓存 + single-flight（合并并发请求）工具。

用于全球市场等高频轮询接口：多个客户端在 TTL 窗口内共享同一份数据源结果，
并对「无缓存时的并发请求」做去重——只有第一个请求真正访问数据源，
其余请求等待同一结果，数据源返回后一并返回给所有等待者。

不做多源兜底：loader 失败即抛出异常，缓存不更新，本批请求（leader + 等待者）都失败。
"""
import threading
import time


class _Flight:
    """一次进行中的数据源请求（single-flight 载体）"""
    __slots__ = ('done', 'data', 'error')

    def __init__(self):
        self.done = threading.Event()
        self.data = None
        self.error = None


_cache = {}      # key -> {'data': ..., 'ts': 写入时间戳}
_flights = {}    # key -> _Flight（进行中的请求）
_lock = threading.Lock()


def cached_singleflight(key, loader, ttl=30):
    """带 TTL 的 single-flight 缓存。

    - 命中且未过期：直接返回缓存数据（不访问数据源）。
    - 未命中/已过期：第一个调用成为 leader 访问数据源，其余并发调用等待同一结果；
      数据源返回后一并返回给所有等待者。
    - loader 抛异常：缓存不更新，leader 与等待者都收到该异常。
    """
    now = time.time()
    with _lock:
        entry = _cache.get(key)
        if entry is not None and now - entry['ts'] < ttl:
            return entry['data']
        flight = _flights.get(key)
        if flight is None:
            flight = _Flight()
            _flights[key] = flight
            is_leader = True
        else:
            is_leader = False

    if is_leader:
        try:
            flight.data = loader()
        except Exception as e:
            flight.error = e
        with _lock:
            if flight.error is None:
                _cache[key] = {'data': flight.data, 'ts': time.time()}
            _flights.pop(key, None)
        flight.done.set()
    else:
        if not flight.done.wait(timeout=20):
            raise RuntimeError(f'等待数据源响应超时: {key}')

    if flight.error is not None:
        raise flight.error
    return flight.data
