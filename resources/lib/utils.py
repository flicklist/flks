import json

import xbmc


# Supported ID types per media type
SUPPORTED_IDS = {
    'movie': {'imdb', 'tmdb', 'tvdb'},
    'episode': {'imdb', 'tmdb', 'tvdb'},
}

# Common aliases used by various Kodi addons
ID_ALIASES = {
    'imdbnumber': 'imdb',
    'imdb_id': 'imdb',
    'themoviedb': 'tmdb',
    'tmdb_id': 'tmdb',
    'tvdb_id': 'tvdb',
    'thetvdb': 'tvdb',
}


def jsonrpc_request(method, params=None):
    """Send a JSON-RPC request to Kodi."""
    request = {'jsonrpc': '2.0', 'method': method, 'id': 1}
    if params is not None:
        request['params'] = params

    request_json = json.dumps(request)
    response_json = xbmc.executeJSONRPC(request_json)
    return json.loads(response_json).get('result', {})


def resolve_ids(unique_ids, media_type):
    """Normalize Kodi uniqueid dict into canonical ID map.

    Handles all the weird formats pirate addons use:
    - Standard: {'tmdb': '12345', 'imdb': 'tt1234567'}
    - Aliased:  {'imdbnumber': 'tt1234567', 'themoviedb': '12345'}
    - Unknown:  {'unknown': 'tt1234567'} or {'unknown': '12345'}
    """
    if not isinstance(unique_ids, dict):
        return {}

    canonical = {}

    for raw_key, raw_value in unique_ids.items():
        if raw_value in (None, ''):
            continue

        key = str(raw_key).strip().lower()
        key = ID_ALIASES.get(key, key)

        if key == 'unknown':
            continue

        canonical[key] = raw_value

    # Fallback: if no recognized IDs, try to parse 'unknown'
    if not canonical and 'unknown' in unique_ids:
        unknown_val = unique_ids['unknown']
        mapped_key, mapped_value = _coerce_unknown_id(unknown_val, media_type)
        if mapped_key:
            canonical[mapped_key] = mapped_value

    # Filter to supported IDs only
    allowed = SUPPORTED_IDS.get(media_type, set())
    filtered = {k: v for k, v in canonical.items() if k in allowed}

    return filtered


def _coerce_unknown_id(value, media_type):
    """Try to identify what an 'unknown' ID actually is."""
    if value is None:
        return None, None

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None, None
        if cleaned.startswith('tt'):
            return 'imdb', cleaned
        if cleaned.isdigit():
            return ('tvdb', cleaned) if media_type == 'episode' else ('tmdb', cleaned)
        return None, None

    if isinstance(value, int):
        return ('tvdb', value) if media_type == 'episode' else ('tmdb', value)

    return None, None


def get_title_year_fallback(video_info):
    """Extract title and year from video info for fuzzy matching.

    Used when no recognized IDs are available (common with pirate addons
    that only set display title and no metadata tags).
    """
    title = (
        video_info.get('originaltitle')
        or video_info.get('title')
        or video_info.get('showtitle')
        or video_info.get('label')
        or ''
    ).strip()

    year = video_info.get('year')
    if not year or year == 0:
        # Try to extract from premiered/firstaired
        for field in ('premiered', 'firstaired'):
            date_str = video_info.get(field, '')
            if date_str and len(date_str) >= 4:
                try:
                    year = int(date_str[:4])
                except (ValueError, TypeError):
                    pass
                if year:
                    break

    return title, year if year and year > 0 else None
