# FlickList Scrobbler for Kodi

Automatically track what you watch in Kodi with [FlickList](https://flicklist.tv). Works with any video addon.

## Features

- Automatic scrobbling for movies, TV episodes, and anime
- Works with any Kodi video addon (library, streaming, or third-party)
- Device code authorization (scan QR or enter code)
- Offline queue for failed events (syncs when connection returns)
- Configurable heartbeat interval, minimum watch time, and stale pause timeout
- Per-event and per-media-type toggles
- Duplicate event filtering
- Title and year fuzzy matching via FlickList API

## Install

### Option 1: Add Source in Kodi (Recommended)

This method lets you install directly from Kodi without needing a computer.

**Step 1: Add the source**

1. Open Kodi
2. Go to **Settings** (gear icon on the home screen)
3. Select **File Manager**
4. Select **Add source**
5. Click on `<None>` and type the following URL exactly:
   ```
   https://flicklist.github.io/flks/packages
   ```
6. In the **name** field below, type `FlickList` (or whatever you want to call it)
7. Click **OK**

**Step 2: Install the addon**

1. Go back to the Kodi home screen
2. Go to **Settings** > **Add-ons**
3. Select **Install from zip file**
4. If Kodi asks about "unknown sources," enable it (Settings > System > Add-ons > Unknown sources)
5. Select **FlickList** (the source you just added)
6. Select `service.flicklist.scrobbler-X.Y.Z.zip`
7. Wait for the "Add-on installed" notification

**Step 3: Authorize**

1. Go to **Add-ons** > **Program add-ons** > **FlickList Scrobbler**
2. Open the addon. It will show a QR code and a link code.
3. Go to [flicklist.tv/link](https://flicklist.tv/link) on your phone or computer
4. Enter the code shown on your TV
5. Done. The scrobbler runs in the background and tracks what you watch.

### Option 2: Manual Zip Download

1. Download the latest `service.flicklist.scrobbler-X.Y.Z.zip` from [Releases](https://github.com/flicklist/flks/releases)
2. Transfer the zip to your device if needed (USB, file manager app, etc.)
3. In Kodi: **Settings** > **Add-ons** > **Install from zip file**
4. Browse to the downloaded zip and select it
5. Follow the **Authorize** steps above

## Requirements

- Kodi 19 (Matrix) or newer
- A FlickList account at [flicklist.tv](https://flicklist.tv)

## License

MIT
