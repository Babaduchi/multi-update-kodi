import json
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs


ADDON = xbmcaddon.Addon()
NAME = ADDON.getAddonInfo("name")
OPERATION_TIMEOUT_SECONDS = 6 * 60 * 60


def log(message, level=xbmc.LOGINFO):
    xbmc.log("[{}] {}".format(NAME, message), level)


def notify(step, message):
    xbmcgui.Dialog().notification(
        NAME,
        "Step {}/6: {}".format(step, message),
        xbmcgui.NOTIFICATION_INFO,
        4000,
    )


def json_rpc(method, params=None):
    request = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        request["params"] = params
    response = json.loads(xbmc.executeJSONRPC(json.dumps(request)))
    if "error" in response:
        raise RuntimeError("{}: {}".format(method, response["error"]))
    return response.get("result")


def clear_directory(path):
    """Delete the contents of one explicitly supplied Kodi directory."""
    removed = 0
    failed = 0
    directories, files = xbmcvfs.listdir(path)

    for filename in files:
        target = path.rstrip("/\\") + "/" + filename
        if xbmcvfs.delete(target):
            removed += 1
        else:
            failed += 1

    for dirname in directories:
        target = path.rstrip("/\\") + "/" + dirname + "/"
        child_removed, child_failed = clear_directory(target)
        removed += child_removed
        failed += child_failed
        if not xbmcvfs.rmdir(target, force=True):
            failed += 1

    return removed, failed


def clear_cache():
    return clear_directory("special://temp/")


def clear_installation_packages():
    # Kodi stores downloaded add-on and repository ZIPs here. Installed add-ons
    # and their settings live elsewhere and are deliberately not touched.
    return clear_directory("special://home/addons/packages/")


def reload_pvr_clients():
    result = json_rpc(
        "Addons.GetAddons",
        {
            "type": "xbmc.pvrclient",
            "enabled": True,
            "installed": True,
            "properties": ["name"],
        },
    ) or {}
    clients = [addon.get("addonid") for addon in result.get("addons", [])]
    clients = [client_id for client_id in clients if client_id]

    disabled = []
    disable_failures = []
    for client_id in clients:
        try:
            json_rpc("Addons.SetAddonEnabled", {"addonid": client_id, "enabled": False})
            disabled.append(client_id)
        except Exception:
            disable_failures.append(client_id)

    if disabled:
        xbmc.Monitor().waitForAbort(1.5)

    enable_failures = []
    for client_id in disabled:
        try:
            json_rpc("Addons.SetAddonEnabled", {"addonid": client_id, "enabled": True})
        except Exception:
            enable_failures.append(client_id)

    if enable_failures:
        raise RuntimeError("Could not re-enable PVR clients: {}".format(", ".join(enable_failures)))
    if disable_failures:
        raise RuntimeError("Could not reload PVR clients: {}".format(", ".join(disable_failures)))
    return len(clients)


def wait_for_scan(condition, label):
    monitor = xbmc.Monitor()
    deadline = time.monotonic() + OPERATION_TIMEOUT_SECONDS
    start_deadline = time.monotonic() + 10

    while not xbmc.getCondVisibility(condition) and time.monotonic() < start_deadline:
        if monitor.waitForAbort(0.25):
            raise RuntimeError("Kodi is shutting down")

    while xbmc.getCondVisibility(condition):
        if time.monotonic() >= deadline:
            raise RuntimeError("{} exceeded six hours".format(label))
        if monitor.waitForAbort(1):
            raise RuntimeError("Kodi is shutting down")


def scan_video_library():
    json_rpc("VideoLibrary.Scan", {"showdialogs": False})
    wait_for_scan("Library.IsScanningVideo", "Video library scan")


def scan_music_library():
    json_rpc("AudioLibrary.Scan", {"showdialogs": False})
    wait_for_scan("Library.IsScanningMusic", "Music library scan")


class CleanMonitor(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.started = set()
        self.finished = set()

    def onCleanStarted(self, library):
        self.started.add(library.lower())

    def onCleanFinished(self, library):
        self.finished.add(library.lower())


def clean_library(monitor, library, method):
    json_rpc(method, {"showdialogs": False})
    deadline = time.monotonic() + OPERATION_TIMEOUT_SECONDS
    start_deadline = time.monotonic() + 10

    while library not in monitor.started and time.monotonic() < start_deadline:
        if monitor.waitForAbort(0.25):
            raise RuntimeError("Kodi is shutting down")

    while library not in monitor.finished:
        # A no-op clean may finish before callbacks are delivered.
        if library not in monitor.started and time.monotonic() >= start_deadline:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError("{} library clean exceeded six hours".format(library.title()))
        if monitor.waitForAbort(1):
            raise RuntimeError("Kodi is shutting down")


def clean_libraries():
    monitor = CleanMonitor()
    clean_library(monitor, "video", "VideoLibrary.Clean")
    clean_library(monitor, "music", "AudioLibrary.Clean")


def main():
    warning = (
        "Multi Update will clear Kodi's temporary cache and downloaded installation packages, "
        "reload enabled PVR clients, scan the video and music libraries, then clean both libraries. "
        "Kodi will not restart."
    )
    if xbmc.getCondVisibility("PVR.IsRecording"):
        warning = "WARNING: A recording appears to be active. Reloading PVR clients may affect it.\n\n" + warning
    elif xbmc.getCondVisibility("PVR.IsPlayingTV"):
        warning = "Live TV playback may stop while PVR clients reload.\n\n" + warning

    if not xbmcgui.Dialog().yesno(NAME, warning, yeslabel="Run Multi Update", nolabel="Cancel"):
        return

    try:
        notify(1, "Clearing Kodi cache")
        removed, failed = clear_cache()
        log("Cache cleanup removed {} entries; {} could not be removed".format(removed, failed))

        notify(2, "Clearing stored installation packages")
        removed, failed = clear_installation_packages()
        log("Package cleanup removed {} entries; {} could not be removed".format(removed, failed))

        notify(3, "Reloading PVR data")
        client_count = reload_pvr_clients()
        log("Reloaded {} enabled PVR clients".format(client_count))

        notify(4, "Scanning video library")
        scan_video_library()

        notify(5, "Scanning music library")
        scan_music_library()

        notify(6, "Cleaning video and music libraries")
        clean_libraries()
    except Exception as exc:
        log("Multi Update failed: {!r}".format(exc), xbmc.LOGERROR)
        xbmcgui.Dialog().ok(NAME, "Multi Update stopped.\n\n{}".format(exc))
        return

    xbmcgui.Dialog().notification(NAME, "All six steps completed", xbmcgui.NOTIFICATION_INFO, 5000)


if __name__ == "__main__":
    main()
