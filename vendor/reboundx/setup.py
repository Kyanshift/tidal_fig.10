from codecs import open
import os
import inspect
import sys 
from glob import glob
import sysconfig
import re
import subprocess
from pathlib import Path
from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext as _build_ext

def get_reb_paths(sitepackagesdir):
    try:
        import rebound
        rebdir = os.path.dirname(inspect.getfile(rebound))
        version = rebound.__version__ 
    except:
        raise AttributeError("REBOUND was not installed.")

    try: # try to get local rebound directory if using editable pip installs
        with open(sitepackagesdir+'rebound-'+version+".dist-info/direct_url.json") as f:
            lines = f.readlines()
            for l in lines:
                blocks = l.split('"')
                if 'url' in blocks:
                    for block in blocks:
                        if block.startswith('file://'):
                            path = block.strip('file:')
        return rebdir, path+'/'
    except:
        return rebdir, ""

suffix = sysconfig.get_config_var('EXT_SUFFIX')
if suffix is None:
    suffix = ".so"

# An archive has no .git directory; avoid recording the enclosing project's hash.
upstream_commit = Path(__file__).with_name("UPSTREAM_COMMIT")
try:
    if upstream_commit.exists():
        ghash = upstream_commit.read_text(encoding="ascii").strip()
    else:
        ghash = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("ascii")
    ghash_arg = "-DREBXGITHASH="+ghash.strip()
except:
    ghash_arg = "-DREBXGITHASH=6253cea575af12b85392baaacd3688045702a5b2" #GITHASHAUTOUPDATE

class build_ext(_build_ext):
    def finalize_options(self):
        _build_ext.finalize_options(self)
        if os.environ.get("REBX_FORCE_BUILD") == "1":
            self.force = True
        if "PYODIDE" in os.environ:
            return None
       
        # get site-packages dir to add to paths in case reb & rebx installed simul in tmp dir
        sitepackagesdir = sysconfig.get_path('platlib')+'/'
        rebdir, editable_rebdir = get_reb_paths(sitepackagesdir)
        rebdir_parent = os.path.dirname(rebdir)
        print("***", rebdir, "***", sitepackagesdir, "***", editable_rebdir, "***")
        ## include both as one seems required for editable installs, the other for wheels.
        self.include_dirs.append(rebdir_parent+"/src")
        self.include_dirs.append(rebdir+"/include")
        #self.include_dirs.append(editable_rebdir)
        
        self.library_dirs.append(rebdir+'/../')
        self.library_dirs.append(sitepackagesdir)
        if sys.platform == 'win32':
            if editable_rebdir:
                self.include_dirs.append(os.path.join(editable_rebdir, "src"))
            return
        for ext in self.extensions:
            ext.runtime_library_dirs.append(rebdir+'/../')
            ext.extra_link_args.append('-Wl,-rpath,'+rebdir+'/../')
            ext.runtime_library_dirs.append(sitepackagesdir)
            ext.extra_link_args.append('-Wl,-rpath,'+sitepackagesdir)
        if editable_rebdir:
            self.library_dirs.append(editable_rebdir)
            for ext in self.extensions:
                ext.runtime_library_dirs.append(editable_rebdir)
                ext.extra_link_args.append('-Wl,-rpath,'+editable_rebdir)

    def build_extensions(self):
        if sys.platform == 'win32':
            if self.compiler.compiler_type != 'msvc':
                raise RuntimeError("This local Windows adaptation requires MSVC.")
            self._prepare_rebound_import_library()
        super().build_extensions()

    def _prepare_rebound_import_library(self):
        """Generate an import library for the exact REBOUND DLL in this venv."""
        import rebound
        if not self.compiler.initialized:
            self.compiler.initialize()
        dll = Path(rebound.clibrebound._name).resolve()
        dumpbin = Path(self.compiler.linker).with_name("dumpbin.exe")
        output = subprocess.check_output([str(dumpbin), "/nologo", "/exports", str(dll)], text=True, errors="replace")
        symbols = re.findall(r"^\s+\d+\s+[0-9A-Fa-f]+\s+[0-9A-Fa-f]+\s+(reb_\w+)\b", output, re.MULTILINE)
        if not symbols:
            raise RuntimeError("No REBOUND exports found in " + str(dll))
        directory = Path(self.build_temp).resolve() / "rebound-import"
        directory.mkdir(parents=True, exist_ok=True)
        definition = directory / "rebound.def"
        definition.write_text('LIBRARY "' + dll.name + '"\nEXPORTS\n' + '\n'.join(symbols) + '\n', encoding="ascii")
        library = directory / "rebound.lib"
        machine = {"win-amd64": "X64", "win32": "X86", "win-arm64": "ARM64"}[self.plat_name]
        subprocess.check_call([self.compiler.lib, "/nologo", "/def:" + str(definition), "/machine:" + machine, "/out:" + str(library)])
        for ext in self.extensions:
            ext.libraries = []
            ext.extra_objects = [str(library)]

    def get_export_symbols(self, ext):
        if sys.platform != 'win32':
            return super().get_export_symbols(ext)
        # This is a ctypes library; export C functions and data, without PyInit_*.
        symbols = set()
        for source in ext.sources:
            contents = Path(source).read_text(encoding="utf-8")
            contents = re.sub(r"/\*.*?\*/|//[^\n]*", "", contents, flags=re.DOTALL)
            symbols.update(re.findall(r"^(?!static\b)[\w *\t]+\b(rebx_\w+)\s*\([^;{}]*\)\s*\{", contents, re.MULTILINE))
        symbols.update(name + ",DATA" for name in ("rebx_build_str", "rebx_version_str", "rebx_githash_str"))
        return sorted(symbols)


extra_link_args=[]
if sys.platform == 'darwin':
    config_vars = sysconfig.get_config_vars()
    config_vars['LDSHARED'] = config_vars['LDSHARED'].replace('-bundle', '-shared')
    extra_link_args.append('-Wl,-install_name,@rpath/libreboundx'+suffix)
if sys.platform == 'win32':
    extra_compile_args=[ghash_arg, '/std:c11', '/fp:precise', '/D_CRT_SECURE_NO_WARNINGS']
else:
    # Default compile args
    extra_compile_args=['-fstrict-aliasing', '-O3','-std=c99','-Wno-unknown-pragmas', ghash_arg, '-D_GNU_SOURCE', '-fPIC']

# Option to disable FMA in CLANG. 
FFP_CONTRACT_OFF = os.environ.get("FFP_CONTRACT_OFF", None)
if FFP_CONTRACT_OFF:
    extra_compile_args.append('/fp:strict' if sys.platform == 'win32' else '-ffp-contract=off')

libreboundxmodule = Extension(
    'libreboundx',
    sources = sorted(glob("src/*.c")),
    include_dirs = ['src'],
    libraries=['rebound'+suffix[:suffix.rfind('.')]],
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
    )

setup(ext_modules=[libreboundxmodule],
    cmdclass={'build_ext':build_ext},
    )
