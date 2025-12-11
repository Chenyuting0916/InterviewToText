import os
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

    if audio_file:
        try:
            # Check if API key is present
            if not os.getenv('GOOGLE_API_KEY'):
                return jsonify({'error': 'Server configuration error: API Key missing'}), 500

            # Save file temporarily
            upload_folder = 'uploads'
            os.makedirs(upload_folder, exist_ok=True)
            temp_path = os.path.join(upload_folder, audio_file.filename)
            audio_file.save(temp_path)

            try:
                # Upload to Gemini (File API)
                print(f"Uploading {audio_file.filename} to Gemini...")
                myfile = genai.upload_file(temp_path)
                
                # Generate content
                print("Generating transcript...")
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
                
                return jsonify({'transcript': transcript_html})
                
            finally:
                # Cleanup temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
        except Exception as e:
            print(f"Error: {e}")
            return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
