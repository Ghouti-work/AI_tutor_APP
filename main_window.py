# main_window.py

import sys
import os
import re
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QTextEdit, QProgressBar, QListWidget, QListWidgetItem, QMessageBox,
    QSizePolicy, QComboBox, QSpinBox, QStackedWidget,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QLineEdit
)
from PyQt6.QtCore import Qt, QUrl, QTimer, QSize, QObject, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QFont, QFontMetrics

try:
    from themes import LIGHT_THEME_STYLESHEET, DARK_THEME_STYLESHEET
except ImportError:
    LIGHT_THEME_STYLESHEET = "QWidget { background-color: #f0f0f0; color: black; font-family: Arial; font-size: 10pt; }"
    DARK_THEME_STYLESHEET = "QWidget { background-color: #333333; color: white; font-family: Arial; font-size: 10pt; }"
    try:
        from core.logger_config import app_logger
        if app_logger: app_logger.warning("themes.py not found. Using basic fallback styling.")
    except ImportError:
        print("Warning: themes.py not found and app_logger not available. Using basic styling.")

from PyQt6.QtWebEngineWidgets import QWebEngineView

from datetime import datetime
import time
import urllib.parse

from agents.gemini_agent import (
    summarize_pdf_content, get_youtube_search_query_and_main_topic,
    fetch_youtube_transcript, summarize_text_for_chat_context,
    generate_explanation, generate_standard_quiz, generate_aggregated_quiz,
    evaluate_answer, generate_learning_summary, extract_skills_from_text,
    ask_follow_up_question, ask_question_about_video
)
from core.session import LearningSession, VideoInteractionSession, AssessmentSession, MAX_SESSION_ATTEMPTS, DEFAULT_AGGREGATED_EXAM_QUESTIONS
from core.user_state import user_state
from core.logger_config import app_logger

XP_GAIN_ON_SUCCESS = 10
XP_GAIN_ON_LESSON_QUIZ_MULTIPLIER = 1.5
XP_GAIN_ON_AGGREGATED_EXAM_MULTIPLIER = 2.0
DEFAULT_NUM_QUESTIONS = 3

LANGUAGES = {
    "English": "English", "Español (Spanish)": "Spanish", "Français (French)": "French",
    "Deutsch (German)": "German", "日本語 (Japanese)": "Japanese", "Português (Portuguese)": "Portuguese",
    "Italiano (Italian)": "Italian", "中文 (Chinese)": "Chinese"
}

def extract_video_id(url):
    if not url: return None
    regex = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
    match = re.search(regex, url)
    return match.group(1) if match else None

class GeminiWorker(QObject):
    finished = pyqtSignal(str, object)
    error = pyqtSignal(str, str)
    def __init__(self, task_id, function_to_run, *args, **kwargs):
        super().__init__(); self.task_id = task_id; self.function_to_run = function_to_run
        self.args = args; self.kwargs = kwargs; app_logger.debug(f"Worker created: {self.task_id}")
    def run(self):
        try:
            app_logger.info(f"Worker '{self.task_id}' starting."); result = self.function_to_run(*self.args, **self.kwargs)
            app_logger.info(f"Worker '{self.task_id}' finished."); self.finished.emit(self.task_id, result)
        except Exception as e:
            app_logger.error(f"Worker error ({self.task_id}): {e}", exc_info=True); self.error.emit(self.task_id, str(e))

