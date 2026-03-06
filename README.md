# Catch-up 0700

매일 아침 7시에 자동으로 뉴스를 수집, 정제, 요약하고 오디오로 변환해 Slack 스레드로 전송하는 AI RAG 뉴스 브리핑 시스템입니다.  
FastAPI 서버에서 상시 구동되며, `APScheduler` 크론으로 정시 실행됩니다.

---

## 1) 프로젝트 개요

이 프로젝트는 아래 흐름을 하나의 파이프라인으로 연결합니다.

1. Google Sheets에서 검색 키워드 + 분석 기준 프롬프트 로드
2. Naver News API로 키워드별 전일 기사 수집
3. URL 기준 1차 병합 + Gemini 기반 의미 중복 2차 제거
4. 심층 기사(Deep Dive) / 단신 기사(Short Brief) 선별
5. 심층 기사 원문 크롤링
6. Agenda 작성 -> 섹션별 대본 작성 -> Slack 메시지 포맷 생성
7. ElevenLabs TTS로 섹션별 MP3 생성
8. Slack 메인 메시지 + 스레드 답글(파일 첨부 포함) 전송
9. 24시간 지난 오디오 파일 자동 정리

---

## 2) 기술 스택

- Python 3.10+
- FastAPI / Uvicorn
- APScheduler
- Google Sheets API (`google-api-python-client`, `google-auth`)
- Gemini API (`google-generativeai`)
- Naver News Open API (`requests`)
- Slack SDK (`slack_sdk`)
- ElevenLabs TTS API (`requests`)
- BeautifulSoup4 (크롤링/텍스트 정제)
- python-dotenv (로컬 환경 변수 로드)

---

## 3) 디렉토리 구조

현재 코드 기준 핵심 구조는 아래와 같습니다.

```text
CatchUp7/
├─ main.py
├─ config/
│  └─ settings.py
├─ services/
│  ├─ google_sheets_client.py
│  ├─ naver_news_client.py
│  ├─ news_service.py
│  ├─ gemini_client.py
│  ├─ deduplication_service.py
│  ├─ selection_service.py
│  ├─ rag_prep_service.py
│  ├─ agenda_agent.py
│  ├─ script_agent.py
│  ├─ slack_agent.py
│  ├─ tts_service.py
│  ├─ slack_service.py
│  └─ __init__.py
├─ utils/
│  ├─ logger.py
│  ├─ data_processor.py
│  ├─ crawler.py
│  └─ __init__.py
├─ .env.example
└─ README.md
```

---

## 4) 빠른 시작

### 4.1 가상환경 생성 및 패키지 설치

```bash
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install fastapi uvicorn[standard] requests beautifulsoup4 google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2 slack_sdk python-dotenv google-generativeai pydantic pydantic-settings httpx tenacity python-dateutil apscheduler
```

> 참고: 현재 저장소에는 `requirements.txt`가 없으면 직접 생성해서 `pip install -r requirements.txt`로 관리하는 것을 권장합니다.

### 4.2 환경 변수 설정

루트에 `.env` 파일을 만들고 아래 값을 채워주세요.

```env
GEMINI_API_KEY=your_gemini_key
NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret
ELEVENLABS_API_KEY=your_elevenlabs_key
ELEVENLABS_VOICE_ID=optional_voice_id
AUDIO_OUTPUT_DIR=audio_output
GOOGLE_DRIVE_AUDIO_FOLDER_ID=103dM-wvNb8cUNfsGuMYA0vIOUa3mgLn6
SLACK_BOT_TOKEN=your_slack_bot_token
SLACK_CHANNEL_ID=your_slack_channel_id
GOOGLE_CREDENTIALS_JSON={"type":"service_account", ...}
SPREADSHEET_ID=your_google_spreadsheet_id
```

#### 환경 변수 설명

