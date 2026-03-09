# FlickList Scrobbler Changelog

## v1.0.4
- Fixed TV episode scrobbling. Episodes now search by show name, not episode title.
- Better detection of TV episodes from addons that don't tag content properly
- Added debug logging for troubleshooting resolution issues

## v1.0.3
- Fixed title matching. Movies and shows now resolve correctly.
- Fixed settings causing errors on slider values
- Renamed client ID to fl_kodi_scrobbler

## v1.0.2
- QR code authorization. Scan to authorize instead of typing a code.
- Fixed username not showing after authorization
- Fixed QR layout so text is fully visible on screen
- Fixed zip structure for Kodi install compatibility
- Fixed plugin directory error when opening from Program add-ons
- New app icon

## v1.0.1
- Fixed compatibility with Kodi 19+ (translatePath)
- Fixed event mapping for server compatibility
- Fixed potential timer overlap on rapid pause/resume
- Fixed database connection cleanup
- Added FlickList icon
- Added Program add-ons entry for easier discovery
- Cleaned up ID alias handling

## v1.0.0
- Initial build
- Automatic scrobbling for any Kodi video addon
- Device code authorization flow
- SQLite offline queue for failed events
- Pirate addon support with ID resolution fallback
- Title and year fuzzy matching via FlickList API
- Per-event and per-media-type toggles
- Configurable heartbeat interval, min watch time, stale pause timeout
- Duplicate event filtering
- Error and scrobble notifications
