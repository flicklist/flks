import sys

import xbmcaddon
import xbmcgui
import xbmcplugin

from resources.lib.auth import handle_authorize, handle_logout


def main():
    handle = int(sys.argv[1])
    addon = xbmcaddon.Addon()
    token = addon.getSetting('token')
    username = addon.getSetting('username')

    if token:
        status = 'Authorized as {}'.format(username or 'unknown')
    else:
        status = 'Not authorized'

    options = []
    if not token:
        options.append('Authorize FlickList')
    else:
        options.append('Status: {}'.format(status))
        options.append('Logout')
    options.append('Check for Updates')
    options.append('Rollback Version')
    options.append('Settings')

    dialog = xbmcgui.Dialog()
    choice = dialog.select('FlickList Scrobbler', options)

    if choice < 0:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return

    selected = options[choice]
    if selected == 'Authorize FlickList':
        handle_authorize()
    elif selected == 'Logout':
        handle_logout()
    elif selected == 'Check for Updates':
        from resources.lib.updater import update_check
        update_check(4)
    elif selected == 'Rollback Version':
        from resources.lib.updater import rollback_check
        rollback_check()
    elif selected == 'Settings':
        addon.openSettings()

    xbmcplugin.endOfDirectory(handle, succeeded=False)


if __name__ == '__main__':
    main()
