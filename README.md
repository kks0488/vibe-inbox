# 📧 Gmail Organizer

**AI 기반 Gmail 정리 도구** - Google Gemini AI를 사용하여 이메일을 자동으로 분류하고 정리합니다.

## ✨ 주요 기능

- 🤖 **AI 이메일 분류**: Google Gemini AI가 이메일 내용을 분석하여 자동 분류
- 🏷️ **자동 레이블 지정**: 분류 결과에 따라 Gmail 레이블 자동 적용
- 📦 **자동 보관처리**: 프로모션, 뉴스레터 등 불필요한 이메일 자동 보관
- 🚫 **스팸 감지**: 스팸으로 의심되는 이메일 자동 분류
- 📊 **통계 및 요약**: 이메일 분류 결과 상세 통계 제공

## 📂 분류 카테고리

| 카테고리 | 설명 | 기본 액션 |
|---------|------|----------|
| 📌 중요 | 중요한 업무/개인 이메일 | 유지 |
| 📧 일반 | 일반적인 커뮤니케이션 | 유지 |
| 📰 뉴스레터/구독 | 뉴스레터, 구독 서비스 | 보관 |
| 🛒 프로모션/광고 | 마케팅, 광고성 이메일 | 보관 |
| 👥 소셜 | SNS 알림 | 보관 |
| 🚫 스팸 | 스팸/피싱 의심 | 스팸함 |
| 🗑️ 구독취소 권장 | 불필요한 구독 | 권장 표시 |

---

## 🚀 설치 방법

### 1. 필수 요구사항

- Python 3.9 이상
- Google Cloud 계정
- Gemini API 키

### 2. 의존성 설치

```bash
cd gmail-organizer
pip install -r requirements.txt
```

### 3. Google Cloud 설정 (Gmail API)

Gmail API를 사용하려면 OAuth 2.0 인증이 필요합니다.

#### Step 1: Google Cloud 프로젝트 생성

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택

#### Step 2: Gmail API 활성화

1. "API 및 서비스" → "라이브러리" 이동
2. "Gmail API" 검색
3. "사용 설정" 클릭

#### Step 3: OAuth 동의 화면 설정

1. "API 및 서비스" → "OAuth 동의 화면"
2. "외부" 선택 (테스트용)
3. 앱 이름, 이메일 입력
4. 범위 추가:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.modify`
   - `https://www.googleapis.com/auth/gmail.labels`
5. 테스트 사용자에 본인 이메일 추가

#### Step 4: OAuth 2.0 클라이언트 ID 생성

1. "API 및 서비스" → "사용자 인증 정보"
2. "사용자 인증 정보 만들기" → "OAuth 클라이언트 ID"
3. 애플리케이션 유형: "데스크톱 앱"
4. 이름 입력 후 "만들기"
5. **JSON 다운로드** 클릭
6. 다운로드한 파일을 `credentials.json`으로 이름 변경
7. 프로젝트 폴더에 `credentials.json` 파일 배치

### 4. Gemini API 키 설정

