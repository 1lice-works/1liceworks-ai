import os

from flask import Flask, request, jsonify
import google.generativeai as genai
import re
from datetime import datetime
from dateutil.parser import parse
import pytz
import json
from dotenv import load_dotenv

app = Flask(__name__)

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

KST = pytz.timezone("Asia/Seoul")

@app.route('/generate_schedule', methods=['POST'])
def generate_schedule():
    """ 사용자의 입력을 기반으로 일정 생성 (한국 시간 기준) """
    try:
        data = request.get_json()
        prompt_text = data.get("prompt", "")

        if not prompt_text:
            return jsonify({"error": "No prompt provided"}), 400

        now_kst = datetime.now(KST)
        now_kst_str = now_kst.strftime("%Y-%m-%dT%H:%M:%S")

        prompt = f"""
        당신은 일정 생성 AI 비서입니다.
        사용자가 입력한 내용을 분석하여 일정 정보를 최대한 유추하여 추출하세요.
        **반드시 한국 표준시(KST, UTC+9) 기준으로 변환해야 합니다.**
        오늘 날짜는 {now_kst_str} 입니다.

        ### 출력 형식 ###
        반드시 순수 JSON 형식으로만 응답하세요. 추가적인 설명이나 코드 블록(```json ... ```)을 포함하지 마세요.
        다음 JSON 형식으로 일정을 반환하세요:
        {{"title": "일정 제목" 유추 가능하면 해당 값 불가능하면 일정,
          "description": 유추 가능하면 해당 값, 불가능하면 null,
          "dtStartTime": "yyyy-MM-dd'T'HH:mm:ss",
          "dtEndTime": "yyyy-MM-dd'T'HH:mm:ss" 유추 불가능하면 dtStartTime의 1시간 후,
          "isAllDay": 유추 가능하면 true 또는 false, 불가능하면 false,
          "privacyType": 유추 가능하면 "PUBLIC" 또는 "PRIVATE", 불가능하면 "PRIVATE",
          "availability": 유추 가능하면 "FREE" 또는 "BUSY", 불가능하면 "BUSY",
          "location": 유추 가능하면 해당 값, 불가능하면 null,
          "eventReminders": 유추 가능하면 해당 값, 불가능하면 [{{"notifyTime": dtStartTime 30분 전}}]}}

        **프롬프트에서 제공되지 않은 값은 최대한 유추해보고, 유추할 수 없는 경우에만 기본값을 반환하세요.**
        **isAllDay가 true인 경우 dtStartTime은 00:00:00, dtEndTime은 23:59:59로 설정하세요.**

        ### 예제 ###
        입력: "오늘 오전 10시에 회의실 A에서 팀 회의 두시간 동안 잡아줘"
        출력: {{
          "title": "팀 회의",
          "description": "팀 회의 입니다.",
          "dtStartTime": "2025-02-25T10:00:00",
          "dtEndTime": "2025-02-25T12:00:00",
          "isAllDay": false,
          "privacyType": "PUBLIC",
          "availability": "BUSY",
          "location": "회의실 A",
          "eventReminders": [{{"notifyTime": "2025-02-25T09:30:00"}}]
          }}

        ### 입력 ###
        입력: "{prompt_text}"
        JSON 형식으로 결과를 반환하세요:
        """

        model = genai.GenerativeModel("gemini-2.0-flash-lite")
        response = model.generate_content(prompt)

        # Gemini 응답을 JSON으로 변환
        try:
            cleaned_response = re.sub(r'```json|```', '', response.text).strip()
            result = json.loads(cleaned_response)
        except json.JSONDecodeError:
            return jsonify({"error": "Failed to parse Gemini response as JSON", "raw_response": response.text}), 500

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/find_free_time', methods=['POST'])
def find_free_time():
    """Gemini API를 사용하여 빈 시간 찾기"""
    try:
        data = request.get_json()

        # 요청 데이터 추출
        date = data.get("date")  # YYYY-MM-DD 형식
        duration = data.get("duration", 60)  # 최소 빈 시간 (기본값: 60분)
        events = data.get("events", [])

        if not date:
            return jsonify({"error": "Missing required field: date"}), 400

        # events가 빈 리스트라면 해당 date 전체를 빈 시간으로 응답
        if not events:
            return jsonify({
                "freeTimeDtos": [
                    {
                        "startTime": f"{date}T09:00:00",
                        "endTime": f"{date}T20:00:00"
                    }
                ]
            })

        # JSON 데이터를 프롬프트에 전달할 포맷으로 변환
        formatted_events = [
            f"이벤트: {event['title']}, 시작 시간: {event['dtStartTime']}, 종료 시간: {event['dtEndTime']}"
            for event in events
        ]

        prompt = f"""
        당신은 일정 관리 AI 비서입니다. 사용자가 제공한 일정 목록을 분석하여 빈 시간을 찾아야 합니다.

        **요구사항:**
        1. 사용자가 요청한 날짜({date})의 **09:00:00 ~ 20:00:00** 사이에서만 빈 시간을 찾습니다.
        2. **빈 시간은 {duration}분 단위로 나누어 제공해야 하며, 이보다 짧은 시간은 절대 포함하지 마세요.**
        3. **빈 시간이 없을 경우 `freeTimeDtos: []` 형식으로 응답하세요.**
        4. **빈 시간의 종료 시간은 반드시 `{date}T20:00:00` 이하로 설정해야 합니다.**
        5. `{date}T20:00:01` 이후의 시간은 절대 포함하지 마세요.
        6. **각 빈 시간이 반드시 요청한 `duration`(단위: 분)에 맞는지 확인하고, 이 조건을 만족하지 않는 빈 시간은 제외하세요.**
        7. 응답은 JSON 형식으로 제공하며, 추가적인 설명이나 코드 블록(```json ... ```)을 포함하지 마세요.

        ### 제공된 일정 ###
        {formatted_events}

        ### 예제1 ###
        만약 일정이 아래와 같고, duration이 60분일 경우:
        - 일정: 08:00 ~ 10:00, 10:00 ~ 11:00, 12:00 ~ 13:00, 14:00 ~ 16:00, 16:30 ~ 17:30, 18:00 ~ 19:00
        - 원하는 출력: 11:00 ~ 12:00, 13:00 ~ 14:00, 19:00 ~ 20:00
        ### 출력 형식 ###
        {{
          "freeTimeDtos": [
            {{"startTime": "yyyy-MM-dd'T'HH:mm:ss", "endTime": "yyyy-MM-dd'T'HH:mm:ss"}}
          ]
        }}
        
        ### 예제2 ###
        만약 일정이 아래와 같고 duration이 120분일 경우:
        - 일정: 08:00 ~ 10:00, 10:00 ~ 11:00, 12:00 ~ 13:00, 14:00 ~ 16:00, 16:30 ~ 17:30, 18:00 ~ 19:00
        - 원하는 출력: 19:00 ~ 20:00
        ### 출력 형식 ###
        {{
          "freeTimeDtos": [
            {{"startTime": "yyyy-MM-dd'T'HH:mm:ss", "endTime": "yyyy-MM-dd'T'HH:mm:ss"}}
          ]
        }}
        
        ### 예제3 ###
        만약 일정이 아래와 같고, duration이 60분일 경우:
        - 일정: 10:00 ~ 11:00, 13:00 ~ 13:30, 14:30 ~ 16:00, 16:00 ~ 18:20 
        - 원하는 출력: 09:00 ~ 10:00, 11:00 ~ 13:00, 13:30 ~ 14:30, 18:20 ~ 20:00
        ### 출력 형식 ###
        {{
          "freeTimeDtos": [
            {{"startTime": "yyyy-MM-dd'T'HH:mm:ss", "endTime": "yyyy-MM-dd'T'HH:mm:ss"}}
          ]
        }}
        """

        model = genai.GenerativeModel("gemini-2.0-flash-lite")
        response = model.generate_content(prompt)

        # Gemini 응답을 JSON으로 변환
        try:
            cleaned_response = response.text.strip("```json").strip("```").strip()
            result = json.loads(cleaned_response)

            free_times = result.get("freeTimeDtos", [])

            # **빈 시간이 duration에 맞지 않는 항목을 제외**
            valid_free_times = [
                free_time for free_time in free_times
                if (parse(free_time['endTime']) - parse(free_time['startTime'])).seconds >= duration * 60
            ]

            return jsonify({"freeTimeDtos": valid_free_times})

        except json.JSONDecodeError:
            return jsonify({"error": "Failed to parse Gemini response as JSON", "raw_response": response.text}), 500


    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return "Flask 서버가 정상 실행 중입니다."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)