import os
import google.generativeai as genai
from dotenv import load_dotenv
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from core.logger_config import app_logger
import time
import urllib.parse
import fitz  # PyMuPDF

# Load environment variables from .env file
load_dotenv()

# Configure the Gemini API key
try:
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        app_logger.critical("GEMINI_API_KEY not found in environment variables. AI features will not work.")
        # raise ValueError("GEMINI_API_KEY not found.") # Or handle more gracefully
    else:
        genai.configure(api_key=gemini_api_key)
except Exception as e:
    app_logger.critical(f"Error configuring Gemini API: {e}", exc_info=True)
    # This might mean genai.GenerativeModel will fail later

# Initialize generative models
text_model = None
vision_model = None # Not actively used for core PDF summary, but kept for potential future use
try:
    if gemini_api_key: # Only attempt if key was found
        text_model = genai.GenerativeModel('gemini-1.5-flash-latest')
        # vision_model = genai.GenerativeModel('gemini-1.5-flash-latest') # Or 'gemini-pro-vision'
        app_logger.info("Gemini text model initialized.")
    else:
        app_logger.warning("Gemini models not initialized due to missing API key.")
except Exception as e:
    app_logger.error(f"Error initializing Gemini models: {e}. API calls may fail.", exc_info=True)


def _make_api_call(model, prompt_parts, retries=3, delay=5):
    if model is None:
        app_logger.error("API model is not initialized. Cannot make API call.")
        return "Error: API model not initialized."
    if not gemini_api_key:
        app_logger.error("GEMINI_API_KEY is missing. Cannot make API call.")
        return "Error: GEMINI_API_KEY is missing."

    if isinstance(prompt_parts, str):
        prompt_parts = [prompt_parts] # Ensure it's a list

    for attempt in range(retries):
        try:
            app_logger.debug(f"Making API call (attempt {attempt + 1}/{retries}) with prompt: {str(prompt_parts)[:200]}...")
            response = model.generate_content(prompt_parts)

            # Check for empty response or explicit blocking
            if not response.parts:
                feedback = response.prompt_feedback
                block_reason = feedback.block_reason if feedback and feedback.block_reason else "Unknown"
                safety_ratings_str = str(feedback.safety_ratings) if feedback else "N/A"
                app_logger.warning(f"API call attempt {attempt + 1} returned an empty or blocked response. "
                                   f"Block Reason: {block_reason}, Safety Ratings: {safety_ratings_str}")
                if attempt < retries - 1:
                    app_logger.info(f"Retrying API call in {delay} seconds...")
                    time.sleep(delay)
                    continue
                return f"Error: API response was empty or blocked after {retries} attempts. Reason: {block_reason}."
            
            # Log successful response text (truncated)
            app_logger.debug(f"API call successful. Response text (first 200 chars): {response.text[:200]}")
            return response.text

        except Exception as e:
            app_logger.error(f"API call attempt {attempt + 1} failed: {e}", exc_info=True)
            if attempt < retries - 1:
                app_logger.info(f"Retrying API call in {delay} seconds...")
                time.sleep(delay * (attempt + 1)) # Exponential backoff might be better
            else:
                app_logger.error("API call failed after multiple retries.")
                return f"Error: API call failed after {retries} retries. Last error: {e}"
    return f"Error: API call failed after {retries} retries (exhausted loop)."


def _get_language_instruction(language="English"):
    if language and language.lower() != "english":
        return f"Please provide the response in {language}."
    return ""

MAX_TEXT_LENGTH_FOR_SUMMARY = 75000 # Adjust based on model and typical PDF sizes

