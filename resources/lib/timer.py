import threading

import xbmc


class SafeTimer(threading.Thread):
    """Repeating timer with exception safety.

    If the callback throws, the timer keeps running instead of dying silently.
    """

    def __init__(self, interval, callback):
        super().__init__(daemon=True)
        self.interval = max(1, interval)
        self.callback = callback
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        while not self.stop_event.is_set():
            if self.stop_event.wait(self.interval):
                break
            try:
                self.callback()
            except Exception as e:
                xbmc.log('FlickList Scrobbler: Timer callback error: {}'.format(str(e)),
                          level=xbmc.LOGERROR)
