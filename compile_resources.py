#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script to compile UI and resource files for QGIS plugin development.
This script will compile all .ui files to their corresponding _ui.py files
and compile the resources.qrc file to resources.py.
"""

import os
import glob
from PyQt5 import uic, pyrcc_main

def compile_ui_files():
    """Compile all .ui files to Python files."""
    print("Compiling UI files...")
    ui_files = glob.glob("*.ui")
    for ui_file in ui_files:
        py_file = os.path.splitext(ui_file)[0] + "_ui.py"
        print(f"  Compiling {ui_file} -> {py_file}")
        with open(py_file, 'w', encoding='utf-8') as f:
            uic.compileUi(ui_file, f)
    print("UI compilation complete.")

def compile_resource_files():
    """Compile all .qrc files to Python files."""
    print("Compiling resource files...")
    qrc_files = glob.glob("*.qrc")
    for qrc_file in qrc_files:
        py_file = os.path.splitext(qrc_file)[0] + ".py"
        print(f"  Compiling {qrc_file} -> {py_file}")
        pyrcc_main.processResourceFile([qrc_file], py_file, False)
    print("Resource compilation complete.")

if __name__ == "__main__":
    print("QGIS Plugin Resource Compiler")
    print("=============================")
    compile_ui_files()
    compile_resource_files()
    print("All files compiled successfully!")
    # Removed input line so the script exits automatically
