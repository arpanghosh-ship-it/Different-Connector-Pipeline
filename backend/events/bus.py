import asyncio
from typing import List

_listeners: List[asyncio.Queue] = []

def add_listener() -> asyncio.Queue:
    q = asyncio.Queue(maxsize=200)
    _listeners.append(q)
    return q

def remove_listener(q: asyncio.Queue):
    if q in _listeners:
        _listeners.remove(q)

async def broadcast(event: dict):
    dead = []
    for q in _listeners:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        if q in _listeners:
            _listeners.remove(q)

def listener_count() -> int:
    return len(_listeners)