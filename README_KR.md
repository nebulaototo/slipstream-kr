# Slipstream KR — 가민 데이터를 Claude에 연결하기 (한국어판)

[yhecht/slipstream](https://github.com/yhecht/slipstream)을 바탕으로, 한국 사용자가 쓰기 편하게 손본 버전입니다.
가민 시계의 기록을 **내 계정에만** 저장해 두고, Claude(웹·앱)에서 "이번 주 얼마나 뛰었어?"처럼 물어볼 수 있게 해 줍니다. 전부 무료입니다.

## 원본과 다른 점

| | 원본 | 이 버전 |
|---|---|---|
| 활동 데이터 | 거리·시간·평균 심박 요약 | + **랩별 페이스·심박·케이던스·보폭**, 심박존 체류 시간, 러닝 다이내믹스, 트레이닝 효과, VO2max |
| 수면·컨디션 | 없음 | **수면 점수·단계·취침/기상 시각, 안정 심박, HRV, 바디 배터리, 스트레스, 트레이닝 준비 상태** |
| 날짜 | UTC라 새벽 러닝이 전날로 밀림 | **한국 시간 기준** |
| 동기화 기간 | 30일 | **90일** |
| Windows(WSL) | 설치 안내가 macOS 기준 | WSL에서 막히던 부분 수정 (아래 "자주 막히는 곳" 참고) |

## 준비물

- **가민** 계정 (시계와 Garmin Connect 앱)
- **GitHub** 계정 (무료)
- **Cloudflare** 계정 (무료, 카드 불필요) — https://dash.cloudflare.com/sign-up
- **Claude** (무료 플랜도 됨)
- Windows라면 **WSL + Ubuntu**. 처음이면 PowerShell(관리자)에서 `wsl --install -d Ubuntu` 후 재부팅.

## 설치 (Ubuntu / WSL 기준, 10~15분)

### 1. 도구 설치 (한 번만)

```bash
sudo apt update
sudo apt install -y git curl openssl python3 python3-venv python3-pip gh
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
gh auth login        # 안내대로 GitHub 로그인 (브라우저 방식 선택)
```

### 2. 내 저장소 만들고 설치 스크립트 실행

```bash
cd ~
gh repo create slipstream --template <이-저장소-주소> --private --clone && cd slipstream && ./setup.sh
```

`<이-저장소-주소>`는 이 페이지 위쪽의 `사용자명/저장소명` (예: `nebulaototo/slipstream-kr`)입니다.
**반드시 `--private`** — 내 운동 기록이 여기에 저장됩니다.

스크립트가 순서대로 물어봅니다:

1. **Garmin 이메일/비밀번호** — 가민 서버에 로그인만 하고 비밀번호는 저장하지 않습니다. 2단계 인증 코드를 물으면 입력.
   `429` 가 뜨면 가민이 잠시 차단한 것 → 폰 핫스팟으로 바꾸거나 30분 뒤 `./setup.sh` 다시 실행.
2. **Cloudflare** — 계정이 없으면 `N` → 가입 페이지가 열림 → 가입 후 Enter. 이어서 브라우저에서 "Allow" 클릭.
3. 끝나면 **커넥터 주소** 가 출력됩니다. `https://slipstream-mcp.xxx.workers.dev/긴문자열/mcp` 형태.
   **이 주소는 비밀번호와 같습니다.** 캡처·공유 금지. (`cat .connector_url` 로 다시 볼 수 있음)

### 3. Claude에 연결

1. https://claude.ai/settings/connectors → **추가 → 사용자 지정 커넥터**
2. 이름 `Slipstream`, URL에 커넥터 주소 붙여넣기, 인증은 **로그인 없음** 그대로 → 추가 → 연결
3. 새 채팅에서 물어보기: *"Slipstream으로 이번 달 러닝 기록 보여줘"*

## 쓰는 법

- 데이터는 **6시간마다 자동** 갱신됩니다.
- 러닝 직후 바로 보고 싶으면: 가민 앱 동기화 → **GitHub 앱** → 내 `slipstream` 저장소 → Actions → *Refresh fitness data* → **워크플로 실행**. 1~2분 뒤 반영.
  (터미널이면 `cd ~/slipstream && gh workflow run refresh.yml`)
- 물어볼 수 있는 것 예시:
  - "지난 3달 월별 러닝 거리랑 평균 페이스"
  - "가장 최근 러닝의 랩별 페이스·심박·케이던스"
  - "이번 주 수면 점수랑 HRV, 안정 심박 추세"
  - "오늘 트레이닝 준비 상태 어때? 인터벌 해도 될까?"

## 자주 막히는 곳

| 증상 | 해결 |
|---|---|
| `Missing 'npm' - install with: brew install node` | brew는 macOS용. 위 1번의 nodesource 명령으로 설치 |
| `ensurepip is not available` / `python3-venv` | `sudo apt install -y python3-venv` 후 `rm -rf .venv && ./setup.sh` |
| `CLOUDFLARE_API_TOKEN environment variable` 에러 | 브라우저 로그인이 안 된 상태. `cd worker && npx wrangler login` 실행(브라우저에서 Allow) 후 `cd .. && ./setup.sh` |
| 마지막에 주소가 `YOUR-SUBDOMAIN` 으로 나옴 | Cloudflare 대시보드 → Workers 및 Pages 에 한 번 들어갔다가 `./setup.sh` 다시 실행 |
| Claude에서 도구가 안 보이거나 옛날 목록 | 설정 → 커넥터 → Slipstream **연결 해제 → 연결**, 그리고 **새 채팅** |
| 러닝은 보이는데 랩/수면이 "없다"고 함 | 첫 갱신이 아직 안 돈 것. GitHub 앱에서 워크플로 실행 후 5분 기다리기 |
| 가민 로그인 429 | 핫스팟으로 IP 바꾸거나 30분 뒤 재시도. 이미 로그인 성공했으면 다시 안 물어봄 |

## 보안 메모

- 가민 비밀번호는 어디에도 저장되지 않습니다. 로그인 후 받은 토큰만 내 GitHub 저장소의 Secret에 들어갑니다.
- 운동 기록은 **내 비공개 GitHub 저장소**, 서버는 **내 Cloudflare 계정**에 있습니다. 제3자 서버를 거치지 않습니다.
- 커넥터 주소가 새어나간 것 같으면: `rm .mcp_secret && ./setup.sh` → 새 주소가 생기고 옛 주소는 즉시 무효. Claude 커넥터에 새 주소로 다시 등록.
- 아예 그만두려면: 가민 비밀번호 변경(토큰 무효화) + Cloudflare 대시보드에서 Worker 삭제 + GitHub 저장소 삭제.

## 주의

Garmin은 개인 개발자용 공식 API를 제공하지 않아, 커뮤니티 라이브러리(`python-garminconnect`)로 Garmin Connect 앱과 같은 방식으로 로그인합니다. 가민이 로그인 방식을 바꾸면 한동안 동작이 멈출 수 있습니다. Anthropic·Garmin 공식 제품이 아닙니다.
