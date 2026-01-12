#!/bin/bash
#
# Gmail Organizer Ubuntu 설치 스크립트
# 사용법: ./install_ubuntu.sh
#

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║       Gmail Organizer - Ubuntu 설치 스크립트             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 현재 사용자
CURRENT_USER=$(whoami)
INSTALL_DIR="$HOME/gmail-organizer"
SERVICE_FILE="gmail-organizer.service"

echo -e "${YELLOW}[1/6] 시스템 패키지 업데이트...${NC}"
sudo apt update
sudo apt install -y python3 python3-pip python3-venv

echo -e "${YELLOW}[2/6] 프로젝트 디렉토리 설정...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}기존 디렉토리가 있습니다. 백업 후 진행합니다.${NC}"
    mv "$INSTALL_DIR" "${INSTALL_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
fi

# 현재 디렉토리의 파일들을 홈으로 복사
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "$SCRIPT_DIR" "$INSTALL_DIR"
cd "$INSTALL_DIR"

echo -e "${YELLOW}[3/6] Python 가상환경 설정...${NC}"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo -e "${YELLOW}[4/6] 로그 디렉토리 생성...${NC}"
mkdir -p logs

echo -e "${YELLOW}[5/6] systemd 서비스 파일 설정...${NC}"
# 서비스 파일에서 사용자명 치환
sed -i "s/YOUR_USERNAME/$CURRENT_USER/g" "$SERVICE_FILE"

# 서비스 파일 복사
sudo cp "$SERVICE_FILE" /etc/systemd/system/
sudo systemctl daemon-reload

echo -e "${YELLOW}[6/6] 환경 설정 확인...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${RED}⚠ .env 파일이 없습니다!${NC}"
    echo -e "${YELLOW}다음 내용으로 .env 파일을 생성해주세요:${NC}"
    echo ""
    echo "GEMINI_API_KEY=your_api_key_here"
    echo "GMAIL_CREDENTIALS_PATH=credentials.json"
    echo ""
fi

if [ ! -f "credentials.json" ]; then
    echo -e "${RED}⚠ credentials.json 파일이 없습니다!${NC}"
    echo -e "${YELLOW}Google Cloud Console에서 OAuth 자격증명을 다운로드해주세요.${NC}"
fi

if [ ! -f "token.json" ]; then
    echo -e "${RED}⚠ token.json 파일이 없습니다!${NC}"
    echo -e "${YELLOW}먼저 인증을 완료해야 합니다:${NC}"
    echo ""
    echo "  cd $INSTALL_DIR"
    echo "  source venv/bin/activate"
    echo "  python main.py auth"
    echo ""
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    설치 완료!                            ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}📁 설치 위치:${NC} $INSTALL_DIR"
echo ""
echo -e "${CYAN}🔐 인증 실행 (처음 한 번만):${NC}"
echo "   cd $INSTALL_DIR"
echo "   source venv/bin/activate"
echo "   python main.py auth"
echo ""
echo -e "${CYAN}🧪 테스트 실행:${NC}"
echo "   python main.py status"
echo "   python main.py analyze -n 10"
echo ""
echo -e "${CYAN}🚀 서비스 시작:${NC}"
echo "   sudo systemctl start gmail-organizer"
echo "   sudo systemctl enable gmail-organizer  # 부팅 시 자동 시작"
echo ""
echo -e "${CYAN}📊 서비스 상태 확인:${NC}"
echo "   sudo systemctl status gmail-organizer"
echo "   tail -f $INSTALL_DIR/logs/scheduler.log"
echo ""
echo -e "${CYAN}🛑 서비스 중지:${NC}"
echo "   sudo systemctl stop gmail-organizer"
echo ""

