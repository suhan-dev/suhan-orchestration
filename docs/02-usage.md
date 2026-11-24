# 02. 사용법

아래의 `oche`는 설치 때 고른 명령 이름입니다(`--command-name`으로 바꿨다면 그 이름으로 읽습니다).
Claude Code만, Codex만, 둘 다 설치한 경우 모두 같은 명령을 씁니다. 한쪽만 설치돼 있으면 `claude`/`codex` 대상 이름을 생략할 수 있습니다.

## 켜기·끄기

```bash
oche on              # 설치된 대상 전부 켜기
oche off             # 전부 끄기
oche on claude       # Claude Code만
oche off codex       # Codex만
```

| | 켜짐(on) | 꺼짐(off) |
|---|---|---|
| Claude Code | `~/.claude/oche/active.md`에 규칙을 복사 → `CLAUDE.md`가 불러옴 | `active.md`에 빈 파일 내용을 복사 |
| Codex | `AGENTS.md`(비어 있지 않은 `AGENTS.override.md`가 있으면 그쪽) 끝에 규칙 구역을 넣음 | 규칙 구역을 지움(구역 밖 내용은 그대로) |
| 게이트 | 작동 | 모든 호출 통과 |

전환은 **다음 세션부터**(ChatGPT 앱은 새 채팅부터) 적용됩니다.

## 화면(TUI)

```bash
oche                 # 터미널에서 인자 없이
oche executor        # 그 역할의 모델 선택 화면을 바로 열고, 고르면 끝냄
oche codex runner    # 대상까지 정해서
oche --plain         # 화면 대신 텍스트 현황판
```

| 키 | 동작 |
|---|---|
| ↑ ↓, k j | 이동 |
| Enter, → | 선택 |
| Esc, ←, q | 뒤로(홈에서 q는 종료) |
| 글자, Backspace | "직접 입력" 칸에서 입력 |
| Ctrl-C | 바로 종료(터미널은 복구됨) |

홈 메뉴: Claude Code ON/OFF, Codex ON/OFF, 대상별 역할 3개(지금 모델·강도), 프리셋, 모델 목록 갱신, 자가 시험, 나가기.
화면 맨 위에는 지금 설정과 일치하는 프리셋(`프리셋: 기본` 또는 `프리셋: 사용자 지정`)이 보입니다.
오른쪽(넓을 때)이나 아래(중간 폭)에는 사용자 → 메인 → 게이트 → 하청 3개 구성도가 그려지고, 상자마다 지금 모델·강도가 들어갑니다.
좁으면(60칸 미만이나 높이 부족) 그림 없이 목록만 보입니다.

역할을 고르면:

```text
 모델 선택 — Codex · executor
 지금: 최신 sol → gpt-6.2-sol · high

 ❯  1. ✔ 최신 sol       지금 gpt-6.2-sol · 같은 계열 새 버전은 자동 반영
    2.   최신 astra     지금 gpt-6.2-astra · 같은 계열 새 버전은 자동 반영
    3.   최신 terra     지금 gpt-6.1-terra · 같은 계열 새 버전은 자동 반영
    4.   최신 luna      지금 gpt-6-luna · 같은 계열 새 버전은 자동 반영
    5.   claude:opus    다리·실험적 — Claude Code CLI로 위임
    …
    9.   직접 입력      전체 모델 ID를 적습니다
 ↑↓ 이동 · Enter 선택 · Esc 뒤로
```

Enter → 강도 목록(그 모델이 지원하는 것만, ultra 없음) → Enter로 바로 적용하고 홈으로 돌아옵니다. 상태줄에 "적용됨 — 다음 세션부터".
ON/OFF 줄에서 Enter를 누르면 바로 토글합니다.

- 터미널이 아니면(파이프·리다이렉트·CI·LLM이 실행) 화면을 띄우지 않습니다.
- 상자 문자가 깨져 보이는 콘솔(일부 Windows 한국어 콘솔)에서는 `OCHE_ASCII=1 oche`로 ASCII 테두리를 씁니다. 출력 인코딩이 UTF-8이 아니면 자동으로 ASCII입니다.
- 색이 싫으면 `NO_COLOR=1`.
- 화면에서 하는 일은 아래 비대화형 명령과 같은 함수를 부릅니다.

## 현황판

```bash
oche --plain        # 또는 터미널이 아닐 때 oche
oche status         # + 부품 점검
```