def extract_text_from_pdf(file_path):
    try:
        doc = fitz.open(file_path)
        text = ""
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text += page.get_text("text") # "text" for plain text
        app_logger.info(f"Extracted {len(text)} characters from '{os.path.basename(file_path)}'.")
        if not text.strip():
            app_logger.warning(f"No text content extracted from '{os.path.basename(file_path)}'. It might be an image-only PDF.")
            return f"Warning: No text content extracted from {os.path.basename(file_path)}. It might be an image-based PDF or empty."
        return text
    except Exception as e:
        app_logger.error(f"Error extracting text from PDF '{file_path}': {e}", exc_info=True)
        return f"Error: Could not extract text from {os.path.basename(file_path)}. {str(e)}"


def summarize_pdf_content(file_paths, language="English"):
    if text_model is None:
        app_logger.error("Text model is not initialized for PDF summarization.")
        return "Error: Text model not initialized. Check API key and configuration."
    if not file_paths:
        return "Error: No PDF file paths provided for summarization."

    full_text_content = [] # List to store text from each PDF
    errors_warnings = [] # List to store errors or warnings

    for file_path in file_paths:
        app_logger.info(f"Processing PDF: {file_path}")
        extracted_text = extract_text_from_pdf(file_path)
        if extracted_text.startswith("Error:") or extracted_text.startswith("Warning:"):
            errors_warnings.append(f"File '{os.path.basename(file_path)}': {extracted_text}")
        if not extracted_text.startswith("Error:"): # Add content even if there was a warning (e.g. empty text)
             full_text_content.append(extracted_text)


    if not any(text.strip() for text in full_text_content if not text.startswith("Warning:")): # No actual text content from any PDF
        if errors_warnings:
             return "Error: No text could be extracted from the provided PDF(s).\nDetails:\n" + "\n".join(errors_warnings)
        return "Error: No text could be extracted from the provided PDF(s)."

    # Combine texts with separators
    combined_text = "\n\n--- Next Document ---\n\n".join(filter(None, full_text_content))

    if len(combined_text) > MAX_TEXT_LENGTH_FOR_SUMMARY:
        app_logger.warning(f"Combined PDF content length ({len(combined_text)}) exceeds max for summary ({MAX_TEXT_LENGTH_FOR_SUMMARY}). Truncating.")
        combined_text = combined_text[:MAX_TEXT_LENGTH_FOR_SUMMARY] + "\n... [CONTENT TRUNCATED]"

    # Prepend any errors/warnings to the prompt context if there's also valid content
    error_warning_prefix = ""
    if errors_warnings:
        error_warning_prefix = "Note: The following issues were encountered during PDF processing:\n" + "\n".join(errors_warnings) + "\n\n"


    prompt_parts = [
        f"{error_warning_prefix}"
        f"Summarize the key information from the following text extracted from PDF document(s). "
        f"Identify the main topics, arguments, and conclusions. The summary should be comprehensive yet concise.",
        "--- PDF CONTENT START ---",
        combined_text,
        "--- PDF CONTENT END ---",
        _get_language_instruction(language)
    ]
    app_logger.info(f"Requesting summary for PDF content of effective length {len(combined_text)}.")
    return _make_api_call(text_model, prompt_parts)


def generate_explanation(topic_summary, student_level, language="English", more_detail=False):
    if text_model is None: return "Error: Text model not initialized."
    detail_instruction = ""
    if more_detail:
        detail_instruction = f"Explain this in more detail, assuming the student (level {student_level}) has some prior knowledge but needs a deeper understanding. Break down complex parts."
    else:
        detail_instruction = f"Explain this topic clearly and concisely, suitable for a student at level {student_level} who is new to this. Use simple terms and examples where possible."
    prompt = f"""
Based on the following summary of a topic:
---
{topic_summary}
---
{detail_instruction}
{_get_language_instruction(language)}
"""
    return _make_api_call(text_model, prompt)

