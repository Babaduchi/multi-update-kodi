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


def launch_cleanup_helper():
    database_dir = xbmcvfs.translatePath("special://database/")
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


def main():
    if not xbmc.getCondVisibility("System.Platform.Windows"):
        xbmcgui.Dialog().ok(NAME, "This add-on supports Windows only.")
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
