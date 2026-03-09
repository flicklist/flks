# -*- coding: utf-8 -*-
"""
Auto-updater for FlickList Kodi Scrobbler.
Checks GitHub for new versions, downloads and installs updates.
Supports prompt, automatic, notification-only, and rollback.
"""
import json
import re
import shutil
from os import path

import requests
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON_ID = 'service.flicklist.scrobbler'
GITHUB_USER = 'flicklist'
GITHUB_REPO = 'flks'
VERSION_FILE = 'flks_version'
CHANGES_FILE = 'flks_changes'
REQUEST_TIMEOUT = 15


def _log(msg):
    xbmc.log('FlickList Scrobbler Updater: {}'.format(msg), level=xbmc.LOGINFO)


def _translate(path_str):
    try:
        return xbmcvfs.translatePath(path_str)
    except AttributeError:
        return xbmc.translatePath(path_str)


def _get_base_url():
    """GitHub raw URL for the packages directory."""
    return 'https://github.com/{}/{}/raw/main/packages'.format(GITHUB_USER, GITHUB_REPO)


def _version_to_num(version_str):
    """Strip non-digit chars and compare as int. '1.0.4' -> 104."""
    return re.sub(r'[^0-9]', '', version_str)


def _current_version():
    return xbmcaddon.Addon(ADDON_ID).getAddonInfo('version')


def _unzip(zip_path, dest, dest_check):
    """Extract zip to dest. Return True if dest_check dir exists after."""
    try:
        import zipfile
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(dest)
        return path.isdir(dest_check)
    except Exception as e:
        _log('Unzip failed: {}'.format(e))
        return False


def get_versions():
    """Fetch online version string, return (current, online) or (None, None)."""
    try:
        url = '{}/{}'.format(_get_base_url(), VERSION_FILE)
        _log('Checking version at {}'.format(url))
        result = requests.get(url, timeout=REQUEST_TIMEOUT)
        if result.status_code != 200:
            _log('Version check failed: HTTP {}'.format(result.status_code))
            return None, None
        online = result.text.strip()
        current = _current_version()
        _log('Current={} Online={}'.format(current, online))
        return current, online
    except Exception as e:
        _log('Version check exception: {}'.format(e))
        return None, None


def version_check(current, online):
    """Return True if versions differ (update available)."""
    return _version_to_num(current) != _version_to_num(online)


def get_changes(online_version=None):
    """Show the online changelog in a text dialog."""
    try:
        if not online_version:
            current, online_version = get_versions()
            if not version_check(current, online_version):
                xbmcgui.Dialog().ok('FLKS Updater', 'You are running the current version. No new changelog to view.')
                return
        xbmc.executebuiltin('ActivateWindow(busydialognocancel)')
        result = requests.get('{}/{}'.format(_get_base_url(), CHANGES_FILE), timeout=REQUEST_TIMEOUT)
        xbmc.executebuiltin('Dialog.Close(busydialognocancel)')
        if result.status_code != 200:
            xbmcgui.Dialog().notification('FLKS Updater', 'Failed to fetch changelog', xbmcgui.NOTIFICATION_ERROR)
            return
        xbmcgui.Dialog().textviewer('FLKS v{} Changelog'.format(online_version), result.text)
    except Exception:
        xbmc.executebuiltin('Dialog.Close(busydialognocancel)')
        xbmcgui.Dialog().notification('FLKS Updater', 'Error fetching changelog', xbmcgui.NOTIFICATION_ERROR)


def update_check(action=4):
    """
    Check for updates and act based on action setting.
    0 = Prompt, 1 = Automatic, 2 = Notification only, 3 = Off, 4 = Manual check
    """
    _log('update_check action={}'.format(action))
    if action == 3:
        return

    current, online = get_versions()
    if not current:
        _log('get_versions failed')
        return

    if not version_check(current, online):
        if action == 4:
            xbmcgui.Dialog().ok('FLKS Updater',
                'Installed: [B]{}[/B]\nOnline: [B]{}[/B]\n\n[B]No Update Available[/B]'.format(current, online))
        return

    show_after = True
    if action in (0, 4):
        if not xbmcgui.Dialog().yesno('FLKS Updater',
                'Installed: [B]{}[/B]\nOnline: [B]{}[/B]\n\n[B]An Update is Available[/B]\nPerform Update?'.format(current, online)):
            return
        if xbmcgui.Dialog().yesno('FLKS Updater', 'View the changelog before installing?'):
            get_changes(online)
            if not xbmcgui.Dialog().yesno('FLKS Updater', 'Continue with update after viewing changes?'):
                return
            show_after = False

    if action == 1:
        xbmcgui.Dialog().notification('FLKS Updater', 'Update in progress...', xbmcgui.NOTIFICATION_INFO)
    elif action == 2:
        xbmcgui.Dialog().notification('FLKS Updater', 'Update available: v{}'.format(online), xbmcgui.NOTIFICATION_INFO)
        return

    return update_addon(online, action, show_after)


