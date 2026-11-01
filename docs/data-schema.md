# 데이터 형식

## 1. 파일
- data/companies.json — 회사 목록
- data/problems/{회사id}.json — 회사별 면접 문제 (1차·2차)
- "sample": true 인 데이터는 흐름 확인용 가짜 값이다. 화면엔 띄우되 실제 통계처럼 쓰지 않는다.

## 2. companies.json
| 필드 | 형식 | 설명 |
| --- | --- | --- |
| id | 문자열 | 영문 소문자, 문제 파일 이름과 같음 (예: chicken) |
| name | 문자열 | 맵 이름표 (COPY.md의 회사 이름) |
| industry | 문자열 | 업종. 화면엔 안 띄움 |
| order | 숫자 | 맵에서 아래부터 순서 (1 = 취업센터 바로 위) |
| building | 문자열 | assets/buildings/ 그림 파일 이름 |
| outfit | 문자열 | 면접관 옷 (assets/interviewers/ 파일 이름의 옷 부분) |
| greeting | 문자열 | 면접 시작 때 면접관 첫 인사 |

## 3. problems/{회사id}.json
```
{ "companyId": "...", "sample": true|false, "interviews": [ 1차 문제, 2차 문제 ] }
```

### 문제 하나
| 필드 | 설명 |
| --- | --- |
| round | 1 또는 2 |
| question | 면접관 질문 |
| unit | 답 단위 (예: 개) |
| actual | 실제 값 { value, source, year } |
| range | 말이 되는 답 범위 { min, max } (실전 입력 안내용) |
| formula | 모범 공식. 요소 목록 [{ id, name, op }] — op는 "×" 또는 "÷", 첫 요소는 "×" |
| guide | 가이드모드 데이터 (아래) |
| review | 복기 화면 요약 한 줄 |

### guide
| 필드 | 설명 |
| --- | --- |
| formulaSteps | 공식 만들기 ①~⑤ 5단계, 순서 고정. 단계마다 { id, label, monologue, choices }. id: target / base / connect / back / stop. ⑥ 말하기는 데이터 없음 — 웹이 formula 요소 이름으로 자동 대사 생성 |
| assumptions | 가정하기. formula 요소 id마다 { factorId, monologue, choices } |
| detail | 디테일. { monologue, choices } |

### choices (선택지 3개, 공통)
| 필드 | 설명 |
| --- | --- |
| text | 선택지 문장 |
| grade | "green" / "yellow" / "red" — 플레이 중 화면에 표시하지 않음 |
| next | 고른 뒤 이어지는 주인공·면접관 대사 |
| review | 복기 화면 한 줄 |

단계별 추가 필드
- formulaSteps: yellow는 multiplier(최종 답에 곱할 오차 배수, 1.5~3배 — 커짐은 1보다 크게, 작아짐은 1보다 작게), red는 redReaction(자진 퇴장 직전 대사 목록 [{ speaker, text }])
  - speaker: "과장" / "부장" / "지원자"
  - base·connect(②·③) 빨강: 2~4줄 주고받기, 나머지 빨강: 1줄
- assumptions: 모든 선택지에 value(그 근거로 쓸 숫자). 최종 답은 green이 아니어도 고른 value로 계산
  - text엔 근거만 쓰고 숫자는 쓰지 않는다. 숫자는 value에만 넣고, 3단계 계산 독백에서 처음 공개
- detail: 모든 선택지에 closing(면접관 마지막 한마디). 판정에는 영향 없음

## 4. 계산
- 가이드 최종 답 = formula 순서대로 assumptions에서 고른 value를 × / ÷ 한 값 × formulaSteps에서 고른 yellow의 multiplier 전부
- 판정은 docs/game-rules.md 기준 (실제 값과의 배수)
