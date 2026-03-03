from flask import Flask, request, jsonify, send_file
import subprocess, requests, os, uuid, json
from pathlib import Path

def install_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except FileNotFoundError:
        os.system("apt-get update -y && apt-get install -y ffmpeg")

install_ffmpeg()

app = Flask(__name__)
OUTPUT_DIR = Path("/tmp/outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

@app.route('/health')
def health():
    return jsonify({"ok": True})

@app.route('/merge', methods=['POST'])
def merge():
    data = request.json
    uid = str(uuid.uuid4())[:8]

    v1     = f"/tmp/v1_{uid}.mp4"
    v2     = f"/tmp/v2_{uid}.mp4"
    audio  = f"/tmp/audio_{uid}.mp3"
    merged = f"/tmp/merged_{uid}.mp4"
    srt    = f"/tmp/sub_{uid}.srt"
    final  = str(OUTPUT_DIR / f"{uid}.mp4")
    list_f = f"/tmp/list_{uid}.txt"

    # Завантаження
    for url, path in [(data['video1'], v1), (data['video2'], v2), (data['audio'], audio)]:
        with open(path, 'wb') as f:
            f.write(requests.get(url, timeout=120).content)

    # Субтитри (4 слова, рівномірно за 20 сек)
    words  = data['text'].split()
    chunks = [words[i:i+5] for i in range(0, len(words), 5)]
    dur    = 20.0 / len(chunks)

    def t(s):
        return f"{int(s//3600):02}:{int((s%3600)//60):02}:{int(s%60):02},{int((s%1)*1000):03}"

    srt_txt = ""
    for i, chunk in enumerate(chunks):
        srt_txt += f"{i+1}\n{t(i*dur)} --> {t((i+1)*dur)}\n{' '.join(chunk).upper()}\n\n"
    open(srt, 'w').write(srt_txt)

    # З'єднати відео
    open(list_f, 'w').write(f"file '{v1}'\nfile '{v2}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_f, "-c", "copy", merged], capture_output=True)

    # Додати аудіо + субтитри
    subprocess.run([
        "ffmpeg", "-y", "-i", merged, "-i", audio,
        "-vf", f"subtitles={srt}:force_style='FontSize=16,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Bold=1,Alignment=2,MarginV=100'",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-c:a", "aac", "-shortest", final
    ], capture_output=True)

    for f in [v1, v2, audio, merged, srt, list_f]:
        if os.path.exists(f): os.remove(f)

    base = os.environ.get("BASE_URL", "https://web-production-97338.up.railway.app")
    return jsonify({"url": f"{base}/download/{uid}"})

@app.route('/download/<uid>')
def download(uid):
    p = OUTPUT_DIR / f"{uid}.mp4"
    return send_file(str(p)) if p.exists() else ("Not found", 404)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
