prain-backend/
├── app/
│   ├── api/                  # API 엔드포인트 라우터
│   │   ├── v1/
│   │   │   ├── auth.py       # 이메일/OAuth 로그인
│   │   │   ├── integrations.py # Figma, Notion, GitHub 연동 API
│   │   │   ├── workspace.py  # 화면 분할 레이아웃 저장/조회
│   │   │   ├── ai.py         # 회의록 요약/챗봇 API
│   │   │   └── notes.py      # 회의록 CRUD
│   │   └── router.py         # v1 라우터 통합
│   ├── core/                 # 핵심 설정 (보안, 환경설정, DB 세션)
│   │   ├── config.py         # Settings (.env 로드)
│   │   ├── database.py       # Async SQLAlchemy 세션 생성
│   │   └── security.py       # JWT 생성, 패스워드 해싱, AES 토큰 암호화
│   ├── models/               # SQLAlchemy DB 테이블 모델 정의
│   │   ├── user.py
│   │   ├── integration.py
│   │   ├── workspace.py
│   │   └── note.py
│   ├── schemas/              # Pydantic 요청/응답 DTO 스키마
│   │   ├── user.py
│   │   ├── workspace.py
│   │   └── ai.py
│   ├── services/             # 비즈니스 로직 및 외부 툴 SDK 연동
│   │   ├── github_service.py
│   │   ├── figma_service.py
│   │   └── ai_service.py
│   └── main.py               # FastAPI 인스턴스 생성 및 미들웨어 설정
├── alembic/                  # DB 마이그레이션 폴더
├── .env                      # API Secret, DB Connection String
├── requirements.txt
└── README.md