```text
oche 1.1.0 — 하청 오케스트레이션 (명령 이름: oche)
프리셋: 기본

[Claude Code] ON   (~/.claude, Claude Code 2.1.321)
  역할           모델(설정 → 실제)         강도
  executor       opus → claude-opus-5-5    high
  deep-reasoner  opus → claude-opus-5-5    xhigh (extra)
  runner         haiku → claude-haiku-5-5  low

[Codex] ON   (~/.codex, CLI 0.171.0)
  역할           모델(설정 → 실제)           강도
  executor       최신 sol → gpt-6.2-sol      high
  deep-reasoner  최신 sol → gpt-6.2-sol      xhigh (extra)
  runner         최신 terra → gpt-6.1-terra  low

경고·안내:
  - Codex 훅은 사람이 한 번 신뢰해야 돕니다: CLI는 /hooks, 앱은 입력창의 Review hooks 또는 Settings > Hooks.
```

경고에는 최신이 아닌 고정 모델, Codex 훅 신뢰 필요, PATH 미등록, 저하 모드가 나옵니다.

## 역할별 모델·강도 바꾸기

역할은 `executor`·`deep-reasoner`(별칭 `deep_reasoner`, `deep`)·`runner` 세 개로 고정입니다. 모델·강도는 자유롭게 정합니다.

```bash
# Claude Code
oche claude executor opus high
oche claude deep-reasoner fable max
oche claude runner haiku low
oche claude runner claude-haiku-5-5 low      # 전체 ID = 그 버전에 고정

# Codex
oche codex executor sol high                 # 최신 Sol 계열
oche codex runner terra low
oche codex executor gpt-6.2-sol              # 그 버전에 고정(강도는 지금 값 유지)

# 대화형(번호 선택 또는 TUI)
oche executor
```

| 대상 | 모델에 쓸 수 있는 것 |
|---|---|
| Claude Code | 계열 별칭(`opus`·`sonnet`·`haiku`·`fable` 등 `oche models`에 나오는 것), 전체 ID(`claude-…`), `codex:<ID 또는 계열>`(다리) |
| Codex | 계열(`sol`·`terra`·`luna`·`astra` 등 = 그 계열 최신), 전체 ID(`gpt-…`), `claude:<별칭>`(다리) |

| 강도 | 비고 |
|---|---|
| `low`·`medium`·`high` | |
| `xhigh` | "extra"라고 적어도 됨 |
| `max` | Claude판 별명 "ultra" |
| `ultra` | 선택지 아님(Codex에서는 강도가 아니라 다중 에이전트 모드) |

- 재확인 질문은 없습니다. 비용이 큰 선택(runner를 low보다 높임, max)이나 최신이 아닌 ID는 한 줄 안내만 출력하고 바로 적용합니다.
- 바꾸면 정의 파일(Claude `.md`의 `model:`·`effort:`, Codex `.toml`의 `model`·`model_reasoning_effort`), 설정, 게이트가 읽는 파일에
  즉시 반영됩니다. 적용은 다음 세션부터입니다.
- 그 모델이 지원하지 않는 강도는 거부합니다. Codex 계열 최신을 고른 뒤 새 버전이 그 강도를 지원하지 않으면 가장 가까운 아래 값을 쓰고 현황판에 표시합니다.

```bash
oche reset                     # 모든 대상·역할을 기본값으로
oche reset claude              # Claude만
oche reset codex runner        # 하나만
oche pin codex executor gpt-6.2-sol     # 버전 고정(= oche codex executor gpt-6.2-sol)
oche unpin codex executor               # 기본 모델로(강도 유지)
```

기본값:

| 역할 | Claude Code | Codex |
|---|---|---|
| executor | `opus` · high | 최신 `sol` · high |
| deep-reasoner | `opus` · xhigh | 최신 `sol` · xhigh |
| runner | `haiku` · low | 최신 `terra` · low |

## 프리셋

프리셋은 역할 3개(executor·deep-reasoner·runner)의 `{model, effort}` 묶음에 이름을 붙인 것입니다. Claude Code 값과 Codex 값을
함께 담습니다. 적용하면 역할마다 위의 역할 설정과 같은 함수를 불러 정의 파일·게이트 설정이 함께 바뀌고, 다음 세션부터 적용됩니다.

내장 프리셋(지울 수 없음):

