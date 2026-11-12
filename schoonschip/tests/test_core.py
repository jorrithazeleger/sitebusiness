"""Tests voor Schoonschip. Draaien: python3 -m unittest discover tests

Alles gebeurt in een nep-thuismap in een tijdelijke map; je eigen bestanden worden nooit aangeraakt.
"""
import json
import os
import plistlib
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))

import scans as SC  # noqa: E402
import veilig as V  # noqa: E402


def write(path, size=1000, data=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if data is not None else os.urandom(size))
    return path


def make_app(folder, name, bundle):
    app = os.path.join(folder, name + ".app")
    os.makedirs(os.path.join(app, "Contents", "MacOS"), exist_ok=True)
    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as fh:
        plistlib.dump({"CFBundleIdentifier": bundle, "CFBundleName": name, "CFBundleShortVersionString": "1.0"}, fh)
    write(os.path.join(app, "Contents", "MacOS", name), 50000)
    return app


class FakeHome(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = self.home
        self.apps = os.path.join(self.tmp, "Applications")
        os.makedirs(self.apps)
        self._old_dirs = SC.APP_DIRS
        SC.APP_DIRS = [self.apps]
        SC._PLIST_CACHE.clear()

    def tearDown(self):
        os.environ["HOME"] = self._old_home
        SC.APP_DIRS = self._old_dirs
        shutil.rmtree(self.tmp, ignore_errors=True)

    def h(self, *p):
        return os.path.join(self.home, *p)


class TestVeilig(FakeHome):
    def test_protected(self):
        for p in [self.home, self.h("Library"), self.h("Library", "Caches"), self.h("Documents"), "/",
                  "/etc/passwd", self.h("Library", "Keychains", "login.keychain-db"), self.h(".ssh", "id_rsa"),
                  self.h("Pictures", "Foto's.photoslibrary", "originals", "x.jpg"), self.h(".Trash", "x")]:
            with self.assertRaises(V.UserError, msg=p):
                V.check_allowed(p)

    def test_allowed(self):
        for p in [self.h("Library", "Caches", "com.foo"), self.h("Downloads", "x.dmg"), self.h(".npm", "_cacache"),
                  self.h("Documents", "a", "b.mov")]:
            self.assertEqual(V.check_allowed(p), p)

    def test_symlink_escape(self):
        os.makedirs(self.h("Downloads"))
        outside = os.path.join(self.tmp, "buiten")
        os.makedirs(outside)
        write(os.path.join(outside, "geheim.txt"))
        os.symlink(outside, self.h("Downloads", "link"))
        # de snelkoppeling zelf mag weg, maar niet wat erachter zit
        self.assertEqual(V.check_allowed(self.h("Downloads", "link")), self.h("Downloads", "link"))
        with self.assertRaises(V.UserError):
            V.check_allowed(self.h("Downloads", "link", "geheim.txt"))
        V.remove(self.h("Downloads", "link"), "delete")
        self.assertTrue(os.path.exists(os.path.join(outside, "geheim.txt")))

    def test_apps_only_with_flag(self):
        with self.assertRaises(V.UserError):
            V.check_allowed("/Applications/Foo.app")
        self.assertEqual(V.check_allowed("/Applications/Foo.app", apps=True), "/Applications/Foo.app")
        with self.assertRaises(V.UserError):
            V.check_allowed("/Applications/Utilities", apps=True)

    def test_delete_keep_dir(self):
        d = self.h("Library", "Caches", "com.foo")
        write(os.path.join(d, "a"), 5000)
        write(os.path.join(d, "sub", "b"), 5000)
        freed, err = V.remove(d, "delete", keep_dir=True)
        self.assertEqual(err, 0)
        self.assertGreater(freed, 9000)
        self.assertTrue(os.path.isdir(d))
        self.assertEqual(os.listdir(d), [])

    def test_trash(self):
        f = write(self.h("Downloads", "x.dmg"), 3000)
        freed, err = V.remove(f, "trash")
        self.assertEqual(err, 0)
        self.assertFalse(os.path.exists(f))
        self.assertTrue(os.path.exists(self.h(".Trash", "x.dmg")))
        f = write(self.h("Downloads", "x.dmg"), 3000)
        V.remove(f, "trash")
        self.assertEqual(len(os.listdir(self.h(".Trash"))), 2)


class TestScans(FakeHome):
    def job(self):
        return SC.Job("test")

    def test_junk(self):
        write(self.h("Library", "Caches", "com.vendor.app", "data"), 200000)
        write(self.h("Library", "Caches", "com.apple.Safari", "data"), 200000)
        write(self.h("Library", "Caches", "com.apple.bird", "data"), 200000)
        write(self.h("Library", "Logs", "Thing", "log.txt"), 50000)
        write(self.h("Library", "Application Support", "Slack", "Cache", "x"), 2000000)
        write(self.h("Library", "Developer", "Xcode", "DerivedData", "Proj", "x"), 2000000)
        write(self.h(".Trash", "oud.txt"), 10000)
        res = SC.scan_junk(self.job())
        groups = {g["key"]: g for g in res["groups"]}
        names = [i["name"] for i in groups["caches"]["items"]]
        self.assertIn("com.vendor.app", names)
        self.assertNotIn("com.apple.bird", names)
        apple = next(i for i in groups["caches"]["items"] if i["name"] == "Safari")
        self.assertFalse(apple["selected"])
        self.assertTrue(groups["appcaches"]["items"][0]["selected"])
        self.assertEqual(groups["dev"]["items"][0]["action"], "delete")
        self.assertEqual(groups["trash"]["items"][0]["action"], "empty_trash")
        self.assertIn("logs", groups)

    def test_clean_junk(self):
        write(self.h("Library", "Caches", "com.vendor.app", "data"), 200000)
        write(self.h(".Trash", "oud.txt"), 10000)
        res = SC.scan_junk(self.job())
        items = [i for g in res["groups"] for i in g["items"]]
        for n, i in enumerate(items):
            i["id"] = str(n)
        out = SC.clean(self.job(), items)
        self.assertEqual(out["failed"], [])
        self.assertGreater(out["freed"], 200000)
        self.assertEqual(os.listdir(self.h("Library", "Caches", "com.vendor.app")), [])
        self.assertEqual(os.listdir(self.h(".Trash")), [])

    def test_large(self):
        write(self.h("Movies", "film.mov"), 3 * 1024 * 1024)
        write(self.h("Movies", "klein.mov"), 100)
        write(self.h("Library", "verborgen.bin"), 3 * 1024 * 1024)
        write(self.h("Pictures", "Foto.photoslibrary", "originals", "a.heic"), 3 * 1024 * 1024)
        write(self.h(".cache", "x.bin"), 3 * 1024 * 1024)
        res = SC.scan_large(self.job(), min_mb=1)
        self.assertEqual([i["name"] for i in res["items"]], ["film.mov"])
        self.assertEqual(res["items"][0]["kind"], "Video")
        self.assertEqual(res["items"][0]["action"], "trash")

    def test_downloads(self):
        write(self.h("Downloads", "Zoom.pkg"), 1000)
        f = write(self.h("Downloads", "oud.pdf"), 1000)
        os.utime(f, (time.time() - 200 * 86400,) * 2)
        write(self.h("Downloads", "nieuw.pdf"), 1000)
        res = SC.scan_downloads(self.job())
        groups = {g["key"]: g for g in res["groups"]}
        self.assertTrue(groups["installers"]["items"][0]["selected"])
        # zonder Spotlight telt de aanmaakdatum; op Linux is die er niet, dan de wijzigdatum
        if not hasattr(os.stat(f), "st_birthtime"):
            self.assertEqual(groups["old"]["items"][0]["name"], "oud.pdf")
        self.assertFalse(groups["recent"]["items"][0]["selected"])

    def test_dupes(self):
        data = os.urandom(2 * 1024 * 1024)
        a = write(self.h("Documents", "a.jpg"), data=data)
        os.utime(a, (time.time() - 1000,) * 2)
        write(self.h("Downloads", "a kopie.jpg"), data=data)
        write(self.h("Documents", "anders.jpg"), data=data[:-1] + b"x")
        os.link(a, self.h("Documents", "hardlink.jpg"))
        res = SC.scan_dupes(self.job(), None, 1)
        self.assertEqual(len(res["groups"]), 1)
        g = res["groups"][0]
        self.assertEqual(len(g["items"]), 2)
        self.assertFalse(g["items"][0]["selected"])
        self.assertTrue(g["items"][1]["selected"])

    def test_dupes_refuses_library(self):
        os.makedirs(self.h("Library", "x"))
        with self.assertRaises(V.UserError):
            SC.scan_dupes(self.job(), self.h("Library", "x"))

    def test_space(self):
        write(self.h("Movies", "a.mov"), 500000)
        write(self.h("Documents", "b.txt"), 1000)
        write(self.h("Library", "c"), 1000)
        res = SC.scan_space(self.job(), self.home)
        names = [i["name"] for i in res["items"]]
        self.assertEqual(names[0], "Movies")
        by = {i["name"]: i for i in res["items"]}
        self.assertFalse(by["Movies"]["can_trash"])   # vaste map
        self.assertFalse(by["Library"]["can_trash"])
        sub = SC.scan_space(self.job(), self.h("Movies"))
        self.assertTrue(sub["items"][0]["can_trash"])
        with self.assertRaises(V.UserError):
            SC.scan_space(self.job(), "/etc")

    def test_uninstall(self):
        app = make_app(self.apps, "Voorbeeld", "com.voorbeeld.app")
        write(self.h("Library", "Application Support", "com.voorbeeld.app", "db"), 5000)
        write(self.h("Library", "Preferences", "com.voorbeeld.app.plist"), 100)
        write(self.h("Library", "Preferences", "com.voorbeeld.app.helper.plist"), 100)
        write(self.h("Library", "Preferences", "com.voorbeeldig.anders.plist"), 100)
        write(self.h("Library", "Group Containers", "ABCDE.com.voorbeeld.app", "x"), 100)
        write(self.h("Library", "Caches", "Voorbeeld", "x"), 100)
        listed = SC.list_apps(self.job())["apps"]
        self.assertEqual([a["name"] for a in listed], ["Voorbeeld"])
        res = SC.app_leftovers(app)
        names = {os.path.basename(i["path"]) for i in res["items"]}
        self.assertIn("com.voorbeeld.app.helper.plist", names)
        self.assertIn("ABCDE.com.voorbeeld.app", names)
        self.assertIn("Voorbeeld", names)
        self.assertNotIn("com.voorbeeldig.anders.plist", names)
        self.assertTrue(res["items"][0]["is_app"])

    def test_startup(self):
        p = self.h("Library", "LaunchAgents", "com.kapot.agent.plist")
        os.makedirs(os.path.dirname(p))
        with open(p, "wb") as fh:
            plistlib.dump({"Label": "com.kapot.agent", "Program": "/bestaat/niet"}, fh)
        res = SC.list_startup(self.job())
        it = res["groups"][0]["items"][0]
        self.assertTrue(it["broken"])
        self.assertTrue(it["editable"])

    def test_cancel(self):
        write(self.h("Downloads", "x"), 10)
        job = self.job()
        job.cancel.set()
        with self.assertRaises(SC.Cancelled):
            SC.scan_downloads(job)


class TestServer(FakeHome):
    def setUp(self):
        super().setUp()
        import server as S
        self.S = S
        S.DATA_DIR = os.path.join(self.tmp, "data")
        port = next(p for p in range(8890, 8990) if S._free(p))
        S._make_server(port)
        self.port = port
        threading.Thread(target=S.SERVER.serve_forever, daemon=True).start()

    def tearDown(self):
        self.S.SERVER.shutdown()
        self.S.SERVER.server_close()
        super().tearDown()

    def call(self, name, body=None, token=True, host=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Token"] = self.S.TOKEN
        if host:
            headers["Host"] = host
        req = urllib.request.Request("http://127.0.0.1:%d/api/%s" % (self.port, name), headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     method="POST" if body is not None else "GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())

    def wait(self, job):
        for _ in range(200):
            st = self.call("job?id=" + job)
            if st["status"] != "running":
                return st
            time.sleep(0.05)
        raise AssertionError("taak bleef hangen")

    def test_token_required(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.call("overview", token=False)
        self.assertEqual(cm.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.call("overview", host="evil.example:80")
        self.assertEqual(cm.exception.code, 403)
        self.assertIn("disk", self.call("overview"))

    def test_scan_and_clean(self):
        write(self.h("Downloads", "Setup.dmg"), 4000)
        write(self.h("Downloads", "bewaar.pdf"), 4000)
        job = self.call("start", {"kind": "downloads"})["job"]
        st = self.wait(job)
        items = [i for g in st["result"]["groups"] for i in g["items"]]
        dmg = next(i for i in items if i["name"] == "Setup.dmg")
        # een verzonnen nummer wordt geweigerd
        with self.assertRaises(urllib.error.HTTPError):
            self.call("clean", {"module": "downloads", "ids": ["d999"]})
        job = self.call("clean", {"module": "downloads", "ids": [dmg["id"]]})["job"]
        st = self.wait(job)
        self.assertEqual(st["status"], "done")
        self.assertGreater(st["result"]["trashed"], 0)
        self.assertFalse(os.path.exists(self.h("Downloads", "Setup.dmg")))
        self.assertTrue(os.path.exists(self.h("Downloads", "bewaar.pdf")))
        self.assertTrue(os.path.exists(self.h(".Trash", "Setup.dmg")))
        hist = self.S.load_history()
        self.assertGreater(hist["total"], 0)
        # hetzelfde nummer kan niet nog een keer
        with self.assertRaises(urllib.error.HTTPError):
            self.call("clean", {"module": "downloads", "ids": [dmg["id"]]})


if __name__ == "__main__":
    unittest.main()
