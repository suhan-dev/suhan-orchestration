# 변경 기록

## 1.1.3

### 추가
- 설치가 성공하면 끝에 저장소 스타 안내와 링크를 한 줄 보여 줍니다. `INSTALL-FOR-LLM.md`에도 설치를 맡은 LLM이 마지막에 한 번 전하도록 단계를 더했습니다. 일부 대상이 거부되거나 설치가 실패하면 나오지 않습니다.

## 1.1.2

### 고침
- **설치기:** `--migrate-legacy`로 옮긴 뒤 다시 `install`하면 남겨 둔 옛 폴더(`~/.claude/fable/`)와 옛 명령(`~/.local/bin/fable`) 때문에 또 거부되던 문제를 고쳤습니다. 이제 `CLAUDE.md`의 `fable/active.md` 줄이나 `orchestration-gate` 훅이 있는 작동 중인 옛 설치본만 충돌로 보고, 옛 폴더·옛 명령만 남아 있으면 "더는 쓰이지 않으니 필요 없으면 지워도 됩니다"라는 안내만 띄우고 설치합니다.

## 1.1.1

### 추가
- **규칙 문서(Claude Code·Codex):** 세 가지 규칙을 더했습니다.
  - 메인 모델의 한도가 바닥나면 한 단계 아래 모델(최신 Opus / 최신 Sol)로 바꿔 그대로 이어갑니다.
  - 보조 세션(사용자와 직접 대화하지 않는 세션)의 모델은 사용자가 정하고, 기본은 최신 Opus / 최신 Sol입니다. 메인급으로 올리는 것은 사용자만 합니다.
  - 세션 간 보고 주기는 기본 10시간에 1신입니다(반증, 체크포인트·사고, 사용자 결정이 필요한 일은 예외).

## 1.1.0

### 추가
- **프리셋:** 역할 3개(executor·deep-reasoner·runner)의 모델·강도 묶음을 이름으로 한 번에 적용합니다.
  - 내장 `default`(기본)·`saver`(절약)·`max`(최대). Claude Code 값과 Codex 값을 함께 담고, 지울 수 없습니다.
  - 모델 목록에 그 계열이 없으면 그 역할만 기본값으로 두고 알립니다. 모델이 그 강도를 지원하지 않으면 가장 가까운 아래 값을 씁니다.
  - 사용자 프리셋: `oche preset save <이름>`·`use`·`delete`. `~/.oche/config.json`의 `presets`에 저장합니다.
  - `oche preset`: 목록, 지금 설정과 일치하는 것에 ✔. `oche preset use <이름> [claude|codex]`.
  - TUI 홈에 "프리셋" 메뉴(적용, 지금 설정 저장). 현황판과 TUI 상단에 `프리셋: …` 표시.

## 1.0.0

### 처음 공개
- Claude Code와 Codex(CLI·ChatGPT 앱)용 설치기 `install.py`(plan·install·verify·uninstall, 대상 선택, 옛 설치본 옮기기, 명령 이름 바꾸기, PATH 추가).
- 메인 + 하청 세 역할(executor·deep-reasoner·runner) 구성, 역할별 모델·강도를 터미널에서 지정.
- PreToolUse 강제 게이트: 세 타입만 허용, 호출 때 model·effort 지정은 설정과 같을 때만, 재하청·Workflow 차단, 메인의 직접 코드 수정 턴당 2개.
- `oche` 명령과 키보드 TUI, on/off 스위치, selftest.
- 하청 모델 자동 최신화(Claude 별칭, Codex 모델 목록과 SessionStart sync), 모델 목록 표(catalog)와 새 계열 알림.
- 다리 하청(실험적), Windows 경로 규칙(흉내 시험).
