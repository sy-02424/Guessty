"""GUESSTY 문제 파일 자동 검사.
사용: python .claude/skills/guessty-problem/check.py data/problems/{회사id}.json
통과하면 종료 코드 0, 실패 항목이 있으면 목록을 출력하고 1.
"""
import json
import re
import sys

STEP_IDS = ["target", "base", "connect", "back", "stop"]
LONG_RED_STEPS = {"base", "connect"}
SPEAKERS = {"과장", "부장", "지원자"}
GRADES = {"green", "yellow", "red"}

errors = []


def err(where, msg):
    errors.append(f"[{where}] {msg}")


def check_choices(where, choices):
    if len(choices) != 3:
        err(where, f"선택지가 3개가 아님 ({len(choices)}개)")
    grades = [c.get("grade") for c in choices]
    if set(grades) != GRADES or len(grades) != 3:
        err(where, f"green·yellow·red 하나씩이 아님 {grades}")
    for c in choices:
        if not str(c.get("text", "")).strip():
            err(where, "빈 선택지 text")
        if not str(c.get("review", "")).strip():
            err(where, f"{c.get('grade')} review 빈칸")


def check_interview(iv):
    r = f"{iv.get('round')}차"

    # 실제 값·출처·범위
    actual = iv.get("actual", {})
    value = actual.get("value")
    src = str(actual.get("source", ""))
    year = actual.get("year")
    if not isinstance(value, (int, float)) or value <= 0:
        err(r, "actual.value가 양수 숫자가 아님")
    if not src.strip() or "샘플" in src or "출처 필요" in src:
        err(r, f"출처 없음 또는 임시 표기: '{src}'")
    if not isinstance(year, int) or year < 2000:
        err(r, f"기준연도 이상: {year}")
    rng = iv.get("range", {})
    if isinstance(value, (int, float)) and not (rng.get("min", 0) <= value <= rng.get("max", 0)):
        err(r, f"actual {value}이 range {rng.get('min')}~{rng.get('max')} 밖")

    # 공식
    formula = iv.get("formula", [])
    if not formula:
        err(r, "formula 비어 있음")
    elif formula[0].get("op") != "×":
        err(r, "formula 첫 요소 op가 × 아님")
    for f in formula:
        if f.get("op") not in ("×", "÷"):
            err(r, f"formula {f.get('id')} op 이상: {f.get('op')}")

    guide = iv.get("guide", {})

    # 공식 만들기
    steps = guide.get("formulaSteps", [])
    ids = [s.get("id") for s in steps]
    if ids != STEP_IDS:
        err(r, f"formulaSteps 순서가 {STEP_IDS} 아님: {ids}")
    for s in steps:
        w = f"{r} {s.get('id')}"
        check_choices(w, s.get("choices", []))
        for c in s.get("choices", []):
            g = c.get("grade")
            if g == "yellow":
                m = c.get("multiplier")
                ok = isinstance(m, (int, float)) and (1.5 <= m <= 3 or 0.33 <= m <= 0.67)
                if not ok:
                    err(w, f"yellow multiplier 범위 밖: {m} (1.5~3 또는 0.33~0.67)")
            if g == "red":
                lines = c.get("redReaction")
                if not isinstance(lines, list) or not lines:
                    err(w, "red redReaction이 대사 목록이 아님")
                    continue
                n = len(lines)
                if s.get("id") in LONG_RED_STEPS and not 2 <= n <= 4:
                    err(w, f"red 대사 {n}줄 (2~4줄이어야 함)")
                if s.get("id") not in LONG_RED_STEPS and n != 1:
                    err(w, f"red 대사 {n}줄 (1줄이어야 함)")
                for line in lines:
                    if line.get("speaker") not in SPEAKERS:
                        err(w, f"speaker 이상: {line.get('speaker')}")
                    if not str(line.get("text", "")).strip():
                        err(w, "빈 red 대사")
            elif not str(c.get("next", "")).strip():
                err(w, f"{g} next 빈칸")

    # 가정하기
    assumptions = guide.get("assumptions", [])
    a_ids = [a.get("factorId") for a in assumptions]
    f_ids = [f.get("id") for f in formula]
    if a_ids != f_ids:
        err(r, f"assumptions 순서가 formula와 다름: {a_ids} vs {f_ids}")
    green_vals = {}
    for a in assumptions:
        w = f"{r} 가정 {a.get('factorId')}"
        check_choices(w, a.get("choices", []))
        for c in a.get("choices", []):
            v = c.get("value")
            if not isinstance(v, (int, float)) or v <= 0:
                err(w, f"{c.get('grade')} value가 양수 숫자가 아님: {v}")
            for field in ("text", "next"):
                if re.search(r"\d", str(c.get(field, ""))):
                    err(w, f"{c.get('grade')} {field}에 숫자 있음: '{c.get(field)}'")
            if c.get("grade") == "green":
                green_vals[a.get("factorId")] = v

    # 모범 공식 3배
    if formula and all(isinstance(green_vals.get(f["id"]), (int, float)) for f in formula):
        result = 1.0
        for f in formula:
            v = green_vals[f["id"]]
            result = result * v if f["op"] == "×" else result / v
        if isinstance(value, (int, float)) and value > 0 and result > 0:
            ratio = max(result, value) / min(result, value)
            mark = "통과" if ratio <= 3 else "실패"
            print(f"  {r} green 계산값 {result:,.2f} / 실제 {value:,} → {ratio:.2f}배 {mark}")
            if ratio > 3:
                err(r, f"green 계산값이 실제 값 대비 {ratio:.2f}배 (3배 이내여야 함)")

    # 디테일
    detail = guide.get("detail", {})
    check_choices(f"{r} 디테일", detail.get("choices", []))
    for c in detail.get("choices", []):
        if not str(c.get("closing", "")).strip():
            err(f"{r} 디테일", f"{c.get('grade')} closing 빈칸")

    if not str(iv.get("review", "")).strip():
        err(r, "복기 review 빈칸")


def main():
    if len(sys.argv) != 2:
        print("사용: python check.py data/problems/{회사id}.json")
        sys.exit(2)
    path = sys.argv[1]
    try:
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError) as e:
        print(f"파일을 읽을 수 없음: {e}")
        sys.exit(1)

    if data.get("sample") is not False:
        err("파일", '"sample": false 아님')
    rounds = [iv.get("round") for iv in data.get("interviews", [])]
    if sorted(rounds) != [1, 2]:
        err("파일", f"interviews에 1차·2차가 하나씩 없음: {rounds}")

    for iv in data.get("interviews", []):
        check_interview(iv)

    if errors:
        print(f"실패 {len(errors)}건")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    print("전체 통과")


if __name__ == "__main__":
    main()