1. [Google AI Studio](https://aistudio.google.com/app/apikey)에서 API 키 발급
2. `.env` 파일 생성:

```bash
# .env 파일 생성
cp env_example.txt .env
```

3. `.env` 파일 편집:

```
GEMINI_API_KEY=your_api_key_here
GMAIL_CREDENTIALS_PATH=credentials.json
```

---

## 📖 사용 방법

### 대화형 메뉴 (권장)

```bash
python main.py
```

### CLI 명령어

```bash
# 상태 확인
python main.py status

# Gmail 인증
python main.py auth

# 이메일 분석 (분류만, 변경 없음)
python main.py analyze -n 50

# 이메일 정리 (분류 + 레이블 적용)
python main.py organize -n 30

# 특정 쿼리로 분석
python main.py analyze -q "is:unread"

# 자동 정리 (확인 없이)
python main.py organize -n 50 -y

# 로그아웃
python main.py logout
```

### 예제: 첫 실행

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 프로그램 실행
python main.py

# 3. 메뉴에서 "4. Gmail 인증" 선택
# 4. 브라우저에서 Google 계정 로그인
# 5. "1. 현재 상태 확인"으로 연결 확인
# 6. "2. 이메일 분석"으로 테스트
# 7. "3. 이메일 정리"로 실제 정리 시작
```

---

## 🔧 설정 커스터마이징

`config.py` 파일에서 다양한 설정을 변경할 수 있습니다:

```python
# AI 모델 변경
GEMINI_MODEL = "gemini-1.5-flash"  # 빠른 모델
# GEMINI_MODEL = "gemini-1.5-pro"  # 더 정확한 모델

# 배치 크기 조정
DEFAULT_BATCH_SIZE = 50

# 이메일 내용 최대 길이
MAX_EMAIL_CONTENT_LENGTH = 2000

# 카테고리별 액션 수정
EMAIL_CATEGORIES = {
    "SPAM": {
        "action": "spam"  # "spam", "archive", "keep" 중 선택
    }
}
```

---

## ⚠️ 주의사항

### 보안

- **절대로 비밀번호를 코드에 직접 입력하지 마세요**
- `credentials.json`과 `token.json`은 `.gitignore`에 추가하세요
- API 키는 환경변수로 관리하세요

### API 사용량

- Gemini API는 무료 할당량이 있습니다 (분당 요청 수 제한)
- 많은 이메일을 한 번에 처리하면 API 한도에 도달할 수 있습니다
- 배치 크기를 조절하여 사용량을 관리하세요

### Gmail API

- 스팸으로 분류된 이메일은 확신도가 높을 때만 이동됩니다
- 레이블은 "AI분류/" 접두사로 생성됩니다
- 삭제 기능은 비활성화되어 있습니다 (안전을 위해)

---

## 📁 프로젝트 구조

```
gmail-organizer/
├── main.py              # 메인 실행 파일
├── config.py            # 설정 파일
├── auth.py              # Gmail OAuth 인증
├── gmail_client.py      # Gmail API 클라이언트
├── ai_classifier.py     # Gemini AI 분류기
├── requirements.txt     # 의존성 목록
├── README.md            # 이 파일
├── env_example.txt      # 환경변수 예시
├── credentials.json     # OAuth 자격 증명 (직접 추가)
└── token.json           # 인증 토큰 (자동 생성)
```

---

## 🖥️ Ubuntu 서버 상시 실행 설정

### 1. 프로젝트 파일 전송

```bash
# 로컬에서 Ubuntu 서버로 파일 전송
scp -r /path/to/gmail-organizer username@your-server:/home/username/
```

### 2. Ubuntu에서 설치 스크립트 실행

```bash
# SSH 접속
ssh username@your-server

# 설치 스크립트 실행
cd ~/gmail-organizer
chmod +x install_ubuntu.sh
./install_ubuntu.sh
```

### 3. 인증 설정 (중요!)

⚠️ **OAuth 인증은 브라우저가 필요합니다.** 두 가지 방법이 있습니다:

**방법 A: 로컬에서 인증 후 token.json 복사 (권장)**
```bash
# 로컬 PC에서 인증 완료 후
scp token.json username@your-server:/home/username/gmail-organizer/
scp credentials.json username@your-server:/home/username/gmail-organizer/
scp .env username@your-server:/home/username/gmail-organizer/
```

**방법 B: SSH 포트 포워딩 사용**
```bash
# 로컬에서 SSH 접속 시 포트 포워딩
ssh -L 8080:localhost:8080 username@your-server

# 서버에서 인증 실행
cd ~/gmail-organizer
source venv/bin/activate
python main.py auth
# 브라우저에서 표시된 URL 접속
```

### 4. 서비스 시작

```bash
# 서비스 시작
sudo systemctl start gmail-organizer

# 부팅 시 자동 시작 설정
sudo systemctl enable gmail-organizer

# 상태 확인
sudo systemctl status gmail-organizer
```

### 5. 로그 모니터링

```bash
# 실시간 로그 확인
tail -f ~/gmail-organizer/logs/scheduler.log

# 서비스 로그 확인
journalctl -u gmail-organizer -f
```

### 6. 스케줄러 옵션

```bash
# 직접 실행 (테스트용)
cd ~/gmail-organizer
source venv/bin/activate

# 기본 실행 (30분 간격, 자동 정리)
python scheduler.py

# 커스텀 옵션
python scheduler.py --interval 60 --batch-size 100  # 1시간 간격, 100개씩
python scheduler.py --analyze-only  # 분석만 (정리 안함)
```

---

## 🐛 문제 해결

### "credentials.json 파일이 없습니다"

- Google Cloud Console에서 OAuth 클라이언트 ID를 생성하고 JSON 파일을 다운로드하세요
- 파일 이름이 정확히 `credentials.json`인지 확인하세요

### "Gemini API 키가 필요합니다"

- `.env` 파일에 `GEMINI_API_KEY`가 설정되어 있는지 확인하세요
- API 키가 유효한지 확인하세요

### "토큰 만료됨"

- `python main.py auth` 명령으로 재인증하세요
- 또는 `token.json` 파일을 삭제하고 다시 인증하세요

### "API 한도 초과"

- 잠시 기다린 후 다시 시도하세요
- `config.py`에서 `DEFAULT_BATCH_SIZE`를 줄이세요

---

## 📄 라이선스

MIT License

---

## 🤝 기여

버그 리포트, 기능 제안, PR을 환영합니다!

