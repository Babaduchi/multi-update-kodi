import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "script.multi.update.kodi" / "default.py"


class BaseMonitor:
    def __init__(self):
        pass

    def abortRequested(self):
        return False

    def waitForAbort(self, _seconds):
        return False


class DialogRecorder:
    def __init__(self, answers=None):
        self.answers = list(answers or [])
        self.yesno_calls = []
        self.ok_calls = []

    def yesno(self, *args, **kwargs):
        self.yesno_calls.append((args, kwargs))
        return self.answers.pop(0)

    def ok(self, *args, **kwargs):
        self.ok_calls.append((args, kwargs))


def load_addon(dialog=None):
    dialog = dialog or DialogRecorder()
    xbmc = types.ModuleType("xbmc")
    xbmc.LOGINFO = 1
    xbmc.LOGWARNING = 2
    xbmc.LOGERROR = 3
    xbmc.Monitor = BaseMonitor
    xbmc.log = mock.Mock()
    xbmc.getCondVisibility = mock.Mock(return_value=False)
    xbmc.executeJSONRPC = mock.Mock(return_value=json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}))

    xbmcaddon = types.ModuleType("xbmcaddon")
    addon = mock.Mock()
    addon.getAddonInfo.return_value = "Multi-Update"
    xbmcaddon.Addon = mock.Mock(return_value=addon)

    xbmcgui = types.ModuleType("xbmcgui")
    xbmcgui.Dialog = mock.Mock(return_value=dialog)

    xbmcvfs = types.ModuleType("xbmcvfs")
    xbmcvfs.listdir = mock.Mock(return_value=([], []))
    xbmcvfs.Stat = mock.Mock()
    xbmcvfs.delete = mock.Mock(return_value=True)
    xbmcvfs.rmdir = mock.Mock(return_value=True)

    modules = {"xbmc": xbmc, "xbmcaddon": xbmcaddon, "xbmcgui": xbmcgui, "xbmcvfs": xbmcvfs}
    with mock.patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("multi_update_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, dialog


class MultiUpdateTests(unittest.TestCase):
    def test_json_rpc_returns_result_and_raises_errors(self):
        addon, _ = load_addon()
        addon.xbmc.executeJSONRPC.return_value = json.dumps({"result": {"ok": True}})
        self.assertEqual({"ok": True}, addon.json_rpc("Test.Method"))
        addon.xbmc.executeJSONRPC.return_value = json.dumps({"error": {"code": -1}})
        with self.assertRaises(RuntimeError):
            addon.json_rpc("Test.Method")

    def test_clear_directory_counts_only_confirmed_deletions(self):
        addon, _ = load_addon()
        addon.xbmcvfs.listdir.side_effect = lambda path: {
            "root/": (["sub"], ["a"]),
            "root/sub/": ([], ["b"]),
        }[path]
        sizes = {"root/a": 10, "root/sub/b": 20}
        addon.xbmcvfs.Stat.side_effect = lambda path: mock.Mock(st_size=lambda: sizes[path])
        addon.xbmcvfs.delete.side_effect = lambda path: path != "root/sub/b"
        addon.xbmcvfs.rmdir.return_value = False

        removed, failed, size = addon.clear_directory("root/")

        self.assertEqual((1, 2, 10), (removed, failed, size))
        addon.xbmcvfs.rmdir.assert_called_once_with("root/sub/")

    def test_installed_addon_query_includes_disabled_without_extra_fields(self):
        addon, _ = load_addon()
        addon.json_rpc = mock.Mock(return_value={"addons": [{"addonid": "a"}, {"addonid": "b"}]})

        self.assertEqual({"a", "b"}, addon.installed_addon_ids())
        addon.json_rpc.assert_called_once_with(
            "Addons.GetAddons",
            {"enabled": "all", "installed": True},
        )

    def test_orphan_cleanup_preserves_installed_folders(self):
        addon, _ = load_addon()
        addon.installed_addon_ids = mock.Mock(return_value={"keep"})
        addon.xbmcvfs.listdir.return_value = (["keep", "gone"], [])
        addon.clear_directory = mock.Mock(return_value=(3, 0, 99))
        addon.xbmcvfs.rmdir.return_value = True

        result = addon.clear_orphaned_addon_data()

        self.assertEqual((1, 1, 0, 99), result)
        addon.clear_directory.assert_called_once_with("special://profile/addon_data/gone/")

    def test_orphan_cleanup_stops_on_empty_installed_list(self):
        addon, _ = load_addon()
        addon.installed_addon_ids = mock.Mock(return_value=set())
        with self.assertRaisesRegex(RuntimeError, "stopped for safety"):
            addon.clear_orphaned_addon_data()
        addon.xbmcvfs.listdir.assert_not_called()

    def test_pvr_reload_attempts_to_restore_every_disabled_client(self):
        addon, _ = load_addon()
        addon.installed_addon_ids = mock.Mock(return_value={"pvr.a", "pvr.b"})
        calls = []

        def rpc(method, params=None):
            calls.append((method, params))
            if method == "Addons.SetAddonEnabled" and params == {"addonid": "pvr.b", "enabled": True}:
                raise RuntimeError("enable failed")

        addon.json_rpc = rpc
        with self.assertRaisesRegex(RuntimeError, "Could not re-enable"):
            addon.reload_pvr_clients()

        self.assertIn(("Addons.SetAddonEnabled", {"addonid": "pvr.a", "enabled": True}), calls)
        self.assertIn(("Addons.SetAddonEnabled", {"addonid": "pvr.b", "enabled": True}), calls)

    def test_texture_cleanup_requests_only_ids_and_counts_failures(self):
        addon, _ = load_addon()
        calls = []

        def rpc(method, params=None):
            calls.append((method, params))
            if method == "Textures.GetTextures":
                return {"textures": [{"textureid": 1}, {"textureid": None}, {"textureid": 2}]}
            if params == {"textureid": 2}:
                raise RuntimeError("remove failed")

        addon.json_rpc = rpc
        self.assertEqual((1, 1), addon.clear_texture_cache())
        self.assertEqual(("Textures.GetTextures", None), calls[0])

    def test_exit_at_first_summary_skips_textures_and_libraries(self):
        dialog = DialogRecorder([True, False])
        addon, _ = load_addon(dialog)
        addon.clear_directory = mock.Mock(side_effect=[(1, 0, 10), (1, 0, 20)])
        addon.reload_pvr_clients = mock.Mock(return_value=1)
        addon.clear_orphaned_addon_data = mock.Mock(return_value=(0, 0, 0, 0))
        addon.clear_texture_cache = mock.Mock()
        addon.scan_library = mock.Mock()
        addon.clean_libraries = mock.Mock()

        addon.main()

        addon.clear_texture_cache.assert_not_called()
        addon.scan_library.assert_not_called()
        addon.clean_libraries.assert_not_called()

    def test_full_dialog_path_runs_both_scans_and_clean(self):
        dialog = DialogRecorder([True, True, True])
        addon, _ = load_addon(dialog)
        addon.clear_directory = mock.Mock(side_effect=[(1, 0, 10), (1, 0, 20)])
        addon.reload_pvr_clients = mock.Mock(return_value=1)
        addon.clear_orphaned_addon_data = mock.Mock(return_value=(0, 0, 0, 0))
        addon.clear_texture_cache = mock.Mock(return_value=(5, 0))
        addon.scan_library = mock.Mock()
        addon.clean_libraries = mock.Mock()

        addon.main()

        self.assertEqual(2, addon.scan_library.call_count)
        addon.clean_libraries.assert_called_once_with()
        self.assertEqual("All libraries are up to date.", dialog.ok_calls[-1][0][1])


if __name__ == "__main__":
    unittest.main()
