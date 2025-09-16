import os
import sys

print("== Python Environment Test ==")
print(f"Python: {sys.executable}")

# Try importing QGIS core
try:
    import qgis.core
    print("QGIS core import: SUCCESS")
except Exception as e:
    print(f"QGIS core import: FAILED - {type(e).__name__}: {e}")

# Try importing PyQt5
try:
    import PyQt5.QtCore
    print("PyQt5 import: SUCCESS")
except Exception as e:
    print(f"PyQt5 import: FAILED - {type(e).__name__}: {e}")

# Try importing the plugin module
try:
    import obn_planner
    print("Plugin module import: SUCCESS")
except Exception as e:
    print(f"Plugin module import: FAILED - {type(e).__name__}: {e}")

print("== Test Complete ==")
