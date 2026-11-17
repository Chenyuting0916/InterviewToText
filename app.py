import os
import re
import threading
import uuid
import time
from flask import Flask, render_template, request, jsonify
import bleach
import google.generativeai as genai
from dotenv import load_dotenv
import markdown

load_dotenv()

app = Flask(__name__)
# Increase max content length for larger audio files (e.g., 50MB)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# Configure Gemini
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

# In-memory storage for tasks (NOTE: Works only with a single worker process)
TASKS = {}
_UPLOADS = {}
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".flac", ".aac", ".mp4", ".mpeg", ".mpga"}
ALLOWED_CONTENT_TYPES = {"", "application/octet-stream", "video/webm", "video/mp4"}

def _client_ip():
    return request.remote_addr or "unknown"

def _too_many_uploads():
    now = time.time()
    ip = _client_ip()
    recent = [stamp for stamp in _UPLOADS.get(ip, []) if now - stamp < 3600]
    if len(recent) >= 8:
        _UPLOADS[ip] = recent
        return True
    recent.append(now)
    _UPLOADS[ip] = recent
    return False

def _audio_path(original_filename):
    extension = os.path.splitext(original_filename or "")[1].lower()
    if extension not in ALLOWED_AUDIO_EXTENSIONS or not re.fullmatch(r"\.[a-z0-9]{1,8}", extension):
        raise ValueError("unsupported")
    folder = os.path.abspath("uploads")
    os.makedirs(folder, exist_ok=True)
    path = os.path.abspath(os.path.join(folder, f"{uuid.uuid4().hex}{extension}"))
    if os.path.commonpath([folder, path]) != folder:
        raise ValueError("unsupported")
    return path

def _transcript_html(text):
    rendered = markdown.markdown(text or "", output_format="html")
    return bleach.clean(
        rendered,
        tags=["p", "br", "strong", "em", "ul", "ol", "li", "h1", "h2", "h3", "blockquote", "code", "pre"],
        attributes={},
        strip=True,
    )

def process_audio_background(task_id, file_path):
    """Background worker to process audio with Gemini."""
    try:
        TASKS[task_id]['status'] = 'processing'
        print(f"Task {task_id}: Uploading audio to Gemini...")
        
        # Upload to Gemini (File API)
        myfile = genai.upload_file(file_path)
        
        # Wait for file to be ready processing (polite waiting)
        while myfile.state.name == "PROCESSING":
            time.sleep(5)
            myfile = genai.get_file(myfile.name)

        if myfile.state.name == "FAILED":
            raise Exception("Gemini File API failed to process the audio.")

        # Generate content
        print(f"Task {task_id}: Generating transcript...")
        model = genai.GenerativeModel("gemini-flash-latest") 
        
        # Prompt for transcription and diarization
        prompt = (
            "Please listen to this audio file and provide a verbatim transcription. "
            "Identify different speakers (Speaker 1, Speaker 2, etc.) and format it clearly. "
            "Do not summarize, I need the full text."
        )
        
        result = model.generate_content([myfile, prompt])
        
        TASKS[task_id]['status'] = 'completed'
        TASKS[task_id]['result'] = _transcript_html(getattr(result, "text", "") or "")
        print(f"Task {task_id}: Completed successfully.")

    except Exception as e:
        print(f"Task {task_id} Error: {e}")
        TASKS[task_id]['status'] = 'failed'
        TASKS[task_id]['error'] = "Transcription failed"
    
    finally:
        # Cleanup temp file
        if os.path.exists(file_path):
            os.remove(file_path)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'audio' not in request.files:
        return jsonify({'error': 'Please provide an audio file'}), 400
    
    audio_file = request.files['audio']
    if audio_file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if not os.getenv('GOOGLE_API_KEY'):
        return jsonify({'error': 'Server configuration error: API Key missing'}), 500

    if _too_many_uploads():
        return jsonify({'error': 'Too many uploads. Please try again later.'}), 429

    content_type = (audio_file.mimetype or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES and not content_type.startswith("audio/"):
        return jsonify({'error': 'Please provide an audio file'}), 400

    try:
        temp_path = _audio_path(audio_file.filename)
    except ValueError:
        return jsonify({'error': 'Unsupported audio type'}), 400
    audio_file.save(temp_path)

    # Create Task
    task_id = str(uuid.uuid4())
    TASKS[task_id] = {
        'status': 'queued',
        'created_at': time.time()
    }

    # Start Background Thread
    thread = threading.Thread(
        target=process_audio_background, 
        args=(task_id, temp_path)
    )
    thread.start()

    return jsonify({'task_id': task_id})

@app.route('/status/<task_id>', methods=['GET'])
def check_status(task_id):
    task = TASKS.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    response = {'status': task['status']}
    if task['status'] == 'completed':
        response['transcript'] = task['result']
        # Optional: Clean up task from memory after retrieval
        # del TASKS[task_id] 
    elif task['status'] == 'failed':
        response['error'] = task.get('error', 'Unknown error')
    
    return jsonify(response)

if __name__ == '__main__':
    app.run(debug=False, host='127.0.0.1')
