import xbmc

from resources.lib.player_monitor import PlayerMonitor
from resources.lib.queue import EventQueue


class MainMonitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.queue = EventQueue()
        self.player_monitor = PlayerMonitor(self.queue)

    def onSettingsChanged(self):
        self.player_monitor.load_settings()
