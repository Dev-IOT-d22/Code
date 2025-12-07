import cv2
import urllib.request
import numpy as np
import time
import os
import face_recognition
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# CONFIG
ESP32_CAM_URL = 'http://172.20.10.14'
STREAM_URL = f'{ESP32_CAM_URL}/480x320.jpg'
UNLOCK_URL = f'{ESP32_CAM_URL}/unlock'

# Google Sheets Config
CREDENTIALS_FILE = 'iot-nhom6.json'
SHEET_NAME = 'iot-chamcongtudong'
WORKSHEET_NAME = 'DANHSACH'

# Google Drive Config
GOOGLE_DRIVE_FOLDER_ID = '0APc81r36Z77dUk9PVA'

# Thingsboard Config
THINGSBOARD_URL = "https://thingsboard.cloud/api/v1"
THINGSBOARD_TOKEN = "f1YwrzEzSXRHX0jpLkx4"

# Global
known_face_encodings = []
known_face_names = []
known_face_ids = {}
attendance_sheet = None

CAPTURE_DIR = "captures"
os.makedirs(CAPTURE_DIR, exist_ok=True)

# UPLOAD ẢNH LÊN GOOGLE DRIVE
def upload_to_drive(image_path):
    try:
        scopes = ['https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scopes)
        drive_service = build('drive', 'v3', credentials=creds)

        file_metadata = {
            'name': os.path.basename(image_path),
            'parents': [GOOGLE_DRIVE_FOLDER_ID]
        }

        media = MediaFileUpload(image_path, mimetype='image/jpeg')

        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True  
        ).execute()

        file_id = file.get('id')
        print(f"[+] ✔ Ảnh đã upload lên Drive (id={file_id})")
        return file_id

    except Exception as e:
        print(f"[!] Lỗi upload Google Drive: {e}")
        return None

# GOOGLE SHEETS
def connect_google_sheet():
    try:
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
        return sheet
    except Exception as e:
        print(f"[!] Lỗi kết nối Google Sheets: {e}")
        return None

# THINGSBOARD
def send_to_thingsboard(person_id, person_name, date_str, time_str, status_str):
    url = f"{THINGSBOARD_URL}/{THINGSBOARD_TOKEN}/telemetry"
    payload = {
        "ID": person_id,
        "Name": person_name,
        "Date": date_str,
        "Time": time_str,
        "Status": status_str
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            print("[+] ✔ Đã gửi dữ liệu lên ThingsBoard!")
        else:
            print(f"[!] Lỗi gửi TB: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[!] Exception gửi ThingsBoard: {e}")

# Chấm Công
def log_attendance(sheet, person_id, person_name, img_path):
    if sheet is None:
        return False
    try:
        now = datetime.now()
        date_str = now.strftime("%d/%m/%Y")
        time_str = now.strftime("%H:%M:%S")
        all_values = sheet.get_all_values()
        if len(all_values) > 1:
            for row in all_values[1:]:
                if len(row) >= 3:
                    if str(row[0]).strip() == str(person_id) and row[2].strip() == date_str:
                        print(f"[!] {person_name} đã chấm công hôm nay! (Trùng)")
                        send_to_thingsboard(person_id, person_name, date_str, time_str, "Đã chấm công hôm nay rồi")
                        upload_to_drive(img_path)
                        return False
        upload_to_drive(img_path)
        row = [person_id, person_name, date_str, time_str, "Đã chấm công"]
        sheet.append_row(row)

        print(f"[+] ✔ Chấm công: {person_name} - {time_str}")
        send_to_thingsboard(person_id, person_name, date_str, time_str, "Đã chấm công")
        return True
    except Exception as e:
        print(f"[!] Lỗi chấm công: {e}")
        return False

# Mở kháo cửa
def unlock_door():
    try:
        response = requests.get(UNLOCK_URL, timeout=3)
        if response.status_code == 200:
            print("[+] ✔ Đã MỞ KHÓA!")
            return True
        return False
    except Exception as e:
        print(f"[!] Lỗi unlock: {e}")
        return False

# LOAD FACES
def load_known_faces():
    global known_face_encodings, known_face_names, known_face_ids
    print("[*] Đang tải dữ liệu khuôn mặt...")
    if not os.path.exists("known_faces"):
        print("[!] Thư mục known_faces không tồn tại! Tạo thư mục và thêm ảnh vào.")
        os.makedirs("known_faces", exist_ok=True)
        return
    for file in os.listdir("known_faces"):
        if file.lower().endswith(('.jpg', '.png', '.jpeg')):
            try:
                img = face_recognition.load_image_file(f"known_faces/{file}")
                encodings = face_recognition.face_encodings(img)
                if encodings:
                    encoding = encodings[0]
                    known_face_encodings.append(encoding)
                    filename = os.path.splitext(file)[0]
                    if '_' in filename:
                        person_id, name = filename.split('_', 1)
                    else:
                        person_id = f"{len(known_face_names) + 1:03d}"
                        name = filename
                    known_face_names.append(name)
                    known_face_ids[name] = person_id
                    print(f"   [+] Nạp ID:{person_id} - {name}")
            except Exception as ex:
                print(f"[!] Lỗi khi đọc file {file}: {ex}")
    print(f"[*] Hoàn tất! Đã nạp {len(known_face_names)} khuôn mặt\n")

# Face RECOGNITION
def start_recognition():
    global attendance_sheet
    print("BẮT ĐẦU NHẬN DIỆN KHUÔN MẶT")
    if not known_face_encodings:
        load_known_faces()
    if attendance_sheet is None:
        attendance_sheet = connect_google_sheet()
    max_attempts = 10
    attempt = 0
    recognized = False
    while attempt < max_attempts and not recognized:
        try:
            attempt += 1
            print(f"[*] Lần thử {attempt}/{max_attempts}...")
            img_resp = urllib.request.urlopen(STREAM_URL, timeout=5)
            imgnp = np.array(bytearray(img_resp.read()), dtype=np.uint8)
            img = cv2.imdecode(imgnp, -1)
            if img is None:
                print("[!] Không lấy được ảnh từ ESP32")
                time.sleep(1)
                continue
            rgb_frame = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_frame)
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
            if not face_encodings:
                print("   [i] Không phát hiện khuôn mặt")
                time.sleep(1)
                continue
            now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            img_path = os.path.join(CAPTURE_DIR, f"{now_str}.jpg")
            cv2.imwrite(img_path, img)

            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(known_face_encodings, face_encoding, tolerance=0.5)
                if True in matches:
                    idx = matches.index(True)
                    name = known_face_names[idx]
                    person_id = known_face_ids.get(name, f"{idx+1:03d}")
                    print(f"\nNHẬN DIỆN THÀNH CÔNG: {name} (ID: {person_id})")
                    if unlock_door():
                        log_attendance(attendance_sheet, person_id, name, img_path)
                        recognized = True
                        print("\n[*] Hoàn tất! Đóng cửa sau 5 giây...\n")
                        time.sleep(5)
                        break
                else:
                    print("[!] Người lạ — Không mở cửa")
            time.sleep(1)
        except Exception as e:
            print(f"[!] Lỗi: {e}")
            time.sleep(2)
    if not recognized:
        print("\n[!] Không nhận diện được sau 10 lần thử!")
    print("KẾT THÚC NHẬN DIỆN")

if __name__ == "__main__":
    start_recognition()

