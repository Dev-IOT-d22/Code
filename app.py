from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import sys
import os

app = Flask(__name__)
CORS(app)

# Google Sheets Config
CREDENTIALS_FILE = 'iot-nhom6.json'
SHEET_NAME = 'iot-chamcongtudong'
WORKSHEET_NAME = 'DANHSACH'

face_recognition_running = False
attendance_sheet = None

def connect_google_sheet():
    try:
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
        print("[+] Kết nối Google Sheets thành công!")
        return sheet
    except Exception as e:
        print(f"[!] Lỗi kết nối Google Sheets: {e}")
        return None

def run_face_recognition():
    global face_recognition_running
    face_recognition_running = True
    try:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        import face_recognition_main
        face_recognition_main.start_recognition() 
    except Exception as e:
        print(f"[!] Lỗi chạy face recognition: {e}")
    finally:
        face_recognition_running = False

@app.route('/')
def index():
    return jsonify({
        "message": "ESP32-CAM Attendance System API",
        "version": "1.0",
        "status": "online",
        "endpoints": {
            "start": "POST /start - Bắt đầu nhận diện khuôn mặt",
            "attendance": "GET /attendance - Lấy dữ liệu chấm công",
            "status": "GET /status - Kiểm tra trạng thái hệ thống"
        }
    })

@app.route('/start', methods=['POST'])
def start_recognition():
    global face_recognition_running
    
    if face_recognition_running:
        return jsonify({
            "success": False,
            "message": "Hệ thống nhận diện đang chạy rồi!"
        })
    
    thread = threading.Thread(target=run_face_recognition)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "message": "Đã khởi động hệ thống nhận diện!"
    })

@app.route('/attendance', methods=['GET'])
def get_attendance():
    try:
        global attendance_sheet
        
        if attendance_sheet is None:
            attendance_sheet = connect_google_sheet()
        
        if attendance_sheet is None:
            return jsonify({
                "success": False,
                "message": "Không thể kết nối Google Sheets"
            })
        
        all_values = attendance_sheet.get_all_values()
        
        if len(all_values) <= 1:
            return jsonify({
                "success": True,
                "records": []
            })
        
        records = []
        for row in all_values[1:]: 
            if len(row) >= 5:
                records.append({
                    "id": row[0],
                    "name": row[1],
                    "date": row[2],
                    "time": row[3],
                    "status": row[4]
                })
        
        records.reverse()
        
        return jsonify({
            "success": True,
            "records": records,
            "total": len(records)
        })
        
    except Exception as e:
        print(f"[!] Lỗi API /attendance: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        })

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({
        "success": True,
        "face_recognition_running": face_recognition_running,
        "google_sheets_connected": attendance_sheet is not None
    })

if __name__ == '__main__':
    print("ESP32-CAM ATTENDANCE SYSTEM - FLASK API")
    attendance_sheet = connect_google_sheet()
    
    print("\n[*] Flask API Server")
    print("[*] API sẽ chạy tại: http://localhost:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)