class MainWindow(QWidget):
    def __init__(self):
        super().__init__(); app_logger.info("MainWindow initializing...")
        self.setWindowTitle("Gemini Adaptive Learning Tutor"); self.setMinimumSize(1200, 800)
        self.current_theme = user_state.theme 
        self.threads = {}; self.current_learning_session = None; self.current_video_session = None
        self.current_assessment_session = None; self.pdf_summary_content = ""
        self.current_pdf_topic_name = "General"; self.selected_language_name = user_state.language
        self.topic_start_time = None; self.suggested_youtube_search_url = None
        self.current_video_id = None; self.current_video_title = "No Video Loaded"
        self.current_video_transcript_summary = None
        self.current_active_session_id = None 
        self._last_loaded_pdf_paths = [] 

        self._init_ui()
        self.apply_theme(self.current_theme)
        self.stacked_widget.setCurrentIndex(0) 
        self.update_ui_status() 
        app_logger.info("MainWindow initialized. Default: Learning Page.")

    def _init_ui(self):
        app_logger.debug("Initializing UI...")
        self.overall_layout = QHBoxLayout(self)
        self.sidebar_widget = QWidget(); self.sidebar_widget.setObjectName("SidebarWidget")
        self.sidebar_layout = QVBoxLayout(self.sidebar_widget); self.sidebar_widget.setFixedWidth(230)
        self.main_content_area = QWidget(); self.main_content_layout = QVBoxLayout(self.main_content_area)
        
        top_bar = QHBoxLayout(); user_info = QHBoxLayout(); self.level_xp_label = QLabel()
        user_info.addWidget(self.level_xp_label); self.xp_progress_bar = QProgressBar()
        self.xp_progress_bar.setFixedHeight(15); self.xp_progress_bar.setTextVisible(False)
        self.xp_progress_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        user_info.addWidget(self.xp_progress_bar); top_bar.addLayout(user_info, 3)
        
        controls = QHBoxLayout(); controls.addWidget(QLabel("Language:"))
        self.language_combo = QComboBox()
        for name, val in LANGUAGES.items(): self.language_combo.addItem(name, val)
        idx = self.language_combo.findData(user_state.language)
        if idx != -1: self.language_combo.setCurrentIndex(idx)
        else: 
            english_idx = self.language_combo.findData(LANGUAGES["English"])
            if english_idx != -1: self.language_combo.setCurrentIndex(english_idx)
        self.language_combo.currentTextChanged.connect(self.language_changed_action)
        controls.addWidget(self.language_combo)
        
        self.btn_refresh_ui_status = QPushButton("🔄"); self.btn_refresh_ui_status.setToolTip("Refresh UI Status")
        self.btn_refresh_ui_status.setFixedSize(35, 30); self.btn_refresh_ui_status.clicked.connect(self.update_ui_status_manually)
        controls.addWidget(self.btn_refresh_ui_status)
        self.btn_toggle_theme = QPushButton("🌙"); self.btn_toggle_theme.setToolTip("Toggle Theme")
        self.btn_toggle_theme.setFixedSize(35, 30); self.btn_toggle_theme.clicked.connect(self.toggle_theme_action)
        controls.addWidget(self.btn_toggle_theme)
        top_bar.addLayout(controls); self.main_content_layout.addLayout(top_bar)

        self.stacked_widget = QStackedWidget(); self.main_content_layout.addWidget(self.stacked_widget, 1)
        
        self._init_learning_page()     
        self._init_video_player_page() 
        self._init_assessment_page()   
        self._init_previous_sessions_page() 
        self._init_dashboard_page()    

        self._init_sidebar() 
        self.overall_layout.addWidget(self.sidebar_widget); self.overall_layout.addWidget(self.main_content_area, 1)
        self.feedback_label = QLabel("Welcome! Load PDF(s) or explore features."); self.feedback_label.setObjectName("FeedbackLabel")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter); self.feedback_label.setWordWrap(True)
        self.feedback_label.setFixedHeight(40); self.main_content_layout.addWidget(self.feedback_label)
        app_logger.debug("UI initialized.")
    
    def _init_sidebar(self):
        title = QLabel("<h2>Tutor Menu</h2>"); title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sidebar_layout.addWidget(title); self.sidebar_layout.addSpacing(15)
        self.btn_load_pdf = QPushButton("📚 Load PDF(s)"); self.btn_load_pdf.clicked.connect(self.load_pdf_action_threaded)
        self.sidebar_layout.addWidget(self.btn_load_pdf); self.sidebar_layout.addSpacing(20)
        
        nav_info = [("🎓 Learning & Chat", 0, "learn.png"), ("▶️ Video Player", 1, "video.png"), 
                      ("📝 Assessments", 2, "assessment.png"), ("📖 Previous Sessions", 3, "previous.png"), 
                      ("📊 Dashboard", 4, "dashboard.png")]
        for text, idx, icon_name in nav_info:
            btn = QPushButton(text); btn.clicked.connect(lambda checked=False, i=idx: self.navigate_to_page(i))
            icon_base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))) 
            icon_path = os.path.join(icon_base_path, "assets", "icons", icon_name)
            if os.path.exists(icon_path): btn.setIcon(QIcon(icon_path))
            else: app_logger.warning(f"Sidebar icon not found: {icon_path} (for {text})")
            self.sidebar_layout.addWidget(btn)
        self.sidebar_layout.addStretch(1)
        self.btn_quit_app = QPushButton("🚪 Exit Application"); self.btn_quit_app.clicked.connect(self.close)
        exit_icon_base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        exit_icon_path = os.path.join(exit_icon_base_path, "assets", "icons", "exit.png")
        if os.path.exists(exit_icon_path): self.btn_quit_app.setIcon(QIcon(exit_icon_path))
        self.sidebar_layout.addWidget(self.btn_quit_app)

    def _init_learning_page(self): # Index 0
        self.learning_page = QWidget(); self.learning_page.setObjectName("LearningPage")
        layout = QVBoxLayout(self.learning_page); title = QLabel("<h2>🎓 Learning & Chat</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(title)
        page_controls = QHBoxLayout(); self.btn_start_lesson = QPushButton("🚀 Start/Restart Lesson")
        self.btn_start_lesson.setToolTip("New learning session with current PDF summary.")
        self.btn_start_lesson.clicked.connect(self.start_lesson_action); page_controls.addWidget(self.btn_start_lesson)
        self.btn_explain_more = QPushButton("💡 Explain More"); self.btn_explain_more.setToolTip("Get a more detailed explanation.")
        self.btn_explain_more.clicked.connect(self.explain_more_action_threaded); page_controls.addWidget(self.btn_explain_more)
        quiz_settings = QHBoxLayout(); quiz_settings.addWidget(QLabel("Quiz Qs:"))
        self.num_lesson_questions_spinbox = QSpinBox(); self.num_lesson_questions_spinbox.setRange(1,10)
        self.num_lesson_questions_spinbox.setValue(DEFAULT_NUM_QUESTIONS); quiz_settings.addWidget(self.num_lesson_questions_spinbox)
        page_controls.addLayout(quiz_settings); layout.addLayout(page_controls)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.learning_content_display = QTextEdit("Load PDF & start lesson for content."); self.learning_content_display.setReadOnly(True)
        splitter.addWidget(self.learning_content_display)
        self.learning_chat_group = QGroupBox("💬 Chat with Tutor"); self.learning_chat_group.setCheckable(True); self.learning_chat_group.setChecked(True)
        chat_layout = QVBoxLayout(); self.learning_chat_display = QTextEdit(); self.learning_chat_display.setReadOnly(True)
        self.learning_chat_display.setPlaceholderText("Tutor responses..."); chat_layout.addWidget(self.learning_chat_display, 1)
        chat_input_layout = QHBoxLayout(); self.learning_chat_input = QLineEdit(); self.learning_chat_input.setPlaceholderText("Ask about lesson...")
        self.learning_chat_input.returnPressed.connect(self.send_lesson_chat_action_threaded); chat_input_layout.addWidget(self.learning_chat_input)
        self.btn_send_lesson_chat = QPushButton("Ask"); self.btn_send_lesson_chat.clicked.connect(self.send_lesson_chat_action_threaded)
        chat_input_layout.addWidget(self.btn_send_lesson_chat); chat_layout.addLayout(chat_input_layout)
        self.learning_chat_group.setLayout(chat_layout); splitter.addWidget(self.learning_chat_group)
        splitter.setSizes([int(self.height()*0.65), int(self.height()*0.35)]); layout.addWidget(splitter,1)
        self.lesson_quiz_display = QTextEdit(); self.lesson_quiz_display.setReadOnly(True); self.lesson_quiz_display.setPlaceholderText("Lesson quiz...")
        self.lesson_quiz_display.setVisible(False); layout.addWidget(self.lesson_quiz_display)
        self.lesson_answer_input = QTextEdit(); self.lesson_answer_input.setPlaceholderText("Your answer(s)..."); self.lesson_answer_input.setFixedHeight(80)
        self.lesson_answer_input.setVisible(False); layout.addWidget(self.lesson_answer_input)
        self.btn_submit_lesson_answer = QPushButton("Submit Lesson Answer"); self.btn_submit_lesson_answer.clicked.connect(lambda: self.submit_answer_action(False))
        self.btn_submit_lesson_answer.setVisible(False); layout.addWidget(self.btn_submit_lesson_answer)
        self.stacked_widget.addWidget(self.learning_page)

    def _init_video_player_page(self): # Index 1
        self.video_page = QWidget(); self.video_page.setObjectName("VideoPage")
        main_layout = QVBoxLayout(self.video_page); title = QLabel("<h2>▶️ Video Player & Interaction</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter); main_layout.addWidget(title)
        controls_layout = QHBoxLayout(); self.btn_ai_suggest_video = QPushButton("🤖 AI Suggest Video")
        self.btn_ai_suggest_video.setToolTip("AI Suggest Video for PDF Topic"); self.btn_ai_suggest_video.clicked.connect(self.ai_suggest_and_load_video_action)
        controls_layout.addWidget(self.btn_ai_suggest_video); controls_layout.addWidget(QLabel("Manual URL:"))
        self.manual_video_url_input = QLineEdit(); self.manual_video_url_input.setPlaceholderText("YouTube URL + Enter/Load")
        self.manual_video_url_input.returnPressed.connect(self.load_manual_video_action); controls_layout.addWidget(self.manual_video_url_input,1)
        self.btn_load_manual_video = QPushButton("Load URL"); self.btn_load_manual_video.clicked.connect(self.load_manual_video_action)
        controls_layout.addWidget(self.btn_load_manual_video); main_layout.addLayout(controls_layout)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        player_container = QGroupBox("Video Player"); player_layout = QVBoxLayout()
        self.video_web_view = QWebEngineView(); self.video_web_view.setMinimumHeight(350)
        player_layout.addWidget(self.video_web_view,1); player_container.setLayout(player_layout); splitter.addWidget(player_container)
        extras_group = QGroupBox("Video Transcript & Chat"); extras_layout = QVBoxLayout()
        self.btn_fetch_transcript = QPushButton("Fetch Transcript & Summary"); self.btn_fetch_transcript.setToolTip("Fetch and summarize video transcript.")
        self.btn_fetch_transcript.clicked.connect(self.fetch_video_transcript_action_threaded); extras_layout.addWidget(self.btn_fetch_transcript)
        self.video_transcript_display = QTextEdit(); self.video_transcript_display.setReadOnly(True); self.video_transcript_display.setPlaceholderText("Transcript summary...")
        extras_layout.addWidget(self.video_transcript_display,1)
        video_chat_group = QGroupBox("Chat with Video"); video_chat_inner = QVBoxLayout()
        self.video_chat_display = QTextEdit(); self.video_chat_display.setReadOnly(True); self.video_chat_display.setPlaceholderText("Ask about video...")
        video_chat_inner.addWidget(self.video_chat_display,1)
        video_chat_input_layout = QHBoxLayout(); self.video_chat_input = QLineEdit(); self.video_chat_input.setPlaceholderText("Ask...")
        self.video_chat_input.returnPressed.connect(self.send_video_chat_action_threaded); video_chat_input_layout.addWidget(self.video_chat_input)
        self.btn_send_video_chat = QPushButton("Ask Video"); self.btn_send_video_chat.clicked.connect(self.send_video_chat_action_threaded)
        video_chat_input_layout.addWidget(self.btn_send_video_chat); video_chat_inner.addLayout(video_chat_input_layout)
        video_chat_group.setLayout(video_chat_inner); extras_layout.addWidget(video_chat_group)
        extras_group.setLayout(extras_layout); splitter.addWidget(extras_group)
        splitter.setSizes([int(self.width()*0.6), int(self.width()*0.4)]); main_layout.addWidget(splitter,1)
        self.stacked_widget.addWidget(self.video_page)

    def _init_assessment_page(self): # Index 2
        self.assessment_page = QWidget(); self.assessment_page.setObjectName("AssessmentPage")
        layout = QVBoxLayout(self.assessment_page); title = QLabel("<h2>📝 Assessment Center</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(title)
        controls = QHBoxLayout(); self.btn_start_aggregated_exam = QPushButton("🚀 Start Comprehensive Exam")
        self.btn_start_aggregated_exam.setToolTip("Exam on PDF & Video content."); self.btn_start_aggregated_exam.clicked.connect(self.start_aggregated_exam_action_threaded)
        controls.addWidget(self.btn_start_aggregated_exam); controls.addWidget(QLabel("Questions:"))
        self.num_assessment_questions_spinbox = QSpinBox(); self.num_assessment_questions_spinbox.setRange(3,25)
        self.num_assessment_questions_spinbox.setValue(DEFAULT_AGGREGATED_EXAM_QUESTIONS); controls.addWidget(self.num_assessment_questions_spinbox)
        layout.addLayout(controls)
        self.assessment_info_label = QLabel("Load PDF & Video (fetch transcript) for comprehensive assessment."); self.assessment_info_label.setWordWrap(True)
        self.assessment_info_label.setObjectName("AssessmentInfoLabel"); layout.addWidget(self.assessment_info_label)
        self.assessment_questions_display = QTextEdit(); self.assessment_questions_display.setReadOnly(True); self.assessment_questions_display.setPlaceholderText("Assessment questions...")
        self.assessment_questions_display.setVisible(False); layout.addWidget(self.assessment_questions_display,1)
        self.assessment_answer_input = QTextEdit(); self.assessment_answer_input.setPlaceholderText("Your answer(s)..."); self.assessment_answer_input.setFixedHeight(100)
        self.assessment_answer_input.setVisible(False); layout.addWidget(self.assessment_answer_input)
        self.btn_submit_assessment_answer = QPushButton("Submit Assessment Answer"); self.btn_submit_assessment_answer.clicked.connect(lambda: self.submit_answer_action(True))
        self.btn_submit_assessment_answer.setVisible(False); layout.addWidget(self.btn_submit_assessment_answer)
        self.stacked_widget.addWidget(self.assessment_page)

    def _init_previous_sessions_page(self): # Index 3
        self.previous_sessions_page = QWidget(); self.previous_sessions_page.setObjectName("PreviousSessionsPage")
        layout = QVBoxLayout(self.previous_sessions_page); title = QLabel("<h2>📖 Previous Learning Sessions</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(title)
        self.previous_sessions_list = QListWidget(); self.previous_sessions_list.setAlternatingRowColors(True)
        self.previous_sessions_list.itemDoubleClicked.connect(self.load_selected_previous_session)
        layout.addWidget(self.previous_sessions_list, 1)
        controls_layout = QHBoxLayout(); btn_refresh_sessions = QPushButton("🔄 Refresh List")
        btn_refresh_sessions.clicked.connect(self.populate_previous_sessions_list)
        controls_layout.addWidget(btn_refresh_sessions); controls_layout.addStretch(1)
        layout.addLayout(controls_layout)
        self.stacked_widget.addWidget(self.previous_sessions_page)

    def _init_dashboard_page(self): # Index 4
        self.dashboard_page = QWidget(); self.dashboard_page.setObjectName("DashboardPage")
        layout = QVBoxLayout(self.dashboard_page); title = QLabel("<h2>📊 User Dashboard</h2>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(title)
        splitter = QSplitter(Qt.Orientation.Vertical)
        skills_group = QGroupBox("🧠 Learned Skills/Topics"); skills_layout = QVBoxLayout()
        self.dashboard_skills_list_widget = QListWidget(); self.dashboard_skills_list_widget.setAlternatingRowColors(True)
        skills_layout.addWidget(self.dashboard_skills_list_widget); skills_group.setLayout(skills_layout); splitter.addWidget(skills_group)
        time_group = QGroupBox("⏱️ Time Spent per Topic"); time_layout = QVBoxLayout()
        self.time_table_widget = QTableWidget(); self.time_table_widget.setColumnCount(2)
        self.time_table_widget.setHorizontalHeaderLabels(["Topic","Time (HH:MM:SS)"])
        self.time_table_widget.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.time_table_widget.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.time_table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.time_table_widget.setAlternatingRowColors(True)
        self.time_table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); time_layout.addWidget(self.time_table_widget)
        time_group.setLayout(time_layout); splitter.addWidget(time_group)
        splitter.setSizes([int(self.height()*0.4), int(self.height()*0.6)]); layout.addWidget(splitter,1)
        refresh_btn = QPushButton("🔄 Refresh Dashboard"); refresh_btn.clicked.connect(self.update_dashboard_page)
        refresh_btn.setFixedWidth(180); layout.addWidget(refresh_btn,0,Qt.AlignmentFlag.AlignRight)
        self.stacked_widget.addWidget(self.dashboard_page)

    def apply_theme(self, theme_name):
        app = QApplication.instance()
        if app is None: app_logger.error("QApp instance None in apply_theme."); return
        self.current_theme = theme_name 
        if theme_name == "dark":
            app.setStyleSheet(DARK_THEME_STYLESHEET)
            self.btn_toggle_theme.setText("☀️"); self.btn_toggle_theme.setToolTip("Switch to Light Theme")
        else: 
            app.setStyleSheet(LIGHT_THEME_STYLESHEET)
            self.btn_toggle_theme.setText("🌙"); self.btn_toggle_theme.setToolTip("Switch to Dark Theme")
        app_logger.info(f"Applied {theme_name.capitalize()} Theme.")
        
    def toggle_theme_action(self):
        new_theme = "dark" if self.current_theme == "light" else "light"
        self.apply_theme(new_theme); user_state.theme = new_theme; user_state.save()

    def navigate_to_page(self, index):
        self.stacked_widget.setCurrentIndex(index)
        page_map = {0: "Learning", 1: "Video", 2: "Assessments", 3: "Previous Sessions", 4: "Dashboard"}
        page_name = page_map.get(index, "Unknown Page")
        self.feedback_label.setText(f"Navigated to {page_name} page.")
        if page_name == "Dashboard": self.update_dashboard_page()
        if page_name == "Previous Sessions": self.populate_previous_sessions_list()
        self.update_ui_status()

    def populate_previous_sessions_list(self):
        self.previous_sessions_list.clear()
        if not hasattr(user_state, 'previous_sessions') or not user_state.previous_sessions:
            self.previous_sessions_list.addItem(QListWidgetItem("No previous sessions found."))
            return
        for session_data in user_state.previous_sessions:
            ts_str = session_data.get('timestamp', 'N/A')
            try: date_str = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).strftime('%Y-%m-%d %H:%M')
            except ValueError: date_str = ts_str 
            item_text = f"{session_data.get('topic_name', 'Untitled')} ({date_str})"
            item = QListWidgetItem(item_text); item.setData(Qt.ItemDataRole.UserRole, session_data.get("id"))
            self.previous_sessions_list.addItem(item)

    def load_selected_previous_session(self, item: QListWidgetItem):
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if not session_id: return
        session_data = user_state.get_session_by_id(session_id)
        if not session_data: QMessageBox.warning(self, "Error", "Session data not found."); return

        app_logger.info(f"Loading previous session: {session_id} - {session_data.get('topic_name')}")
        self._stop_current_topic_timer(); self.current_active_session_id = session_id
        self.pdf_summary_content = session_data.get("pdf_summary", "")
        self.current_pdf_topic_name = session_data.get("topic_name", "Restored Topic")
        self._last_loaded_pdf_paths = session_data.get("pdf_file_paths", [])

        display_content = (f"**Topic: {self.current_pdf_topic_name} (Restored Session)**\n\n"
                           f"*PDF Summary:*\n\n---\n{self.pdf_summary_content}")
        last_explanation = session_data.get("last_explanation")
        chat_history = session_data.get("chat_history", [])
        self.learning_chat_display.clear()

        if last_explanation or chat_history:
            self.current_learning_session = LearningSession(
                self.pdf_summary_content, user_state.level, self.selected_language_name
            )
            # Do not automatically show COMPLETED explanations, just the summary
            if last_explanation and not last_explanation.startswith("COMPLETED:"):
                self.current_learning_session.current_explanation = last_explanation
                display_content = last_explanation 
            
            self.current_learning_session.tutor_chat_history = chat_history
            for entry in chat_history:
                role_disp = "You" if entry["role"] == "user" else "Tutor"
                self.learning_chat_display.append(f"<b>{role_disp}:</b> {entry['text']}\n")
        else: self.current_learning_session = None
        
        self.learning_content_display.setMarkdown(display_content)
        self.feedback_label.setText(f"Restored session: '{self.current_pdf_topic_name}'.")
        self._reset_lesson_quiz_ui(); self._reset_assessment_ui()
        self.navigate_to_page(0); self.topic_start_time = time.time(); self.update_ui_status()

    def _save_current_learning_state_as_session(self, session_type="update"):
        if not self.current_pdf_topic_name or not self.pdf_summary_content:
            app_logger.warning("Cannot save session: No PDF topic or summary."); return
        session_id = self.current_active_session_id
        if not session_id:
            safe_topic = "".join(c if c.isalnum() else "_" for c in self.current_pdf_topic_name.replace(" ", "_"))
            session_id = f"{int(time.time())}_{safe_topic[:30]}"; self.current_active_session_id = session_id
        
        session_data = {
            "id": session_id, "topic_name": self.current_pdf_topic_name, "pdf_summary": self.pdf_summary_content,
            "pdf_file_paths": [os.path.basename(p) for p in self._last_loaded_pdf_paths] if hasattr(self, '_last_loaded_pdf_paths') else [],
            "last_explanation": self.current_learning_session.current_explanation if self.current_learning_session else None,
            "chat_history": self.current_learning_session.tutor_chat_history if self.current_learning_session else [],
            "timestamp": datetime.now().isoformat(), "session_type": session_type
        }
        user_state.add_or_update_session(session_data)
        app_logger.info(f"Saved/Updated session ID: {session_id} (Type: {session_type})")

    def update_dashboard_page(self):
        app_logger.debug("Updating dashboard page.")
        self.dashboard_skills_list_widget.clear()
        if user_state.skills: self.dashboard_skills_list_widget.addItems(sorted(list(set(user_state.skills))))
        else: self.dashboard_skills_list_widget.addItem("No skills learned yet.")
        self.time_table_widget.setRowCount(0)
        if user_state.time_per_topic:
            valid_topics = {k:v for k,v in user_state.time_per_topic.items() if k and k!="General" and v>0}
            self.time_table_widget.setRowCount(len(valid_topics))
            for i,(topic,sec) in enumerate(sorted(valid_topics.items(),key=lambda x:x[1],reverse=True)):
                self.time_table_widget.setItem(i,0,QTableWidgetItem(topic))
                self.time_table_widget.setItem(i,1,QTableWidgetItem(time.strftime('%H:%M:%S',time.gmtime(sec))))
        app_logger.debug("Dashboard page updated.")

    def language_changed_action(self, display_name):
        val = self.language_combo.currentData()
        if val:
            self.selected_language_name = val; user_state.language = val; user_state.save()
            self.feedback_label.setText(f"Language: {display_name} ({val}).")
            app_logger.info(f"Language changed to {display_name} ({val}).")
            for sess_attr in ['current_learning_session', 'current_video_session', 'current_assessment_session']:
                sess = getattr(self, sess_attr, None)
                if sess: sess.language = val
        else: app_logger.warning(f"Lang change to '{display_name}' failed to find value.")

    def update_ui_status_manually(self):
        app_logger.info("Manual UI status refresh."); self.update_ui_status()
        current_feedback = self.feedback_label.text() # Storing current before changing
        self.feedback_label.setText("UI status refreshed manually.")
        # Use a property to store pre-refresh text if not already the refresh message
        if current_feedback != "UI status refreshed manually.":
             self.feedback_label.setProperty("original_text_before_manual_refresh", current_feedback)

        QTimer.singleShot(3000, lambda: self.feedback_label.setText(self.feedback_label.property("original_text_before_manual_refresh") or "Ready.") if self.feedback_label.text() == "UI status refreshed manually." else None)

    def update_ui_status(self):
        app_logger.debug("Updating UI status...")
        xp_needed=user_state.get_xp_for_next_level(); self.level_xp_label.setText(f"Lvl: {user_state.level} | XP: {int(user_state.xp)}/{xp_needed}")
        self.xp_progress_bar.setMaximum(xp_needed if xp_needed > 0 else 100); self.xp_progress_bar.setValue(int(user_state.xp))
        pdf_ok = bool(self.pdf_summary_content and not self.pdf_summary_content.startswith("Error:"))
        vid_tx_ok = bool(self.current_video_transcript_summary and not self.current_video_transcript_summary.startswith("Error:"))
        lesson_quiz_on = self.btn_submit_lesson_answer.isVisible(); assess_quiz_on = self.btn_submit_assessment_answer.isVisible()
        any_quiz = lesson_quiz_on or assess_quiz_on
        busy_pdf = any(tid.startswith("pdf_") or tid.startswith("topic_") for tid in self.threads)
        busy_lesson = any(tid.startswith("explanation_") or tid.startswith("lesson_quiz_") for tid in self.threads)
        busy_video = any(tid.startswith("transcript_") or tid.startswith("ai_video_") for tid in self.threads)
        busy_assess = any(tid.startswith("assessment_") for tid in self.threads)
        busy_chat = any(tid.startswith("lesson_chat_") or tid.startswith("video_chat_") for tid in self.threads)
        busy_eval = any(tid.startswith("evaluate_") for tid in self.threads)
        ui_locked = any_quiz or busy_pdf or busy_lesson or busy_video or busy_assess or busy_eval

        self.btn_load_pdf.setEnabled(not ui_locked)
        # Enable start lesson if PDF is loaded, not busy, AND no lesson is currently active OR current active lesson is marked "COMPLETED"
        can_start_new_lesson = pdf_ok and not ui_locked and \
                                (not self.current_learning_session or \
                                 (self.current_learning_session and self.current_learning_session.current_explanation and \
                                  self.current_learning_session.current_explanation.startswith("COMPLETED:")))
        self.btn_start_lesson.setEnabled(can_start_new_lesson)

        can_explain = bool(self.current_learning_session and self.current_learning_session.current_explanation and not ui_locked and not self.current_learning_session.current_explanation.startswith("COMPLETED:"))
        self.btn_explain_more.setEnabled(can_explain)
        
        chat_ok = False
        if self.current_learning_session and (self.current_learning_session.current_explanation or self.current_learning_session.initial_content_summary) and not (self.current_learning_session.current_explanation and self.current_learning_session.current_explanation.startswith("COMPLETED:")):
            chat_ok = True
        elif not self.current_learning_session and pdf_ok: chat_ok = True 
        lesson_chat_active = chat_ok and not (ui_locked or busy_chat or lesson_quiz_on)
        self.learning_chat_group.setEnabled(lesson_chat_active); self.btn_send_lesson_chat.setEnabled(lesson_chat_active); self.learning_chat_input.setEnabled(lesson_chat_active)
        self.num_lesson_questions_spinbox.setEnabled(not ui_locked and not self.current_learning_session)

        self.btn_ai_suggest_video.setEnabled(pdf_ok and not ui_locked); self.btn_load_manual_video.setEnabled(not ui_locked)
        self.manual_video_url_input.setEnabled(not ui_locked); self.btn_fetch_transcript.setEnabled(bool(self.current_video_id) and not ui_locked)
        vid_chat_active = vid_tx_ok and not (ui_locked or busy_chat)
        if hasattr(self,'video_chat_input') and self.video_chat_input.parent() and self.video_chat_input.parent().parent(): self.video_chat_input.parent().parent().setEnabled(vid_chat_active)
        if hasattr(self,'btn_send_video_chat'): self.btn_send_video_chat.setEnabled(vid_chat_active)
        if hasattr(self,'video_chat_input'): self.video_chat_input.setEnabled(vid_chat_active)

        self.btn_start_aggregated_exam.setEnabled(pdf_ok and not ui_locked); self.num_assessment_questions_spinbox.setEnabled(not ui_locked)
        self.assessment_info_label.setText(f"PDF: '{self.current_pdf_topic_name if pdf_ok else 'N/A'}'. Video: '{self.current_video_title if self.current_video_id else 'N/A'}' (Transcript: {'Yes' if vid_tx_ok else 'No'}).")
        
        self.language_combo.setEnabled(not ui_locked)
        if hasattr(self,'btn_refresh_ui_status'): self.btn_refresh_ui_status.setEnabled(True)
        if hasattr(self,'btn_toggle_theme'): self.btn_toggle_theme.setEnabled(True)
        if self.btn_submit_lesson_answer.isVisible(): self.btn_submit_lesson_answer.setEnabled(not busy_eval)
        if self.btn_submit_assessment_answer.isVisible(): self.btn_submit_assessment_answer.setEnabled(not busy_eval)
        app_logger.debug("UI status updated.")

    def _stop_current_topic_timer(self):
        if self.topic_start_time and self.current_pdf_topic_name and self.current_pdf_topic_name!="General":
            dur = time.time()-self.topic_start_time; app_logger.info(f"Timer stop for '{self.current_pdf_topic_name}'. Dur: {dur:.2f}s")
            user_state.record_time_spent(self.current_pdf_topic_name, dur)
        self.topic_start_time = None

    def load_pdf_action_threaded(self):
        self._stop_current_topic_timer()
        sdir = user_state.last_pdf_path if os.path.isdir(user_state.last_pdf_path) else os.path.expanduser("~")
        paths, _ = QFileDialog.getOpenFileNames(self,"Open PDFs",sdir,"PDF (*.pdf)")
        if not paths: app_logger.info("PDF load cancelled."); return
        user_state.last_pdf_path = os.path.dirname(paths[0]); user_state.save()
        self.feedback_label.setText(f"Processing {len(paths)} PDF(s)..."); QApplication.processEvents()
        self._last_loaded_pdf_paths = paths 
        task_id = f"pdf_summary_{time.time()}"; thread=QThread(self)
        worker=GeminiWorker(task_id, summarize_pdf_content, paths, self.selected_language_name)
        worker.moveToThread(thread); worker.finished.connect(lambda tid,smy: self.handle_pdf_summary_response(tid,smy,paths))
        worker.error.connect(self.handle_api_error); thread.started.connect(worker.run)
        worker.finished.connect(thread.quit);worker.finished.connect(worker.deleteLater);thread.finished.connect(thread.deleteLater)
        self.threads[task_id]=thread; thread.start(); self.update_ui_status()

    def handle_pdf_summary_response(self, task_id, summary_text, file_paths):
        app_logger.info(f"PDF Summary task {task_id} finished.");
        if task_id in self.threads: del self.threads[task_id]
        self.current_pdf_topic_name = "General"; self.suggested_youtube_search_url = None; self.pdf_summary_content = ""
        self.current_active_session_id = None 
        
        if summary_text.startswith("Error:"):
            QMessageBox.critical(self, "PDF Summarization Error", summary_text)
            self.feedback_label.setText(f"Failed to summarize: {summary_text.split(':',1)[-1].strip()}")
            self.current_learning_session = None; self.update_ui_status(); return
        self.pdf_summary_content = summary_text
        self.feedback_label.setText("PDF(s) summarized. Identifying topic..."); QApplication.processEvents()
        topic_task_id = f"topic_generation_{time.time()}"; thread = QThread(self)
        worker = GeminiWorker(topic_task_id, get_youtube_search_query_and_main_topic, self.pdf_summary_content, self.selected_language_name)
        worker.moveToThread(thread)
        worker.finished.connect(lambda t_id, topic_info: self.handle_topic_generation_response(t_id, topic_info, file_paths))
        worker.error.connect(self.handle_api_error); thread.started.connect(worker.run)
        worker.finished.connect(thread.quit); worker.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater)
        self.threads[topic_task_id] = thread; thread.start(); self.update_ui_status()
    
    def handle_topic_generation_response(self, task_id, topic_info_dict, file_paths):
        app_logger.info(f"Topic Generation task {task_id} finished. Info: {topic_info_dict}")
        if task_id in self.threads: del self.threads[task_id]
        base_filename = os.path.basename(file_paths[0]).replace(".pdf", "") if file_paths else "Loaded Topic"
        self.current_pdf_topic_name = topic_info_dict.get("main_topic") or base_filename
        # self.current_active_session_id = None # Reset for a new PDF load
        self._last_loaded_pdf_paths = file_paths 

        if topic_info_dict.get("error") or not topic_info_dict.get("main_topic"):
            err_msg = topic_info_dict.get("error", "No specific topic returned by AI.")
            QMessageBox.warning(self, "Topic Identification Info", f"AI issue with topic: {err_msg}. Using: '{self.current_pdf_topic_name}'.")
        
        if topic_info_dict.get("search_query"):
            self.suggested_youtube_search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(topic_info_dict['search_query'])}"
            self.feedback_label.setText(f"PDFs ready. Topic: '{self.current_pdf_topic_name}'. Video search available.")
        else:
            self.feedback_label.setText(f"PDFs ready. Topic: '{self.current_pdf_topic_name}'. No video query suggested.")

        self.learning_content_display.setMarkdown(
            f"**Topic: {self.current_pdf_topic_name}**\n\n*PDF Summary:*\n\n---\n{self.pdf_summary_content}"
        )
        self.current_learning_session = None 
        self._reset_lesson_quiz_ui(); self._reset_assessment_ui()
        
        self._save_current_learning_state_as_session(session_type="pdf_loaded") # current_active_session_id will be set here

        self.update_ui_status()
        self.navigate_to_page(0)

    def start_lesson_action(self):
        if not self.pdf_summary_content or self.pdf_summary_content.startswith("Error:"):
            QMessageBox.warning(self.learning_page, "No Content", "Load valid PDF(s) first."); return
        
        self._stop_current_topic_timer(); self.topic_start_time = time.time()
        app_logger.info(f"Starting lesson for '{self.current_pdf_topic_name}' (Session ID: {self.current_active_session_id}). Timer started.")

        self.current_learning_session = LearningSession(
            self.pdf_summary_content, user_state.level, language=self.selected_language_name
        )
        # If current_active_session_id is set (from PDF load or previous session load), load its chat history
        if self.current_active_session_id:
            existing_data = user_state.get_session_by_id(self.current_active_session_id)
            if existing_data and existing_data.get("chat_history"):
                self.current_learning_session.tutor_chat_history = existing_data["chat_history"]
                self.learning_chat_display.clear()
                for entry in self.current_learning_session.tutor_chat_history:
                    role_disp = "You" if entry["role"] == "user" else "Tutor"
                    self.learning_chat_display.append(f"<b>{role_disp}:</b> {entry['text']}\n")
            # Also, if there was a last explanation that wasn't "COMPLETED", restore it.
            if existing_data and existing_data.get("last_explanation") and not existing_data.get("last_explanation", "").startswith("COMPLETED:"):
                 self.current_learning_session.current_explanation = existing_data.get("last_explanation")
                 self.learning_content_display.setMarkdown(self.current_learning_session.current_explanation)
                 # Proceed to quiz directly if explanation was restored
                 self.feedback_label.setText(f"Restored lesson on '{self.current_pdf_topic_name}'. Generating quiz...");
                 self._initiate_lesson_quiz_generation_threaded()
                 self.update_ui_status()
                 return # Don't generate new explanation


        self.feedback_label.setText(f"Lesson on '{self.current_pdf_topic_name}'. Generating explanation..."); 
        if not self.current_learning_session.tutor_chat_history: 
            self.learning_chat_display.clear() 
        self._initiate_lesson_explanation_and_quiz_threaded(); self.update_ui_status()

    def explain_more_action_threaded(self):
        if self.current_learning_session and self.pdf_summary_content:
            if self.current_learning_session.attempts_on_current_content >= MAX_SESSION_ATTEMPTS:
                 QMessageBox.information(self, "Max Attempts", "Max explanation/quiz attempts reached. Restart lesson or load new content."); self.update_ui_status(); return
            self.feedback_label.setText(f"Generating detailed explanation for '{self.current_pdf_topic_name}'..."); QApplication.processEvents()
            self._initiate_lesson_explanation_and_quiz_threaded(more_detail=True) 
        else: QMessageBox.warning(self.learning_page, "No Active Lesson", "Start a lesson first."); self.update_ui_status()

    def _initiate_lesson_explanation_and_quiz_threaded(self, more_detail=False):
        if not self.current_learning_session: 
            self.feedback_label.setText("Error: No active learning session."); app_logger.error("No learning session for explanation."); self.update_ui_status(); return
        if self.current_learning_session.is_generating_explanation or self.current_learning_session.is_generating_quiz:
            self.feedback_label.setText("Content generation in progress. Please wait."); app_logger.warning("Explain/quiz gen. already busy."); return
        self.current_learning_session.is_generating_explanation = True 
        self.feedback_label.setText(f"Generating explanation for '{self.current_pdf_topic_name}' (Detail: {more_detail})..."); QApplication.processEvents()
        task_id = f"explanation_{time.time()}"; thread = QThread(self)
        worker = GeminiWorker(task_id, self.current_learning_session.explain, more_detail)
        worker.moveToThread(thread); worker.finished.connect(self.handle_explanation_response); worker.error.connect(self.handle_api_error)
        thread.started.connect(worker.run); worker.finished.connect(thread.quit); worker.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater)
        self.threads[task_id] = thread; thread.start(); self.update_ui_status()

    def handle_explanation_response(self, task_id, explanation_text):
        app_logger.info(f"Explanation task {task_id} finished.")
        if task_id in self.threads: del self.threads[task_id]
        if not self.current_learning_session: app_logger.warning("Explanation response, but no session."); self.update_ui_status(); return 
        self.current_learning_session.is_generating_explanation = False
        if explanation_text.startswith("Error:"):
            self.learning_content_display.setMarkdown(f"### Failed explanation:\n{explanation_text}")
            self.feedback_label.setText(f"Error getting explanation: {explanation_text.split(':',1)[-1].strip()}")
        else:
            self.learning_content_display.setMarkdown(explanation_text)
            self.feedback_label.setText(f"Explanation ready. Generating quiz for '{self.current_pdf_topic_name}'..."); QApplication.processEvents()
            self._save_current_learning_state_as_session(session_type="lesson_explanation")
            self._initiate_lesson_quiz_generation_threaded()
        self.update_ui_status()

    def _initiate_lesson_quiz_generation_threaded(self):
        if not self.current_learning_session: app_logger.error("Quiz gen attempt, no session."); self.update_ui_status(); return
        if self.current_learning_session.is_generating_quiz: app_logger.warning("Quiz gen. already in progress."); return
        self.current_learning_session.is_generating_quiz = True
        num_q = self.num_lesson_questions_spinbox.value()
        self.feedback_label.setText(f"Generating {num_q}-question quiz..."); QApplication.processEvents()
        task_id = f"lesson_quiz_gen_{time.time()}"; thread = QThread(self)
        worker = GeminiWorker(task_id, self.current_learning_session.create_lesson_quiz, num_q)
        worker.moveToThread(thread); worker.finished.connect(self.handle_lesson_quiz_generation_response); worker.error.connect(self.handle_api_error)
        thread.started.connect(worker.run); worker.finished.connect(thread.quit); worker.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater)
        self.threads[task_id] = thread; thread.start(); self.update_ui_status()

    def handle_lesson_quiz_generation_response(self, task_id, quiz_text):
        app_logger.info(f"Lesson quiz gen task {task_id} finished.")
        if task_id in self.threads: del self.threads[task_id]
        if not self.current_learning_session: app_logger.warning("Quiz response, but no session."); self.update_ui_status(); return
        self.current_learning_session.is_generating_quiz = False
        if quiz_text.startswith("Error:"):
            self.lesson_quiz_display.setMarkdown(f"### Failed quiz gen:\n{quiz_text}")
            self.feedback_label.setText(f"Error generating quiz: {quiz_text.split(':',1)[-1].strip()}"); self._reset_lesson_quiz_ui()
        else:
            self.lesson_quiz_display.setMarkdown(quiz_text); self.lesson_answer_input.clear(); self._show_lesson_quiz_ui() 
            self.feedback_label.setText(f"Lesson Quiz (Attempt {self.current_learning_session.attempts_on_current_content + 1}) on '{self.current_pdf_topic_name}'.")
        self.update_ui_status()

    def send_lesson_chat_action_threaded(self):
        user_question = self.learning_chat_input.text().strip()
        if not user_question: return
        context_for_chat = ""; current_chat_history_for_call = []
        session_was_active_at_send = bool(self.current_learning_session)
        worker_function = None; worker_args = []

        if self.current_learning_session and (self.current_learning_session.current_explanation or self.current_learning_session.initial_content_summary):
            # This will use and update self.current_learning_session.tutor_chat_history internally
            worker_function = self.current_learning_session.ask_lesson_tutor
            worker_args = [user_question] 
        elif self.pdf_summary_content and not self.pdf_summary_content.startswith("Error:"):
            context_for_chat = self.pdf_summary_content
            # For raw PDF summary chat, we build history for this call only
            # The actual history for raw PDF summary is not being formally stored yet
            # unless a session is created later.
            current_chat_history_for_call = [{"role": "user", "text": user_question}]
            worker_function = ask_follow_up_question
            worker_args = [context_for_chat, user_question, self.selected_language_name, current_chat_history_for_call]
            app_logger.info("Sending chat about raw PDF summary (no active lesson session).")
        else:
            QMessageBox.warning(self.learning_page, "No Context", "Load a PDF or start a lesson to chat."); return

        self.learning_chat_display.append(f"<b>You:</b> {user_question}\n"); self.learning_chat_input.clear(); QApplication.processEvents()
        self.feedback_label.setText("Tutor is thinking..."); 
        task_id = f"lesson_chat_{time.time()}"; thread = QThread(self)
        worker = GeminiWorker(task_id, worker_function, *worker_args) 
        worker.moveToThread(thread)
        worker.finished.connect(lambda t_id, resp: self.handle_lesson_chat_response(t_id, resp, session_was_active_at_send))
        worker.error.connect(self.handle_api_error_for_chat)
        thread.started.connect(worker.run); worker.finished.connect(thread.quit); worker.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater)
        self.threads[task_id] = thread; thread.start(); self.update_ui_status()

    def handle_lesson_chat_response(self, task_id, ai_response, session_was_active_at_send):
        app_logger.info(f"Lesson chat task {task_id} finished.")
        if task_id in self.threads: del self.threads[task_id]
        if ai_response.startswith("Error:"): 
            self.learning_chat_display.append(f"<b>Tutor (Error):</b> {ai_response}\n")
            self.feedback_label.setText(f"Tutor error: {ai_response.split(':', 1)[-1].strip()}")
        else:
            self.learning_chat_display.append(f"<b>Tutor:</b> {ai_response}\n")
            self.feedback_label.setText("Tutor responded. Ask another question or continue lesson.")
            if session_was_active_at_send and self.current_learning_session:
                 # ask_lesson_tutor in session already updated its history. Now save this state.
                self._save_current_learning_state_as_session(session_type="chat_update")
        self.update_ui_status()

    def handle_api_error_for_chat(self, task_id, error_message):
        app_logger.error(f"Chat API Error task {task_id}: {error_message}")
        if task_id in self.threads: del self.threads[task_id]
        self.feedback_label.setText(f"Chat error: {error_message}.")
        self.learning_chat_display.append(f"<b>Tutor (System Error):</b> Response error. {error_message}\n"); self.update_ui_status()

    def _show_lesson_quiz_ui(self):
        self.lesson_quiz_display.setVisible(True); self.lesson_answer_input.setVisible(True); self.btn_submit_lesson_answer.setVisible(True)
        self.learning_content_display.setVisible(False); self.learning_chat_group.setVisible(False)
        self.btn_start_lesson.setEnabled(False); self.btn_explain_more.setEnabled(False); self.num_lesson_questions_spinbox.setEnabled(False)
        self.update_ui_status()

    def _reset_lesson_quiz_ui(self):
        self.lesson_quiz_display.setVisible(False); self.lesson_quiz_display.clear()
        self.lesson_answer_input.setVisible(False); self.lesson_answer_input.clear(); self.btn_submit_lesson_answer.setVisible(False)
        self.learning_content_display.setVisible(True) 
        can_chat = bool(self.current_learning_session and self.current_learning_session.current_explanation or self.pdf_summary_content)
        self.learning_chat_group.setVisible(can_chat)
        if can_chat: self.learning_chat_group.setChecked(True)
        self.update_ui_status()

    def ai_suggest_and_load_video_action(self):
        app_logger.info("AI suggest video action.")
        if self.suggested_youtube_search_url:
            self.video_web_view.setUrl(QUrl(self.suggested_youtube_search_url)); self.current_video_id = None
            self.current_video_title = f"Search: {self.current_pdf_topic_name}"
            self.current_video_transcript_summary = "Select video from search, then fetch transcript."
            self.video_transcript_display.setPlainText(self.current_video_transcript_summary); self.video_chat_display.clear(); self.current_video_session = None
            self.feedback_label.setText(f"YouTube search for '{self.current_pdf_topic_name}'."); self.navigate_to_page(1) 
        elif self.pdf_summary_content:
            self.feedback_label.setText("AI finding video topic/query..."); QApplication.processEvents()
            task_id = f"ai_video_suggestion_{time.time()}"; thread = QThread(self)
            worker = GeminiWorker(task_id, get_youtube_search_query_and_main_topic, self.pdf_summary_content, self.selected_language_name)
            worker.moveToThread(thread); worker.finished.connect(self.handle_ai_video_suggestion_response_for_player); worker.error.connect(self.handle_api_error)
            thread.started.connect(worker.run); worker.finished.connect(thread.quit); worker.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater)
            self.threads[task_id] = thread; thread.start()
        else: QMessageBox.warning(self.video_page, "No PDF Content", "Load PDF for AI video suggestions."); self.update_ui_status()

    def handle_ai_video_suggestion_response_for_player(self, task_id, topic_info):
        app_logger.info(f"AI Video Suggestion (player) task {task_id} finished. Info: {topic_info}")
        if task_id in self.threads: del self.threads[task_id]
        if topic_info.get("error") or not topic_info.get("search_query"):
            QMessageBox.warning(self.video_page, "Suggestion Failed", f"AI suggest video query failed. {topic_info.get('error', 'N/A')}")
            self.feedback_label.setText(f"AI video suggestion failed: {topic_info.get('error', 'N/A')}")
        else:
            self.suggested_youtube_search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(topic_info['search_query'])}"
            self.feedback_label.setText(f"AI video suggestion for '{topic_info.get('main_topic', 'topic')}' ready. Showing search."); self.ai_suggest_and_load_video_action()
        self.update_ui_status()

    def load_manual_video_action(self):
        url_text = self.manual_video_url_input.text().strip(); video_id = extract_video_id(url_text)
        if video_id:
            app_logger.info(f"Loading manual video ID: {video_id}")
            self.video_web_view.setUrl(QUrl(f"https://www.youtube.com/embed/{video_id}?autoplay=0&modestbranding=1&rel=0"))
            self.current_video_id = video_id; self.current_video_title = f"Video ID: {video_id}"
            self.feedback_label.setText(f"Loading video: {video_id}. Fetch transcript if needed.")
            self.current_video_transcript_summary = None; self.video_transcript_display.clear(); self.video_transcript_display.setPlaceholderText("Fetch transcript...")
            self.video_chat_display.clear(); self.current_video_session = None; user_state.store_video_transcript(video_id, None)
            self.navigate_to_page(1) 
        else:
            QMessageBox.warning(self.video_page, "Invalid URL", "Could not extract YouTube video ID."); self.video_web_view.setUrl(QUrl("about:blank"))
            self.current_video_id = None; self.current_video_title = "No Video Loaded"
        self.update_ui_status()

    def fetch_video_transcript_action_threaded(self):
        if not self.current_video_id: QMessageBox.warning(self.video_page, "No Video", "Load video first."); return
        stored_summary = user_state.get_video_transcript(self.current_video_id)
        if stored_summary and "Error:" not in stored_summary:
            self.current_video_transcript_summary = stored_summary
            self.video_transcript_display.setPlainText(f"Stored Transcript Summary for {self.current_video_title or self.current_video_id}:\n\n{self.current_video_transcript_summary}")
            self.current_video_session = VideoInteractionSession(self.current_video_id, self.current_video_title, self.current_video_transcript_summary, self.selected_language_name)
            self.feedback_label.setText("Using stored transcript summary."); self.update_ui_status(); return
        elif stored_summary and "Error:" in stored_summary:
             self.video_transcript_display.setPlainText(f"Previously failed transcript for {self.current_video_title or self.current_video_id}:\n\n{stored_summary}")
             self.current_video_transcript_summary = stored_summary; self.current_video_session = None
             self.feedback_label.setText("Previously failed to fetch transcript."); self.update_ui_status(); return
        self.feedback_label.setText(f"Fetching transcript for video {self.current_video_id}..."); QApplication.processEvents()
        task_id_fetch = f"transcript_fetch_{self.current_video_id}_{time.time()}"; thread_fetch = QThread(self)
        lang_map = {"English": ["en"], "Español (Spanish)": ["es", "es-MX"], "Français (French)": ["fr"], "Deutsch (German)": ["de"]}
        api_lang_codes = lang_map.get(LANGUAGES.get(self.language_combo.currentText()), ["en"])
        worker_fetch = GeminiWorker(task_id_fetch, fetch_youtube_transcript, self.current_video_id, preferred_languages=api_lang_codes)
        worker_fetch.moveToThread(thread_fetch)
        worker_fetch.finished.connect(lambda t_id, tr: self.handle_raw_transcript_response(t_id, tr, self.current_video_id))
        worker_fetch.error.connect(self.handle_api_error_for_transcript_fetch)
        thread_fetch.started.connect(worker_fetch.run); worker_fetch.finished.connect(thread_fetch.quit); worker_fetch.finished.connect(worker_fetch.deleteLater); thread_fetch.finished.connect(thread_fetch.deleteLater)
        self.threads[task_id_fetch] = thread_fetch; thread_fetch.start(); self.update_ui_status()

    def handle_api_error_for_transcript_fetch(self, task_id, error_message):
        app_logger.error(f"Transcript fetch API Error task {task_id}: {error_message}")
        if task_id in self.threads: del self.threads[task_id]
        video_id_from_task = task_id.split('_')[2];
        if video_id_from_task != self.current_video_id: app_logger.warning(f"Stale transcript fetch error for {video_id_from_task}."); return
        self.feedback_label.setText(f"Transcript fetch failed: {error_message}.")
        self.video_transcript_display.setPlainText(f"Error fetching transcript for {self.current_video_title or self.current_video_id}:\n{error_message}")
        self.current_video_transcript_summary = f"Error: {error_message}"; user_state.store_video_transcript(self.current_video_id, self.current_video_transcript_summary)
        self.current_video_session = None; self.update_ui_status()

    def handle_raw_transcript_response(self, task_id, raw_transcript, video_id_for_task):
        app_logger.info(f"Raw transcript fetch task {task_id} for video {video_id_for_task} done.")
        if task_id in self.threads: del self.threads[task_id]
        if video_id_for_task != self.current_video_id: app_logger.warning(f"Transcript for {video_id_for_task}, current is {self.current_video_id}. Discarding."); self.update_ui_status(); return
        if raw_transcript.startswith("Error:"):
            self.video_transcript_display.setPlainText(f"Failed transcript for {self.current_video_title or self.current_video_id}:\n\n{raw_transcript}")
            self.current_video_transcript_summary = raw_transcript
            user_state.store_video_transcript(self.current_video_id, raw_transcript)
            self.feedback_label.setText(f"Failed to fetch transcript: {raw_transcript.split(':',1)[-1].strip()}"); self.current_video_session = None
        else:
            self.feedback_label.setText("Transcript fetched. Summarizing..."); QApplication.processEvents()
            task_id_summary = f"transcript_summary_{self.current_video_id}_{time.time()}"; thread_summary = QThread(self)
            worker_summary = GeminiWorker(task_id_summary, summarize_text_for_chat_context, raw_transcript, language=self.selected_language_name)
            worker_summary.moveToThread(thread_summary)
            worker_summary.finished.connect(lambda t_id, summary: self.handle_transcript_summary_response(t_id, summary, self.current_video_id, raw_transcript))
            worker_summary.error.connect(self.handle_api_error_for_transcript_summary)
            thread_summary.started.connect(worker_summary.run); worker_summary.finished.connect(thread_summary.quit); worker_summary.finished.connect(worker_summary.deleteLater); thread_summary.finished.connect(thread_summary.deleteLater)
            self.threads[task_id_summary] = thread_summary; thread_summary.start()
        self.update_ui_status()

    def handle_api_error_for_transcript_summary(self, task_id, error_message):
        app_logger.error(f"Transcript summary API Error task {task_id}: {error_message}")
        if task_id in self.threads: del self.threads[task_id]
        video_id_from_task = task_id.split('_')[2];
        if video_id_from_task != self.current_video_id: return
        self.feedback_label.setText(f"Transcript summarization failed: {error_message}.")
        self.current_video_transcript_summary = f"Error summarizing: {error_message}"
        self.video_transcript_display.setPlainText(self.current_video_transcript_summary + "\n(Raw transcript may be too long for display).")
        user_state.store_video_transcript(self.current_video_id, self.current_video_transcript_summary)
        self.current_video_session = None; self.update_ui_status()

    def handle_transcript_summary_response(self, task_id, summary_text, video_id_for_task, raw_transcript_for_fallback=""):
        app_logger.info(f"Transcript summary task {task_id} for video {video_id_for_task} done.")
        if task_id in self.threads: del self.threads[task_id]
        if video_id_for_task != self.current_video_id: app_logger.warning(f"Summary for {video_id_for_task}, current {self.current_video_id}. Discarding."); self.update_ui_status(); return
        if summary_text.startswith("Error:"):
            if raw_transcript_for_fallback and not raw_transcript_for_fallback.startswith("Error:"):
                self.current_video_transcript_summary = raw_transcript_for_fallback
                self.video_transcript_display.setPlainText(f"Error summarizing: {summary_text.split(':',1)[-1].strip()}\n\nUsing Full Transcript (may be long):\n{self.current_video_transcript_summary[:3000]}...")
                self.feedback_label.setText("Error summarizing transcript. Using full transcript.")
            else: 
                self.current_video_transcript_summary = summary_text 
                self.video_transcript_display.setPlainText(f"Failed to process transcript for {self.current_video_title or self.current_video_id}:\n{summary_text}")
                self.feedback_label.setText(f"Error summarizing transcript: {summary_text.split(':',1)[-1].strip()}")
        else:
            self.current_video_transcript_summary = summary_text
            self.video_transcript_display.setPlainText(f"Transcript Summary for {self.current_video_title or self.current_video_id}:\n\n{self.current_video_transcript_summary}")
            self.feedback_label.setText("Transcript summarized. Ready for chat/assessment.")
        user_state.store_video_transcript(self.current_video_id, self.current_video_transcript_summary)
        if not self.current_video_transcript_summary.startswith("Error:"):
            self.current_video_session = VideoInteractionSession(self.current_video_id, self.current_video_title, self.current_video_transcript_summary, self.selected_language_name)
        else:
            self.current_video_session = None
        self.update_ui_status()

    def send_video_chat_action_threaded(self):
        if not self.current_video_session: QMessageBox.warning(self.video_page, "No Video Context", "Fetch transcript/summary first."); return
        user_question = self.video_chat_input.text().strip();
        if not user_question: return
        self.video_chat_display.append(f"<b>You:</b> {user_question}\n"); self.video_chat_input.clear(); QApplication.processEvents()
        self.feedback_label.setText(f"Asking AI about '{self.current_video_title}'..."); 
        task_id = f"video_chat_{self.current_video_id}_{time.time()}"; thread = QThread(self)
        worker = GeminiWorker(task_id, self.current_video_session.ask_about_video, user_question)
        worker.moveToThread(thread); worker.finished.connect(self.handle_video_chat_response); worker.error.connect(self.handle_api_error_for_video_chat)
        thread.started.connect(worker.run); worker.finished.connect(thread.quit); worker.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater)
        self.threads[task_id] = thread; thread.start(); self.update_ui_status()

    def handle_video_chat_response(self, task_id, ai_response):
        app_logger.info(f"Video chat task {task_id} finished.")
        if task_id in self.threads: del self.threads[task_id]
        if ai_response.startswith("Error:"):
            self.video_chat_display.append(f"<b>AI (Video Error):</b> {ai_response}\n")
            self.feedback_label.setText(f"AI video chat error: {ai_response.split(':',1)[-1].strip()}")
        else:
            self.video_chat_display.append(f"<b>AI (Video):</b> {ai_response}\n")
            self.feedback_label.setText("AI responded about the video.")
        self.update_ui_status()

    def handle_api_error_for_video_chat(self, task_id, error_message):
        app_logger.error(f"Video Chat API Error task {task_id}: {error_message}")
        if task_id in self.threads: del self.threads[task_id]
        self.feedback_label.setText(f"Video chat error: {error_message}.")
        self.video_chat_display.append(f"<b>AI (System Error):</b> Response error. {error_message}\n"); self.update_ui_status()

    def start_aggregated_exam_action_threaded(self):
        if not self.pdf_summary_content or self.pdf_summary_content.startswith("Error:"):
            QMessageBox.warning(self.assessment_page, "No PDF Content", "Load valid PDF for assessment."); return
        video_summary = None; video_title = "None"
        if self.current_video_id and self.current_video_transcript_summary and not self.current_video_transcript_summary.startswith("Error:"):
            video_summary = self.current_video_transcript_summary; video_title = self.current_video_title
            self.feedback_label.setText(f"Aggregated exam on '{self.current_pdf_topic_name}' & video '{video_title}'.")
        else: self.feedback_label.setText(f"Exam on '{self.current_pdf_topic_name}' (no valid video content).")
        self.current_assessment_session = AssessmentSession(self.pdf_summary_content, video_summary, self.selected_language_name)
        num_q = self.num_assessment_questions_spinbox.value()
        self.assessment_info_label.setText(f"Generating {num_q}-question assessment..."); QApplication.processEvents()
        task_id = f"assessment_gen_{time.time()}"; thread = QThread(self)
        worker = GeminiWorker(task_id, self.current_assessment_session.create_assessment, num_questions=num_q)
        worker.moveToThread(thread)
        worker.finished.connect(lambda t_id, q: self.handle_aggregated_exam_generation_response(t_id, q, num_q))
        worker.error.connect(self.handle_api_error_for_assessment_gen)
        thread.started.connect(worker.run); worker.finished.connect(thread.quit); worker.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater)
        self.threads[task_id] = thread; thread.start(); self.update_ui_status()

    def handle_aggregated_exam_generation_response(self, task_id, questions, num_q_requested):
        app_logger.info(f"Aggregated exam gen task {task_id} finished.")
        if task_id in self.threads: del self.threads[task_id]
        if not self.current_assessment_session: app_logger.warning("Assessment gen response, no session."); self.update_ui_status(); return
        if questions.startswith("Error:"):
            self.assessment_questions_display.setMarkdown(f"### Error generating assessment:\n{questions}")
            self.feedback_label.setText(f"Error generating assessment: {questions.split(':',1)[-1].strip()}")
            self.current_assessment_session = None; self._reset_assessment_ui()
        else:
            self.assessment_questions_display.setMarkdown(questions); self.assessment_answer_input.clear(); self._show_assessment_ui()
            self.feedback_label.setText(f"Comprehensive assessment ({num_q_requested} questions) ready.")
        self.update_ui_status()

    def handle_api_error_for_assessment_gen(self, task_id, error_message):
        app_logger.error(f"Assessment Gen API Error task {task_id}: {error_message}")
        if task_id in self.threads: del self.threads[task_id]
        self.feedback_label.setText(f"Assessment gen error: {error_message}.")
        self.assessment_questions_display.setMarkdown(f"### Failed assessment gen:\n{error_message}")
        self.current_assessment_session = None; self._reset_assessment_ui(); self.update_ui_status()

    def _show_assessment_ui(self):
        self.assessment_questions_display.setVisible(True); self.assessment_answer_input.setVisible(True); self.btn_submit_assessment_answer.setVisible(True)
        self.btn_start_aggregated_exam.setEnabled(False); self.num_assessment_questions_spinbox.setEnabled(False); self.update_ui_status()

    def _reset_assessment_ui(self):
        self.assessment_questions_display.setVisible(False); self.assessment_questions_display.clear()
        self.assessment_answer_input.setVisible(False); self.assessment_answer_input.clear(); self.btn_submit_assessment_answer.setVisible(False)
        self.update_ui_status()

    def submit_answer_action(self, is_assessment_page):
        active_session = self.current_assessment_session if is_assessment_page else self.current_learning_session
        interaction_type = "Comprehensive Assessment" if is_assessment_page else "Lesson Quiz"
        answer_input = self.assessment_answer_input if is_assessment_page else self.lesson_answer_input
        if not active_session: QMessageBox.critical(self, "Error", f"No active {interaction_type.lower()} session."); app_logger.error(f"Submit answer, no session for {interaction_type}."); self.update_ui_status(); return
        user_answer = answer_input.toPlainText().strip();
        if not user_answer: QMessageBox.warning(self, "No Answer", "Provide an answer."); return
        self.feedback_label.setText(f"Evaluating {interaction_type} answer..."); QApplication.processEvents()
        task_id = f"evaluate_{interaction_type.lower().replace(' ', '_')}_{time.time()}"
        questions_to_eval = active_session.current_assessment_questions if is_assessment_page else active_session.current_quiz_or_exam
        func_to_call = active_session.check_assessment_answer if is_assessment_page else active_session.check_answer
        if not questions_to_eval or not func_to_call: QMessageBox.critical(self, "Error", "Session/questions missing for eval."); app_logger.error(f"Missing questions/func for eval in {interaction_type}."); self.update_ui_status(); return
        thread = QThread(self); worker = GeminiWorker(task_id, func_to_call, user_answer) 
        worker.moveToThread(thread)
        worker.finished.connect(lambda t_id, res: self.handle_evaluation_response(t_id, res, is_assessment_page, user_answer, questions_to_eval, interaction_type))
        worker.error.connect(self.handle_api_error_for_evaluation)
        thread.started.connect(worker.run); worker.finished.connect(thread.quit); worker.finished.connect(worker.deleteLater); thread.finished.connect(thread.deleteLater)
        self.threads[task_id] = thread; thread.start(); self.update_ui_status()

    def handle_api_error_for_evaluation(self, task_id, error_message):
        app_logger.error(f"Evaluation API Error task {task_id}: {error_message}")
        if task_id in self.threads: del self.threads[task_id]
        self.feedback_label.setText(f"Evaluation error: {error_message}.")
        QMessageBox.critical(self, "Evaluation Error", f"Error during answer evaluation:\n{error_message}"); self.update_ui_status()

    def handle_evaluation_response(self, task_id, result_tuple, is_assessment_page, user_answer, questions_for_log, interaction_type_str):
        app_logger.info(f"Evaluation task {task_id} finished. Result: {result_tuple}")
        if task_id in self.threads: del self.threads[task_id]
        status_str, justification = "Error", "Eval result parsing failed."
        if isinstance(result_tuple, tuple) and len(result_tuple) == 2: status_str, justification = result_tuple
        elif isinstance(result_tuple, str) and result_tuple.startswith("Error:"): justification = result_tuple; app_logger.error(f"Eval returned string error: {result_tuple}")
        else: justification = f"Unexpected eval result: {result_tuple}"; app_logger.error(justification)
        is_correct = status_str == "Correct"; is_partially_correct = status_str == "Partially Correct"
        active_session = self.current_assessment_session if is_assessment_page else self.current_learning_session
        page_content_display = self.assessment_questions_display if is_assessment_page else self.learning_content_display
        log_topic = self.current_pdf_topic_name
        if is_assessment_page and self.current_video_title != "No Video Loaded": log_topic += f" & Video: {self.current_video_title}"
        quiz_log = {"type": interaction_type_str, "topic": log_topic, "timestamp": datetime.now().isoformat(), "language": self.selected_language_name, "questions": questions_for_log, "user_answer": user_answer, "evaluation_result": status_str.upper(), "evaluation_justification": justification}
        if is_correct or is_partially_correct:
            if not is_assessment_page: self._stop_current_topic_timer()
            QMessageBox.information(self, status_str, f"Answer was {status_str.lower()}.\n{justification}")
            xp_mult = XP_GAIN_ON_AGGREGATED_EXAM_MULTIPLIER if is_assessment_page else XP_GAIN_ON_LESSON_QUIZ_MULTIPLIER
            xp_gain = XP_GAIN_ON_SUCCESS * xp_mult * (0.5 if is_partially_correct else 1.0)
            user_state.gain_xp(int(round(xp_gain)))
            success_md = f"### **{interaction_type_str} on '{log_topic}' - {status_str}!**"
            if not is_assessment_page and active_session:
                summary = active_session.get_learning_summary_from_explanation(); skills = active_session.get_skills_from_lesson()
                if not summary.startswith("Error:"): user_state.save_summary(summary, topic_name=self.current_pdf_topic_name, quiz_details=quiz_log); page_content_display.setMarkdown(f"{success_md}\n\n**Summary:**\n{summary}")
                else: user_state.save_summary(f"{interaction_type_str} - {status_str} (summary error).", topic_name=self.current_pdf_topic_name, quiz_details=quiz_log); page_content_display.setMarkdown(f"{success_md}\n\n{justification}\n\n*(Summary error: {summary})*")
                skills_msg = ""
                if isinstance(skills, list) and (not skills or not skills[0].startswith("Error:")):
                    added_skills = sum(1 for s in skills if user_state.add_skill(s))
                    if added_skills > 0: skills_msg = f" Learned {added_skills} new skill(s)!"
                elif isinstance(skills, list) and skills and skills[0].startswith("Error:"): app_logger.error(f"Error extracting skills: {skills[0]}")
                self.feedback_label.setText(f"{status_str}! {justification}{skills_msg} Lesson complete!")
                if self.current_active_session_id: 
                    current_ps = user_state.get_session_by_id(self.current_active_session_id)
                    if current_ps: 
                        current_ps["last_explanation"] = "COMPLETED: " + (current_ps.get("last_explanation","")[:100])
                        current_ps["status"] = "completed" # Add a status field
                        user_state.add_or_update_session(current_ps)

            else: user_state.save_summary(f"{interaction_type_str} on '{log_topic}' - {status_str}.", topic_name=log_topic, quiz_details=quiz_log);
            if page_content_display: page_content_display.setMarkdown(f"{success_md}\n\n{justification}"); self.feedback_label.setText(f"{interaction_type_str} {status_str.lower()}! {justification}")
            if is_assessment_page: self.current_assessment_session = None; self._reset_assessment_ui()
            else: self.current_learning_session = None; self._reset_lesson_quiz_ui()
        else:
            if active_session:
                if not is_assessment_page:
                    active_session.attempts_on_current_content += 1; max_attempts = MAX_SESSION_ATTEMPTS
                    QMessageBox.warning(self, status_str, f"Not quite right. {justification}")
                    if active_session.attempts_on_current_content < max_attempts: self.feedback_label.setText(f"{status_str} for '{log_topic}'. {justification}. Try again (Attempt {active_session.attempts_on_current_content + 1}/{max_attempts}).")
                    else: self._stop_current_topic_timer(); self.feedback_label.setText(f"Max attempts for '{log_topic}'. {justification}. Restart lesson."); page_content_display.setMarkdown(self.current_learning_session.current_explanation + f"\n\n---\nMax attempts. Restart Lesson or Explain More."); self.current_learning_session = None; self._reset_lesson_quiz_ui()
                else: QMessageBox.warning(self, status_str, f"Assessment answer {status_str.lower()}. {justification}"); self.feedback_label.setText(f"Assessment for '{log_topic}' was {status_str.lower()}. {justification}"); self.current_assessment_session = None; self._reset_assessment_ui()
            else: QMessageBox.warning(self, "Eval Issue", f"Issue: {justification}"); self.feedback_label.setText(f"Eval issue for '{log_topic}'. {justification}")
            user_state.save_summary(f"{interaction_type_str} on '{log_topic}' - {status_str}.", topic_name=log_topic, quiz_details=quiz_log)
        user_state.save(); self.update_ui_status()

    def handle_api_error(self, task_id, error_message):
        app_logger.error(f"Generic API Error task {task_id}: {error_message}")
        if task_id in self.threads: del self.threads[task_id]
        self.feedback_label.setText(f"API error: {error_message}. Check logs.")
        QMessageBox.critical(self, "API Error", f"Problem with AI service for task '{task_id}':\n{error_message}\n\nCheck connection/API key. See logs.")
        if task_id.startswith("pdf_summary_") or task_id.startswith("topic_generation_"): self.pdf_summary_content = ""; self.current_learning_session = None
        elif task_id.startswith("explanation_") or task_id.startswith("lesson_quiz_gen_"):
            if self.current_learning_session: self.current_learning_session.is_generating_explanation = False; self.current_learning_session.is_generating_quiz = False
            self._reset_lesson_quiz_ui()
        elif task_id.startswith("transcript_") or task_id.startswith("ai_video_suggestion_"): self.current_video_transcript_summary = f"Error: {error_message}"; self.current_video_session = None
        elif task_id.startswith("assessment_gen_"): self.current_assessment_session = None; self._reset_assessment_ui()
        self.update_ui_status()

    def cleanup_threads(self):
        app_logger.info("Cleaning up active threads...")
        active_ids = list(self.threads.keys())
        for task_id in active_ids:
            thread = self.threads.get(task_id)
            if thread and thread.isRunning():
                app_logger.debug(f"Stopping thread: {task_id}...")
                thread.quit()
                if not thread.wait(1500): app_logger.warning(f"Thread {task_id} didn't stop gracefully, terminating."); thread.terminate();
                if not thread.wait(500): app_logger.error(f"Thread {task_id} failed to terminate.")
                else: app_logger.debug(f"Thread {task_id} stopped.")
            if task_id in self.threads: del self.threads[task_id]
        app_logger.info(f"Thread cleanup finished. Remaining: {len(self.threads)}")

    def closeEvent(self, event):
        app_logger.info("MainWindow closeEvent called.")
        self._stop_current_topic_timer()
        # Optionally save current state if a lesson/PDF was active but not formally completed/saved recently
        if self.pdf_summary_content and self.current_active_session_id:
            self._save_current_learning_state_as_session(session_type="app_close_active_lesson")
        elif self.pdf_summary_content and not self.current_active_session_id : # PDF loaded but no session ID yet
            self._save_current_learning_state_as_session(session_type="app_close_pdf_loaded")


        if hasattr(self, 'video_web_view') and self.video_web_view:
            app_logger.debug("Cleaning up web view..."); self.video_web_view.stop(); self.video_web_view.setUrl(QUrl("about:blank"))
        super().closeEvent(event)