import os
import json
import threading
import io
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
from google.auth.transport.requests import Request
from fastapi.middleware.cors import CORSMiddleware

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

# 获取 OAuth2 凭证
def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise RuntimeError(f"缺少 {CREDENTIALS_FILE}")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
                f.write(creds.to_json())
    return creds

# Drive 服务
def get_drive_service():
    creds = get_credentials()
    return build('drive', 'v3', credentials=creds)

# 获取当前登录用户 Email
def get_user_email():
    creds = get_credentials()
    oauth2 = build('oauth2', 'v2', credentials=creds)
    info = oauth2.userinfo().get().execute()
    return info.get('email')

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
def load_reminders() -> List[dict]:
    user_email = get_user_email()
    service = get_drive_service()
    settings = load_settings()
    if user_email not in settings:
        create_new_reminder_file(service, user_email)
        return []
    file_id = settings[user_email]
    try:
        data = service.files().get_media(fileId=file_id).execute()
        reminders = json.loads(data)
    except HttpError as e:
        if e.resp.status == 404:
            create_new_reminder_file(service, user_email)
            return []
        raise
    # 确保所有提醒项都有 id
    for idx, r in enumerate(reminders):
        if 'id' not in r:
            r['id'] = idx + 1
    return reminders

# 保存提醒
def save_reminders(reminders: List[dict]):
    user_email = get_user_email()
    service = get_drive_service()
    settings = load_settings()
    if user_email not in settings:
        raise HTTPException(status_code=404, detail="未找到提醒文件，请先获取提醒列表")
    file_id = settings[user_email]
    buffer = io.BytesIO(json.dumps(reminders, ensure_ascii=False, indent=2).encode('utf-8'))
    media = MediaIoBaseUpload(buffer, mimetype='application/json')
    service.files().update(
        fileId=file_id,
        media_body=media
    ).execute()

# FastAPI 接口
@app.get("/reminders", response_model=List[Reminder])
def get_reminders():
    return load_reminders()

@app.post("/reminders", response_model=Reminder)
def add_reminder(reminder: ReminderIn):
    reminders = load_reminders()
    next_id = max((r['id'] for r in reminders), default=0) + 1
    new = reminder.dict()
    new['id'] = next_id
    if 'description' not in new or new['description'] is None:
        new['description'] = ''
    reminders.append(new)
    save_reminders(reminders)
    return new

@app.put("/reminders/{remid}", response_model=Reminder)
def update_reminder(remid: int, updated: ReminderIn):
    reminders = load_reminders()
    for idx, r in enumerate(reminders):
        if r['id'] == remid:
            reminders[idx].update(updated.dict())
            reminders[idx]['id'] = remid
            save_reminders(reminders)
            return reminders[idx]
    raise HTTPException(status_code=404, detail="未找到指定提醒")

@app.delete("/reminders/{remid}")
def delete_reminder(remid: int):
    reminders = load_reminders()
    reminders = [r for r in reminders if r['id'] != remid]
    save_reminders(reminders)
    return {"message": "删除成功"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)