let currentVoiceId = null;
let mediaRecorder = null;
let audioChunks = [];
let recTimerInterval = null;
let recSeconds = 0;

// DOM Elements
const dropzone = document.getElementById('dropzone');
const voiceFileInput = document.getElementById('voiceFileInput');
const dropContent = document.getElementById('dropContent');
const uploadStatus = document.getElementById('uploadStatus');
const uploadStatusText = document.getElementById('uploadStatusText');
const voicePreviewBox = document.getElementById('voicePreviewBox');
const voiceAudioPlayer = document.getElementById('voiceAudioPlayer');
const previewFilename = document.getElementById('previewFilename');
const refTextInput = document.getElementById('refTextInput');
const scriptTextInput = document.getElementById('scriptTextInput');
const speedRange = document.getElementById('speedRange');
const speedVal = document.getElementById('speedVal');
const generateBtn = document.getElementById('generateBtn');
const generateBtnText = document.getElementById('generateBtnText');
const progressBox = document.getElementById('progressBox');
const progressMsg = document.getElementById('progressMsg');
const progressPct = document.getElementById('progressPct');
const progressBar = document.getElementById('progressBar');
const resultCard = document.getElementById('resultCard');
const resultAudioPlayer = document.getElementById('resultAudioPlayer');
const downloadWavBtn = document.getElementById('downloadWavBtn');
const downloadMp3Btn = document.getElementById('downloadMp3Btn');
const recordBtn = document.getElementById('recordBtn');
const recordBtnText = document.getElementById('recordBtnText');
const recTimer = document.getElementById('recTimer');

// Speed Slider
speedRange.addEventListener('input', (e) => {
    speedVal.textContent = `${parseFloat(e.target.value).toFixed(2)}×`;
});

// Drag & Drop
['dragenter', 'dragover'].forEach(name => {
    dropzone.addEventListener(name, (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });
});

['dragleave', 'drop'].forEach(name => {
    dropzone.addEventListener(name, (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
    });
});

dropzone.addEventListener('drop', (e) => {
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('audio/')) {
        handleFileUpload(file);
    }
});

voiceFileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        handleFileUpload(file);
    }
});

// Upload and Process Audio File
async function handleFileUpload(file) {
    dropContent.style.display = 'none';
    uploadStatus.style.display = 'block';
    uploadStatusText.textContent = `Uploading & transcribing ${file.name}...`;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/upload_voice', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        currentVoiceId = data.voice_id;
        previewFilename.textContent = data.duration ? `${data.filename} (${data.duration.toFixed(1)}s reference)` : data.filename;
        voiceAudioPlayer.src = data.audio_url;
        voicePreviewBox.style.display = 'block';

        if (data.transcript) {
            refTextInput.value = data.transcript;
        }

        uploadStatus.style.display = 'none';
        dropContent.style.display = 'block';
        checkReadyState();

    } catch (err) {
        alert('Failed to upload audio: ' + err);
        uploadStatus.style.display = 'none';
        dropContent.style.display = 'block';
    }
}

// Live Microphone Recording
recordBtn.addEventListener('click', async () => {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
        recordBtnText.textContent = 'Record Live via Microphone';
        recordBtn.classList.remove('btn-danger');
        clearInterval(recTimerInterval);
        recTimer.style.display = 'none';
    } else {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    channelCount: 1,
                    sampleRate: 48000
                }
            });
            audioChunks = [];
            mediaRecorder = new MediaRecorder(stream);
            
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0) audioChunks.push(e.data);
            };

            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                const recordedFile = new File([audioBlob], 'live_recording.wav', { type: 'audio/wav' });
                handleFileUpload(recordedFile);
                stream.getTracks().forEach(track => track.stop());
            };

            mediaRecorder.start();
            recordBtnText.textContent = 'Stop Recording (5–10s recommended)';
            recordBtn.classList.add('btn-danger');
            
            // Timer
            recSeconds = 0;
            recTimer.style.display = 'inline-block';
            recTimer.textContent = '00:00';
            recTimerInterval = setInterval(() => {
                recSeconds++;
                const mins = String(Math.floor(recSeconds / 60)).padStart(2, '0');
                const secs = String(recSeconds % 60).padStart(2, '0');
                recTimer.textContent = `${mins}:${secs}`;
            }, 1000);

        } catch (err) {
            alert('Microphone access denied or unavailable: ' + err);
        }
    }
});

