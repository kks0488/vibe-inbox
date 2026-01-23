FROM python:3.11-slim

WORKDIR /app

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY *.py ./

# 로그 디렉토리 생성
RUN mkdir -p logs

# 환경변수
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Seoul

# 헬스체크
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "from auth import check_auth_status; exit(0 if check_auth_status() else 1)" || exit 1

# 스케줄러 실행
CMD ["python", "scheduler.py", "-i", "30"]
