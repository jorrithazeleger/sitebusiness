"""Bouwt Schrijfblad.app als echte Mac-app.

De app krijgt een klein startprogramma (in C) dat Python binnen de app laadt. Daardoor ziet
macOS het draaiende programma als 'Schrijfblad', met het eigen icoon in het Dock, en komen
bestanden die je in de Finder of Mail opent rechtstreeks bij Schrijfblad binnen.

Gebruik (met de Python uit de Schrijfblad-omgeving):
  python bouw_app.py <doelmap/Schrijfblad.app> <pad/naar/server.py> <pad/naar/icon.png>
Exitcode 0 = gelukt, 3 = kan hier niet (dan valt het installatiescript terug op de eenvoudige app).
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

DOC_TYPES = [
    "org.openxmlformats.wordprocessingml.document",
    "org.openxmlformats.wordprocessingml.document.macroenabled",
    "org.openxmlformats.wordprocessingml.template",
]
# Deze opent Schrijfblad ook, door ze om te zetten naar .docx.
OTHER_TYPES = ["com.microsoft.word.doc", "public.rtf", "org.oasis-open.opendocument.text"]

LAUNCHER = r"""
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>

static const char *PY_LIB = %(lib)s;
static const char *PY_HOME = %(home)s;
static const char *PY_PATH = %(path)s;
static const char *SERVER = %(server)s;

static void fail(const char *what) {
    char cmd[2048];
    fprintf(stderr, "Schrijfblad: %%s\n", what);
    snprintf(cmd, sizeof cmd,
             "/usr/bin/osascript -e 'display dialog \"Schrijfblad kan niet starten. Draai het "
             "installatiescript opnieuw.\" buttons {\"OK\"} default button \"OK\" with title \"Schrijfblad\"' "
             ">/dev/null 2>&1");
    system(cmd);
}

int main(int argc, char **argv) {
    (void)argc;
    setenv("PYTHONHOME", PY_HOME, 1);
    setenv("PYTHONPATH", PY_PATH, 1);
    setenv("PYTHONNOUSERSITE", "1", 1);
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1);
    unsetenv("__PYVENV_LAUNCHER__");
    void *lib = dlopen(PY_LIB, RTLD_NOW | RTLD_GLOBAL);
    if (!lib) { fail(dlerror()); return 1; }
    int (*py_main)(int, char **) = (int (*)(int, char **))dlsym(lib, "Py_BytesMain");
    if (!py_main) { fail("Py_BytesMain ontbreekt"); return 1; }
    char *args[] = { argv[0], (char *)SERVER, "--app", NULL };
    return py_main(3, args);
}
"""


def c_string(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def find_libpython():
    """Zoek de gedeelde Python-bibliotheek van deze Python (framework of .dylib/.so)."""
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


def compiler():
    for cc in ("clang", "cc"):
        path = shutil.which(cc)
        if path:
            return path
    return None


def build(app, server, icon, test=False):
    lib = find_libpython()
    if not lib:
        print("  Deze Python heeft geen gedeelde bibliotheek; ik gebruik de eenvoudige app.")
        return 3
    cc = compiler()
    if not cc or (sys.platform == "darwin" and subprocess.run(
            ["xcode-select", "-p"], capture_output=True).returncode != 0):
        print("  Geen C-compiler gevonden; ik gebruik de eenvoudige app.")
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
                      "path": c_string(os.pathsep.join(paths)), "server": c_string(server)}
    with tempfile.TemporaryDirectory() as tmp:
        cfile = os.path.join(tmp, "launcher.c")
        with open(cfile, "w", encoding="utf-8") as fh:
            fh.write(src)
        cmd = [cc, "-O2", "-o", os.path.join(macos, "Schrijfblad"), cfile]
        if sys.platform == "darwin":
            cmd[1:1] = ["-arch", platform.machine(), "-mmacosx-version-min=10.13"]
        else:
            cmd.append("-ldl")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            print("  Compileren mislukt; ik gebruik de eenvoudige app.\n" + proc.stderr)
            shutil.rmtree(app, ignore_errors=True)
            return 3

        icon_file = None
        icns = os.path.join(res, "Schrijfblad.icns")
        ready = os.path.join(os.path.dirname(os.path.abspath(icon)), "Schrijfblad.icns")
        if os.path.exists(ready):
            # kant-en-klaar icoonbestand met alle formaten (sips maakt van een PNG soms een leeg icoon)
            shutil.copyfile(ready, icns)
            icon_file = "Schrijfblad"
        elif sys.platform == "darwin" and os.path.exists(icon):
            if subprocess.run(["sips", "-s", "format", "icns", icon, "--out", icns],
                              capture_output=True).returncode == 0:
                icon_file = "Schrijfblad"

    info = {
        "CFBundleName": "Schrijfblad",
        "CFBundleDisplayName": "Schrijfblad",
        "CFBundleIdentifier": "nl.schrijfblad.app",
        "CFBundleExecutable": "Schrijfblad",
        "CFBundlePackageType": "APPL",
        "CFBundleSignature": "????",
        "CFBundleShortVersionString": "1.0",
        "CFBundleVersion": "1",
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSMinimumSystemVersion": "10.13",
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSHighResolutionCapable": True,
        "NSSupportsAutomaticGraphicsSwitching": True,
        "CFBundleDocumentTypes": [{
            "CFBundleTypeName": "Word-document",
            "CFBundleTypeRole": "Editor",
            "LSHandlerRank": "Alternate",
            "LSItemContentTypes": DOC_TYPES,
        }, {
            "CFBundleTypeName": "Ander tekstdocument",
            "CFBundleTypeRole": "Viewer",
            "LSHandlerRank": "Alternate",
            "LSItemContentTypes": OTHER_TYPES,
        }],
    }
    if icon_file:
        info["CFBundleIconFile"] = icon_file
    with open(os.path.join(contents, "Info.plist"), "wb") as fh:
        plistlib.dump(info, fh)
    with open(os.path.join(contents, "PkgInfo"), "w") as fh:
        fh.write("APPL????")

    if sys.platform == "darwin":
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app], capture_output=True)
        lsreg = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
                 "LaunchServices.framework/Support/lsregister")
        os.utime(app, None)  # Finder en Dock laten zien dat het icoon veranderd is
        if os.path.exists(lsreg):
            subprocess.run([lsreg, "-f", app], capture_output=True)
    print("  Echte app gebouwd (Python: %s)." % lib)
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)
    sys.exit(build(*sys.argv[1:4]))
