#  Backend - 프로젝트 전과정 진행 현황 및 아키텍처 가이드 (Status)

> 본 문서는 백엔드의 **현재까지 구현된 완료 항목, 기술적 의사결정 이유(Learning Point), 그리고 앞으로 구현해야 할 전체 개발 전과정(Roadmap)**을 통합 정리한 상태 보고서입니다.

---

## 1. 프로젝트 전과정 마일스톤 및 진행 현황 (Full Roadmap)

| 분류 | 개발 단계 및 세부 항목 | 상태 | 설명 |
| :--- | :--- | :---: | :--- |
| **Phase 1** | 프로젝트 초기 구조 설계 & Git 관리 | ✅ 완료 | 계층형 아키텍처(Layered) 및 `.gitignore` 설정 완료 |
| **Phase 1** | 비동기 DB 엔진 & 라이프사이클 세팅 | ✅ 완료 | `SQLAlchemy (Async)` 세션 팩토리 및 테이블 자동 생성(`lifespan`) |
| **Phase 2** | 보안 계층: 외부 SaaS 토큰 암호화 금고 | ✅ 완료 | `Fernet (AES-256)` 양방향 암호화 유틸 구현 (`security.py`) |
| **Phase 2** | 보안 계층: 유저 비밀번호 단방향 해싱 | ✅ 완료 | `bcrypt` 기반 단방향 해싱 및 검증 유틸 구현 |
| **Phase 2** | 보안 계층: 세션 토큰 발급 및 DI 미들웨어 | ✅ 완료 | `PyJWT` 기반 무상태 JWT 발급 & `get_current_user` 미들웨어 |
| **Phase 3** | 핵심 API: 자체 회원가입 및 로그인 | ✅ 완료 | `POST /api/v1/auth/signup`, `POST /api/v1/auth/login` |
| **Phase 3** | 핵심 API: 대시보드 멀티 패널 레이아웃 | ✅ 완료 | `GET /api/v1/workspace/layout`, `PUT /api/v1/workspace/layout` |
| **Phase 4** | 외부 툴 연동: OAuth 2.0 인증 플로우 | ⏳ 대기 | GitHub, Discord, Figma, Notion 인가 코드 및 콜백 처리 |
| **Phase 4** | 외부 툴 연동: 토큰 Vault 영속화 | ⏳ 대기 | 발급받은 외부 토큰을 Fernet으로 암호화하여 `UserIntegration` 저장 |
| **Phase 5** | API 프록시 서비스: 외부 데이터 동기화 | ⏳ 대기 | `httpx` 및 공식 SDK를 이용해 이슈, PR, 파일 목록 대리 조회 |
| **Phase 6** | AI 모듈: 회의록 자동 요약 및 챗봇 | ⏳ 대기 | OpenAI LLM 파이프라인 연동 및 Action Item 추출 기능 |
| **Phase 7** | 배포 및 최종 통합 테스트 | ⏳ 대기 | Docker 컨테이너화, 클라우드 서버 배포 및 프론트 연동 테스트 |

---

## 2. 현재까지 완료된 핵심 구현 및 학습 포인트 (Completed & Learning Points)

### ① 보안 계층: 단방향 해싱과 양방향 암호화의 분리 (`app/core/security.py`)
* **비밀번호 (`bcrypt` - 단방향 해시):** 데이터베이스가 유출되어도 원래 비밀번호를 알아낼 수 없도록 `gensalt()`를 섞어 안전하게 단방향 보호합니다.
* **외부 토큰 금고 (`Fernet / AES-256` - 양방향 암호화):** 백엔드가 유저를 대신해 외부 API를 호출해야 하므로, DB 저장 시 암호화(`encrypt_token`)하고 필요할 때만 복호화(`decrypt_token`)하여 사용합니다.
* **Prain 세션 (`PyJWT`):** 유저 ID(`sub`)와 만료 시간(`exp`)을 서버 비밀키로 전자서명하여 무상태(Stateless) 기반의 인증 상태를 유지합니다.

