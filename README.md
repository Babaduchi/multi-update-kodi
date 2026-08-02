# Multi Update for Kodi

Multi Update is a Windows-only utility add-on for Kodi 21 Omega. When launched and confirmed, it:

1. Runs a complete video library update scan and waits for it to finish.
2. Runs a complete music library update scan and waits for it to finish.
3. Closes Kodi.
4. Removes Kodi's cached `TV*.db` and `Epg*.db` databases—the equivalent of **Settings → PVR & Live TV → General → Clear data**.
5. Restarts Kodi so every enabled PVR client rebuilds its channels, groups, timers, recordings, providers, and guide data.

The add-on does not alter PVR client configuration. Do not run it during Live TV playback or an active recording.

## Installation

Install the **Babaduchi Kodi Repository**, then select **Add-ons → Install from repository → Babaduchi Kodi Repository → Program add-ons → Multi Update**.

For direct installation, download the versioned `script.multi.update.kodi` ZIP from this repository's GitHub release and use **Add-ons → Install from ZIP file**.

## Diagnostics

The Windows cleanup helper writes `%TEMP%\kodi-multi-update.log`.

## License

MIT
