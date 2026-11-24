# 05. 모델과 강도

## 역할과 기본값

| 역할 | 하는 일 | Claude Code 기본 | Codex 기본 |
|---|---|---|---|
| executor | 범위가 정해진 구현·수정·테스트·리뷰 | 최신 Opus(`opus`) · high | 최신 Sol(`latest:sol`) · high |
| deep-reasoner (Codex 이름 `deep_reasoner`) | 국소 난제(근본원인·알고리즘·설계 대안) | 최신 Opus · xhigh | 최신 Sol · xhigh |
| runner | 명령 실행·조회·로그 | 최신 Haiku(`haiku`) · low | 최신 Terra(`latest:terra`) · low |

기본값일 뿐입니다. 어느 역할이든 어떤 모델·강도로든 바꿀 수 있습니다([02](02-usage.md#역할별-모델강도-바꾸기)).

## Claude ↔ Codex 강도 대응표

| 이 설정에서 부르는 말 | Claude Code 값 | Codex 값 | 비고 |
|---|---|---|---|
| low | `low` | `low` | runner 기본 |
| medium | `medium` | `medium` | |
| high | `high` | `high` | executor 기본 |
| extra | `xhigh` | `xhigh` | deep-reasoner 기본 |
| ultra (Claude판 별명) | `max` | `max` | 가장 비싼 강도 |
| ultracode | Workflow 도구(다중 에이전트) | `ultra` | **강도가 아니라 하청을 스스로 여럿 띄우는 모드. 둘 다 금지** |
| (Codex 전용) | — | `none`·`minimal` | 일부 모델만 지원 |

- **같은 이름이어도 실제 사고량·비용은 회사마다, 모델마다 다릅니다.** 이 표는 단계의 상대적 위치를 맞춘 것입니다.
- **ultra가 헷갈립니다.** Claude판 규칙에서는 `max`의 별명이었지만, Codex의 `ultra`는 Claude Code의 ultracode에 해당합니다.
  그래서 하청 강도 선택지에서 `ultra`를 뺐고(TUI·명령 모두), 게이트는 호출 때 `ultra`를 늘 막습니다. 규칙 문서에는
  "사용자가 ultra라고 하면 max인지 ultra 모드인지 먼저 확인"을 넣었습니다.
- Codex의 `ultra` 모드는 메인 강도 설정이라 훅이 볼 수 없습니다. 규칙으로만 막습니다([08](08-limitations.md)).

## 모델 목록 표 (catalog)

`~/.oche/catalog.json`에 대상별 목록을 둡니다. TUI·명령의 모델 선택지는 여기서 만듭니다. 계열 이름은 코드에 박혀 있지 않습니다.

| 대상 | 얻는 곳 | 계열 판정 |
|---|---|---|
| Claude Code | `claude` 실행 파일 안의 `latest_per_family:{계열:"ID",…}` 문자열(정규식) | 표에 있는 계열 전부. 계열 이름 = 별칭. 못 읽으면 내장 기본값(fable/opus/sonnet/haiku), `source: builtin` |
| Codex | `codex debug models`(실시간) 또는 Codex가 받아 둔 모델 캐시 | `^gpt-(\d+(?:\.\d+)*)-([a-z]+)$`에 맞고 `visibility`가 `list`인 slug를 계열별로 묶어 버전이 가장 높은 것. 숨김 slug는 제외 |

갱신 시점:

| 언제 | 무엇을 |
|---|---|
| `oche update` | Claude는 실행 파일을 다시 읽고, Codex는 실시간 목록을 받음 |
| TUI의 "모델 목록 갱신" | 같음 |
| `oche`·`oche models`·`oche status` 실행 때 | 기록된 `claude --version`·`codex --version`이 지금과 다르면 자동 갱신 |
| Codex sync 훅(세션 시작, 1시간에 1번) | 모델 캐시만 읽어 계열별 최신 표를 갱신(더 낡은 값으로는 되돌리지 않음) |

새 계열이나 새 최신 버전이 보이면 한 줄로 알립니다(예: `새 계열 발견: vega (gpt-7-vega)`). **역할 설정은 자동으로 바꾸지 않습니다.**
계열을 옮기는 것은 사용자가 고릅니다. 같은 계열 안의 버전 상승만 자동입니다(Claude는 별칭, Codex는 sync).

## 자동 최신화의 원리

### Claude Code: 별칭

하청 정의 파일에 `model: opus`처럼 별칭을 적습니다. Claude Code는 별칭을 그 버전이 아는 계열 최신 ID로 바꿔 부릅니다
(예: Claude Code 2.1.321에서 `opus` → `claude-opus-5-5`). Claude Code가 업데이트되면 새 최신으로 저절로 바뀌고,
구버전 Claude Code가 모르는 ID라서 거부되는 일도 없습니다.

### Codex: 목록 → sync

1. 설치·`oche update` 때 모델 목록(실시간 → 없으면 가장 최근 캐시)에서 계열별로 가장 높은 버전을 고릅니다.
2. **ChatGPT 앱 캐시 규칙:** 앱의 모델 캐시(`models_cache.codex_work_desktop.json`)가 14일 안에 받은 것이고, 그 캐시의 `client_version`이
   지금 앱 엔진 버전과 같고(major.minor.patch 비교, 알파 접미사 무시), 고른 slug가 거기 없으면, 앱과 목록 양쪽에 있는 같은 계열 중 가장 높은 것을
   쓰고 경고합니다(앱이 모르는 모델로 하청 정의를 쓰면 앱에서 거부될 수 있어서). 버전이 다르거나 14일이 넘었으면 낡은 캐시로 보고 무시하며,
   plan·status에 "앱 모델 캐시가 낡아 무시함 — ChatGPT 앱에서 새 Codex 채팅을 한 번 열면 갱신됨"을 띄웁니다.
3. 하청 TOML의 `model`과 `oche/models.json`에 씁니다.
4. 세션이 시작될 때 sync 훅이 돕니다. 1시간에 한 번, 하위 프로세스·네트워크 없이 Codex가 받아 둔 캐시만 읽고, 계열 최신 버전이 올라갔으면
   TOML의 `model` 줄만 바꿉니다. 바뀌었을 때만 사용자 표시용 한 줄(`oche: 하청 모델 갱신 — executor gpt-6.2-sol → gpt-6.3-sol`)을
   내고, 그 밖에는 아무것도 출력하지 않습니다(모델 문맥에 들어가는 출력 없음). 스위치가 꺼져 있어도 돕니다.
5. 새 버전이 역할 강도를 지원하지 않으면 `[none, minimal, low, medium, high, xhigh, max]` 순서에서 가장 가까운 아래 값을 씁니다. `ultra`는 고르지 않습니다.

### LLM 토큰이 들지 않는 이유

- Claude: 별칭 해석은 Claude Code가 로컬에서 합니다.
- Codex: sync는 로컬 파이썬 스크립트가 이미 받아 둔 캐시 파일만 1시간에 한 번 읽습니다.
- `oche update`·설치 때의 `codex debug models`는 목록 요청일 뿐 모델 호출이 아닙니다.
- 규칙 문서에는 모델에게 `oche models`를 실행하거나 버전을 확인하라는 지시가 없습니다. 이 확인은 사람이 터미널에서 합니다.

## 고정(pin)

특정 버전에 묶고 싶을 때:

```bash
oche claude executor claude-opus-5-5     # 전체 ID = 고정
oche pin codex runner gpt-6.1-terra      # 같은 뜻
oche unpin codex runner                  # 기본(최신 계열)으로
```

- 고정한 역할은 자동 최신화되지 않습니다. 고정 ID가 계열 최신보다 옛것이면 현황판에 "최신 아님(최신: …)"이 뜹니다.
- 직접 입력한 ID가 옛것이면 적용할 때 한 줄 안내를 냅니다(재확인은 묻지 않음).

## 게이트와 모델

- 호출 때 지정한 `model`은 그 역할의 설정값(또는 정의 파일 값)과 같을 때만 통과합니다. 비어 있으면 정의 파일 값을 쓰니 통과합니다.
  이렇게 해서 `claude-opus-5-4` 같은 옛 ID를 실수로 부르는 일, 하청을 메인급으로 몰래 올리는 일이 막힙니다.
- 호출 때 지정한 강도(Claude `effort`, Codex `reasoning_effort`)도 설정 강도와 같을 때만 통과합니다(높든 낮든 다르면 차단). `ultra`는 늘 차단.
- 사용자가 터미널에서 어떤 역할을 메인급 모델로 정했다면 그 정의 파일은 그 모델을 씁니다. 게이트는 계열 이름으로 판정하지 않습니다.

## 다리 하청(실험적)

한 도구의 역할을 다른 회사 모델로 돌립니다.

```bash
oche claude executor codex:gpt-6.2-sol high   # Claude Code의 executor → Codex 모델
oche codex runner claude:haiku low            # Codex의 runner → Claude 모델
```

- **Claude 역할 → Codex 모델:** 그 역할의 Claude 정의를 다리용(`model: haiku`, `effort: low`)으로 바꿉니다. 다리 하청은 받은 지시를
  임시 파일에 그대로 쓰고 아래를 실행해 결과 파일 내용과 종료 코드를 그대로 돌려줍니다. 스스로 작업하지 않습니다.

  ```text
  oche bridge codex <역할> --task <작업파일> --out <결과파일> --cwd <작업 폴더>
  → ORCH_BRIDGE=1 codex exec -m <ID> -c model_reasoning_effort="<강도>" -s workspace-write -C "<작업 폴더>" --skip-git-repo-check --ephemeral -o <결과파일> - < <작업파일>
  ```

- **Codex 역할 → Claude 모델:** 대칭입니다. Codex 정의는 runner 기본 계열(최신 terra)·low로 두고 아래를 실행합니다.

  ```text
  ORCH_BRIDGE=1 claude -p --model <별칭> --effort <강도> --output-format text --permission-mode acceptEdits < <작업파일>
  ```

- 프롬프트 앞에 "너는 하청 실행자다. 하청을 띄우지 말고 직접 수행하라."를 붙입니다.
- **재귀 방지:** 두 게이트 모두 `ORCH_BRIDGE=1`이면 하청 생성(Agent/Task/Workflow/spawn_agent)을 막습니다. 수정 개수는 세지 않습니다.
- 명령 조립만 보려면: `ORCH_BRIDGE_DRYRUN=1 oche bridge codex executor --task t.txt --out o.txt`
- 한계: 다른 쪽 CLI가 설치·로그인돼 있어야 합니다. 긴 작업은 셸 도구의 시간 제한(약 10분)에 걸릴 수 있습니다.
  권한·샌드박스는 다른 쪽 CLI 설정을 따릅니다. 실제 두 CLI를 잇는 실행은 시험하지 않았습니다.
