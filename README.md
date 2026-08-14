#  Prain Backend (흩어진 협업을 하나로)

> Discord, GitHub, Figma, Notion 등 다양한 협업 도구를 한 화면에서 연동하고 통합 제어하는 **Prain**의 FastAPI 기반 비동기 백엔드 서버입니다.

---

## 기술 스택 (Tech Stack)

* **Framework:** Python 3.10+ / FastAPI
* **Server:** Uvicorn (ASGI)
* **Database & ORM:** PostgreSQL / SQLite, SQLAlchemy (Async), Alembic
* **Auth & Security:** JWT (python-jose), Cryptography (AES-256 Fernet 토큰 암호화), Passlib
* **Integrations:** PyGithub, notion-client, HTTPX (비동기 통신), OpenAI API

---

## 프로젝트 폴더 구조 (Project Architecture)

```text
prain-backend/
├── app/
│   ├── api/                      # API 라우팅 계층
│   │   ├── v1/
│   │   │   ├── auth.py           # 회원가입, 이메일 로그인, Discord/GitHub OAuth
│   │   │   ├── integrations.py   # Figma, Notion, GitHub 연동 및 데이터 프록시
│   │   │   ├── workspace.py      # 대시보드 화면 분할 레이아웃 저장/조회
│   │   │   ├── ai.py             # 회의록 자동 요약 및 AI 질의응답
│   │   │   └── notes.py          # 회의록 & 메모 CRUD
│   │   └── router.py             # v1 API 엔드포인트 통합 관리
│   │
│   ├── core/                     # 핵심 인프라 및 전역 설정
│   │   ├── config.py             # .env 환경 변수 관리 (Pydantic Settings)
│   │   ├── database.py           # 비동기 SQLAlchemy 세션/엔진 설정
│   │   └── security.py           # JWT 발급, 패스워드 해싱, OAuth 토큰 암호화 유틸
│   │
│   ├── models/                   # 데이터베이스 테이블 정의 (SQLAlchemy Base)
│   │   ├── user.py               # 유저 기본 정보 테이블
│   │   ├── integration.py        # 연동된 툴(Figma, Discord 등) 및 암호화 토큰
│   │   ├── workspace.py          # 사용자별 그리드/분할 패널 레이아웃 상태
│   │   └── note.py               # 회의록 데이터 모델
│   │
│   ├── schemas/                  # 데이터 검증 및 직렬화 DTO (Pydantic)
│   │   ├── user.py               # 회원가입/로그인 요청/응답 스키마
│   │   ├── workspace.py          # 패널 레이아웃 요청/응답 스키마
│   │   └── ai.py                 # AI 프롬프트 질의응답 스키마
│   │
│   ├── services/                 # 비즈니스 로직 및 외부 툴 SDK 호출
│   │   ├── github_service.py     # GitHub API (이슈, PR, 커밋 조회)
│   │   ├── figma_service.py      # Figma API (프로젝트/파일 데이터 연동)
│   │   └── ai_service.py         # OpenAI LLM 회의록 요약 로직
│   │
│   └── main.py                   # FastAPI 앱 인스턴스, CORS, 생명주기 관리
│
├── alembic/                      # DB 스키마 마이그레이션 이력 관리
├── .env                          # 환경 변수 (API Keys, DB URL, Secret Keys)
├── requirements.txt              # 파이썬 의존성 패키지 목록
└── README.md                     # 프로젝트 문서
