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
        "Step {}/10: {}".format(step, message),
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
    bytes_removed = 0
    directories, files = xbmcvfs.listdir(path)

    for filename in files:
        target = path.rstrip("/\\") + "/" + filename
        try:
            file_size = xbmcvfs.Stat(target).st_size()
        except Exception:
            file_size = 0
        if xbmcvfs.delete(target):
            removed += 1
            bytes_removed += file_size
        else:
            failed += 1

    for dirname in directories:
        target = path.rstrip("/\\") + "/" + dirname + "/"
        child_removed, child_failed, child_bytes_removed = clear_directory(target)
        removed += child_removed
        failed += child_failed
        bytes_removed += child_bytes_removed
        if not xbmcvfs.rmdir(target, force=True):
            failed += 1

    return removed, failed, bytes_removed


def format_size(byte_count):
    size = float(byte_count)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            if unit == "B":
                return "{} {}".format(int(size), unit)
            return "{:.1f} {}".format(size, unit)
        size /= 1024.0


def clear_cache():
    return clear_directory("special://temp/")


def clear_installation_packages():
    # Kodi stores downloaded add-on and repository ZIPs here. Installed add-ons
    # and their settings live elsewhere and are deliberately not touched.
    return clear_directory("special://home/addons/packages/")


def clear_orphaned_addon_data():
    result = json_rpc(
        "Addons.GetAddons",
        {
            "enabled": "all",
            "installed": True,
            "properties": ["name"],
        },
    ) or {}
    installed_addons = {
        addon.get("addonid")
        for addon in result.get("addons", [])
        if addon.get("addonid")
    }
    if not installed_addons:
        raise RuntimeError("Kodi returned no installed add-ons; orphan cleanup was stopped for safety")

    addon_data_path = "special://profile/addon_data/"
    directories, _files = xbmcvfs.listdir(addon_data_path)
    orphaned = sorted(dirname for dirname in directories if dirname not in installed_addons)

    folders_removed = 0
    failed = 0
    bytes_removed = 0
    for dirname in orphaned:
        target = addon_data_path + dirname + "/"
        child_removed, child_failed, child_bytes_removed = clear_directory(target)
        failed += child_failed
        bytes_removed += child_bytes_removed
        if xbmcvfs.rmdir(target, force=True):
            folders_removed += 1
            log("Removed orphaned add-on data folder: {}".format(dirname))
        else:
            failed += 1
            log("Could not remove orphaned add-on data folder: {}".format(dirname), xbmc.LOGWARNING)
        log("Orphan folder {} contained {} removable entries".format(dirname, child_removed))

    return folders_removed, len(orphaned), failed, bytes_removed


