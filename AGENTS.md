# NVMeVirt Practice 2 Agent Guide

이 저장소에서는 시작할 때 긴 조사 문서를 전부 다시 읽지 않는다.
새 세션은 이 파일만 먼저 읽으면 충분하며, 추가로 읽을 문서는 이 파일이 결정한다.

## 시작 절차

1. 이 파일을 읽는다.
2. 이 파일의 지시에 따라 `docs/CODEX_BOOTSTRAP.md`를 읽는다.
3. `git status --short`와 `git diff --stat`만 먼저 확인한다.
4. 이전 작업을 이어가는 경우 `docs/CURRENT_TASK.md`를 읽는다.
5. 나머지 문서는 현재 작업에 직접 필요할 때만 읽는다.

## 기본 원칙

- 처음부터 `Note.md`, 긴 지침 문서, PDF, 로그 전체를 다시 훑지 않는다.
- 구현을 이어가는 목적이면 현재 흐름, 막힌 점, 다음 우선순위만 먼저 파악하고 진행한다.
- 상세 근거가 필요할 때만 관련 문서를 추가로 읽는다.
- 과제 범위를 임의로 넓히지 않는다.
- 현재 worktree의 사용자 변경은 보존한다.

## 파일 안내

- `docs/CODEX_BOOTSTRAP.md`
  - 새 세션이 가장 먼저 읽어야 하는 짧은 시작 요약이다.
  - 현재 브랜치 맥락, 구현 상태, 다음 우선순위, 주의사항만 담는다.
- `docs/CURRENT_TASK.md`
  - 바로 이어서 할 작업을 적는 작업 인계 메모다.
  - 현재 구현 위치, 다음 액션, 검증 상태, blocker를 짧게 적는다.
- `docs/PRACTICE2_CODEX_INSTRUCTIONS.md`
  - 전체 조사 절차와 상세 작업 원칙을 담은 장문 지침이다.
  - 기본 시작 단계에서는 읽지 않고, 상세 근거가 필요할 때만 참고한다.
- `docs/PRACTICE2_IMPLEMENTATION_LOG.md`
  - 실습2 코드 변경 이력을 날짜순으로 적는 구현 로그다.
  - 왜 이런 구조가 들어갔는지 추적할 때 참고한다.
- `docs/PRACTICE2_LOG.md`
  - 조사, 환경 확인, 설계 메모가 섞인 진행 기록이다.
  - 오래된 판단과 최신 판단이 함께 있으므로 필요할 때만 읽는다.
- `docs/PRACTICE2_AGENTS`
  - 과제 PDF 대체 텍스트다.
  - 공식 요구사항 문구를 다시 확인해야 할 때 사용한다.
- `Note.md`
  - 실습1 전체 기록과 환경 메모다.
  - 실습1 구현 근거, 실험 습관, 과거 시행착오가 필요할 때만 읽는다.
- `codestudy/studynote.md`
  - 학습용 설명 노트다.
  - 구현보다 개념 설명이 필요할 때 참고한다.
- `docs/Analysis_on_Heterogeneous_SSD_Configuration_with_Quadruple_Level.pdf`
  - 배경 논문이다.
  - 과제 요구사항보다 우선하지 않는다.
- `docs/hotstorage20_paper_yoo.pdf`
  - 배경 논문이다.
  - 과제 요구사항보다 우선하지 않는다.

## 문서 갱신 규칙

- 세션 시작 비용을 늘리지 않기 위해 긴 문서보다 `docs/CURRENT_TASK.md`를 우선 갱신한다.
- 새 세션이 바로 알아야 하는 내용이 바뀌면 `docs/CODEX_BOOTSTRAP.md`를 함께 갱신한다.
- 상세 변경 이력은 `docs/PRACTICE2_IMPLEMENTATION_LOG.md`에 남긴다.