def rollback_check():
    """List available older versions from GitHub and let user pick one to install."""
    current = _current_version()
    _log('rollback_check current={}'.format(current))

    api_url = 'https://api.github.com/repos/{}/{}/contents/packages'.format(GITHUB_USER, GITHUB_REPO)
    _log('Listing packages from {}'.format(api_url))

    xbmc.executebuiltin('ActivateWindow(busydialognocancel)')
    try:
        result = requests.get(api_url, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        xbmc.executebuiltin('Dialog.Close(busydialognocancel)')
        _log('GitHub API error: {}'.format(e))
        xbmcgui.Dialog().ok('FLKS Updater', 'Error contacting GitHub.\nPlease install rollback manually.')
        return
    xbmc.executebuiltin('Dialog.Close(busydialognocancel)')

    if result.status_code != 200:
        xbmcgui.Dialog().ok('FLKS Updater', 'Error listing versions (HTTP {}).\nPlease install rollback manually.'.format(result.status_code))
        return

    files = result.json()
    prefix = '{}-'.format(ADDON_ID)
    versions = []
    for f in files:
        name = f.get('name', '')
        if name.startswith(prefix) and name.endswith('.zip'):
            ver = name[len(prefix):-4]  # strip prefix and .zip
            if ver != current:
                versions.append(ver)

    if not versions:
        xbmcgui.Dialog().ok('FLKS Updater', 'No previous versions found.\nPlease install rollback manually.')
        return

    versions.sort(reverse=True)
    choice = xbmcgui.Dialog().select('Choose Rollback Version', versions)
    if choice < 0:
        return

    rollback_version = versions[choice]
    if not xbmcgui.Dialog().yesno('FLKS Updater',
            'Are you sure?\nVersion [B]{}[/B] will overwrite your current version.\nUpdate checking will be set to OFF.'.format(rollback_version)):
        return

    update_addon(rollback_version, 5)


def update_addon(new_version, action, show_after=True):
    """Download and install a specific version."""
    xbmc.executebuiltin('Dialog.Close(all,true)')

    is_rollback = (action == 5)
    label = 'Rollback' if is_rollback else 'Update'
    xbmcgui.Dialog().notification('FLKS Updater', 'Performing {}...'.format(label.lower()), xbmcgui.NOTIFICATION_INFO)

    zip_name = '{}-{}.zip'.format(ADDON_ID, new_version)
    url = '{}/{}'.format(_get_base_url(), zip_name)
    _log('Downloading {}'.format(url))

    xbmc.executebuiltin('ActivateWindow(busydialognocancel)')
    try:
        result = requests.get(url, stream=True, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        xbmc.executebuiltin('Dialog.Close(busydialognocancel)')
        _log('Download failed: {}'.format(e))
        xbmcgui.Dialog().ok('FLKS Updater', 'Download failed.\n{}'.format(e))
        return
    xbmc.executebuiltin('Dialog.Close(busydialognocancel)')

    if result.status_code != 200:
        _log('Download HTTP {}'.format(result.status_code))
        xbmcgui.Dialog().ok('FLKS Updater', 'Download failed (HTTP {}).\nPlease install manually.'.format(result.status_code))
        return

    # Save zip to Kodi packages dir
    packages_dir = _translate('special://home/addons/packages/')
    zip_path = path.join(packages_dir, zip_name)
    _log('Saving to {}'.format(zip_path))

    try:
        with open(zip_path, 'wb') as f:
            shutil.copyfileobj(result.raw, f)
        _log('Saved {} bytes'.format(path.getsize(zip_path)))
    except Exception as e:
        _log('Save failed: {}'.format(e))
        xbmcgui.Dialog().ok('FLKS Updater', 'Failed to save update.\n{}'.format(e))
        return

    # Remove old addon directory
    addon_dir = path.join(_translate('special://home/addons/'), ADDON_ID)
    _log('Removing {}'.format(addon_dir))
    try:
        shutil.rmtree(addon_dir)
    except Exception as e:
        _log('rmtree failed: {}'.format(e))
        xbmcgui.Dialog().ok('FLKS Updater', 'Failed to remove old version.\n{}'.format(e))
        return

    # Extract new version
    dest = _translate('special://home/addons/')
    dest_check = path.join(dest, ADDON_ID)
    success = _unzip(zip_path, dest, dest_check)
    _log('Unzip success={}'.format(success))

    # Clean up zip
    try:
        import os
        os.remove(zip_path)
    except Exception:
        pass

    if not success:
        xbmcgui.Dialog().ok('FLKS Updater', 'Unzip failed.\nPlease install manually.')
        return

    # Reload addon in Kodi
    xbmc.executebuiltin('UpdateLocalAddons()')
    xbmc.sleep(1000)
    xbmc.executebuiltin('DisableAddon({})'.format(ADDON_ID))
    xbmc.sleep(500)
    xbmc.executebuiltin('EnableAddon({})'.format(ADDON_ID))

    # Post-install: notify user and handle rollback settings
    if is_rollback:
        try:
            addon = xbmcaddon.Addon(ADDON_ID)
            addon.setSetting('update.action', '3')  # set to Off after rollback
        except Exception:
            pass
        xbmcgui.Dialog().ok('FLKS Updater', 'Success.\nRolled back to version [B]{}[/B].\nUpdate checking set to OFF.'.format(new_version))
    elif action in (0, 4):
        if show_after:
            if xbmcgui.Dialog().yesno('FLKS Updater',
                    'Success.\nUpdated to version [B]{}[/B].'.format(new_version),
                    yeslabel='View Changelog', nolabel='Done'):
                changelog_path = path.join(_translate('special://home/addons/'), ADDON_ID, 'CHANGELOG.md')
                if path.exists(changelog_path):
                    with open(changelog_path, 'r') as f:
                        xbmcgui.Dialog().textviewer('FLKS Changelog', f.read())
        else:
            xbmcgui.Dialog().ok('FLKS Updater', 'Success.\nUpdated to version [B]{}[/B].'.format(new_version))
    elif action == 1:
        xbmcgui.Dialog().notification('FLKS Updater', 'Updated to v{}'.format(new_version), xbmcgui.NOTIFICATION_INFO)