def get_youtube_search_query_and_main_topic(topic_summary, language="English"):
    if text_model is None:
        app_logger.error("Text model not initialized for topic/query generation.")
        return {"main_topic": "Error: Text model not initialized.", "search_query": None, "error": "Text model not initialized."}

    prompt = f"""
Analyze the following text summary:
---
{topic_summary}
---
1. Identify the primary, most specific subject or topic discussed in this summary. Respond with just the topic name on the first line. This should be concise, like a chapter title (e.g., "Introduction to Photosynthesis", "Newton's Laws of Motion", "Data Types in Python"). Make it specific and informative.
2. On the second line, provide a concise and effective YouTube search query (3-7 words if possible) that a student could use to find a good introductory or explanatory video about this primary topic. Examples: "Introduction to Quantum Physics", "How Photosynthesis Works", "Python For Loops Explained".

Example Output:
Quantum Entanglement
Quantum Entanglement for beginners explained

Another Example:
The French Revolution Causes
Causes of the French Revolution summary

{_get_language_instruction(language)}
Ensure your response strictly follows this two-line format. If you cannot determine a topic or query from the summary, respond with "N/A" on both lines.
"""
    response_text = _make_api_call(text_model, prompt)
    if response_text.startswith("Error:"):
        return {"main_topic": "Error: API call failed.", "search_query": None, "error": response_text}

    lines = response_text.strip().split('\n')
    main_topic_str = "Could not determine topic"
    search_query_str = None
    error_msg = None

    if len(lines) >= 1 and lines[0].strip().lower() not in ["n/a", ""]:
        main_topic_str = lines[0].strip()
    
    if len(lines) >= 2 and lines[1].strip().lower() not in ["n/a", ""]:
        search_query_str = lines[1].strip()

    if main_topic_str == "Could not determine topic" and search_query_str is None:
        error_msg = "AI could not determine a specific topic or search query from the provided summary."
        app_logger.warning(f"{error_msg} Raw AI Response: {response_text}")
    
    app_logger.info(f"Generated topic: '{main_topic_str}', query: '{search_query_str}'")
    return {"main_topic": main_topic_str, "search_query": search_query_str, "error": error_msg}


def fetch_youtube_transcript(video_id, preferred_languages=None):
    if preferred_languages is None:
        # Prioritize original language if available, then English, then others
        preferred_languages = ['en', 'es', 'fr', 'de', 'ja', 'pt', 'it', 'zh-Hans', 'zh-Hant'] 
    
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try to find transcript in preferred languages
        for lang_code in preferred_languages:
            try:
                transcript = transcript_list.find_transcript([lang_code])
                app_logger.info(f"Found transcript for {video_id} in language: {lang_code}")
                fetched_transcript = transcript.fetch()
                return " ".join([item['text'] for item in fetched_transcript])
            except NoTranscriptFound:
                continue
        
        # Fallback: try manually created transcripts in any language
        try:
            manual_langs = transcript_list.manually_created_transcripts_by_language_code.keys()
            if manual_langs:
                transcript = transcript_list.find_manually_created_transcript(list(manual_langs))
                app_logger.info(f"Found manual transcript for {video_id} in language: {transcript.language_code}")
                fetched_transcript = transcript.fetch()
                return " ".join([item['text'] for item in fetched_transcript])
        except NoTranscriptFound:
            pass # Continue to generated

        # Fallback: try generated transcripts in any language
        try:
            generated_langs = transcript_list.generated_transcripts_by_language_code.keys()
            if generated_langs:
                transcript = transcript_list.find_generated_transcript(list(generated_langs))
                app_logger.info(f"Found auto-generated transcript for {video_id} in language: {transcript.language_code}")
                fetched_transcript = transcript.fetch()
                return " ".join([item['text'] for item in fetched_transcript])
        except NoTranscriptFound:
            app_logger.warning(f"No transcript (manual or generated) found for video {video_id} in any language.")
            return "Error: No transcript found for this video in any available language."

    except TranscriptsDisabled:
        app_logger.warning(f"Transcripts are disabled for video {video_id}.")
        return "Error: Transcripts are disabled for this video."
    except NoTranscriptFound: # Should be caught by inner fallbacks
        app_logger.warning(f"No transcript ultimately found for video {video_id} (outer catch).")
        return "Error: No transcript found for this video (outer catch)."
    except Exception as e:
        app_logger.error(f"Error fetching YouTube transcript for {video_id}: {e}", exc_info=True)
        return f"Error: Could not fetch transcript. {str(e)}"
    return "Error: Transcript fetching failed unexpectedly." # Should not be reached

