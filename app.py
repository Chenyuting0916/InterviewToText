import os
import threading
import uuid
import time
from flask import Flask, render_template, request, jsonify
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

def process_audio_background(task_id, file_path, original_filename):
    """Background worker to process audio with Gemini."""
    try:
        TASKS[task_id]['status'] = 'processing'
        print(f"Task {task_id}: Uploading {original_filename} to Gemini...")
        
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
        
        # Convert Markdown result to HTML
        transcript_html = markdown.markdown(result.text)
        
        TASKS[task_id]['status'] = 'completed'
        TASKS[task_id]['result'] = transcript_html
        print(f"Task {task_id}: Completed successfully.")

    except Exception as e:
        print(f"Task {task_id} Error: {e}")
        TASKS[task_id]['status'] = 'failed'
        TASKS[task_id]['error'] = str(e)
    
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

    # Save file temporarily
    upload_folder = 'uploads'
    os.makedirs(upload_folder, exist_ok=True)
    temp_filename = f"{uuid.uuid4()}_{audio_file.filename}"
    temp_path = os.path.join(upload_folder, temp_filename)
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
        args=(task_id, temp_path, audio_file.filename)
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
    app.run(debug=True)
