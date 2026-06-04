# run.py
from app import create_app
import fcntl
import logging
import os

app = create_app()
logger = logging.getLogger(__name__)

_background_lock_fh = None


def _acquire_background_lock() -> bool:
    """
    Ensure background threads start in only one OS process.

    - Gunicorn: prevents each worker from running its own fetch loop.
    - Flask reloader: must be combined with WERKZEUG_RUN_MAIN guard so the
      reloader parent doesn't steal the lock from the serving child.
    """
    global _background_lock_fh

    if _background_lock_fh is not None:
        return True

    lock_path = os.environ.get("INDICATOR_API_BG_LOCK", "/tmp/indicator_api_bg.lock")
    lock_fh = open(lock_path, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _background_lock_fh = lock_fh
        return True
    except BlockingIOError:
        lock_fh.close()
        return False

def start_background_services():
    """
    Start all background threads/services.
    Called per worker process (Gunicorn or dev server).
    """
    if os.environ.get("DISABLE_BACKGROUND_SERVICES", "").lower() in {"1", "true", "yes"}:
        logger.info("Background services disabled via DISABLE_BACKGROUND_SERVICES")
        return

    if not _acquire_background_lock():
        logger.info("Background services already running (lock held), skipping startup")
        return

    from services.unified_data_service import start_unified_data_service
    start_unified_data_service()

# Dev server
if __name__ == "__main__":
    # When debug reloader is enabled, only start background services in the
    # reloader child process (WERKZEUG_RUN_MAIN=true).
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_background_services()
    app.run(host="0.0.0.0", port=5001, debug=True)

# Gunicorn import: start background threads automatically per worker
else:
    start_background_services()
