"""Cython build script for pyd package"""
import os
import sys
from distutils.core import setup
from Cython.Build import cythonize

PYD_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_DIR = os.path.dirname(PYD_DIR)

sys.path.insert(0, CLIENT_DIR)

setup(
    name="pyd",
    ext_modules=cythonize(
        ["app_config.pyx", "credential_manager.pyx", "mysql_client.pyx"],
        compiler_directives={"language_level": "3"},
        build_dir=os.path.join(PYD_DIR, "_build_c"),
    ),
    script_args=["build_ext", "--inplace"],
)