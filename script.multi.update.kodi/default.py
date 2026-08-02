import json
import os
import subprocess
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs


ADDON = xbmcaddon.Addon()
NAME = ADDON.getAddonInfo("name")
SCAN_TIMEOUT_SECONDS = 6 * 60 * 60


def log(message, level=xbmc.LOGINFO):
    xbmc.log("[{}] {}".format(NAME, message), level)


def json_rpc(method, params=None):
    request = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        request["params"] = params
    response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
    if "error" in response:
        raise RuntimeError("{}: {}".format(method, response["error"]))
    return response.get("result")


def wait_for_scan(condition, label):
    monitor = xbmc.Monitor()
    deadline = time.monotonic() + SCAN_TIMEOUT_SECONDS

    # JSON-RPC schedules the scan asynchronously. Give Kodi a short window to
    # expose its scanning condition before deciding a no-op scan is complete.
    start_deadline = time.monotonic() + 10
    while not xbmc.getCondVisibility(condition) and time.monotonic() < start_deadline:
        if monitor.waitForAbort(0.25):
            raise RuntimeError("Kodi is shutting down")

    while xbmc.getCondVisibility(condition):
        if time.monotonic() >= deadline:
            raise RuntimeError("{} scan exceeded six hours".format(label))
        if monitor.waitForAbort(1):
            raise RuntimeError("Kodi is shutting down")


def run_library_scans():
    xbmcgui.Dialog().notification(NAME, "Updating video library", xbmcgui.NOTIFICATION_INFO, 3000)
    json_rpc("VideoLibrary.Scan", {"showdialogs": False})
    wait_for_scan("Library.IsScanningVideo", "Video library")

    xbmcgui.Dialog().notification(NAME, "Updating music library", xbmcgui.NOTIFICATION_INFO, 3000)
    json_rpc("AudioLibrary.Scan", {"showdialogs": False})
    wait_for_scan("Library.IsScanningMusic", "Music library")


def launch_windows_cleanup(database_dir):
    kodi_executable = xbmcvfs.translatePath("special://xbmc/kodi.exe")
    helper = os.path.join(ADDON.getAddonInfo("path"), "resources", "clear_pvr.ps1")

    if not os.path.isfile(kodi_executable):
        raise RuntimeError("Kodi executable was not found: {}".format(kodi_executable))
    if not os.path.isdir(database_dir):
        raise RuntimeError("Kodi database directory was not found: {}".format(database_dir))
    if not os.path.isfile(helper):
        raise RuntimeError("PVR cleanup helper was not found")

    command = [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        helper,
        "-DatabaseDirectory",
        database_dir,
        "-KodiExecutable",
        kodi_executable,
        "-KodiProcessId",
        str(os.getpid()),
    ]

    # Detach the helper and suppress a console window so it survives Kodi exit.
    creation_flags = 0x00000008 | 0x00000200 | 0x08000000
    subprocess.Popen(command, close_fds=True, creationflags=creation_flags)


def launch_macos_cleanup(database_dir):
    # A detached shell survives Kodi's exit, waits for SQLite handles to close,
    # clears the PVR databases, and reopens the Kodi application bundle.
    script = r'''
database_dir=$1
kodi_pid=$2
log_path="${TMPDIR:-/tmp}/kodi-multi-update.log"
deadline=120
elapsed=0

printf '%s Waiting for Kodi process %s to exit.\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$kodi_pid" >> "$log_path"
while kill -0 "$kodi_pid" 2>/dev/null && [ "$elapsed" -lt "$deadline" ]; do
    sleep 1
    elapsed=$((elapsed + 1))
done

if kill -0 "$kodi_pid" 2>/dev/null; then
    printf '%s ERROR: Kodi did not exit within two minutes; no PVR data was removed.\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$log_path"
    /usr/bin/open -a Kodi
    exit 1
fi

sleep 1
found=0
for database in "$database_dir"/TV*.db "$database_dir"/Epg*.db; do
    [ -f "$database" ] || continue
    found=1
    /bin/rm -f -- "$database"
    printf '%s Removed %s.\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$database" >> "$log_path"
done

if [ "$found" -eq 0 ]; then
    printf '%s No TV*.db or Epg*.db files were present.\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$log_path"
fi

printf '%s Restarting Kodi.\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$log_path"
/usr/bin/open -a Kodi
'''
    subprocess.Popen(
        ["/bin/sh", "-c", script, "multi-update", database_dir, str(os.getpid())],
        close_fds=True,
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def launch_cleanup_helper():
    database_dir = xbmcvfs.translatePath("special://database/")
    if not os.path.isdir(database_dir):
        raise RuntimeError("Kodi database directory was not found: {}".format(database_dir))

    if xbmc.getCondVisibility("System.Platform.Windows"):
        launch_windows_cleanup(database_dir)
    elif xbmc.getCondVisibility("System.Platform.OSX"):
        launch_macos_cleanup(database_dir)
    else:
        raise RuntimeError("This add-on supports Windows and macOS only")


def main():
    supported = (
        xbmc.getCondVisibility("System.Platform.Windows")
        or xbmc.getCondVisibility("System.Platform.OSX")
    )
    if not supported:
        xbmcgui.Dialog().ok(NAME, "This add-on supports Windows and macOS only.")
        return

    warning = (
        "This will update the complete video and music libraries. Kodi will then close, "
        "clear all cached PVR and guide data, and restart. Enabled PVR clients will rebuild "
        "their channels, groups, timers, recordings, providers, and EPG data."
    )
    if xbmc.getCondVisibility("PVR.IsRecording"):
        warning = "WARNING: A recording appears to be active.\n\n" + warning
    elif xbmc.getCondVisibility("PVR.IsPlayingTV"):
        warning = "Live TV playback will stop.\n\n" + warning

    if not xbmcgui.Dialog().yesno(NAME, warning, yeslabel="Update Everything", nolabel="Cancel"):
        return

    try:
        run_library_scans()
        launch_cleanup_helper()
    except Exception as exc:
        log("Update failed: {!r}".format(exc), xbmc.LOGERROR)
        xbmcgui.Dialog().ok(NAME, "The update could not be completed.\n\n{}".format(exc))
        return

    log("Library scans completed; closing Kodi for PVR database rebuild")
    xbmcgui.Dialog().notification(NAME, "Scans complete; restarting Kodi", xbmcgui.NOTIFICATION_INFO, 3000)
    xbmc.executebuiltin("Quit")


if __name__ == "__main__":
    main()
