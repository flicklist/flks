import sys
import xbmc
import xbmcaddon

from resources.lib.main_monitor import MainMonitor
from resources.lib.auth import handle_authorize, handle_logout


def main():
    # Handle script actions (authorize/logout from settings)
    if len(sys.argv) > 1:
        action = sys.argv[1].lower()
        if action == 'authorize':
            handle_authorize()
        elif action == 'logout':
            handle_logout()
        return

    addon = xbmcaddon.Addon()
    token = addon.getSetting('token')

    if not token:
        xbmc.log('FlickList Scrobbler: Not authorized. Go to Settings to authorize.', level=xbmc.LOGWARNING)

    monitor = MainMonitor()
    xbmc.log('FlickList Scrobbler v{} started'.format(addon.getAddonInfo('version')), level=xbmc.LOGINFO)
    monitor.waitForAbort()
    xbmc.log('FlickList Scrobbler stopped', level=xbmc.LOGINFO)


if __name__ == '__main__':
    main()
