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
    subtitle_text = data['text']

    uid = str(uuid.uuid4())[:8]
    v1 = f"/tmp/v1_{uid}.mp4"
    v2 = f"/tmp/v2_{uid}.mp4"
    audio = f"/tmp/audio_{uid}.mp3"
    merged = f"/tmp/merged_{uid}.mp4"
    final = f"/tmp/final_{uid}.mp4"
    srt = f"/tmp/sub_{uid}.srt"

    # Download files
    for url, path in [(video1_url, v1), (video2_url, v2), (audio_url, audio)]:
        r = requests.get(url, timeout=60)
        with open(path, 'wb') as f:
            f.write(r.content)

    # Generate SRT subtitles
    words = subtitle_text.split()
    total_duration = 20
    chunk_size = 4
    chunks = [words[i:i+chunk_size] for i in range(0, len(words), chunk_size)]

    def to_srt_time(t):
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = t % 60
        return f"{h:02}:{m:02}:{s:06.3f}".replace('.', ',')

    srt_content = ""
    for i, chunk in enumerate(chunks):
        start = i * (total_duration / len(chunks))
        end = (i + 1) * (total_duration / len(chunks))
        srt_content += f"{i+1}\n{to_srt_time(start)} --> {to_srt_time(end)}\n{' '.join(chunk)}\n\n"

    with open(srt, 'w') as f:
        f.write(srt_content)

    # Merge two videos
    list_file = f"/tmp/list_{uid}.txt"
    with open(list_file, "w") as f:
        f.write(f"file '{v1}'\nfile '{v2}'\n")

    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy", merged
    ], check=True)

    # Add audio + subtitles
    subprocess.run([
        "ffmpeg", "-y",
        "-i", merged,
        "-i", audio,
        "-vf", f"subtitles={srt}:force_style='FontName=Arial,FontSize=20,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Bold=1,Alignment=2,MarginV=40'",
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",
        final
    ], check=True)

    # Upload to file.io
    with open(final, 'rb') as f:
        response = requests.post('https://file.io/?expires=1d', files={'file': f})

    result = response.json()
    return jsonify({"url": result.get('link', ''), "success": result.get('success', False)})


@app.route('/upload-audio', methods=['POST'])
def upload_audio():
    uid = str(uuid.uuid4())[:8]
    audio_path = f"/tmp/audio_{uid}.mp3"
    with open(audio_path, 'wb') as f:
        f.write(request.data)
    with open(audio_path, 'rb') as f:
        response = requests.post('https://file.io/?expires=1d', files={'file': f})
    return jsonify({"audio_url": response.json().get('link', '')})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
