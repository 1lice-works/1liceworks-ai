import os

from flask import Flask, request, jsonify
import google.generativeai as genai  # Google Gemini API
import re
from datetime import datetime, time, timedelta
from dateutil import parser
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
        now_kst_str = now_kst.strftime("%Y-%m-%d %H:%M:%S")

        prompt = f"""
        당신은 일정 생성 AI 비서입니다.
        사용자가 입력한 내용을 분석하여 일정 정보를 추출하세요.
        **반드시 한국 표준시(KST, UTC+9) 기준으로 변환해야 합니다.**
        오늘 날짜는 {now_kst_str} 입니다.

        ### 출력 형식 ###
        다음 JSON 형식으로 일정을 반환하세요:
        {{"title": "일정 제목",
          "description": "설명 (없으면 빈 문자열)",
          "startTime": "YYYY-MM-DDTHH:MM:SS",
          "endTime": "YYYY-MM-DDTHH:MM:SS",
          "allDay": false,
          "location": "위치 (없으면 빈 문자열)"}}

        ### 예제 ###
        입력: "오늘 오전 10시에 팀 회의 잡아줘"
        출력: {{
            "title": "팀 회의",
            "description": "주간 회의",
            "startTime": "2025-02-15T10:00:00",
            "endTime": "2025-02-15T11:00:00",
            "allDay": false,
            "location": "회의실 A"
        }}

        **프롬프트에서 제공되지 않은 값은 빈 문자열("") 또는 null로 설정하세요.**

        ### 입력 ###
        입력: "{prompt_text}"
        JSON 형식으로 결과를 반환하세요:
        """

        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt)

        # Gemini 응답을 JSON으로 변환
        try:
            result = json.loads(response.text)
        except json.JSONDecodeError:
            return jsonify({"error": "Failed to parse Gemini response as JSON", "raw_response": response.text}), 500

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def create_find_free_time_prompt(calendars):
    """빈 시간 찾기 프롬프트 생성"""
    calendar_json_str = json.dumps(calendars, indent=2, ensure_ascii=False)

    prompt = f"""
    당신은 일정 조정 AI 비서입니다.  
    사용자의 일정 데이터를 분석하여 빈 시간을 찾아주세요.  
    사용자의 근무 시간은 **09:00 ~ 18:00 (KST, UTC+9)** 입니다.  

    **규칙**  
    - `calendars`에 있는 모든 `events`를 병합하여 하나의 일정 목록을 만드세요.  
    - `startTime` 기준으로 정렬한 후 **이전 일정의 `endTime`과 다음 일정의 `startTime` 사이의 빈 시간**을 계산하세요.  
    - **근무 시간 (09:00 ~ 18:00) 내에서만 빈 시간을 반환**하세요.  
    - JSON 형식으로 **코드 블록 없이** 결과를 반환하세요.  

    ### 📌 **입력 데이터 예시**
    {calendar_json_str}

    ### 📌 **출력 형식 예시**
    {{
        "results": [
            {{
                "startTime": "2025-02-15T09:00:00",
                "endTime": "2025-02-15T10:00:00"
            }},
            {{
                "startTime": "2025-02-15T11:00:00",
                "endTime": "2025-02-15T14:00:00"
            }},
            {{
                "startTime": "2025-02-15T15:00:00",
                "endTime": "2025-02-15T18:00:00"
            }}
        ]
    }}
    """
    return prompt


def clean_gemini_response(response_text):
    """Gemini 응답에서 JSON만 추출"""
    # ```json ... ``` 코드 블록 제거
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", response_text, re.DOTALL)
    if json_match:
        clean_json = json_match.group(1)
    else:
        clean_json = response_text.strip()

    return clean_json


@app.route('/find_free_time', methods=['POST'])
def find_free_time():
    """Gemini API를 사용하여 빈 시간 찾기"""
    try:
        data = request.get_json()

        # 캘린더 데이터 확인
        calendars = data.get("calendars", [])
        if not isinstance(calendars, list):
            return jsonify({"error": "Invalid data format: 'calendars' must be a list"}), 400

        # Gemini 프롬프트 생성
        prompt = create_find_free_time_prompt(calendars)

        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt)

        # 응답에서 JSON 데이터만 추출
        clean_json = clean_gemini_response(response.text)

        # JSON 변환
        try:
            result = json.loads(clean_json)
        except json.JSONDecodeError:
            return jsonify({"error": "Failed to parse Gemini response", "raw_response": response.text}), 500

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)