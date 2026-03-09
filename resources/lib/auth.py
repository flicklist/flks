import os
import sys
import time

import requests
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

# Ensure resources/lib is on path for bundled segno
_lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '')
if _lib_path not in sys.path:
    sys.path.insert(0, _lib_path)
_parent_lib = os.path.dirname(os.path.abspath(__file__))
if _parent_lib not in sys.path:
    sys.path.insert(0, _parent_lib)


REQUEST_TIMEOUT = 15
POLL_INTERVAL = 5  # seconds between token polls
POLL_TIMEOUT = 300  # 5 minutes max wait


def _make_qrcode(url):
    """Generate QR code PNG, return file path or None."""
    try:
        import segno
    except ImportError:
        xbmc.log('FlickList Scrobbler: segno not found', xbmc.LOGERROR)
        return None
    try:
        profile = xbmcvfs.translatePath('special://profile/')
    except AttributeError:
        profile = xbmc.translatePath('special://profile/')
    art_path = os.path.join(profile, 'fl_kodi_scrobbler_qr.png')
    try:
        qr = segno.make(url, micro=False)
        qr.save(art_path, scale=20)
        return art_path
    except Exception:
        return None


class _QRWindow(xbmcgui.WindowDialog):
    """Full-screen QR code + user code. Press Back to cancel."""

    def __init__(self, qr_path, user_code, url):
        super(_QRWindow, self).__init__()
        W = 1920
        self.addControl(xbmcgui.ControlImage(0, 0, W, 1080, '', colorDiffuse='CC000000'))

        # QR code on the right side of center
        qr_sz = 300
        qr_x = 1020
        qr_y = 280
        self.addControl(xbmcgui.ControlImage(qr_x, qr_y, qr_sz, qr_sz, qr_path))

        # Text labels to the left of QR, right-aligned flush toward it
        txt_x = 100
        txt_w = qr_x - txt_x - 60  # 60px gap before QR
        self.addControl(xbmcgui.ControlLabel(txt_x, 320, txt_w, 50,
                        'Scan the QR code', font='font13', textColor='FFFFFFFF', alignment=5))
        self.addControl(xbmcgui.ControlLabel(txt_x, 390, txt_w, 40,
                        'or go to {} and enter:'.format(url), textColor='FFAAAAAA', alignment=5))
        self.addControl(xbmcgui.ControlLabel(txt_x, 450, txt_w, 80,
                        user_code, font='font30', textColor='FF22D3A7', alignment=5))

        # Waiting + cancel below everything, centered
        self.addControl(xbmcgui.ControlLabel(0, 660, W, 40,
                        'Waiting for authorization...', textColor='FF888888', alignment=6))
        self.addControl(xbmcgui.ControlLabel(0, 710, W, 40,
                        'Press Back to cancel', textColor='FF666666', alignment=6))
        self.cancelled = False

    def onAction(self, action):
        if action.getId() in (10, 92):
            self.cancelled = True
            self.close()


def handle_authorize():
    """Device code auth flow. Shows QR code + user code dialog."""
    addon = xbmcaddon.Addon()
    api_url = (addon.getSetting('api_url') or 'https://flicklist.tv/api').rstrip('/')

    try:
        resp = requests.post(
            '{}/auth/device/code'.format(api_url),
            json={'client_id': 'fl_kodi_scrobbler'},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            xbmcgui.Dialog().ok('FlickList Scrobbler', 'Failed to get device code. Try again later.')
            return
        data = resp.json()
    except Exception:
        xbmcgui.Dialog().ok('FlickList Scrobbler', 'Could not reach FlickList. Check your connection.')
        return

    device_code = data.get('device_code', '')
    user_code = data.get('user_code', '')
    verification_uri = 'https://flicklist.tv/link'
    expires_in = data.get('expires_in', POLL_TIMEOUT)
    auth_url = '{}?code={}'.format(verification_uri, user_code)

    qr_path = _make_qrcode(auth_url)

    # QR window if image generated, text fallback otherwise
    window = None
    progress = None
    if qr_path:
        window = _QRWindow(qr_path, user_code, verification_uri)
        window.show()
    else:
        progress = xbmcgui.DialogProgress()
        progress.create('FlickList Scrobbler',
                        'Go to: {}\n\nEnter code: {}'.format(verification_uri, user_code))

    monitor = xbmc.Monitor()
    start_time = time.time()
    while True:
        if monitor.abortRequested():
            break
        if window and window.cancelled:
            break
        if progress and progress.iscanceled():
            break

        elapsed = time.time() - start_time
        if elapsed > expires_in:
            if window: window.close()
            if progress: progress.close()
            xbmcgui.Dialog().ok('FlickList Scrobbler', 'Authorization timed out. Try again.')
            return

        if progress:
            progress.update(int((elapsed / expires_in) * 100))

        if monitor.waitForAbort(POLL_INTERVAL):
            break

        try:
            token_resp = requests.post(
                '{}/auth/device/token'.format(api_url),
                json={'client_id': 'fl_kodi_scrobbler', 'device_code': device_code},
                timeout=REQUEST_TIMEOUT,
            )
            if token_resp.status_code == 200:
                token_data = token_resp.json()
                access_token = token_data.get('access_token', '')
                if access_token:
                    addon.setSetting('token', access_token)
                    # Token response doesn't include username, fetch from /auth/me
                    username = ''
                    try:
                        me_resp = requests.get(
                            '{}/auth/me'.format(api_url),
                            headers={'Authorization': 'Bearer {}'.format(access_token)},
                            timeout=REQUEST_TIMEOUT,
                        )
                        if me_resp.status_code == 200:
                            me_data = me_resp.json()
                            username = me_data.get('username', me_data.get('display_name', ''))
                    except Exception:
                        pass
                    addon.setSetting('username', username)
                    addon.setSetting('status', 'Authorized as {}'.format(username))
                    if window: window.close()
                    if progress: progress.close()
                    xbmcgui.Dialog().ok('FlickList Scrobbler',
                                        'Authorized as {}!'.format(username))
                    return
        except Exception:
            pass

    if window: window.close()
    if progress: progress.close()


def handle_logout():
    """Clear stored credentials."""
    addon = xbmcaddon.Addon()
    addon.setSetting('token', '')
    addon.setSetting('username', '')
    addon.setSetting('status', 'Not authorized')
    xbmcgui.Dialog().ok('FlickList Scrobbler', 'Logged out.')
