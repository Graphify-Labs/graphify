project('checks', 'c', 'cython')

py = import('python').find_installation(pure: false)

cc = meson.get_compiler('c')
cy = meson.get_compiler('cython')

# Keep synced with pyproject.toml
if not cy.version().version_compare('>=3.0.6')
  error('tests requires Cython >= 3.0.6')
endif

npy_include_path = run_command(py, [
    '-c',
    'import os; os.chdir(".."); import numpy; print(os.path.abspath(numpy.get_include()))'
    ], check: true).stdout().strip()

npy_path = run_command(py, [
    '-c',
    'import os; os.chdir(".."); import numpy; print(os.path.dirname(numpy.__file__).removesuffix("numpy"))'
    ], check: true).stdout().strip()

# TODO: This is a hack due to https://github.com/cython/cython/issues/5820,
# where cython may not find the right __init__.pyd file.
add_project_arguments('-I', npy_path, language : 'cython')

py.extension_module(
    'limited_api1',
    'limited_api1.c',
    c_args: [
      '-DNPY_NO_DEPRECATED_API=NPY_1_21_API_VERSION',
    ],
    include_directories: [npy_include_path],
    limited_api: '3.6',
)

py.extension_module(
    'limited_api_latest',
    'limited_api_latest.c',
    c_args: [
      '-DNPY_NO_DEPRECATED_API=NPY_1_21_API_VERSION',
    ],
    include_directories: [npy_include_path],
    limited_api: py.language_version(),
)

py.extension_module(
    'limited_api2',
    'limited_api2.pyx',
    install: false,
    c_args: [
      '-DNPY_NO_DEPRECATED_API=0',
      # Require 1.25+ to test datetime additions
      '-DNPY_TARGET_VERSION=NPY_2_0_API_VERSION',
      '-DCYTHON_LIMITED_API=1',
    ],
    include_directories: [npy_include_path],
    limited_api: '3.7',
)
