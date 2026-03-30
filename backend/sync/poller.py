from apscheduler.schedulers.asyncio import AsyncIOScheduler
from events.bus import broadcast

scheduler = AsyncIOScheduler()
_root_folder_id: str | None = None
_root_folder_name: str = ""
_paused: bool = False

async def _poll_job():
    if not _root_folder_id or _paused:
        return
    from sync.crawler import start_crawl, is_crawling
    if is_crawling():
        await broadcast({"type": "poll_skip", "reason": "Crawl already in progress"})
        return
    await broadcast({"type": "poll_start"})
    await start_crawl(_root_folder_id, _root_folder_name)
    await broadcast({"type": "poll_complete"})

def start_poller(folder_id: str, folder_name: str = ""):
    global _root_folder_id, _root_folder_name, _paused
    _root_folder_id = folder_id
    _root_folder_name = folder_name
    _paused = False

    if scheduler.get_job("drive_poller"):
        scheduler.remove_job("drive_poller")

    scheduler.add_job(_poll_job, "interval", seconds=30, id="drive_poller", replace_existing=True)

    if not scheduler.running:
        scheduler.start()

def pause_poller():
    global _paused
    _paused = True

def resume_poller():
    global _paused
    _paused = False

def stop_poller():
    if scheduler.running:
        scheduler.shutdown(wait=False)

def is_polling() -> bool:
    return scheduler.running and scheduler.get_job("drive_poller") is not None and not _paused