def summarize_text_for_chat_context(text_content, max_length_input=75000, language="English"): # Increased input length
    if text_model is None: return "Error: Text model not initialized."
    if not text_content or not text_content.strip():
        return "Error: No text content provided to summarize."
    
    actual_length = len(text_content)
    if actual_length <= 1000: # If already very short, no need to summarize for chat context
        app_logger.info("Text content is short, using as is for chat context.")
        return text_content

    truncated_text = text_content
    if actual_length > max_length_input:
        app_logger.warning(f"Input text for summary ({actual_length} chars) is longer than max_length_input ({max_length_input}). Truncating.")
        truncated_text = text_content[:max_length_input] + "... [TRUNCATED FOR SUMMARY INPUT]"
        
    prompt = f"""
Please summarize the following text concisely. Focus on the main ideas and key information that would be most relevant for a Q&A session.
The summary should be significantly shorter than the original, aiming for a few key paragraphs or a detailed bullet list.
--- TEXT START ---
{truncated_text}
--- TEXT END ---
{_get_language_instruction(language)}
Provide a concise summary:
"""
    app_logger.info(f"Requesting summary for text of length {len(truncated_text)}.")
    return _make_api_call(text_model, prompt)

def ask_question_about_video(video_transcript_summary, user_question, language="English", chat_history=None):
    if text_model is None: return "Error: Text model not initialized."
    history_prompt = ""
    if chat_history: # Use last 5 messages
        history_prompt = "Conversation history (last 5 messages):\n"
        for entry in chat_history[-5:]: #
            role = "Student" if entry['role'] == 'user' else "Tutor"
            history_prompt += f"{role}: {entry['text']}\n"
        history_prompt += "---\n"
        
    prompt = f"""
You are an AI assistant helping a student understand a video.
The student is watching a video. Here is a summary or transcript of its content:
--- VIDEO CONTENT START ---
{video_transcript_summary}
--- VIDEO CONTENT END ---

{history_prompt}
The student's question about the video is:
"{user_question}"

Please answer the question based *only* on the provided video content summary/transcript.
If the answer isn't in the video content, politely state that the information is not available in the provided material.
{_get_language_instruction(language)}
"""
    return _make_api_call(text_model, prompt)

def generate_standard_quiz(topic_summary, num_questions=3, language="English", is_exam=False):
    if text_model is None: return "Error: Text model not initialized."
    try:
        num_questions = int(num_questions)
        if not (1 <= num_questions <= 20): # Range check
            app_logger.warning(f"num_questions ({num_questions}) out of range [1,20]. Clamping to 3.")
            num_questions = 3
    except ValueError:
        app_logger.warning(f"Invalid num_questions value, defaulting to 3.")
        num_questions = 3

    quiz_type_str = "Simple Exam" if is_exam else "Lesson Quiz"
    prompt = f"""
Based on the following content:
---
{topic_summary}
---
Create a {quiz_type_str} with {num_questions} questions to test understanding of the main concepts.
For each question, ensure it's clear and directly related to the provided content.
The questions can be multiple-choice (provide options A, B, C, D), short answer (expecting a brief textual response), or true/false. 
Clearly specify the format for each question (e.g., "Multiple Choice:", "Short Answer:", "True/False:").
If multiple choice, indicate the correct answer after the options, like "Correct Answer: C)".
Format the {quiz_type_str} clearly with questions numbered.
{_get_language_instruction(language)}
"""
    return _make_api_call(text_model, prompt)

