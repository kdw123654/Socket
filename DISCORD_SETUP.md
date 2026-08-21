# Discord Activity 설정

1. Discord Developer Portal에서 새 Application을 만듭니다.
2. **Installation**에서 User Install과 Guild Install을 활성화합니다.
3. **Activities**를 활성화하고 지원 플랫폼을 선택합니다.
4. **OAuth2 > Redirects**에 `https://127.0.0.1`을 추가합니다.
5. `.env.example`을 `.env`로 복사하고 Application ID와 Client Secret을 입력합니다. Client Secret은 절대로 커밋하거나 공유하지 마세요.
6. `npm install`, `npm run build`, `npm start`를 실행합니다.
7. HTTPS로 배포한 주소를 **Activities > URL Mappings**의 `/` 대상에 등록합니다.
8. Discord의 개발자 모드를 켜고 음성 채널의 Activity 실행 메뉴에서 Prain을 엽니다.

## 봇 설치와 실행

1. Developer Portal의 **Bot** 메뉴에서 Bot을 생성하고 토큰을 발급합니다.
2. 토큰을 `.env`의 `DISCORD_BOT_TOKEN`에 입력합니다. 토큰은 절대로 공유하거나 커밋하지 마세요.
3. 배포된 Prain 주소를 `PRAIN_APP_URL`에 입력합니다.
4. `npm run bot`을 실행하면 `/prain`, `/프로젝트요약` 명령어가 등록됩니다.
5. 웹의 **Discord로 계속하기** 버튼을 누르면 공식 설치 창이 열리고, 사용자가 원하는 서버를 선택할 수 있습니다.

일반 파일 미리보기에서는 `index.html`을 직접 열어도 모든 화면 전환이 작동합니다. 실제 봇 설치 버튼을 시험하려면 `config.js`의 `discordClientId`에도 Application ID를 입력하세요.

로컬 개발 중에는 Vite와 API 서버를 각각 실행하고 Cloudflare Tunnel 같은 HTTPS 터널 주소를 URL Mapping에 등록해야 합니다.
