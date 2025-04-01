import os
import sys

def setup_qgis_env():
    """Set up QGIS Python environment for standalone scripts.
    Call this before importing any QGIS modules."""
    
    # QGIS install locations
    qgis_prefix = r"C:\Program Files\QGIS 3.34.9"
    qgis_app = os.path.join(qgis_prefix, "apps", "qgis-ltr")
    qgis_python = os.path.join(qgis_app, "python")
    qgis_bin = os.path.join(qgis_prefix, "bin")
    qgis_app_bin = os.path.join(qgis_app, "bin")
    qt5_bin = os.path.join(qgis_prefix, "apps", "Qt5", "bin")
    proj_share = os.path.join(qgis_prefix, "share", "proj")
    
    # Set environment variables
    paths_to_add = [qgis_bin, qgis_app_bin, qt5_bin]
    for path in paths_to_add:
        if path not in os.environ.get('PATH', ''):
            os.environ['PATH'] = path + os.pathsep + os.environ.get('PATH', '')
    
    os.environ['QGIS_PREFIX_PATH'] = qgis_app
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(qgis_prefix, "apps", "Qt5", "plugins")
    os.environ['PROJ_LIB'] = proj_share
    
    # Add QGIS Python path to sys.path
    if qgis_python not in sys.path:
        sys.path.insert(0, qgis_python)
    
    return {
        'qgis_prefix': qgis_prefix,
        'qgis_app': qgis_app,
        'qgis_python': qgis_python
    }

if __name__ == "__main__":
    # Test the environment setup
    env = setup_qgis_env()
    print("QGIS Environment Setup:")
    for key, value in env.items():
        print(f"  {key}: {value}")
    
    # Test importing QGIS modules
    try:
        from qgis.core import Qgis
        print(f"QGIS import successful - version: {Qgis.version()}")
    except Exception as e:
        print(f"QGIS import failed: {e}")
        
    # Test importing PyQt5
    try:
        from PyQt5.QtCore import QT_VERSION_STR
        print(f"PyQt5 import successful - version: {QT_VERSION_STR}")
    except Exception as e:
        print(f"PyQt5 import failed: {e}")