def reload_pvr_clients():
    result = json_rpc(
        "Addons.GetAddons",
        {
            "type": "kodi.pvrclient",
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


def clear_texture_cache():
    result = json_rpc(
        "Textures.GetTextures",
        {"properties": ["cachedurl"]},
    ) or {}
    texture_ids = [texture.get("textureid") for texture in result.get("textures", [])]
    texture_ids = [texture_id for texture_id in texture_ids if texture_id is not None and texture_id >= 0]

    removed = 0
    failed = 0
    monitor = xbmc.Monitor()
    for texture_id in texture_ids:
        if monitor.abortRequested():
            raise RuntimeError("Kodi is shutting down")
        try:
            json_rpc("Textures.RemoveTexture", {"textureid": texture_id})
            removed += 1
        except Exception as exc:
            failed += 1
            log("Could not remove texture {}: {!r}".format(texture_id, exc), xbmc.LOGWARNING)

    return removed, failed


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
        "Multi-Update will clear Kodi's temporary cache and downloaded installation packages, "
        "reload enabled PVR clients, and delete data folders belonging to uninstalled add-ons. "
        "You can then choose whether to delete cached textures and scan and clean the libraries. "
        "Kodi will not restart."
    )
    if xbmc.getCondVisibility("PVR.IsRecording"):
        warning = "WARNING: A recording appears to be active. Reloading PVR clients may affect it.\n\n" + warning
    elif xbmc.getCondVisibility("PVR.IsPlayingTV"):
        warning = "Live TV playback may stop while PVR clients reload.\n\n" + warning

    if not xbmcgui.Dialog().yesno(NAME, warning, yeslabel="Run Multi-Update", nolabel="Cancel"):
        return

    try:
        notify(1, "Clearing Kodi cache")
        removed, failed, bytes_removed = clear_cache()
        cache_deleted_size = format_size(bytes_removed)
        log("Cache cleanup removed {} entries ({}); {} could not be removed".format(removed, cache_deleted_size, failed))

        notify(2, "Clearing stored installation packages")
        removed, failed, bytes_removed = clear_installation_packages()
        packages_deleted_size = format_size(bytes_removed)
        log("Package cleanup removed {} entries ({}); {} could not be removed".format(removed, packages_deleted_size, failed))

        notify(3, "Reloading PVR data")
        client_count = reload_pvr_clients()
        log("Reloaded {} enabled PVR clients".format(client_count))

        notify(4, "Removing uninstalled add-on data")
        orphan_folders_removed, orphan_folders_found, orphan_failures, orphan_bytes_removed = (
            clear_orphaned_addon_data()
        )
        orphan_deleted_size = format_size(orphan_bytes_removed)
        log(
            "Orphan cleanup removed {}/{} folders ({}); {} failures".format(
                orphan_folders_removed,
                orphan_folders_found,
                orphan_deleted_size,
                orphan_failures,
            )
        )

        if client_count:
            pvr_result = "Complete ({} enabled client{})".format(
                client_count,
                "" if client_count == 1 else "s",
            )
        else:
            pvr_result = "Complete (no enabled clients found)"

        summary = (
            "Step 5 maintenance summary\n\n"
            "Kodi cache deleted: {}\n"
            "Installation packages deleted: {}\n"
            "PVR and EPG refresh: {}\n"
            "Uninstalled add-on data: {}/{} folders deleted ({})\n"
            "Add-on data cleanup failures: {}\n\n"
            "Delete Kodi's registered texture cache next?"
        ).format(
            cache_deleted_size,
            packages_deleted_size,
            pvr_result,
            orphan_folders_removed,
            orphan_folders_found,
            orphan_deleted_size,
            orphan_failures,
        )
        if not xbmcgui.Dialog().yesno(
            NAME,
            summary,
            yeslabel="Delete Textures",
            nolabel="Exit",
        ):
            return

        notify(6, "Clearing texture cache")
        textures_removed, texture_failures = clear_texture_cache()
        log(
            "Texture cleanup removed {} entries; {} could not be removed".format(
                textures_removed,
                texture_failures,
            )
        )
        texture_summary = (
            "Step 6 maintenance summary\n\n"
            "Texture-cache entries removed: {}\n"
            "Texture cleanup failures: {}\n\n"
            "Do you want to scan and clean the libraries?"
        ).format(textures_removed, texture_failures)
        if not xbmcgui.Dialog().yesno(
            NAME,
            texture_summary,
            yeslabel="Scan Libraries",
            nolabel="Exit",
        ):
            return

        notify(8, "Scanning video library")
        scan_video_library()

        notify(9, "Scanning music library")
        scan_music_library()

        notify(10, "Cleaning video and music libraries")
        clean_libraries()
    except Exception as exc:
        log("Multi-Update failed: {!r}".format(exc), xbmc.LOGERROR)
        xbmcgui.Dialog().ok(NAME, "Multi-Update stopped.\n\n{}".format(exc))
        return

    xbmcgui.Dialog().ok(NAME, "All libraries are up to date.")
    xbmcgui.Dialog().notification(NAME, "Multi-Update is now complete", xbmcgui.NOTIFICATION_INFO, 5000)


if __name__ == "__main__":
    main()