def generate_aggregated_quiz(pdf_summary, video_summary=None, num_questions=10, language="English", is_exam=True):
    if text_model is None: return "Error: Text model not initialized."
    try:
        num_questions = int(num_questions)
        if not (1 <= num_questions <= 25): # Range check
            app_logger.warning(f"num_questions ({num_questions}) out of range [1,25]. Clamping to {DEFAULT_AGGREGATED_EXAM_QUESTIONS if 'DEFAULT_AGGREGATED_EXAM_QUESTIONS' in globals() else 10}.")
            num_questions = DEFAULT_AGGREGATED_EXAM_QUESTIONS if 'DEFAULT_AGGREGATED_EXAM_QUESTIONS' in globals() else 10
    except ValueError:
        app_logger.warning(f"Invalid num_questions value, defaulting.")
        num_questions = DEFAULT_AGGREGATED_EXAM_QUESTIONS if 'DEFAULT_AGGREGATED_EXAM_QUESTIONS' in globals() else 10

    combined_content = f"PDF Content Summary:\n---\n{pdf_summary}\n---\n"
    if video_summary and "Error:" not in video_summary and video_summary.strip():
        combined_content += f"\nVideo Content Summary:\n---\n{video_summary}\n---\n"
    else:
        combined_content += "\nNo additional video content summary was provided or it contained an error. Base questions primarily on PDF content.\n"
    
    quiz_type_str = "Comprehensive Exam" if is_exam else "Aggregated Quiz"
    prompt = f"""
Based on the following combined learning materials:
{combined_content}
Create a {quiz_type_str} with {num_questions} questions.
Test understanding of the main concepts from ALL provided materials.
If video content is available and distinct, try to include some questions specific to it.
Prioritize questions that synthesize information if possible, or cover key distinct points from each source.
Format: Multiple-choice (options A,B,C,D), short answer, or true/false. Specify format clearly for each question.
If multiple choice, indicate the correct answer after the options, like "Correct Answer: B)".
Format the assessment clearly with questions numbered.
{_get_language_instruction(language)}
"""
    return _make_api_call(text_model, prompt)

def evaluate_answer(evaluation_context, quiz_questions, user_answer, language="English"):
    if text_model is None:
        app_logger.error("Text model not initialized for answer evaluation.")
        return "Error", "Evaluation could not be performed: Text model not initialized."

    prompt = f"""
You are an AI evaluating a student's answer to a quiz/exam.
The quiz/exam was based on the following context/content:
--- CONTEXT START ---
{evaluation_context[:30000]} 
--- CONTEXT END --- 
(Context above might be truncated if very long)

The specific Quiz/Exam Questions were:
--- QUESTIONS START ---
{quiz_questions}
--- QUESTIONS END ---

The Student's Answer was:
--- ANSWER START ---
{user_answer}
--- ANSWER END ---

**Instructions for Evaluation:**
1.  On the very first line, state ONLY ONE of the following: "Correct", "Partially Correct", or "Incorrect". Do not add any other text on this line.
2.  On the subsequent lines, provide a brief but clear justification for your evaluation. Explain *why* the answer is correct, partially correct, or incorrect. Refer to the context or questions if it helps clarify. Be constructive.

Example of a "Correct" response:
Correct
The student correctly identified the main causes of the phenomenon as described in the context.

Example of an "Incorrect" response:
Incorrect
The student confused concept A with concept B. The correct answer, based on the provided context, should have focused on the definition of concept A.

Example of a "Partially Correct" response:
Partially Correct
The student correctly identified one aspect but missed another crucial detail mentioned in the material regarding the process.

{_get_language_instruction(language)}
Follow the two-part response format strictly.
"""
    response = _make_api_call(text_model, prompt)
    
    if response.startswith("Error:"):
        return "Error", response.replace("Error: ", "").strip()

    lines = response.strip().split('\n', 1)
    if len(lines) >= 1: # Must have at least the status line
        status = lines[0].strip()
        justification = lines[1].strip() if len(lines) > 1 else "No justification provided by AI."

        valid_statuses = ["Correct", "Partially Correct", "Incorrect"]
        if status not in valid_statuses:
            app_logger.warning(f"AI returned an unexpected status: '{status}'. Full response: '{response}'. Treating as 'Error'.")
            # Try to find a valid status in the justification if the first line is off
            for valid_stat in valid_statuses:
                if valid_stat.lower() in response.lower(): # Check anywhere in response
                    status = valid_stat # Take the first valid one found
                    justification = f"AI response format was unusual. Status inferred: {status}. Original response: {response}"
                    break
            else: # Still no valid status found
                status = "Error"
                justification = f"AI evaluation format error. Could not determine status. Raw response: {response}"
        
        app_logger.info(f"Evaluation result: Status='{status}', Justification='{justification[:100]}...'")
        return status, justification
    else:
        app_logger.warning(f"Could not parse evaluation response (not enough lines): {response}")
        return "Error", "Could not parse evaluation from AI. Response: " + response


