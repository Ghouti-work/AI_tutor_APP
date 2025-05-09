# themes.py

LIGHT_THEME_STYLESHEET = """
    QWidget {
        background-color: #f0f0f0;
        color: #333333;
        font-family: Arial, sans-serif;
    }
    QPushButton {
        background-color: #e0e0e0;
        border: 1px solid #c0c0c0;
        padding: 5px;
        min-height: 25px;
        border-radius: 3px; /* Added for consistency */
    }
    QPushButton:hover {
        background-color: #d0d0d0;
    }
    QPushButton:pressed {
        background-color: #c0c0c0;
    }
    QPushButton:disabled {
        background-color: #f5f5f5;
        color: #a0a0a0;
    }
    QLineEdit, QTextEdit, QSpinBox {
        background-color: #ffffff;
        border: 1px solid #c0c0c0;
        padding: 3px;
        border-radius: 3px;
        selection-background-color: #a8caff;
        selection-color: #000000;
    }
    QTextEdit[readOnly="true"] {
        background-color: #e8e8e8;
    }
    QComboBox {
        background-color: #ffffff;
        border: 1px solid #c0c0c0;
        padding: 3px;
        border-radius: 3px;
        min-height: 20px; /* Ensure combo box has some height */
    }
    QComboBox::drop-down {
        border: none;
        /* You might need to provide a small image for the arrow or style it */
    }
    QComboBox::down-arrow {
        /* image: url(path/to/light_arrow.png); */
        /* For simplicity, often left to native rendering or a simple border */
        /* border-left: 1px solid #c0c0c0; */
    }
    QGroupBox {
        font-weight: bold;
        border: 1px solid #c0c0c0;
        border-radius: 5px;
        margin-top: 12px; /* Space for title */
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 5px 0 5px;
        left: 7px; /* Align title slightly from left */
        background-color: #f0f0f0; /* Match QWidget background */
    }
    QListWidget, QTableWidget {
        background-color: #ffffff;
        border: 1px solid #c0c0c0;
        alternate-background-color: #f7f7f7;
        selection-background-color: #a8caff;
        selection-color: #000000;
    }
    QHeaderView::section {
        background-color: #e0e0e0;
        border: 1px solid #c0c0c0;
        padding: 4px;
    }
    QProgressBar {
        border: 1px solid #c0c0c0;
        border-radius: 3px;
        text-align: center;
        background-color: #e8e8e8;
    }
    QProgressBar::chunk {
        background-color: #50a0d0;
        border-radius: 2px; /* Match progress bar radius */
        /* width: 10px; margin: 0.5px; (Chunk width/margin might not be needed if chunk is continuous) */
    }
    QLabel {
        /* color: #333333; (inherited) */
    }
    QStackedWidget {
        /* No specific styling needed usually, it's a container */
    }
    QSplitter::handle {
        background-color: #d0d0d0; /* Light gray handle */
        /* image: url(path/to/splitter_handle.png); */
    }
    QSplitter::handle:horizontal {
        width: 5px;
    }
    QSplitter::handle:vertical {
        height: 5px;
    }
    QSplitter::handle:hover {
        background-color: #c0c0c0;
    }


    /* --- Specific ObjectName Styling --- */
    #SidebarWidget {
        background-color: #d8e2eb; /* Lighter blue-gray for sidebar */
        border-right: 1px solid #b0b8c0;
    }
    #SidebarWidget QPushButton {
        background-color: #e8f0f5; /* Slightly off-white for sidebar buttons */
        border: 1px solid #b0b8c0;
        color: #212529;
        text-align: left; padding-left: 15px; font-size: 11pt;
        border-radius: 5px;
        height: 45px; /* Explicit height for sidebar buttons */
    }
    #SidebarWidget QPushButton:hover {
        background-color: #d0d8e0;
    }
    #SidebarWidget QPushButton:pressed {
        background-color: #c0c8d0;
    }
    #SidebarWidget QPushButton:disabled {
        background-color: #e0e5ea;
        color: #70757a;
    }
    #FeedbackLabel {
        padding: 5px;
        border-top: 1px solid #c0c0c0;
        background-color: #e8e8e8;
        font-style: italic;
        color: #444444;
    }
    /* Ensure QWebEngineView has a clear background or matches the theme */
    QWebEngineView {
        background-color: #ffffff; /* Or a very light gray */
    }
"""

