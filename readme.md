uvicorn main:app --reload

接口文档（超方便??！）： http://127.0.0.1:8000/docs

接口JSON： http://127.0.0.1:8000/reminders


// https://reminder-api-topaz.vercel.app/reminders


https://reminder-api-o3ba.onrender.com



API 文档（?文本格式）
-----------------------

所有?求需携?以下?求?：
Authorization: Bearer <Google ID Token>
Content-Type: application/json

==============================
GET: /reminders
------------------------------
?取当前用?所有提醒事?。

Header:
  Authorization: Bearer <id_token>

Body:
  无

Response:
  [
    {
      "id": 1,
      "title": "吃?",
      "description": "?得吃午?",
      "date": "2024-05-01",
      "time": "12:00"
    }
  ]


==============================
POST: /reminders
------------------------------
添加一条新的提醒事?。

Header:
  Authorization: Bearer <id_token>
  Content-Type: application/json

Body:
  {
    "title": "?会",
    "description": "?目周会",
    "date": "2024-05-02",
    "time": "10:00"
  }

Response:
  {
    "id": 2,
    "title": "?会",
    "description": "?目周会",
    "date": "2024-05-02",
    "time": "10:00"
  }


==============================
PUT: /reminders/{remid}
------------------------------
根据提醒 ID 更新提醒内容。

Header:
  Authorization: Bearer <id_token>
  Content-Type: application/json

Path Params:
  remid: 提醒? ID

Body:
  {
    "title": "?会改??",
    "description": "推?到下午?点",
    "date": "2024-05-02",
    "time": "14:00"
  }

Response:
  {
    "id": 2,
    "title": "?会改??",
    "description": "推?到下午?点",
    "date": "2024-05-02",
    "time": "14:00"
  }


==============================
DELETE: /reminders/{remid}
------------------------------
?除指定 ID 的提醒?。

Header:
  Authorization: Bearer <id_token>

Path Params:
  remid: 提醒? ID

Response:
  {
    "message": "?除成功"
  }