// Check if inputs are ready to enable generate button
function checkReadyState() {
    const hasVoice = currentVoiceId !== null;
    const hasScript = scriptTextInput.value.trim().length > 0;
    const hasRefText = refTextInput.value.trim().length > 0;

    generateBtn.disabled = !(hasVoice && hasScript && hasRefText);
}

scriptTextInput.addEventListener('input', checkReadyState);
refTextInput.addEventListener('input', checkReadyState);

// Pause Helper
function insertPause(pauseMarker) {
    const start = scriptTextInput.selectionStart;
    const end = scriptTextInput.selectionEnd;
    const text = scriptTextInput.value;
    scriptTextInput.value = text.substring(0, start) + ` ${pauseMarker} ` + text.substring(end);
    scriptTextInput.focus();
    scriptTextInput.setSelectionRange(start + pauseMarker.length + 2, start + pauseMarker.length + 2);
    checkReadyState();
}

// Preset Scripts
function loadPreset(type) {
    if (type === 'tech') {
        scriptTextInput.value = "Every large language model you have used has the same quiet limitation. / Once training ends, its weights are frozen. // But what if a model could look at your question first, / decide what kind of thinker it needs to be, / and then rewire itself in real time? // That is the promise of self-adaptive neural architectures.";
    } else if (type === 'youtube') {
        scriptTextInput.value = "Welcome back to the channel! / Today, we are breaking down one of the most exciting breakthroughs in AI. // If you enjoy technical deep dives like this, / hit subscribe and let's jump right into the architecture.";
    } else if (type === 'podcast') {
        scriptTextInput.value = "That wraps up our discussion for today. / A huge thank you to everyone tuning in. // Make sure to check the description for all paper references and benchmark code. // Until next time, / keep building.";
    }
    checkReadyState();
}

// Generate Narration Action
generateBtn.addEventListener('click', async () => {
    if (!currentVoiceId) return;

    generateBtn.disabled = true;
    generateBtnText.textContent = 'Synthesizing with Your Voice...';
    progressBox.style.display = 'block';
    resultCard.style.display = 'none';
    progressBar.style.width = '5%';
    progressPct.textContent = '5%';
    progressMsg.textContent = 'Conditioning speaker flow model...';

    try {
        const res = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                voice_id: currentVoiceId,
                ref_text: refTextInput.value.trim(),
                script_text: scriptTextInput.value.trim(),
                speed: parseFloat(speedRange.value)
            })
        });

        const data = await res.json();
        if (data.error) throw new Error(data.error);

        const jobId = data.job_id;
        pollProgress(jobId);

    } catch (err) {
        alert('Generation failed to start: ' + err);
        generateBtn.disabled = false;
        generateBtnText.textContent = 'Clone Voice & Synthesize Audio';
        progressBox.style.display = 'none';
    }
});

// Poll Generation Progress
function pollProgress(jobId) {
    const pollInterval = setInterval(async () => {
        try {
            const res = await fetch(`/api/progress/${jobId}`);
            const job = await res.json();

            if (job.status === 'processing') {
                progressBar.style.width = `${job.progress}%`;
                progressPct.textContent = `${job.progress}%`;
                progressMsg.textContent = job.message;
            } else if (job.status === 'completed') {
                clearInterval(pollInterval);
                progressBar.style.width = '100%';
                progressPct.textContent = '100%';
                progressMsg.textContent = 'Complete!';

                // Show Deliverable Result
                resultAudioPlayer.src = job.mp3_url;
                downloadWavBtn.href = job.wav_url;
                downloadMp3Btn.href = job.mp3_url;
                resultCard.style.display = 'block';

                generateBtn.disabled = false;
                generateBtnText.textContent = 'Clone Voice & Synthesize Audio';
                resultCard.scrollIntoView({ behavior: 'smooth' });

            } else if (job.status === 'failed') {
                clearInterval(pollInterval);
                alert('Synthesis error: ' + job.message);
                generateBtn.disabled = false;
                generateBtnText.textContent = 'Clone Voice & Synthesize Audio';
            }
        } catch (err) {
            console.error('Polling error:', err);
        }
    }, 1500);
}
