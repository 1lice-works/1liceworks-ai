import os

from flask import Flask, request, jsonify
import google.generativeai as genai  # Google Gemini API
import re
from datetime import datetime
import pytz
import json
from dotenv import load_dotenv

app = Flask(__name__)

# Gemini API 키 설정
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

# 한국 시간대 설정
KST = pytz.timezone("Asia/Seoul")

@app.route('/generate_schedule', methods=['POST'])
def generate_schedule():
    """ 사용자의 입력을 기반으로 일정 생성 (한국 시간 기준 변환) """
    try:
        data = request.get_json()
        prompt_text = data.get("prompt", "")

        if not prompt_text:
            return jsonify({"error": "No prompt provided"}), 400

        # 현재 한국 시간 계산
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
    """ 일정 데이터를 받아 빈 시간을 찾아 반환 """
    try:
        data = request.get_json()
        duration = data.get("duration", 60)
        events = data.get("events", [])

        if not events:
            return jsonify({"freeTimeDtos": []})  # 일정이 없으면 빈 배열 반환

        # JSON 데이터를 Gemini 프롬프트에 전달할 포맷으로 변환
        formatted_events = [
            f"이벤트: {event['title']}, 시작 시간: {event['dtStartTime']}, 종료 시간: {event['dtEndTime']}"
            for event in events
        ]

        prompt = f"""
        당신은 일정 관리 AI 비서입니다. 사용자가 제공한 일정 목록을 분석하여 주어진 시간(duration) 이상 비어있는 시간을 찾아야 합니다.
        사용자가 요청한 빈 시간은 {duration}분 이상입니다.

        ### 제공된 일정 ###
        {formatted_events}

        ### 출력 형식 ###
        JSON 형식으로 응답하세요. 추가적인 설명이나 코드 블록(```json ... ```)을 포함하지 마세요.
        다음과 같은 형식으로 응답하세요:
        {{
          "freeTimeDtos": [
            {{"startTime": "yyyy-MM-dd'T'HH:mm:ss", "endTime": "yyyy-MM-dd'T'HH:mm:ss"}},
            ...
          ]
        }}

        **한국 표준시(KST, UTC+9) 기준으로 날짜 및 시간을 변환해야 합니다.**
        """

        # Gemini API 호출
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

@app.route('/')
def home():
    return "Flask 서버가 정상 실행 중입니다."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)