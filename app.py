from flask import Flask, request, jsonify
import subprocess
import requests
import os
import uuid

app = Flask(__name__)

@app.route('/merge', methods=['POST'])
def merge():
    data = request.json
    video1_url = data['video1']
    video2_url = data['video2']
    audio_url = data['audio']
    
    uid = str(uuid.uuid4())[:8]
    v1 = f"/tmp/v1_{uid}.mp4"
    v2 = f"/tmp/v2_{uid}.mp4"
    audio = f"/tmp/audio_{uid}.mp3"
    merged = f"/tmp/merged_{uid}.mp4"
    final = f"/tmp/final_{uid}.mp4"
    
    # Download files
    for url, path in [(video1_url, v1), (video2_url, v2), (audio_url, audio)]:
        r = requests.get(url)
        with open(path, 'wb') as f:
            f.write(r.content)
    
    # Merge videos
    with open(f"/tmp/list_{uid}.txt", "w") as f:
        f.write(f"file '{v1}'\nfile '{v2}'\n")
    
    subprocess.run([
        "ffmpeg", "-f", "concat", "-safe", "0",
        "-i", f"/tmp/list_{uid}.txt",
        "-c", "copy", merged
    ])
    
    # Add audio
    subprocess.run([
        "ffmpeg", "-i", merged, "-i", audio,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac",
        "-shortest", final
    ])
    
    # Upload to file.io
    with open(final, 'rb') as f:
        response = requests.post(
            'https://file.io/?expires=1d',
            files={'file': f}
        )
    
    return jsonify({"url": response.json()['link']})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