- `GEMINI_API_KEY`: Gemini API 키
- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`: Naver 뉴스 검색 API 인증값
- `ELEVENLABS_API_KEY`: ElevenLabs TTS API 키
- `ELEVENLABS_VOICE_ID` (선택): 음성 ID (없으면 코드 기본값 사용)
- `AUDIO_OUTPUT_DIR` (선택): 로컬 오디오 저장 폴더 (기본값 `audio_output`)
- `GOOGLE_DRIVE_AUDIO_FOLDER_ID` (선택): 생성 오디오 업로드 대상 Google Drive 폴더 ID
- `SLACK_BOT_TOKEN`: Slack Bot 토큰
- `SLACK_CHANNEL_ID`: 메시지 전송 대상 채널 ID
- `GOOGLE_CREDENTIALS_JSON`: 서비스 계정 JSON 문자열 전체
- `SPREADSHEET_ID`: Google Sheet 문서 ID

---

## 5) Google Sheet 포맷

`SPREADSHEET_ID`가 가리키는 시트에서 아래 규칙으로 읽습니다.

### 5.1 `Setting` 탭

- 읽기 범위: `Setting!A2:B`
- A열: 검색 키워드 목록 (빈 값 제외)
- B열: 분석 방향 텍스트 (여러 행 가능, 빈 값 제외 후 줄바꿈으로 결합)

`services/google_sheets_client.py`의 `get_config_data()`가 아래 구조로 반환합니다.

```python
{
  "keywords": ["키워드1", "키워드2", ...],
  "prompt_criteria": "분석 방향 1\n분석 방향 2\n..."
}
```

### 5.2 `News` 탭

- 쓰기 범위: `News!A:E`
- `append_news_to_sheet()`가 최종 선별 기사(심층 + 단신)를 append
- 컬럼 순서:
  - A: 수집일자 (`YYYY-MM-DD`)
  - B: 발행일자 (`pubDate` 파싱 `YYYY-MM-DD`)
  - C: 제목
  - D: 요약 (너무 길면 200자 요약)
  - E: 링크 (`originallink` 우선)

---

## 6) 실행 방법

### 6.1 로컬 실행

```bash
python main.py
```

또는

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 6.2 수동 테스트 실행

서버가 켜진 상태에서 다음 엔드포인트를 호출하면 파이프라인이 백그라운드로 즉시 실행됩니다.

- `GET /run`

응답 예시:

```json
{"message":"Daily briefing started in background."}
```

### 6.3 자동 스케줄 실행

- 시간대: `Asia/Seoul`
- 스케줄: 매일 `07:00`
- 위치: `main.py`의 `lifespan`에서 `BackgroundScheduler` 등록

---

## 7) 파이프라인 상세

`main.py`의 `run_daily_briefing()` 기준 처리 순서:

1. `collect_daily_news()`
2. `merge_by_url()`
3. `filter_duplicate_articles()`
4. `prepare_final_data()`
5. `append_news_to_sheet()` (최종 선별 기사 DB 저장)
6. `generate_agenda()`
7. `write_script()`
8. `format_slack_messages()`
9. `generate_audio()` (섹션별)
10. `send_main_message()` + `send_thread_reply_with_file()`
11. `cleanup_old_audios()`

예외 처리:

- 기사가 없거나 치명적 오류가 발생하면 Slack에 아래 단일 메시지를 전송하고 종료합니다.
- `"오늘은 브리핑할 뉴스가 없거나 시스템 에러가 발생했습니다."`

---

## 8) 로그 및 산출물

### 로그

- 파일: `logs/app.log`
- 콘솔 + 파일 동시 출력
- 포맷:
  - `[시간] [레벨] [파일명:라인] - 메시지`

### 오디오 파일

- 기본 폴더: `audio_output/` (`AUDIO_OUTPUT_DIR`로 변경 가능)
- 파일명: `{생성일자yymmdd}_{기사제목}.mp3`
- 정리 정책: 생성 후 24시간이 지난 `.mp3` 자동 삭제
- 저장 방식:
  - 로컬 저장 후
  - Google Drive 폴더(`GOOGLE_DRIVE_AUDIO_FOLDER_ID`) 업로드 시도

---

## 9) Slack 전송 구조

`services/slack_agent.py`가 생성하는 구조:

```json
{
  "slack_messages": [
    {"type":"main","text":"메인 요약"},
    {"type":"thread_deep_dive","article_id":"article_001","text":"심층 요약 + 링크"},
    {"type":"thread_short_brief","text":"단신 링크 목록"}
  ]
}
```

`services/slack_service.py`가 이를 사용해:

- 메인 메시지 전송 -> `ts` 확보
- 같은 `thread_ts`로 스레드 답글 순차 전송
- 파일 경로가 있으면 `files_upload_v2`, 없으면 `chat_postMessage`

---

## 10) Cloudtype 배포 체크리스트

1. Python 런타임 버전 설정 (3.10+)
2. 환경 변수(Secrets) 전부 등록
3. 실행 커맨드 예시:
   - `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. 헬스체크 필요 시 별도 엔드포인트 추가 권장
