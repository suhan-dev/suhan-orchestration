# 08. 한계와 시험 범위

## 강제의 한계

- **하청 건수나 내역은 세거나 기록하지 않습니다.** 게이트는 호출마다 판정만 하고, 호출 내용을 어디에도 저장하지 않습니다.
- **훅은 가드레일입니다.** 게이트가 오류를 내거나 시간 초과되면 호출은 그대로 실행됩니다(fail-open). 세션을 마비시키지 않으려는 선택입니다.
  웹 검색 같은 호스팅 도구는 훅을 거치지 않습니다. Codex 문서도 훅을 완전한 강제 경계가 아니라 가드레일로 규정합니다.
- **Codex `ultra` 모드**는 도구 호출이 아니라 메인 강도 설정이라 훅이 볼 수 없습니다. 규칙으로만 막습니다. 게이트는 그 모드가 띄우는
  하청의 타입·모델·강도는 막지만 개수는 막지 못합니다.
- **세션당 동시 하청 1개**는 규칙으로만 지킵니다(양쪽 모두).
- **Bash/셸을 통한 파일 수정**은 세지 않습니다. 게이트는 Edit/Write(Claude), apply_patch(Codex) 경로의 코드 파일 수만 셉니다.
- **턴 id가 없는 하네스**(Claude `prompt_id`, Codex `turn_id`)에서는 수정 개수를 세지 않습니다.
- **Codex 하청의 파일 편집 끄기**는 정의 파일로 할 수 없습니다. runner의 "파일을 고치지 않는다"는 지침으로만 지킵니다.
- **Codex 0.171.0 미만**에서는 저하 모드로 돕니다([06](06-codex-and-chatgpt-app.md#저하-모드)).
- 하청 판별 필드(`agent_id`/`agent_type`)는 Codex 0.171.0 소스 스키마 기준이고 공개 문서 표에는 없습니다. 업데이트 뒤 이상하면 버전부터 확인합니다.

## 모델 목록의 한계

- Claude 계열표는 `claude` 실행 파일 안의 문자열을 읽어 얻습니다. 배포 형태가 바뀌어 못 읽으면 내장 기본값(fable/opus/sonnet/haiku)을 씁니다.
  `claude`가 스크립트 래퍼(예: Windows npm의 `claude.cmd`)면 읽지 못할 수 있습니다.
- Claude 모델별 지원 강도는 목록에서 얻지 못해 모든 모델에 `low`~`max`를 보입니다. 실제로 지원하지 않는 조합은 Claude Code가 처리합니다.
- 메인급(가장 비싼) 계열 판정은 하지 않습니다. 계열 이름만 보여 줍니다.
- sync 훅은 캐시만 읽어 올리기만 합니다. 더 낮은 버전으로 내리려면 `oche update`나 고정을 씁니다.
- 앱 캐시의 `client_version`이 앱 엔진 버전과 다르면 앱 캐시를 무시합니다. 이때 앱이 아직 모르는 모델이 하청 정의에 들어갈 수 있습니다.
  앱에서 새 Codex 채팅을 한 번 열어 캐시를 갱신한 뒤 `oche update codex`를 실행하면 앱 기준이 다시 반영됩니다.

## 다리 하청(실험적)

- 다른 쪽 CLI 설치·로그인이 필요합니다.
- 다리 하청은 셸 도구로 다른 CLI를 부르므로 셸 도구의 시간 제한(약 10분)에 걸릴 수 있습니다.
- 권한·샌드박스는 다른 쪽 CLI 설정을 따릅니다(`codex exec -s workspace-write`, `claude -p --permission-mode acceptEdits`).
- 시험은 명령 조립(dry-run)까지만 했습니다. 실제 두 CLI를 잇는 실행은 시험하지 않았습니다.

## 시험 범위

### 자동 시험

`python3 tests/run_tests.py`가 임시 HOME, 가짜 `claude`·`codex` 실행 파일, 임시 PATH로 시험합니다(실제 `~/.claude`·`~/.codex`는 건드리지 않음).
Claude만·Codex만·둘 다, 옛 설치본 옮기기, 재설치 중복 없음, on/off와 게이트 판정 행렬, 하청 안·다리 실행 중 차단, sync(갱신·시간 제한·고정 존중·
꺼져도 동작·깨진 파일), 앱 캐시 규칙(버전 일치·불일치·날짜), 강도 강등, `AGENTS.override.md`, 사용자 내용 보존·제거, 훅 명령을 `PATH=/usr/bin:/bin`으로
실행, 저하 모드, 명령 이름 충돌, 역할 변경, 새 계열, TUI(render·키 처리·pty 실행), Windows 경로 규칙 흉내(`ORCH_FORCE_WINDOWS=1`)를 다룹니다.
Python 3.9와 3.14에서 실행했고, 3.8은 문법 검사만 했습니다.

### 실제 세션 시험 (Codex CLI 0.171.0, `codex exec`)

실제 인증으로, 훅과 하청 정의는 임시 폴더의 것을 `-c`(인라인 `hooks.PreToolUse`, `agents.<이름>.config_file`)와
`--dangerously-bypass-hook-trust`로 그 실행에만 넣었습니다. 메인 `gpt-6-luna`·low, 역할도 싼 모델·low.

| 확인 | 결과 |
|---|---|
| `agent_type: worker` 하청 | **차단**, `[oche 게이트] 하청 타입 'worker'은(는) 금지입니다…`가 모델에게 그대로 전달됨 |
| executor 하청(지정 없음) | 통과. 하청 rollout의 `turn_context`가 정의 파일 값(`gpt-6.1-terra`, `low`)으로 돎(메인은 `gpt-6-luna`) |
| 호출 때 `model`·`reasoning_effort` 지정 | **차단**(`하청 model 지정 'gpt-6-luna'은(는) 역할 executor의 설정과 다릅니다…`) |
| 메인이 `apply_patch`로 .py 3개 | 1·2개째 통과, **3개째 차단** |
| 하청 안의 `apply_patch` | 입력에 `agent_id`·`agent_type: "executor"`가 붙고 통과(개수 안 셈) |
| 하청 안의 재하청 | **확인 못 함** — 하청이 정의 파일의 지시("하청을 띄우지 않는다")를 따라 호출 자체를 하지 않음 |

실제 입력 필드(덤프): `session_id`, `turn_id`, `transcript_path`, `cwd`, `hook_event_name`, `model`(메인 모델), `permission_mode`, `tool_name`,
`tool_input`, `tool_use_id`, 하청 안에서는 `agent_id`·`agent_type`. 하청 생성 도구 이름은 문서상 이름 `spawn_agent`가 아니라
**`collaborationspawn_agent`** 였고, `tool_input`은 `agent_type`·`model`·`reasoning_effort`·`task_name`·`fork_turns`·`message`(암호화)였습니다.
`apply_patch`의 `tool_input.command`는 `*** Begin Patch … *** End Patch` 본문 그대로였습니다. 이 결과로 게이트와 matcher를 고쳤습니다
(이름이 `spawn_agent`로 끝나는 도구를 모두 하청 생성으로 봄, matcher `^(apply_patch|.*spawn_agent|Agent)$`).
`--ephemeral`로는 하청 생성 자체가 실패해(`no rollout found for thread id`) 이 옵션 없이 시험했습니다.

### 실제 세션 시험 (Claude Code 2.1.321, 데스크톱 앱의 대화형 세션)

실제 컴퓨터에 `install --only claude --migrate-legacy`로 설치한 뒤(자가 시험 30개 통과), 열려 있던 세션에서 메인이 직접 호출해 확인했습니다.

- 설정과 다른 강도로 하청 호출(`executor`, `effort: medium`) → 차단. 모델에게 전달된 메시지:
  `[oche 게이트] 하청 effort 지정 'medium'은(는) 역할 executor의 설정과 다릅니다. …`
- 지정 없이 `executor` 호출 → 통과. 하청이 답한 자기 모델 ID는 `claude-opus-5-5`였습니다(정의 파일의 별칭 `opus`가 최신으로 해석됨).
- `general-purpose` 하청 → 차단(`하청 타입 'general-purpose'은(는) 부모 세션의 모델을 물려받으므로 금지입니다`).
- 메인이 코드 파일 3개를 직접 만들기 → 3개째 차단(`이번 턴에 메인이 직접 수정한 코드 파일이 이미 2개입니다`).

이것으로 실제 훅 입력의 `tool_name`(`Agent`·`Write`), `tool_input.subagent_type`·`effort`·`file_path`, 턴 id가 가정과 맞는 것을 확인했습니다.
게이트 훅은 설치 직후 이미 열려 있던 세션에도 적용되는 것을 관찰했습니다. 규칙 문서는 새 세션부터 읽힙니다.

실제 세션에서 확인하지 못한 것은 Workflow 차단, 하청 안의 재하청 차단, 호출 때 `model` 지정 차단, 옛 도구 이름 `Task`입니다. 이것들은 자동 시험으로만 확인했습니다.
비대화형 `claude -p` 시험은 CLI 로그인이 만료된 상태라 하지 못했습니다(`Failed to authenticate: OAuth session expired …`).

### 시험하지 않은 것

- Linux(경로 규칙은 macOS와 같지만 실제 기기에서 돌려 보지 않았습니다)
- ChatGPT 앱에서의 훅 신뢰·실행, Codex CLI의 대화형 `/hooks` 신뢰 흐름
- 실제 Windows(`.cmd`/`.ps1`, `commandWindows`, 콘솔 키 입력, 앱 엔진 감지)
- 다리 하청의 실제 실행, IDE 확장, 다중 에이전트 V2, Python 3.8 실행

## Windows

- 경로는 `%USERPROFILE%\.claude`, `%USERPROFILE%\.codex`(또는 `%CODEX_HOME%`), 명령은 `%USERPROFILE%\.local\bin\oche.cmd`·`oche.ps1`.
- 심링크를 쓰지 않습니다. 모든 파일은 UTF-8로 읽고 쓰고, 스크립트 시작 때 출력을 UTF-8로 바꿉니다(cp949 콘솔 대비).
- 실제 Windows에서는 시험하지 않았습니다. 테스트는 `ORCH_FORCE_WINDOWS=1`로 macOS에서 경로 규칙만 흉내 냈습니다.
- Claude Code 훅은 Windows에서 Git Bash(없으면 PowerShell)로 실행된다는 공식 문서에 맞춰 명령을 만들었습니다([03](03-architecture.md#훅-명령)).
- Windows 앱 엔진 버전 확인은 수동입니다.
