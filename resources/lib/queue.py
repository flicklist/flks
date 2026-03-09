import json
import os
import sqlite3
import time

import requests
import xbmc
import xbmcaddon
import xbmcvfs


REQUEST_TIMEOUT = 10
DB_NAME = 'fl_kodi_scrobbler_queue.db'


class EventQueue:
    """SQLite-backed offline queue for failed scrobble events.

    Events that fail to send (network down, API error, no token) get
    stored locally and retried on the next successful API call.
    """

    def __init__(self):
        self._db_path = None
        self._ensure_db()

    def _get_db_path(self):
        if self._db_path:
            return self._db_path
        addon = xbmcaddon.Addon()
        try:
            profile = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
        except AttributeError:
            profile = xbmc.translatePath(addon.getAddonInfo('profile'))
        if not os.path.exists(profile):
            os.makedirs(profile)
        self._db_path = os.path.join(profile, DB_NAME)
        return self._db_path

    def _ensure_db(self):
        try:
            conn = sqlite3.connect(self._get_db_path())
            conn.execute('''
                CREATE TABLE IF NOT EXISTS event_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    attempts INTEGER DEFAULT 0
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            xbmc.log('FlickList Scrobbler: Queue DB init failed: {}'.format(str(e)),
                      level=xbmc.LOGERROR)

    def enqueue(self, payload):
        """Store a failed event for later retry."""
        try:
            # Check max queue size
            addon = xbmcaddon.Addon()
            try:
                max_queue = int(addon.getSetting('retry.max_queue') or '500')
            except (ValueError, TypeError):
                max_queue = 500

            conn = sqlite3.connect(self._get_db_path())
            try:
                count = conn.execute('SELECT COUNT(*) FROM event_queue').fetchone()[0]
                if count >= max_queue:
                    # Drop oldest entries to make room
                    drop_count = count - max_queue + 1
                    conn.execute('''
                        DELETE FROM event_queue WHERE id IN (
                            SELECT id FROM event_queue ORDER BY id ASC LIMIT ?
                        )
                    ''', (drop_count,))

                conn.execute(
                    'INSERT INTO event_queue (payload, created_at) VALUES (?, ?)',
                    (json.dumps(payload), time.time())
                )
                conn.commit()
            finally:
                conn.close()
            xbmc.log('FlickList Scrobbler: Queued event for retry', level=xbmc.LOGDEBUG)
        except Exception as e:
            xbmc.log('FlickList Scrobbler: Failed to queue event: {}'.format(str(e)),
                      level=xbmc.LOGERROR)

    def flush(self, token, api_url):
        """Send all queued events. Called after a successful live send."""
        try:
            addon = xbmcaddon.Addon()
            try:
                retry_enabled = addon.getSetting('retry.enabled')
                if retry_enabled and retry_enabled.lower() == 'false':
                    return
            except Exception:
                pass

            conn = sqlite3.connect(self._get_db_path())
            try:
                rows = conn.execute(
                    'SELECT id, payload, attempts FROM event_queue ORDER BY id ASC LIMIT 50'
                ).fetchall()

                if not rows:
                    return

                url = '{}/scrobble/event'.format(api_url)
                sent_ids = []

                for row_id, payload_json, attempts in rows:
                    try:
                        payload = json.loads(payload_json)
                        resp = requests.post(
                            url,
                            json=payload,
                            headers={
                                'Authorization': 'Bearer {}'.format(token),
                                'Content-Type': 'application/json',
                                'X-Scrobbler-Source': 'fl_kodi_scrobbler',
                            },
                            timeout=REQUEST_TIMEOUT,
                        )
                        if resp.status_code < 400:
                            sent_ids.append(row_id)
                        elif resp.status_code == 401:
                            # Token invalid, stop flushing
                            break
                        else:
                            # Server error, increment attempts but keep in queue
                            conn.execute(
                                'UPDATE event_queue SET attempts = ? WHERE id = ?',
                                (attempts + 1, row_id)
                            )
                    except requests.exceptions.RequestException:
                        # Network still down, stop flushing
                        break

                if sent_ids:
                    placeholders = ','.join('?' * len(sent_ids))
                    conn.execute(
                        'DELETE FROM event_queue WHERE id IN ({})'.format(placeholders),
                        sent_ids
                    )
                    xbmc.log('FlickList Scrobbler: Flushed {} queued events'.format(len(sent_ids)),
                              level=xbmc.LOGINFO)

                # Purge events older than 7 days
                cutoff = time.time() - (7 * 24 * 3600)
                conn.execute('DELETE FROM event_queue WHERE created_at < ?', (cutoff,))

                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            xbmc.log('FlickList Scrobbler: Queue flush failed: {}'.format(str(e)),
                      level=xbmc.LOGERROR)

    def count(self):
        try:
            conn = sqlite3.connect(self._get_db_path())
            try:
                return conn.execute('SELECT COUNT(*) FROM event_queue').fetchone()[0]
            finally:
                conn.close()
        except Exception:
            return 0