### ② 인증 미들웨어: FastAPI 의존성 주입(DI) (`app/core/deps.py`)
* **`get_current_user`:** 보호된 엔드포인트에 주입되어 요청 헤더의 `Authorization: Bearer <토큰>`을 자동 검증하고, 유효한 경우 DB에서 유저 객체를 꺼내 컨트롤러에 전달합니다. Swagger UI(`/docs`)의 자물쇠(`Authorize`)와 연동됩니다.

### ③ 대시보드 레이아웃: 유연한 JSON 스키마 및 Zero-Config
* **`pane_configs` (JSON 컬럼):** 사용자마다 2분할, 3분할, Grid 등 패널 구성과 앱 종류가 다르므로 RDBMS 내에 유연한 JSON 타입으로 저장합니다.
* **Zero-Config 자동 생성:** 신규 가입 유저가 처음 레이아웃을 조회할 때 에러 대신 **기본 2분할(좌: Discord, 우: GitHub)** 설정을 DB에 즉시 자동 생성(Auto-seeding)합니다.

---

## 3. 앞으로 구현해야 할 상세 전과정 (Upcoming Process)

### 4: 외부 SaaS 연동 및 토큰 Vault 구축 (`api/v1/integrations.py`)
* **OAuth 2.0 로그인/연동 라우터:**
  * 사용자가 "GitHub 연동하기"를 누르면 각 플랫폼 인증 페이지로 리다이렉트하는 `GET /auth/github` 구현.
  * 플랫폼에서 돌아오는 인가 코드(Code)를 받아 Access Token으로 교환하는 `GET /auth/github/callback` 구현.
* **토큰 암호화 저장:**
  * 교환된 토큰을 `security.py`의 `encrypt_token()`으로 감싸 `UserIntegration` 테이블에 영속화.

### 5: 외부 API 프록시 서비스 계층 (`services/`)
* **비동기 클라이언트 (`httpx` / `PyGithub` / `notion-client`):**
  * 암호화된 토큰을 복호화하여 GitHub(이슈, PR, 커밋), Figma(파일/컴포넌트 데이터), Notion(페이지 블록) 등의 API를 병렬로 호출(`async/await`).
  * 프론트엔드가 여러 툴의 데이터를 지연 없이 한 대시보드에서 볼 수 있도록 가공하여 전달.

### 6: AI 회의록 요약 및 챗봇 모듈 (`services/ai_service.py`)
* **OpenAI LLM 연동:**
  * 사용자가 작성한 회의록 메모나 디스코드 채팅 로그를 입력받아 핵심 요약본 및 **Action Item(할 일 목록)**을 자동으로 추출해 주는 API 구현 (`POST /api/v1/ai/summarize`).

### 7: 프로덕션 배포 및 최종 통합
* **Docker화:** `Dockerfile` 및 `docker-compose.yml`을 작성하여 백엔드 서버와 DB(PostgreSQL) 환경을 컨테이너로 패키징.
* **클라우드 배포:** AWS, GCP, 또는 PaaS 플랫폼에 서버를 배포하고 프론트엔드 팀원과 최종 End-to-End 연동 테스트 진행.

---

## 4. 현재까지 구축된 API 명세 요약

| Method | Endpoint | 설명 | 상태 / 인증 여부 |
| :--- | :--- | :--- | :---: |
| `POST` | `/api/v1/auth/signup` | 이메일/비밀번호 회원가입 | ✅ 완료 (공개) |
| `POST` | `/api/v1/auth/login` | 로그인 및 JWT 토큰 발급 | ✅ 완료 (공개) |
| `GET` | `/api/v1/workspace/layout` | 대시보드 화면 분할 레이아웃 조회 | ✅ 완료 (인증 필요) |
| `PUT` | `/api/v1/workspace/layout` | 대시보드 화면 분할 레이아웃 저장 | ✅ 완료 (인증 필요) |
| `GET` | `/api/v1/integrations/...` | GitHub/Discord OAuth 연동 | ⏳ 예정 |
| `GET` | `/api/v1/ai/summarize` | AI 회의록 자동 요약 | ⏳ 예정 |
| `GET` | `/health` | 서버 헬스체크 | ✅ 완료 (공개) |