5. 서버가 꺼지지 않도록 항상-on 정책 확인

---

## 11) 트러블슈팅

### `Missing required environment variable` 에러

- `.env` 누락 또는 값 누락입니다.
- `config/settings.py`는 필수 키가 하나라도 비면 앱을 종료합니다.

### Slack 메시지 전송 실패

- `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID` 확인
- 봇이 채널에 초대되어 있는지 확인
- 파일 업로드 권한(`files:write`) 확인

### Gemini 응답 파싱 실패

- 모델 출력이 비거나 스키마를 벗어나면 fallback 처리됩니다.
- `logs/app.log`에서 해당 agent 로그 확인

### Google Drive 업로드 실패

- 서비스 계정 이메일이 대상 폴더에 편집 권한으로 공유되어 있는지 확인
- `GOOGLE_DRIVE_AUDIO_FOLDER_ID`가 올바른지 확인

### 크롤링 텍스트가 빈 문자열

- 언론사 차단/구조 변경 가능성이 있습니다.
- `utils/crawler.py`의 selector 후보를 확장해 보세요.

---

## 12) 보안 주의사항

- API 키, 토큰, 서비스 계정 JSON은 절대 저장소에 커밋하지 마세요.
- `.env`는 반드시 `.gitignore`로 제외하세요.
- 운영 환경에서는 Cloudtype 환경 변수(Secret) 주입 방식을 사용하세요.

---

## 13) 다음 개선 포인트 (권장)

- 테스트 코드 추가 (`unit/integration`)
- 재시도/백오프 정책 강화 (`tenacity`)
- Slack 전송 재시도 큐
- `requirements.txt` 고정 및 CI 파이프라인
- `/health` 엔드포인트 추가

---

## 14) 대본 품질/TTS 작성 규칙

`services/script_agent.py`는 아래 규칙을 프롬프트에 반영해 대본을 생성합니다.

- 친근한 설명 톤을 유지하되, 분석 깊이와 전문성 확보
- 심층 기사에서 배경/쟁점/영향/전망을 구조적으로 설명
- 어려운 용어가 있으면 섹션 마지막에 1~2개 짧게 풀이
- 전체 분량 목표: 약 3~5분 (문자수 기반 추정)
  - 추정 기준: 분당 약 500자
  - 목표 범위: 약 1,500~2,600자
  - 초기 생성이 짧으면 핵심 섹션을 자동 확장 재생성
- TTS 최적화 표기:
  - 쉼표(,)로 속도 조절
  - 대시(-)로 끊어 읽기
  - 줄임표(...)로 여운
  - 단락 전환 시 `\n\n` 사용
  - 숫자/영문은 한글 발음으로 풀기
  - 괄호 병기(한글+영문 동시 표기) 지양

---

## 15) 업데이트 이력

> 원칙: 기능 변경 시 이 섹션에 계속 누적 기록합니다.

### 2026-03-06

- Google Sheets 구조를 `Setting`/`News` 2탭으로 반영
  - `Setting!A2:B` 읽기
  - `News!A:E` append 저장
- 파이프라인에서 선별 직후 `append_news_to_sheet()` 호출 추가
- 오디오 파일명 규칙 변경
  - `{생성일자yymmdd}_{기사제목}.mp3`
- 오디오 저장 경로 확장
  - 로컬(`AUDIO_OUTPUT_DIR`) + Google Drive 업로드
- 스크립트 프롬프트 강화
  - 전문성 강화, 용어 설명 추가, TTS 친화적 표기 규칙 반영
- 스크립트 길이 강화
  - 목표 분량(3~5분) 가이드 추가
  - 섹션별 목표 길이 지시 + 길이 부족 시 자동 확장 로직 추가

