from flask import Flask, request, jsonify, send_file
import subprocess
import requests
import os
import uuid
import json
from pathlib import Path

# ============================================================
# ВСТАНОВЛЕННЯ FFmpeg (до старту Flask)
# ============================================================
def install_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        print("ffmpeg OK")
    except FileNotFoundError:
        print("Installing ffmpeg...")
        subprocess.run(["apt-get", "update", "-y"], capture_output=True)
        subprocess.run(["apt-get", "install", "-y", "ffmpeg"], capture_output=True)
        print("ffmpeg installed")

install_ffmpeg()

app = Flask(__name__)

OUTPUT_DIR = Path("/tmp/outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# ============================================================
# HEALTH CHECK
# ============================================================
@app.route('/health', methods=['GET'])
def health():
    try:
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True)
        ffmpeg_ok = r.returncode == 0
    except:
        ffmpeg_ok = False
    return jsonify({"status": "ok", "ffmpeg": ffmpeg_ok})

# ============================================================
# MERGE — зʼєднання 2 відео + аудіо + субтитри
# ============================================================
@app.route('/merge', methods=['POST'])
def merge():
    try:
        data = request.json
        video1_url    = data['video1']
        video2_url    = data['video2']
        audio_url     = data['audio']
        subtitle_text = data['text']

        uid    = str(uuid.uuid4())[:8]
        v1     = f"/tmp/v1_{uid}.mp4"
        v2     = f"/tmp/v2_{uid}.mp4"
        audio  = f"/tmp/audio_{uid}.mp3"
        merged = f"/tmp/merged_{uid}.mp4"
        final  = str(OUTPUT_DIR / f"{uid}_final.mp4")
        srt    = f"/tmp/sub_{uid}.srt"
        list_f = f"/tmp/list_{uid}.txt"

        # --- Завантаження файлів ---
        for url, path in [(video1_url, v1), (video2_url, v2), (audio_url, audio)]:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            with open(path, 'wb') as f:
                f.write(r.content)

        # --- Тривалість аудіо ---
        probe = subprocess.run([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", audio
        ], capture_output=True, text=True)
        duration = float(json.loads(probe.stdout)["format"]["duration"])

        # --- Генерація SRT (динамічно за довжиною слів) ---
        words = subtitle_text.split()
        group_size = 4
        groups = [" ".join(words[i:i+group_size]) for i in range(0, len(words), group_size)]
        total_chars = sum(len(g) for g in groups)
        current_time = 0.2

        def to_srt_time(t):
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            ms = int((t % 1) * 1000)
            return f"{h:02}:{m:02}:{s:02},{ms:03}"

        srt_content = ""
        for i, group in enumerate(groups):
            char_ratio = len(group) / total_chars
            group_dur  = (duration - 0.4) * char_ratio
            start = current_time
            end   = start + group_dur
            if end > duration: end = duration
            srt_content += f"{i+1}\n{to_srt_time(start)} --> {to_srt_time(end)}\n{group.upper()}\n\n"
            current_time = end

        with open(srt, 'w') as f:
            f.write(srt_content)

        # --- Concat двох відео ---
        with open(list_f, "w") as f:
            f.write(f"file '{v1}'\nfile '{v2}'\n")

        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_f, "-c", "copy", merged
        ], check=True, capture_output=True)

        # --- Аудіо + субтитри ---
        style = "FontName=Arial,FontSize=16,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Bold=1,Alignment=2,MarginV=100"
        subprocess.run([
            "ffmpeg", "-y",
            "-i", merged,
            "-i", audio,
            "-vf", f"subtitles={srt}:force_style='{style}'",
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-af", "aresample=async=1",
            "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
            "-shortest",
            "-pix_fmt", "yuv420p",
            final
        ], check=True, capture_output=True)

        # Cleanup тимчасових файлів
        for f in [v1, v2, audio, merged, srt, list_f]:
            if os.path.exists(f): os.remove(f)

        base_url = os.environ.get("BASE_URL", "https://web-production-97338.up.railway.app")
        return jsonify({
            "status":       "success",
            "download_url": f"{base_url}/download/{uid}"
        })

    except subprocess.CalledProcessError as e:
        return jsonify({"error": "ffmpeg failed", "details": e.stderr.decode() if e.stderr else str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# DOWNLOAD — віддати готове відео
# ============================================================
@app.route('/download/<video_id>')
def download(video_id):
    p = OUTPUT_DIR / f"{video_id}_final.mp4"
    if p.exists():
        return send_file(str(p), as_attachment=True, download_name="shorts.mp4")
    return jsonify({"error": "Not found"}), 404


# ============================================================
# UPLOAD AUDIO (опційно)
# ============================================================
@app.route('/upload-audio', methods=['POST'])
def upload_audio():
    uid = str(uuid.uuid4())[:8]
    audio_path = f"/tmp/audio_{uid}.mp3"
    with open(audio_path, 'wb') as f:
        f.write(request.data)
    with open(audio_path, 'rb') as f:
        resp = requests.post('https://file.io/?expires=1d', files={'file': f})
    return jsonify({"audio_url": resp.json().get('link', '')})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
