"""Bouwt Notulist.app.

De app krijgt een klein startprogramma (in C) dat Python binnen de app laadt. Daardoor ziet
macOS het draaiende programma als 'Notulist': toestemming voor microfoon en schermopname geef
je aan Notulist zelf, niet aan Terminal of Python. Naast het startprogramma komt
notulist-audiocap (Swift), dat het systeemgeluid opneemt.

Gebruik (met de Python uit de Notulist-omgeving):
  python bouw_app.py <doelmap/Notulist.app> <pad/naar/notulist.py> <pad/naar/audiocap.swift>
Exitcode 0 = gelukt, 3 = kan hier niet bouwen.
"""
from __future__ import annotations

import os
import platform
import plistlib
import shutil
import subprocess
import sys
import sysconfig
import tempfile

BUNDLE_ID = "nl.notulist.app"
VERSIE = "1.0"

LAUNCHER = r"""
#include <dlfcn.h>
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *PY_LIB = %(lib)s;
static const char *PY_HOME = %(home)s;
static const char *PY_PATH = %(path)s;
static const char *SCRIPT = %(script)s;

static void fail(const char *what) {
    fprintf(stderr, "Notulist: %%s\n", what);
    system("/usr/bin/osascript -e 'display dialog \"Notulist kan niet starten. Draai het "
           "installatiescript opnieuw.\" buttons {\"OK\"} default button \"OK\" with title \"Notulist\"' "
           ">/dev/null 2>&1");
}

int main(int argc, char **argv) {
    (void)argc;
    char exe[PATH_MAX], real[PATH_MAX], helper[PATH_MAX];
    uint32_t size = sizeof exe;
    if (_NSGetExecutablePath(exe, &size) == 0 && realpath(exe, real)) {
        snprintf(helper, sizeof helper, "%%s/notulist-audiocap", dirname(real));
        setenv("NOTULIST_HELPER", helper, 1);
    }
    setenv("PYTHONHOME", PY_HOME, 1);
    setenv("PYTHONPATH", PY_PATH, 1);
    setenv("PYTHONNOUSERSITE", "1", 1);
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1);
    unsetenv("__PYVENV_LAUNCHER__");
    void *lib = dlopen(PY_LIB, RTLD_NOW | RTLD_GLOBAL);
    if (!lib) { fail(dlerror()); return 1; }
    int (*py_main)(int, char **) = (int (*)(int, char **))dlsym(lib, "Py_BytesMain");
    if (!py_main) { fail("Py_BytesMain ontbreekt"); return 1; }
    char *args[] = { argv[0], (char *)SCRIPT, "--app", NULL };
    return py_main(3, args);
}
"""


def c_string(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def find_libpython():
    """Zoek de gedeelde Python-bibliotheek van deze Python (framework of .dylib)."""
    base = sys.base_prefix
    fw = sysconfig.get_config_var("PYTHONFRAMEWORK") or ""
    ld = sysconfig.get_config_var("LDLIBRARY") or ""
    libdir = sysconfig.get_config_var("LIBDIR") or ""
    candidates = []
    if fw:
        candidates += [os.path.join(base, fw), os.path.join(base, "Python3"), os.path.join(base, "Python")]
    if ld and not ld.endswith(".a"):
        candidates += [os.path.join(base, "lib", os.path.basename(ld)), os.path.join(libdir, ld),
                       os.path.join(libdir, os.path.basename(ld))]
    inst = sysconfig.get_config_var("INSTSONAME") or ""
    if inst:
        candidates.append(os.path.join(libdir, inst))
    import ctypes
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                if hasattr(ctypes.CDLL(path), "Py_BytesMain"):
                    return path
            except OSError:
                continue
    return None


def bouw_helper(swift_bron, doel):
    """Compileert notulist-audiocap. Geeft True terug als het gelukt is."""
    if sys.platform != "darwin":
        return False
    swiftc = subprocess.run(["xcrun", "--find", "swiftc"], capture_output=True, text=True)
    if swiftc.returncode != 0:
        print("  Swift ontbreekt; Notulist neemt dan alleen je microfoon op.")
        return False
    cmd = [swiftc.stdout.strip(), "-O", "-swift-version", "5",
           "-target", "%s-apple-macos13.0" % platform.machine(), "-o", doel, swift_bron]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print("  Het hulpprogramma voor systeemgeluid kon niet gebouwd worden:\n" + proc.stderr[-2000:])
        return False
    return True


def build(app, script, swift_bron):
    lib = find_libpython()
    if not lib:
        print("  Deze Python heeft geen gedeelde bibliotheek.")
        return 3
    cc = shutil.which("clang") or shutil.which("cc")
    if not cc or (sys.platform == "darwin" and subprocess.run(
            ["xcode-select", "-p"], capture_output=True).returncode != 0):
        print("  Geen C-compiler gevonden (Command Line Tools ontbreken).")
        return 3
    paths = []
    for key in ("purelib", "platlib"):
        p = sysconfig.get_paths()[key]
        if p not in paths:
            paths.append(p)

    contents = os.path.join(app, "Contents")
    macos = os.path.join(contents, "MacOS")
    res = os.path.join(contents, "Resources")
    if os.path.exists(app):
        shutil.rmtree(app)
    os.makedirs(macos)
    os.makedirs(res)

    src = LAUNCHER % {"lib": c_string(lib), "home": c_string(sys.base_prefix),
                      "path": c_string(os.pathsep.join(paths)), "script": c_string(script)}
    with tempfile.TemporaryDirectory() as tmp:
        cfile = os.path.join(tmp, "launcher.c")
        with open(cfile, "w", encoding="utf-8") as fh:
            fh.write(src)
        cmd = [cc, "-O2", "-o", os.path.join(macos, "Notulist"), cfile]
        if sys.platform == "darwin":
            cmd[1:1] = ["-arch", platform.machine(), "-mmacosx-version-min=11.0"]
        else:
            cmd.append("-ldl")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print("  Compileren mislukt.\n" + proc.stderr)
            shutil.rmtree(app, ignore_errors=True)
            return 3

    helper_ok = bouw_helper(swift_bron, os.path.join(macos, "notulist-audiocap"))

    info = {
        "CFBundleName": "Notulist",
        "CFBundleDisplayName": "Notulist",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleExecutable": "Notulist",
        "CFBundlePackageType": "APPL",
        "CFBundleSignature": "????",
        "CFBundleShortVersionString": VERSIE,
        "CFBundleVersion": VERSIE,
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSMinimumSystemVersion": "13.0",
        "LSApplicationCategoryType": "public.app-category.productivity",
        "LSUIElement": True,  # alleen in de menubalk, niet in het Dock
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription":
            "Notulist neemt je microfoon op tijdens meetings om er een transcript van te maken.",
        "NSAudioCaptureUsageDescription":
            "Notulist neemt het geluid van je meetings op om er een transcript van te maken.",
    }
    with open(os.path.join(contents, "Info.plist"), "wb") as fh:
        plistlib.dump(info, fh)
    with open(os.path.join(contents, "PkgInfo"), "w") as fh:
        fh.write("APPL????")

    if sys.platform == "darwin":
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app], capture_output=True)
        lsreg = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
                 "LaunchServices.framework/Support/lsregister")
        if os.path.exists(lsreg):
            subprocess.run([lsreg, "-f", app], capture_output=True)
    print("  App gebouwd%s." % ("" if helper_ok else " (zonder systeemgeluid)"))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)
    sys.exit(build(*sys.argv[1:4]))
