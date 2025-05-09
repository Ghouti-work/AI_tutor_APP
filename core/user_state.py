# core/user_state.py
import json
import os
from datetime import datetime
from .logger_config import app_logger

XP_REQUIRED_PER_LEVEL_MULTIPLIER = 20
USER_STATE_FILE = "user_state.json"
DEFAULT_LANGUAGE = "English"
DEFAULT_THEME = "light"

class UserState:
    def __init__(self, level=1, xp=0, skills=None, language=DEFAULT_LANGUAGE,                  last_pdf_path=".", time_per_topic=None, video_transcripts=None,                 summaries_log=None, theme=DEFAULT_THEME, previous_sessions=None): # Added previous_sessions
        app_logger.debug(f"UserState __init__ called. Theme: {theme}")
        _default_level = 1; self.level = int(level) if isinstance(level, (int, float)) else _default_level
        _default_xp = 0; self.xp = int(xp) if isinstance(xp, (int, float)) else _default_xp
        self.skills = skills if isinstance(skills, list) else []
        self.language = str(language) if isinstance(language, str) else DEFAULT_LANGUAGE
        self.last_pdf_path = str(last_pdf_path) if isinstance(last_pdf_path, str) else "."
        self.time_per_topic = time_per_topic if isinstance(time_per_topic, dict) else {}
        self.video_transcripts = video_transcripts if isinstance(video_transcripts, dict) else {}
        self.summaries_log = summaries_log if isinstance(summaries_log, list) else []
        self.theme = str(theme) if theme in ["light", "dark"] else DEFAULT_THEME
        self.previous_sessions = previous_sessions if isinstance(previous_sessions, list) else []

        if self.level < 1: self.level = _default_level
        if self.xp < 0: self.xp = _default_xp
        app_logger.debug(f"UserState instance created/updated. Level: {self.level}, Theme: {self.theme}")

    def gain_xp(self, amount):
        if not isinstance(amount, (int, float)) or amount <= 0: return
        self.xp += int(round(amount))
        app_logger.info(f"Gained {int(round(amount))} XP. Current XP: {self.xp}, Level: {self.level}")
        xp_needed = self.get_xp_for_next_level()
        while self.xp >= xp_needed and xp_needed > 0 :
            self.xp -= xp_needed; self.level += 1
            app_logger.info(f"Level up! Level {self.level}. XP: {self.xp}.")
            xp_needed = self.get_xp_for_next_level()
        self.save()

    def add_skill(self, skill_name):
        skill_name = str(skill_name).strip()
        if skill_name and skill_name.lower() not in [s.lower() for s in self.skills]:
            self.skills.append(skill_name); app_logger.info(f"Skill added: {skill_name}"); self.save(); return True
        return False

    def get_xp_for_next_level(self): return max(1, self.level * XP_REQUIRED_PER_LEVEL_MULTIPLIER)

    def record_time_spent(self, topic_name, duration_seconds):
        if not topic_name or topic_name == "General" or duration_seconds <= 0: return
        key = "".join(c if c.isalnum() or c in " _-" else "" for c in str(topic_name)).strip()[:100] or "Unnamed_Topic"
        self.time_per_topic[key] = float(self.time_per_topic.get(key, 0.0)) + float(duration_seconds)
        self.save(); app_logger.info(f"Time for '{key}': {duration_seconds:.2f}s. Total: {self.time_per_topic[key]:.2f}s")

    def store_video_transcript(self, video_id, transcript_summary):
        if video_id: self.video_transcripts[str(video_id)] = transcript_summary; self.save(); app_logger.info(f"Stored transcript for video: {video_id}")

    def get_video_transcript(self, video_id): return self.video_transcripts.get(str(video_id))

    def save_summary(self, summary_content, topic_name="general", quiz_details=None):
        summaries_dir = os.path.join("assets", "summaries")
        try: os.makedirs(summaries_dir, exist_ok=True)
        except OSError as e: app_logger.error(f"Error creating dir '{summaries_dir}': {e}"); return
        
        safe_topic = "".join(c if c.isalnum() else "_" for c in str(topic_name).replace(" ", "_"))[:50] or "summary"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S"); fname = f"{safe_topic}_{ts}.md"; fpath = os.path.join(summaries_dir, fname)
        log_entry = {"topic": str(topic_name), "timestamp": datetime.now().isoformat(), "file_path": fpath, "file_name": fname, "quiz_taken": bool(quiz_details)}

        try:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(f"# Summary: {topic_name}\nDate: {log_entry['timestamp']}\nLevel: {self.level}\nLang: {self.language}\n\n## Content:\n{summary_content}\n\n")
                if quiz_details and isinstance(quiz_details, dict):
                    f.write(f"---\n## Quiz Details:\nType: {quiz_details.get('type', 'N/A')}\nTopic: {quiz_details.get('topic', 'N/A')}\nDate: {quiz_details.get('timestamp', 'N/A')}\nLang: {quiz_details.get('language', 'N/A')}\n\n")
                    f.write(f"### Questions:\n```\n{str(quiz_details.get('questions', 'N/A'))}\n```\n\n### User Answer:\n```\n{str(quiz_details.get('user_answer', 'N/A'))}\n```\n\n")
                    f.write(f"### Eval: **{str(quiz_details.get('evaluation_result', 'N/A')).upper()}**\nFeedback:\n{str(quiz_details.get('evaluation_justification', 'N/A'))}\n---\n")
            app_logger.info(f"Summary saved: {fpath}"); self.summaries_log.append(log_entry); self.save()
        except Exception as e: app_logger.error(f"Error saving summary to {fpath}: {e}", exc_info=True)

    def add_or_update_session(self, session_data):
        if not isinstance(session_data, dict): app_logger.error("Invalid session_data to add_or_update_session"); return
        session_id = session_data.get("id")
        if not session_id:
            session_id = f"{datetime.now().timestamp()}_{session_data.get('topic_name', 'untitled_session').replace(' ','_')}"
            session_data["id"] = session_id
            
        found_idx = -1
        for i, s in enumerate(self.previous_sessions):
            if s.get("id") == session_id: found_idx = i; break
        
        if found_idx != -1: self.previous_sessions[found_idx].update(session_data); app_logger.info(f"Updated session: {session_id}")
        else: self.previous_sessions.append(session_data); app_logger.info(f"Added new session: {session_id}")
        self.previous_sessions.sort(key=lambda s: s.get("timestamp", "0"), reverse=True)
        self.save()

    def get_session_by_id(self, session_id):
        return next((s for s in self.previous_sessions if s.get("id") == session_id), None)

    def save(self):
        app_logger.debug(f"Saving user state to {USER_STATE_FILE}...")
        data = {k: v for k, v in self.__dict__.items() if not k.startswith('_')} # Basic serialization
        try:
            with open(USER_STATE_FILE, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)
            app_logger.info(f"User state saved: {os.path.abspath(USER_STATE_FILE)}")
        except Exception as e: app_logger.error(f"Error saving state to {USER_STATE_FILE}: {e}", exc_info=True)

    @classmethod
    def load(cls):
        app_logger.debug(f"Loading user state from {USER_STATE_FILE}...")
        if os.path.exists(USER_STATE_FILE):
            try:
                with open(USER_STATE_FILE, "r", encoding="utf-8") as f: data = json.load(f)
                app_logger.info(f"User state loaded: {os.path.abspath(USER_STATE_FILE)}")
                return cls(**data) # Unpack loaded data into constructor
            except Exception as e: app_logger.error(f"Error loading/parsing state from {USER_STATE_FILE}: {e}. Using defaults.", exc_info=True)
        else: app_logger.info(f"No state file at {USER_STATE_FILE}. Creating default state.")
        return cls()

try:
    user_state = UserState.load()
    app_logger.info(f"Global user_state loaded. Theme: {user_state.theme}, Lang: {user_state.language}")
except Exception as e:
    app_logger.critical(f"FATAL: Initial UserState.load() failed: {e}", exc_info=True)
    user_state = UserState() # Fallback
    app_logger.warning("Fallback to new default UserState due to load error.")