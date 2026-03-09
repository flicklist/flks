import time

import requests
import xbmc
import xbmcaddon

from resources.lib.timer import SafeTimer
from resources.lib.utils import jsonrpc_request, resolve_ids, get_title_year_fallback
from resources.lib.queue import EventQueue


REQUEST_TIMEOUT = 10
SOURCE_ID = 'fl_kodi_scrobbler'
DEDUP_WINDOW = 5  # seconds

# Server only accepts these 4 events. Map client-side names to valid server values.
SERVER_EVENT_MAP = {
    'start': 'start',
    'pause': 'pause',
    'stop': 'stop',
    'heartbeat': 'heartbeat',
    'resume': 'heartbeat',   # resume = progress update, not a distinct server event
    'seek': 'heartbeat',     # seek = progress update at new position
    'end': 'stop',           # natural playback end = stop
}


class PlayerMonitor(xbmc.Player):
    def __init__(self, queue):
        super().__init__()

        self.queue = queue
        self.settings = None
        self.heartbeat_timer = None

        self.total_time = None
        self.current_time = None
        self.playback_start_time = None
        self.session_active = False

        self.video_info = {}
        self.resolved_media = {}  # tmdb_id, media_type, season, episode
        self.last_event = None
        self.last_event_time = 0

        self.load_settings()

    def load_settings(self):
        self.settings = xbmcaddon.Addon().getSettings()

    def notify(self, message):
        jsonrpc_request('GUI.ShowNotification', {
            'title': 'FlickList Scrobbler',
            'message': message
        })

    def get_api_url(self):
        addon = xbmcaddon.Addon()
        url = addon.getSetting('api_url') or 'https://flicklist.tv/api'
        return url.rstrip('/')

    def get_token(self):
        return xbmcaddon.Addon().getSetting('token')

    def is_dedup(self, event):
        """Skip duplicate events for the same item within DEDUP_WINDOW seconds."""
        now = time.time()
        tmdb_id = self.resolved_media.get('tmdb_id')
        key = '{}:{}:{}'.format(event, tmdb_id, self.resolved_media.get('episode'))
        if key == self.last_event and (now - self.last_event_time) < DEDUP_WINDOW:
            return True
        self.last_event = key
        self.last_event_time = now
        return False

    def meets_min_watch_time(self):
        """Check if we've watched long enough to bother scrobbling."""
        if self.playback_start_time is None:
            return False
        try:
            min_secs = int(self.settings.getSetting('min_watch_seconds') or 30)
        except Exception:
            min_secs = 30
        elapsed = time.time() - self.playback_start_time
        return elapsed >= min_secs

    def is_stale_pause(self):
        """Check if we've been paused too long (treat resume as new start)."""
        if self.last_event_time == 0:
            return False
        try:
            hours = int(self.settings.getSetting('stale_pause_hours') or 4)
        except Exception:
            hours = 4
        return (time.time() - self.last_event_time) > (hours * 3600)

    def build_payload(self, event):
        if not self.resolved_media.get('tmdb_id'):
            return None

        media_type = self.resolved_media.get('media_type')
        try:
            if not self.settings.getBool('mediatype.{}'.format(media_type)):
                return None
        except TypeError:
            return None

        total_time = self.getTotalTime() if self.isPlaying() else self.total_time
        current_time = self.getTime() if self.isPlaying() else self.current_time

        if total_time and total_time > 0 and current_time is not None:
            progress = round((current_time / total_time) * 100, 2)
        else:
            progress = 0.0

        server_event = SERVER_EVENT_MAP.get(event, event)

        payload = {
            'tmdb_id': self.resolved_media['tmdb_id'],
            'media_type': media_type,
            'event': server_event,
            'progress': max(0.0, min(100.0, progress)),
            'source': SOURCE_ID,
        }

        if total_time and total_time > 0:
            payload['duration'] = int(total_time)
        if current_time is not None and current_time >= 0:
            payload['current_time'] = int(current_time)

        if media_type == 'episode':
            season = self.resolved_media.get('season')
            episode = self.resolved_media.get('episode')
            if season is not None:
                payload['season'] = season
            if episode is not None:
                payload['episode'] = episode

        return payload

    def send_event(self, event):
        # Check if this event type is enabled
        event_setting = event
        if event == 'heartbeat':
            event_setting = 'heartbeat'
        try:
            if not self.settings.getBool('event.{}'.format(event_setting)):
                return
        except TypeError:
            pass

        # Dedup check
        if self.is_dedup(event):
            xbmc.log('FlickList Scrobbler: Dedup skip {} for tmdb:{}'.format(
                event, self.resolved_media.get('tmdb_id')), level=xbmc.LOGDEBUG)
            return

        # Min watch time filter: only send start after threshold
        if event == 'start' and not self.meets_min_watch_time():
            # Don't skip start entirely, but delay. We'll re-send on first heartbeat
            # if the threshold is met by then.
            pass

        payload = self.build_payload(event)
        if not payload:
            return

        token = self.get_token()
        if not token:
            xbmc.log('FlickList Scrobbler: No token, queuing event', level=xbmc.LOGDEBUG)
            self.queue.enqueue(payload)
            return

        url = '{}/scrobble/event'.format(self.get_api_url())

        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    'Authorization': 'Bearer {}'.format(token),
                    'Content-Type': 'application/json',
                    'X-Scrobbler-Source': SOURCE_ID,
                },
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code == 401:
                xbmc.log('FlickList Scrobbler: Token expired or invalid', level=xbmc.LOGWARNING)
                if self._should_notify('errors'):
                    self.notify('Authorization expired. Re-authorize in Settings.')
                return
            if response.status_code >= 400:
                xbmc.log('FlickList Scrobbler: API error {} on {}'.format(
                    response.status_code, event), level=xbmc.LOGERROR)
                self.queue.enqueue(payload)
                return

            # Successful send. Flush any queued events.
            self.queue.flush(token, self.get_api_url())

            # Notify on scrobble completion
            if event in ('stop', 'end') and self._should_notify('scrobble'):
                title = self.resolved_media.get('title', 'Unknown')
                progress = payload.get('progress', 0)
                if progress >= 85:
                    self.notify('Scrobbled: {}'.format(title))

        except requests.exceptions.RequestException as e:
            xbmc.log('FlickList Scrobbler: Request failed: {}'.format(str(e)), level=xbmc.LOGERROR)
            self.queue.enqueue(payload)
        except Exception as e:
            xbmc.log('FlickList Scrobbler: Unexpected error: {}'.format(str(e)), level=xbmc.LOGERROR)

    def _should_notify(self, category):
        try:
            return self.settings.getBool('notify.{}'.format(category))
        except Exception:
            return True

    def fetch_and_resolve(self):
        """Fetch video info from Kodi and resolve to tmdb_id + media_type."""
        try:
            self.video_info = jsonrpc_request('Player.GetItem', {
                'playerid': 1,
                'properties': [
                    'tvshowid', 'showtitle', 'season', 'episode',
                    'firstaired', 'premiered', 'year', 'uniqueid',
                    'title', 'originaltitle',
                ]
            }).get('item', {})
        except Exception:
            self.video_info = {}

        if not self.video_info:
            self.resolved_media = {}
            return

        raw_type = self.video_info.get('type', '')
        showtitle = (self.video_info.get('showtitle') or '').strip()
        season = self.video_info.get('season')
        episode_num = self.video_info.get('episode')

        # Detect episodes even when pirate addons report type='video'
        is_episode = raw_type == 'episode' or (
            showtitle and season is not None and season >= 0
            and episode_num is not None and episode_num > 0
        )
        media_type = 'episode' if is_episode else ('movie' if raw_type != 'episode' else raw_type)

        xbmc.log('FlickList Scrobbler: raw_type={}, detected={}, uniqueid={}, showtitle={}, title={}, season={}, episode={}'.format(
            raw_type, media_type,
            self.video_info.get('uniqueid', {}),
            showtitle,
            self.video_info.get('title', ''),
            season, episode_num,
        ), level=xbmc.LOGWARNING)

        # Try to get IDs from Kodi metadata
        unique_ids = self.video_info.get('uniqueid', {})

        # For episodes, also grab show-level IDs
        if is_episode:
            tvshow_id = self.video_info.get('tvshowid', -1)
            if tvshow_id > 0:
                try:
                    show_info = jsonrpc_request('VideoLibrary.GetTVShowDetails', {
                        'tvshowid': tvshow_id,
                        'properties': ['uniqueid']
                    }).get('tvshowdetails', {})
                    show_ids = show_info.get('uniqueid', {})
                    # Show IDs take priority for show-level resolution
                    unique_ids = {**unique_ids, **show_ids}
                except Exception:
                    pass

        resolved = resolve_ids(unique_ids, media_type)
        tmdb_id = resolved.get('tmdb')

        # Fallback: title + year matching (for pirate addons with no metadata IDs)
        if not tmdb_id:
            # For episodes, search by show name, not episode title
            if is_episode and showtitle:
                search_title = showtitle
            else:
                search_title, _ = get_title_year_fallback(self.video_info)
            _, year = get_title_year_fallback(self.video_info)
            if search_title:
                xbmc.log('FlickList Scrobbler: title fallback search="{}" year={} type={}'.format(
                    search_title, year, 'tv' if is_episode else 'movie'), level=xbmc.LOGWARNING)
                tmdb_id = self._lookup_tmdb_by_title(search_title, year, media_type)

        if not tmdb_id:
            xbmc.log('FlickList Scrobbler: Could not resolve tmdb_id for "{}"'.format(
                self.video_info.get('label', 'unknown')), level=xbmc.LOGWARNING)
            self.resolved_media = {}
            return

        self.resolved_media = {
            'tmdb_id': int(tmdb_id),
            'media_type': media_type,
            'season': season,
            'episode': episode_num,
            'title': showtitle or self.video_info.get('title') or self.video_info.get('label', ''),
        }

    def _lookup_tmdb_by_title(self, title, year, media_type):
        """Ask FlickList API to fuzzy-match a title to a tmdb_id."""
        token = self.get_token()
        if not token:
            return None

        search_type = 'tv' if media_type == 'episode' else 'movie'
        url = '{}/search?q={}&type={}'.format(self.get_api_url(), requests.utils.quote(title), search_type)

        try:
            resp = requests.get(url, headers={
                'Authorization': 'Bearer {}'.format(token),
            }, timeout=REQUEST_TIMEOUT)
            xbmc.log('FlickList Scrobbler: search url={} status={}'.format(url, resp.status_code), level=xbmc.LOGWARNING)
            if resp.status_code != 200:
                xbmc.log('FlickList Scrobbler: search error body={}'.format(resp.text[:500]), level=xbmc.LOGWARNING)
                return None
            results = resp.json()
            xbmc.log('FlickList Scrobbler: search returned {} results, first={}'.format(
                len(results) if isinstance(results, list) else type(results).__name__,
                str(results[0])[:200] if isinstance(results, list) and results else 'none'
            ), level=xbmc.LOGWARNING)
            if not results:
                return None
            # Return the first result's tmdb_id. If year is available, prefer a year match.
            if isinstance(results, list):
                for r in results:
                    r_year = r.get('year') or r.get('first_air_date', '')[:4]
                    if year and str(r_year) == str(year):
                        return r.get('tmdb_id') or r.get('id')
                return results[0].get('tmdb_id') or results[0].get('id')
            return None
        except Exception as e:
            xbmc.log('FlickList Scrobbler: Title lookup failed: {}'.format(str(e)), level=xbmc.LOGWARNING)
            return None

    def start_heartbeat(self):
        self.stop_heartbeat()
        try:
            interval = int(self.settings.getSetting('interval') or 30)
        except Exception:
            interval = 30
        self.heartbeat_timer = SafeTimer(interval, self.on_heartbeat)
        self.heartbeat_timer.start()

    def stop_heartbeat(self):
        if self.heartbeat_timer and self.heartbeat_timer.is_alive():
            self.heartbeat_timer.stop()

    def update_time(self):
        if self.isPlaying():
            try:
                self.total_time = self.getTotalTime()
                self.current_time = self.getTime()
            except Exception:
                pass

    # ── Kodi Player Callbacks ────────────────────────────────────────

    def onAVStarted(self):
        self.playback_start_time = time.time()
        self.session_active = True
        self.fetch_and_resolve()
        self.update_time()
        self.send_event('start')
        self.start_heartbeat()

    def onPlayBackPaused(self):
        if not self.resolved_media or not self.session_active:
            return
        self.update_time()
        self.send_event('pause')
        self.stop_heartbeat()

    def onPlayBackResumed(self):
        if not self.resolved_media or not self.session_active:
            return
        if self.is_stale_pause():
            # Treat as new session
            self.playback_start_time = time.time()
            self.send_event('start')
        else:
            self.send_event('resume')
        self.start_heartbeat()

    def onPlayBackStopped(self):
        if not self.resolved_media or not self.session_active:
            return
        self.update_time()
        if self.meets_min_watch_time():
            self.send_event('stop')
        self.stop_heartbeat()
        self.session_active = False

    def onPlayBackEnded(self):
        if not self.resolved_media or not self.session_active:
            return
        self.update_time()
        if self.meets_min_watch_time():
            self.send_event('end')
        self.stop_heartbeat()
        self.session_active = False

    def onPlayBackSeek(self, time_ms, seekOffset):
        if not self.resolved_media or not self.session_active:
            return
        self.update_time()
        self.send_event('seek')

    def onPlayBackSeekChapter(self, chapter):
        if not self.resolved_media or not self.session_active:
            return
        self.update_time()
        self.send_event('seek')

    def on_heartbeat(self):
        if not self.resolved_media or not self.session_active:
            return
        self.update_time()
        self.send_event('heartbeat')
