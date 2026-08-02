# Multi Update for Kodi

![Multi Update icon](script.multi.update.kodi/resources/icon.png)

Multi Update is a cross-platform maintenance utility for Kodi 21 Omega. After confirmation it performs six ordered steps without restarting Kodi:

1. Clears the contents of Kodi's `special://temp/` cache.
2. Clears downloaded add-on and build packages from `special://home/addons/packages/`.
3. Reloads every enabled PVR client to refresh its cached PVR and EPG data without deleting Kodi's open databases.
4. Runs and waits for a complete video-library update scan.
5. Runs and waits for a complete music-library update scan.
6. Cleans both video and music libraries.

Installed add-ons, add-on settings, media, sources, and PVR databases are not deleted. Reloading PVR clients may interrupt Live TV or client-managed activity, so the add-on warns before it starts.

## Installation

Install the **Babaduchi Kodi Repository**, then select **Add-ons → Install from repository → Babaduchi Kodi Repository → Program add-ons → Multi Update**.

For direct installation, download the versioned `script.multi.update.kodi` ZIP from this repository's GitHub release and use **Add-ons → Install from ZIP file**.

## Diagnostics

Progress and cleanup counts are written to Kodi's standard log. Any failure is also shown in a dialog.

## License

MIT
