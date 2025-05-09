from agents.gemini_agent import (
    generate_explanation,
    generate_standard_quiz,
    generate_aggregated_quiz,
    evaluate_answer,
    generate_learning_summary,
    extract_skills_from_text,
    ask_follow_up_question,
    ask_question_about_video
)
from core.logger_config import app_logger

MAX_SESSION_ATTEMPTS = 3  # For lesson quizzes before suggesting moving on
DEFAULT_EXAM_QUESTIONS = 10 # For standard exam (not currently used by UI)
DEFAULT_AGGREGATED_EXAM_QUESTIONS = 10 # Default for comprehensive assessment if spinbox fails

class LearningSession:
    def __init__(self, initial_content_summary, student_level, language="English"):
        self.initial_content_summary = initial_content_summary
        self.student_level = student_level
        self.language = language
        self.current_explanation = ""
        self.current_quiz_or_exam = ""
        self.attempts_on_current_content = 0
        self.tutor_chat_history = [] # Stores {"role": "user/ai", "text": "..."}
        self.is_generating_explanation = False # Flag to prevent concurrent calls
        self.is_generating_quiz = False      # Flag for quiz generation

        app_logger.info(f"LearningSession initialized for student level {student_level}, lang: {language}.")

    def explain(self, more_detail=False):
        self.current_explanation = generate_explanation(
            self.initial_content_summary, self.student_level, self.language, more_detail
        )
        self.tutor_chat_history = [] # Reset chat history when new explanation is generated
        self.attempts_on_current_content = 0 # Reset attempts for new explanation/quiz cycle
        return self.current_explanation

    def create_lesson_quiz(self, num_questions=3):
        if not self.current_explanation and not self.initial_content_summary:
            return "Error: No content available to create a quiz."
        
        content_for_quiz = self.current_explanation if self.current_explanation else self.initial_content_summary
        self.current_quiz_or_exam = generate_standard_quiz(
            content_for_quiz,
            num_questions=num_questions, language=self.language, is_exam=False
        )
        return self.current_quiz_or_exam

    # Simple exam on PDF summary - not directly used by UI currently, but available
    def create_simple_exam(self, num_questions=DEFAULT_EXAM_QUESTIONS):
        self.current_quiz_or_exam = generate_standard_quiz(
            self.initial_content_summary,
            num_questions=num_questions, language=self.language, is_exam=True
        )
        return self.current_quiz_or_exam

    def check_answer(self, user_answer):
        if not self.current_quiz_or_exam:
            return "Error", "No quiz/exam is currently active in this session."
        if not (self.current_explanation or self.initial_content_summary):
             return "Error", "Session has no content context for evaluation."

        eval_context = self.current_explanation if self.current_explanation else self.initial_content_summary
        return evaluate_answer(
            eval_context, self.current_quiz_or_exam, user_answer, self.language
        )

    def get_learning_summary_from_explanation(self):
        if not self.current_explanation:
            return "No explanation was provided yet to summarize."
        return generate_learning_summary(self.current_explanation, language=self.language)

    def get_skills_from_lesson(self):
        text_to_analyze = self.initial_content_summary
        if self.current_explanation:
            text_to_analyze += "\n" + self.current_explanation
        
        if not text_to_analyze.strip():
            return ["Error: No content available to extract skills from."]
            
        return extract_skills_from_text(text_to_analyze, language=self.language)

    def ask_lesson_tutor(self, user_question):
        if not self.current_explanation and not self.initial_content_summary:
            return "Please start a lesson or load a PDF to provide context for your question."
        
        context_for_chat = self.current_explanation if self.current_explanation else self.initial_content_summary
        
        # Add user question to history before API call
        self.tutor_chat_history.append({"role": "user", "text": user_question})
        
        ai_response = ask_follow_up_question(
            context_for_chat, user_question, self.language, self.tutor_chat_history
        )
        # Add AI response to history after API call
        if not ai_response.startswith("Error:"):
            self.tutor_chat_history.append({"role": "ai", "text": ai_response})
        return ai_response


class VideoInteractionSession:
    def __init__(self, video_id, video_title, transcript_summary, language="English"):
        self.video_id = video_id
        self.video_title = video_title
        self.transcript_summary = transcript_summary # This should be the potentially summarized transcript
        self.language = language
        self.chat_history = [] # Stores {"role": "user/ai", "text": "..."}
        app_logger.info(f"VideoInteractionSession initialized for video '{video_title}', lang: {language}.")

    def ask_about_video(self, user_question):
        if not self.transcript_summary or self.transcript_summary.startswith("Error:"):
            error_detail = f" ({self.transcript_summary})" if self.transcript_summary else ""
            return f"No valid video transcript/summary available to ask questions about{error_detail}. Please fetch/load it first."
        
        self.chat_history.append({"role": "user", "text": user_question})
        ai_response = ask_question_about_video(
            self.transcript_summary, user_question, self.language, self.chat_history
        )
        if not ai_response.startswith("Error:"):
            self.chat_history.append({"role": "ai", "text": ai_response})
        return ai_response


class AssessmentSession:
    def __init__(self, pdf_summary, video_summary, language="English"):
        self.pdf_summary = pdf_summary
        self.video_summary = video_summary # Can be None or error string
        self.language = language
        self.current_assessment_questions = ""
        self.attempts = 0 # Could add max attempts here too if desired (UI currently resets after 1)
        app_logger.info(f"AssessmentSession initialized, lang: {language}.")


    def create_assessment(self, num_questions=DEFAULT_AGGREGATED_EXAM_QUESTIONS, is_exam=True):
        if not self.pdf_summary:
            return "Error: PDF summary is required to create an assessment."
            
        self.current_assessment_questions = generate_aggregated_quiz(
            self.pdf_summary, self.video_summary, num_questions, self.language, is_exam
        )
        return self.current_assessment_questions

    def check_assessment_answer(self, user_answer):
        if not self.current_assessment_questions:
            return "Error", "No assessment questions are currently active."
        if not self.pdf_summary:
            return "Error", "Assessment session has no PDF content context for evaluation."
        
        eval_context = f"PDF Summary:\n{self.pdf_summary}"
        if self.video_summary and not self.video_summary.startswith("Error:") and self.video_summary.strip():
            eval_context += f"\n\nVideo Summary:\n{self.video_summary}"

        return evaluate_answer(
            eval_context, self.current_assessment_questions, user_answer, self.language
        )