from flask import Flask, request, jsonify, Response, send_from_directory, stream_with_context
import yt_dlp
import os
import re
import threading
import time

app = Flask(__name__)

DOWNLOAD_FOLDER = 'downloads'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    
progress_dict = {}

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def download_in_background(url):
    try:
        def progress_hook(d):
            if d['status'] == 'downloading':
                percent_str = d.get('_percent_str', '0.0%').strip()
                try:
                    percent_num = float(percent_str.replace('%',''))
                except:
                    percent_num = 0
                progress_dict[url] = percent_num
            elif d['status'] == 'finished':
                progress_dict[url] = 100

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            'noplaylist': True,
            'progress_hooks': [progress_hook],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)
            progress_dict[url] = 100

    except Exception as e:
        progress_dict[url] = -1  # error indicator

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/assets/<path:path>')
def serve_assets(path):
    return send_from_directory('assets', path)

@app.route('/start', methods=['POST'])
def start_download():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({'error': 'URL required'}), 400

    progress_dict[url] = 0
    threading.Thread(target=download_in_background, args=(url,), daemon=True).start()
    return jsonify({'status': 'started'})

@app.route('/progress')
def progress():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL required'}), 400

    def generate():
        last_prog = -1
        while True:
            prog = progress_dict.get(url, 0)
            if prog != last_prog:
                yield f"data: {prog}\n\n"
                last_prog = prog
            if prog >= 100 or prog < 0:
                break
            time.sleep(0.2)

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/download')
def download_file():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL required'}), 400

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        title = sanitize_filename(info.get('title', 'download'))
        mp3_filename = f"{title}.mp3"
        mp3_path = os.path.join(DOWNLOAD_FOLDER, mp3_filename)

    if not os.path.exists(mp3_path):
        return jsonify({'error': 'File not found'}), 404

    def generate_file():
        with open(mp3_path, 'rb') as f:
            while chunk := f.read(8192):
                yield chunk
        try:
            os.remove(mp3_path)
        except Exception as e:
            print(f"Error deleting file: {e}")
        if url in progress_dict:
            del progress_dict[url]

    return Response(generate_file(), mimetype='audio/mpeg',
                    headers={"Content-Disposition": f"attachment; filename={mp3_filename}"})
port = int(os.environ.get("PORT", 5000))
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=port)