DARK_THEME_STYLESHEET = """
    QWidget {
        background-color: #2e2e2e;
        color: #e0e0e0;
        font-family: Arial, sans-serif;
    }
    QPushButton {
        background-color: #4a4a4a;
        border: 1px solid #606060;
        color: #e0e0e0;
        padding: 5px;
        min-height: 25px;
        border-radius: 3px;
    }
    QPushButton:hover {
        background-color: #5a5a5a;
    }
    QPushButton:pressed {
        background-color: #6a6a6a;
    }
    QPushButton:disabled {
        background-color: #383838;
        color: #808080;
    }
    QLineEdit, QTextEdit, QSpinBox {
        background-color: #3c3c3c;
        border: 1px solid #606060;
        color: #e0e0e0;
        padding: 3px;
        border-radius: 3px;
        selection-background-color: #007acc; /* Brighter blue for dark mode selection */
        selection-color: #ffffff;
    }
    QTextEdit[readOnly="true"] {
        background-color: #353535;
    }
    QComboBox {
        background-color: #3c3c3c;
        border: 1px solid #606060;
        color: #e0e0e0;
        padding: 3px;
        border-radius: 3px;
        min-height: 20px;
    }
    QComboBox::drop-down {
        border: none;
    }
    QComboBox::down-arrow {
        /* image: url(path/to/dark_arrow.png); */
        /* border-left: 1px solid #606060; */
    }
    QGroupBox {
        font-weight: bold;
        color: #e0e0e0;
        border: 1px solid #606060;
        border-radius: 5px;
        margin-top: 12px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 5px 0 5px;
        left: 7px;
        background-color: #2e2e2e; /* Match QWidget background */
        color: #e0e0e0; /* Ensure title is visible */
    }
    QListWidget, QTableWidget {
        background-color: #3c3c3c;
        border: 1px solid #606060;
        color: #e0e0e0;
        alternate-background-color: #333333;
        selection-background-color: #007acc;
        selection-color: #ffffff;
    }
    QHeaderView::section {
        background-color: #4a4a4a;
        border: 1px solid #606060;
        color: #e0e0e0;
        padding: 4px;
    }
    QProgressBar {
        border: 1px solid #606060;
        border-radius: 3px;
        text-align: center;
        color: #e0e0e0;
        background-color: #383838;
    }
    QProgressBar::chunk {
        background-color: #007acc; /* A brighter blue for dark mode */
        border-radius: 2px;
    }
    QLabel {
        /* color: #e0e0e0; (inherited) */
    }
    QStackedWidget {
        /* background-color: #2e2e2e; (to ensure it matches if it has a border or padding) */
    }
    QSplitter::handle {
        background-color: #404040; /* Darker gray handle */
    }
    QSplitter::handle:horizontal {
        width: 5px;
    }
    QSplitter::handle:vertical {
        height: 5px;
    }
    QSplitter::handle:hover {
        background-color: #505050;
    }

    /* --- Specific ObjectName Styling --- */
    #SidebarWidget {
        background-color: #252525; /* Darker sidebar */
        border-right: 1px solid #404040;
    }
    #SidebarWidget QPushButton {
        background-color: #3a3a3a;
        border: 1px solid #505050;
        color: #d0d0d0;
        text-align: left; padding-left: 15px; font-size: 11pt;
        border-radius: 5px;
        height: 45px;
    }
    #SidebarWidget QPushButton:hover {
        background-color: #484848;
    }
    #SidebarWidget QPushButton:pressed {
        background-color: #555555;
    }
    #SidebarWidget QPushButton:disabled {
        background-color: #303030;
        color: #707070;
    }
    #FeedbackLabel {
        padding: 5px;
        border-top: 1px solid #404040;
        background-color: #353535;
        font-style: italic;
        color: #c0c0c0;
    }
    QWebEngineView {
        background-color: #282828; /* Dark background for web view area */
    }
"""

