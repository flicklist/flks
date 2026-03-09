import sys
import threading
import time

import xbmc
import xbmcaddon

from resources.lib.main_monitor import MainMonitor
from resources.lib.auth import handle_authorize, handle_logout


def _run_update_check():
    """Background update check, runs once per Kodi session after a delay."""
    addon = xbmcaddon.Addon()
    try:
        delay = int(addon.getSetting('update.delay') or '15')
    except (ValueError, TypeError):
        delay = 15
    try:
        action = int(addon.getSetting('update.action') or '0')
    except (ValueError, TypeError):
        action = 0

    monitor = xbmc.Monitor()
    player = xbmc.Player()

    # Wait for the configured delay
    end_time = time.time() + delay
    while time.time() < end_time:
        if monitor.waitForAbort(1):
            return

    # Wait until nothing is playing
    while player.isPlayingVideo():
        if monitor.waitForAbort(1):
            return

    from resources.lib.updater import update_check
    update_check(action)


def main():
    # Handle script actions (authorize/logout/update from settings)
    if len(sys.argv) > 1:
        action = sys.argv[1].lower()
        if action == 'authorize':
            handle_authorize()
        elif action == 'logout':
            handle_logout()
        elif action == 'update_check':
            from resources.lib.updater import update_check
            update_check(4)  # 4 = manual check
        elif action == 'rollback':
            from resources.lib.updater import rollback_check
            rollback_check()
        return

    addon = xbmcaddon.Addon()
    token = addon.getSetting('token')

    if not token:
        xbmc.log('FlickList Scrobbler: Not authorized. Go to Settings to authorize.', level=xbmc.LOGWARNING)

    monitor = MainMonitor()
    xbmc.log('FlickList Scrobbler v{} started'.format(addon.getAddonInfo('version')), level=xbmc.LOGINFO)

    # Start background update check (once per session)
    threading.Thread(target=_run_update_check, daemon=True).start()

    monitor.waitForAbort()
    xbmc.log('FlickList Scrobbler stopped', level=xbmc.LOGINFO)


if __name__ == '__main__':
    main()
