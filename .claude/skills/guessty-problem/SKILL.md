---
name: guessty-problem
description: GUESSTY 회사 하나의 1차·2차 게스티메이션 면접 문제를 data/problems/{회사id}.json으로 만든다. "/guessty-problem {회사id}" 뒤에 1차·2차 질문이 오면 사용.
---

# GUESSTY 문제 제작

## 입력
```
/guessty-problem {회사id}
1차: {질문}
2차: {질문}
```
- 하향식(전체에서 쪼개 내려감)·상향식(한 단위에서 쌓아 올림)은 질문에 어울리는 쪽으로 고른다

## 읽을 파일 — 이것만
- docs/data-schema.md, COPY.md, docs/game-rules.md
- data/problems/chicken.json (형식·완성 예시)
- 다른 파일·폴더는 열지 않는다

## 순서 (문제마다, 이 순서를 지킨다)

### 1. 실제 값 먼저
- 공식 통계에서 찾는다. 출처·기준연도 필수
- 숫자는 원문에 적힌 그대로. 반올림·추정 금지
- 기사 인용이면 구분해서 적는다
  - 원 통계 숫자: "{기관} {통계명} ({매체} {날짜} 인용)"
  - 기사가 계산한 숫자: "{매체} {날짜} · {기관} {통계명} 기반 계산"
- 못 찾으면 지어내지 말고 멈추고 물어본다

### 2. 범위 일치 확인 — 선택지 쓰기 전에
아래 한 줄을 먼저 쓰고, 셋이 같은 대상을 세는지 확인한다.
```
통계가 세는 것: ___ / 질문이 세는 것: ___ / 공식이 세는 것: ___
```
- 예: 공식은 먹는 닭(수입 포함), 통계는 국내 도축(수입 제외) → 불일치
- 불일치면 공식이 아니라 질문·실제 값 쪽을 맞춘다
- target 초록 선택지 = 통계가 세는 대상

### 3. 모범 공식 확인
- assumptions의 green value로 formula 순서대로 계산
- 실제 값 대비 3배 이내가 아니면 공식이나 green value를 고친다

### 4. 선택지·대사 작성
- 공식 만들기 5단계 순서 고정: target / base / connect / back / stop
- 단계마다 선택지 3개, green·yellow·red 하나씩
- yellow: multiplier 1.5~3 (작아짐은 0.33~0.67)
- red: redReaction 대사 목록 [{ speaker, text }]. base·connect는 2~4줄 주고받기, 나머지 1줄
- 가정하기: formula 요소마다 하나. text·next에 숫자 금지, 숫자는 value에만
  - 근거 문장만 읽어도 숫자 크기가 느껴지게
- 디테일: green 결과를 바꾸는 요소(조건과 함께), yellow 영향 없는 장식, red 엉뚱
- 세 선택지는 길이·톤 비슷하게. 빨강도 진지한 말투로 엉뚱하게
- COPY.md 말투. 회사 자체를 깎아내리지 않기. 문제집·블로그 문장 베끼지 않기

### 5. 자동 검사
```
python .claude/skills/guessty-problem/check.py data/problems/{회사id}.json
```
- 실패 항목은 스스로 고치고 다시 돌린다. 통과할 때까지

### 6. 보고 (짧게)
- 문제마다: 질문 / 실제 값·출처·연도 / 범위 일치 한 줄 / green 계산값과 배수
- check.py 결과: 통과 여부만
- 사람이 직접 확인할 것: 출처 링크, 톤

## 출력
- data/problems/{회사id}.json, "sample": false, interviews에 round 1·2
- 다른 회사 파일은 건드리지 않는다