def generate_learning_summary(explained_content, language="English"):
    if text_model is None: return "Error: Text model not initialized."
    prompt = f"""
Based on the following explained content that a student has just learned:
--- CONTENT START ---
{explained_content}
--- CONTENT END ---
Generate a concise summary of the key learning points. This summary should help the student remember what they've learned.
Organize it with bullet points or short, clear paragraphs for readability.
{_get_language_instruction(language)}
"""
    return _make_api_call(text_model, prompt)

def extract_skills_from_text(text_content, language="English"):
    if text_model is None: 
        app_logger.error("Text model not initialized for skill extraction.")
        return ["Error: Text model not initialized."] # Return as list with error

    prompt = f"""
Analyze the following text content and identify key skills, concepts, or topics a student might learn from it.
List each skill or concept on a new line. Be specific and concise (2-5 words per item if possible).
Do not include generic terms like "understanding" or "learning". Focus on nouns or noun phrases representing the knowledge.
--- TEXT START ---
{text_content[:30000]} 
--- TEXT END ---
(Text above might be truncated if very long)
{_get_language_instruction(language)}

Example Output:
Photosynthesis
Cellular Respiration
Newton's First Law
Python Data Types
Object-Oriented Programming
"""
    response = _make_api_call(text_model, prompt)
    if response.startswith("Error:"):
        return [response] # Return as list with error
        
    skills = [skill.strip() for skill in response.strip().split('\n') if skill.strip() and len(skill.strip()) > 2] # Filter out very short/empty lines
    if not skills:
        app_logger.warning(f"No skills extracted or response was not in expected format. Raw response: {response}")
        return ["No specific skills identified by AI."]
    app_logger.info(f"Extracted skills: {skills[:5]}...") # Log first few
    return skills


def ask_follow_up_question(context_text, user_question, language="English", chat_history=None):
    if text_model is None: return "Error: Text model not initialized."
    history_prompt = ""
    if chat_history:
        history_prompt = "Conversation history (last 5 messages):\n"
        for entry in chat_history[-5:]:
            role = "Student" if entry['role'] == 'user' else "Tutor"
            history_prompt += f"{role}: {entry['text']}\n"
        history_prompt += "---\n"
        
    prompt = f"""
You are an AI Tutor. The student is learning about the following topic/context:
--- CONTEXT START ---
{context_text[:30000]}
--- CONTEXT END ---
(Context above might be truncated if very long)

{history_prompt}
The student's current question or statement is:
"{user_question}"

Provide a helpful and informative answer to the student's question based on the provided context.
If the question seems unrelated to the context, politely state that you can only answer questions about the material.
Keep your answers concise and easy to understand.
{_get_language_instruction(language)}
"""
    return _make_api_call(text_model, prompt)