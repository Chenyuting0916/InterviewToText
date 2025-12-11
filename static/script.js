document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const uploadForm = document.getElementById('upload-form');
    const statusContainer = document.getElementById('status-container');
    const resultCard = document.getElementById('result-card');
    const resultContent = document.getElementById('result-content');
    const errorMessage = document.getElementById('error-message');
    const selectedFilename = document.getElementById('selected-filename');
    const copyBtn = document.getElementById('copy-btn');

    // Drag & Drop Handling
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length > 0) {
            handleFiles(e.dataTransfer.files[0]);
        }
    });

    // Click Handling
    dropZone.addEventListener('click', () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            handleFiles(fileInput.files[0]);
        }
    });

    function handleFiles(file) {
        if (!file.type.startsWith('audio/')) {
            showError('Please select a valid audio file.');
            return;
        }

        if (file.size > 50 * 1024 * 1024) {
            showError('File size exceeds the 50MB limit.');
            return;
        }

        // Reset UI
        errorMessage.classList.add('hidden');
        resultCard.classList.add('hidden');
        selectedFilename.textContent = file.name;

        // Auto upload
        uploadFile(file);
    }

    function uploadFile(file) {
        const formData = new FormData();
        formData.append('audio', file);

        // Show loading state
        dropZone.classList.add('hidden');
        statusContainer.classList.remove('hidden');

        fetch('/upload', {
            method: 'POST',
            body: formData
        })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    showError(data.error);
                    statusContainer.classList.add('hidden');
                    dropZone.classList.remove('hidden');
                } else if (data.task_id) {
                    // improved polling starts here
                    pollStatus(data.task_id);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                statusContainer.classList.add('hidden');
                dropZone.classList.remove('hidden');
                showError('An error occurred during upload. Please try again.');
            });
    }

    function pollStatus(taskId) {
        // Poll every 5 seconds to reduce network traffic
        setTimeout(() => {
            fetch(`/status/${taskId}`)
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'completed') {
                        statusContainer.classList.add('hidden');
                        dropZone.classList.remove('hidden');
                        showResult(data.transcript);
                    } else if (data.status === 'failed') {
                        statusContainer.classList.add('hidden');
                        dropZone.classList.remove('hidden');
                        showError(data.error || 'Processing failed.');
                    } else {
                        // Still processing or queued
                        // Update status text if needed
                        pollStatus(taskId);
                    }
                })
                .catch(error => {
                    console.error('Polling Error:', error);
                    statusContainer.classList.add('hidden');
                    dropZone.classList.remove('hidden');
                    showError('Network error while checking status.');
                });
        }, 5000);
    }

    function showResult(htmlContent) {
        resultContent.innerHTML = htmlContent;
        resultCard.classList.remove('hidden');
        // Scroll to result
        resultCard.scrollIntoView({ behavior: 'smooth' });
    }

    function showError(msg) {
        errorMessage.textContent = msg;
        errorMessage.classList.remove('hidden');
    }

    // Copy to Clipboard
    copyBtn.addEventListener('click', () => {
        const text = resultContent.innerText;
        navigator.clipboard.writeText(text).then(() => {
            const originalText = copyBtn.innerText;
            copyBtn.innerText = 'Copied!';
            setTimeout(() => {
                copyBtn.innerText = originalText;
            }, 2000);
        });
    });
});
