# GUESSTY — 게스티메이션 면접 도장깨기 게임

## 1. 개요
- 모바일 세로 픽셀 웹 게임. 신입이 회사를 돌며 면접에서 게스티메이션(페르미 추정) 문제를 푼다
- HTML / CSS / 바닐라 JS, 데이터는 data/ JSON, GitHub Pages 배포 (/guessty/)
- 로컬 실행은 VS Code Live Server (JSON을 fetch로 불러와서 파일 더블클릭으로는 열리지 않음)
- 규칙 원본은 이 파일. AGENTS.md는 이 파일을 가리킨다

## 2. 구조
```
guessty/
├── CLAUDE.md · AGENTS.md   # 작업 규칙
├── DESIGN.md · COPY.md     # 화면 규칙 · 문구 규칙
├── README.md               # 실행 방법, 출처·라이선스
├── .gitignore
├── index.html · css/ · js/
├── data/                   # companies.json, problems/{회사id}.json
├── docs/game-rules.md      # 게임 규칙
├── docs/data-schema.md     # 데이터 형식
├── .claude/skills/          # 문제 제작 스킬
├── tools/                  # 그림 변환 스크립트
├── assets/                 # 게임에 쓰는 그림
├── assets/raw/             # 그림 원본 (로컬 전용)
└── docs/mockups/           # 화면 시안 (로컬 전용)
```

## 3. 규칙
- 통계·실제 값·출처는 data/ JSON에 있는 것만 쓴다. 없으면 지어내지 말고 "출처 필요"라고 알린다.
- 회사·문제는 data/ JSON에서 불러오고, 형식은 docs/data-schema.md를 따른다. 형식을 바꿔야 하면 먼저 알린다.
- 웹 코드는 ./ 상대 경로만 쓴다(Pages 하위 경로 때문). 외부 라이브러리는 DESIGN.md의 폰트 2개 외에 쓰지 않는다. 그림 변환 스크립트(Python·Pillow)는 tools/에 둔다.
- 스타일 작업 전엔 DESIGN.md, 문구 작업 전엔 COPY.md, 게임 로직 작업 전엔 docs/game-rules.md를 읽는다.
- 화면 문구는 COPY.md와 data/ JSON에 있는 것만 쓴다. 없으면 지어내지 말고 [문구 필요]로 비워 둔다.
- 그림은 직접 만든 시안(docs/mockups, assets/raw)을 픽셀 변환해서만 쓰고, 외부 이미지는 가져오지 않는다.
- 문제·해설은 다른 문제집·블로그 문장을 옮기지 않고 새로 쓴다. 폰트·통계 등 외부 자료는 라이선스·출처를 README에 적는다.
- 데이터를 못 불러오면 빈 화면 대신 COPY.md의 실패 안내를 띄우고, localStorage는 try/catch로 감싼다.
- 문서끼리 내용이 다르면 임의로 고르지 말고 먼저 묻는다.
- 요청받은 범위만 수정한다. 파일 추가·구조 변경은 계획을 먼저 보여 주고, 범위 밖 아이디어는 끝에 한 줄로 제안만 한다.
- 커밋·푸시는 하지 않고 커밋 메시지(feat/fix/refactor/docs/chore: 내용)만 제안한다. 올라갈 파일에 키·개인정보·.gitignore 대상이 섞여 있으면 먼저 알린다.
- 작업이 끝나면 프롬프트.md에 남길 한 줄(도구 / 요청 / 결과 / 고친 점)을 제안한다.
- 규칙 문서(CLAUDE.md·AGENTS.md·DESIGN.md·COPY.md·docs/)는 내가 요청할 때만 고친다. 고쳐야 할 것 같으면 제안만 한다.

## 4. 현재 범위
-진행: PRESS START → 인트로(첫 방문만) → 맵(회사 3곳) → 가이드모드 면접(1차·2차) → 결과(합격·보류·탈락)
다음 단계: 실전모드, 튜토리얼
보류: 효과음, CITYPOP 테마
