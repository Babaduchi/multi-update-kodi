# Multi-Update for Kodi

![Multi-Update icon](script.multi.update.kodi/resources/icon.png)

Multi-Update is a cross-platform maintenance utility for Kodi 21 Omega. After confirmation it performs up to ten ordered steps without restarting Kodi:

The launch dialog says **The all-purpose cleaner!**

1. Clears the contents of Kodi's `special://temp/` cache.
2. Clears downloaded add-on and build packages from `special://home/addons/packages/`.
3. Reloads every enabled PVR client to refresh its cached PVR and EPG data without deleting Kodi's open databases.
4. Automatically removes data folders belonging to add-ons that are no longer installed.
5. Shows the first maintenance summary and offers **Delete Textures** or **Exit**.
6. Safely purges all registered texture-cache entries through Kodi's JSON-RPC API, without deleting the live `Textures13.db` file or restarting Kodi.
7. Shows texture cleanup statistics and offers **Scan Libraries** or **Exit**.
8. Runs and waits for a complete video-library update scan.
9. Runs and waits for a complete music-library update scan.
10. Cleans both video and music libraries, then displays **All libraries are up to date.**

The first summary reports the cache and installation-package sizes deleted, PVR/EPG refresh result, and orphaned add-on data cleanup statistics. **Delete Textures** continues to step 6; **Exit** stops. The second summary reports texture entries removed and failures. **Scan Libraries** continues to steps 8-10; **Exit** stops.

Data belonging to installed or disabled add-ons, media, sources, and PVR databases are not deleted. Orphaned data from uninstalled add-ons is permanently removed. Reloading PVR clients may interrupt Live TV or client-managed activity, so the add-on warns before it starts.

## Installation

Install the **Babaduchi Kodi Repository**, then select **Add-ons → Install from repository → Babaduchi Kodi Repository → Program add-ons → Multi-Update**.

For direct installation, download the versioned `script.multi.update.kodi` ZIP from this repository's GitHub release and use **Add-ons → Install from ZIP file**.

## Diagnostics

Progress and cleanup counts are written to Kodi's standard log. Any failure is also shown in a dialog.

## License

MIT
