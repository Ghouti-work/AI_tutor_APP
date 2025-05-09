# main.py
import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QLoggingCategory

# Optional: Configure Qt WebEngine logging (can be verbose)
# QLoggingCategory.setFilterRules("qt.webenginecontext.debug=false")
# QLoggingCategory.setFilterRules("*.debug=false") # Disable all Qt debug messages

# Ensure paths are set up if running from a bundle later
# if hasattr(sys, '_MEIPASS'): # PyInstaller
#     os.environ['QTWEBENGINE_RESOURCES_PATH'] = os.path.join(sys._MEIPASS, 'PyQt6', 'Qt6', 'resources')
#     os.environ['QT_PLUGIN_PATH'] = os.path.join(sys._MEIPASS, 'PyQt6', 'Qt6', 'plugins')


from main_window import MainWindow # Assuming main_window.py is in the same directory
from core.user_state import user_state
from core.logger_config import app_logger

def main():
    app_logger.info("Application starting...")
    # For HiDPI displays, might be useful:
    # QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling)
    # QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)

    app.setApplicationName("Gemini Adaptive Learning Tutor")
    app.setOrganizationName("YourOrg") 
    app.setApplicationVersion("1.1.0") # Updated version
    
    main_window = MainWindow()

    app.aboutToQuit.connect(main_window.cleanup_threads)
    app.aboutToQuit.connect(user_state.save)
    app.aboutToQuit.connect(lambda: app_logger.info("Application shutting down."))

    main_window.show()
    app_logger.info("MainWindow shown. Entering event loop.")
    
    try:
        sys.exit(app.exec())
    except SystemExit:
        app_logger.info("Application exited.")
    except Exception as e:
        app_logger.critical(f"Unhandled exception in QApplication: {e}", exc_info=True)

if __name__ == '__main__':
    main()