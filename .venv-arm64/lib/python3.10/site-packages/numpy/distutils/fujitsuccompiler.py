from distutils.unixccompiler import UnixCCompiler

class FujitsuCCompiler(UnixCCompiler):

    """
    Fujitsu compiler.
    """

    compiler_type = 'fujitsu'
    cc_exe = 'fcc'
    cxx_exe = 'FCC'

    def __init__(self, verbose=0, dry_run=0, force=0):
        UnixCCompiler.__init__(self, verbose, dry_run, force)
        cc_compiler = self.cc_exe
        cxx_compiler = self.cxx_exe
        self.set_executables(
            compiler=cc_compiler +
            ' -O3 -Nclang -fPIC',
            compiler_so=cc_compiler +
            ' -O3 -Nclang -fPIC',
            compiler_cxx=cxx_compiler +
            ' -O3 -Nclang -fPIC',
            linker_exe=cc_compiler +
            ' -lfj90i -lfj90f -lfjsrcinfo -lelf -shared',
            linker_so=cc_compiler +
            ' -lfj90i -lfj90f -lfjsrcinfo -lelf -shared'
            )