| id | 이름 | Claude Code (executor / deep-reasoner / runner) | Codex (executor / deep_reasoner / runner) |
|---|---|---|---|
| `default` | 기본 | opus·high / opus·xhigh / haiku·low | sol·high / sol·xhigh / terra·low |
| `saver` | 절약 | sonnet·medium / opus·high / haiku·low | terra·medium / sol·high / luna·low |
| `max` | 최대 | opus·xhigh / opus·max / haiku·medium | sol·xhigh / sol·max / terra·medium |

- 내장 프리셋의 모델은 계열 이름입니다(Claude는 별칭, Codex는 그 계열 최신). 모델 목록에 그 계열이 없으면 그 역할만 `default` 값으로 두고 한 줄로 알립니다.
- 모델이 그 강도를 지원하지 않으면 가장 가까운 아래 값을 씁니다(예: max를 지원하지 않으면 xhigh).

```bash
oche preset                       # 목록. 지금 설정과 일치하는 것에 ✔
oche preset use saver             # 설치된 대상 모두에 적용
oche preset use 절약              # 표시 이름으로도 됨
oche preset use max codex         # Codex만
oche preset save 내조합           # 지금 설정(설치된 대상 모두)을 사용자 프리셋으로 저장
oche preset use 내조합
oche preset delete 내조합
```

```text
프리셋 (✔ = 지금 설정과 일치)
 ✔ default (기본)
      Claude Code opus·high / opus·xhigh / haiku·low
      Codex       최신 sol·high / 최신 sol·xhigh / 최신 terra·low
   saver (절약)
      Claude Code sonnet·medium / opus·high / haiku·low
      Codex       최신 terra·medium / 최신 sol·high / 최신 luna·low
   max (최대)
   …
```

- 사용자 프리셋은 `~/.oche/config.json`의 `presets`에 저장됩니다. 이름은 공백 없는 글자면 되고(한글 가능), 내장 이름
  (`default`·`saver`·`max`·`기본`·`절약`·`최대`)과 겹치면 거부합니다. 같은 이름으로 다시 저장하면 덮어씁니다.
- 대상마다 다른 프리셋을 적용했거나 역할을 따로 바꿨으면 `프리셋: 사용자 지정`으로 보입니다.
- TUI: 홈의 **프리셋** → 목록에서 Enter로 적용(홈으로 돌아와 상태줄에 "프리셋 '절약' 적용됨 — 다음 세션부터") ·
  **지금 설정 저장** → 이름 입력 → Enter. Esc로 돌아옵니다.

## 모델 목록

```bash
oche models          # 계열별 최신 + 역할 매핑
oche update          # 목록 갱신(Claude: 실행 파일 다시 읽기, Codex: 실시간 목록) + Codex 최신 계열 다시 정함
oche update codex
```

새 계열이나 새 최신 버전이 보이면 `알림: Codex 새 계열 발견: vega (gpt-7-vega)`처럼 한 줄로 알립니다. 역할은 바꾸지 않습니다.
계열을 옮기는 것은 사용자가 고릅니다. `claude --version`·`codex --version`이 기록과 다르면 `oche`·`oche models`·`oche status`가
알아서 목록을 갱신합니다. 자세한 것은 [05](05-models-and-effort.md).

## 시험

```bash
oche selftest            # 설치된 대상 전부
oche selftest codex
```

켜짐·꺼짐 상태의 게이트 판정을 행렬로 확인하고, 원래 상태로 되돌립니다.

## 모델 호출 단계에서 막히는 것 (켜져 있을 때)

| 막힘 | Claude Code | Codex |
|---|---|---|
| 세 타입 밖의 하청 | `general-purpose`·`Explore`·`Plan`·타입 없음 | `agent_type` 없음·`default`·`worker`·`explorer` |
| 호출 때 model이 역할 설정과 다름 | `Agent`/`Task`의 `model` | `spawn_agent`의 `model` |
| 호출 때 강도가 역할 설정과 다름(높든 낮든), ultra | `effort` | `reasoning_effort` |
| 하청 안의 재하청 | `Agent`·`Task`·`Workflow` | `spawn_agent` |
| 다중 에이전트 | `Workflow` 도구 | 훅으로는 못 막음(규칙) |
| 메인의 직접 코드 수정 | 턴당 3개째 파일부터(`Edit`·`Write` 등) | 턴당 3개째 파일부터(`apply_patch`) |

차단 메시지는 `[oche 게이트]`로 시작하고, 모델은 그 메시지를 받으면 규칙대로 다시 위임합니다.
