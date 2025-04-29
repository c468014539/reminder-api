import os
import json
import threading
import io
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi import Request
from pydantic import BaseModel
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2.credentials import Credentials


app = FastAPI()

# ---- 配置 ----
TOKEN_FILE = 'token.json'           # OAuth 2.0 用户凭证
CREDENTIALS_FILE = 'credentials.json'  # OAuth 客户端凭证
SETTINGS_FILE = 'set.prop'          # 保存 user_email:reminder_fileId
SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/userinfo.email']

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有请求头
)

# 请求模型（不含 id）
class ReminderIn(BaseModel):
    title: str
    description: Optional[str] = None
    date: str
    time: str

# 响应模型（含 id）
class Reminder(ReminderIn):
    id: int

def get_user_info_and_drive(request: Request):
    from google.oauth2 import id_token
    from google.auth.transport import requests as grequests

    auth_header = request.headers.get("Authorization", "")
    access_token = request.headers.get("X-Access-Token")

    if not auth_header.startswith("Bearer ") or not access_token:
        raise HTTPException(status_code=401, detail="缺少认证头")

    id_token_val = auth_header.split(" ")[1]
    try:
        idinfo = id_token.verify_oauth2_token(id_token_val, grequests.Request())
        user_email = idinfo["email"]
    except Exception:
        raise HTTPException(status_code=401, detail="无效的 ID token")

    creds = Credentials(token=access_token)
    drive_service = build("drive", "v3", credentials=creds)
    return user_email, drive_service

# 本地设置文件操作
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_settings(settings: dict):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

# 创建新文件并记录映射
def create_new_reminder_file(service, user_email):
    file_metadata = {'name': 'reminders.json', 'mimeType': 'application/json'}
    buffer = io.BytesIO(json.dumps([], ensure_ascii=False).encode('utf-8'))
    media = MediaIoBaseUpload(buffer, mimetype='application/json')
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    file_id = file.get('id')
    settings = load_settings()
    settings[user_email] = file_id
    save_settings(settings)
    return file_id

# 读取提醒
def load_reminders(drive, user_email: str) -> List[dict]:
    settings = load_settings()
    if user_email not in settings:
        create_new_reminder_file(drive, user_email)
        return []
    file_id = settings[user_email]
    try:
        data = drive.files().get_media(fileId=file_id).execute()
        reminders = json.loads(data)
    except HttpError as e:
        if e.resp.status == 404:
            create_new_reminder_file(drive, user_email)
            return []
        raise
    # 确保所有提醒项都有 id
    for idx, r in enumerate(reminders):
        if 'id' not in r:
            r['id'] = idx + 1
    return reminders

# 保存提醒
def save_reminders(reminders: List[dict], drive, user_email: str):
    settings = load_settings()
    if user_email not in settings:
        raise HTTPException(status_code=404, detail="未找到提醒文件，请先获取提醒列表")
    file_id = settings[user_email]
    buffer = io.BytesIO(json.dumps(reminders, ensure_ascii=False, indent=2).encode('utf-8'))
    media = MediaIoBaseUpload(buffer, mimetype='application/json')
    drive.files().update(
        fileId=file_id,
        media_body=media
    ).execute()

# FastAPI 接口
@app.get("/reminders", response_model=List[Reminder])
def get_reminders(request: Request):
    user_email, drive = get_user_info_and_drive(request)
    return load_reminders(drive, user_email)

@app.post("/reminders", response_model=Reminder)
def add_reminder(reminder: ReminderIn, request: Request):
    user_email, drive = get_user_info_and_drive(request)
    reminders = load_reminders(drive, user_email)
    next_id = max((r['id'] for r in reminders), default=0) + 1
    new = reminder.dict()
    new['id'] = next_id
    if 'description' not in new or new['description'] is None:
        new['description'] = ''
    reminders.append(new)
    save_reminders(reminders, drive, user_email)
    return new

@app.put("/reminders/{remid}", response_model=Reminder)
def update_reminder(remid: int, updated: ReminderIn, request: Request):
    user_email, drive = get_user_info_and_drive(request)
    reminders = load_reminders(drive, user_email)
    for idx, r in enumerate(reminders):
        if r['id'] == remid:
            reminders[idx].update(updated.dict())
            reminders[idx]['id'] = remid
            save_reminders(reminders, drive, user_email)
            return reminders[idx]
    raise HTTPException(status_code=404, detail="未找到指定提醒")

@app.delete("/reminders/{remid}")
def delete_reminder(remid: int, request: Request):
    user_email, drive = get_user_info_and_drive(request)
    reminders = load_reminders(drive, user_email)
    reminders = [r for r in reminders if r['id'] != remid]
    save_reminders(reminders, drive, user_email)
    return {"message": "删除成功"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)