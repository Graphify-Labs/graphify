project('checks', 'c', 'cython')

py = import('python').find_installation(pure: false)

cc = meson.get_compiler('c')
cy = meson.get_compiler('cython')

# Keep synced with pyproject.toml
if not cy.version().version_compare('>=3.0.6')
  error('tests requires Cython >= 3.0.6')
endif

cython_args = []
if cy.version().version_compare('>=3.1.0')
  cython_args += ['-Xfreethreading_compatible=True']
endif

npy_include_path = run_command(py, [
    '-c',
    'import os; os.chdir(".."); import numpy; print(os.path.abspath(numpy.get_include()))'
    ], check: true).stdout().strip()

npy_path = run_command(py, [
    '-c',
    'import os; os.chdir(".."); import numpy; print(os.path.dirname(numpy.__file__).removesuffix("numpy"))'
    ], check: true).stdout().strip()

# TODO: This is a hack due to gh-25135, where cython may not find the right
#       __init__.pyd file.
add_project_arguments('-I', npy_path, language : 'cython')

py.extension_module(
    'checks',
    'checks.pyx',
    install: false,
    c_args: [
      '-DNPY_NO_DEPRECATED_API=0',  # Cython still uses old NumPy C API
      # Require 1.25+ to test datetime additions
      '-DNPY_TARGET_VERSION=NPY_2_0_API_VERSION',
    ],
    include_directories: [npy_include_path],
    cython_args: cython_args,
)
