# 06. Codex CLI와 ChatGPT 앱

## 한 번 설치로 둘 다

Codex CLI(npm `@openai/codex`)와 ChatGPT 데스크톱 앱의 Codex는 같은 `$CODEX_HOME`(기본 `~/.codex`)을 씁니다. 그래서 한 번 설치하면
지침·하청 정의·훅이 양쪽에 적용됩니다. 앱은 엔진을 따로 넣어 두고(macOS: `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex`)
앱이 업데이트될 때 함께 바뀝니다.

| 클라이언트 | 적용 |
|---|---|
| Codex CLI | 새 `codex` 세션부터 |
| ChatGPT 앱의 Codex | 새 Codex 채팅부터 |
| 웹·Codex Cloud·호스팅 환경 | 적용 안 됨(이 컴퓨터의 파일을 읽지 않음) |
| IDE 확장 | 시험하지 않음 |

설치기는 CLI(`codex --version`)와 앱 엔진(`--version`)의 버전을 각각 읽습니다. 앱 엔진 감지는 macOS는 위 경로, Windows는
`%LOCALAPPDATA%`·`%ProgramFiles%` 아래의 `…\resources\codex-cli\bin\codex.exe`를 최선으로 찾고, 못 찾으면 조용히 건너뜁니다.
**Windows 앱 엔진 버전 확인은 수동입니다**(앱 정보 화면에서 확인).

## 훅 신뢰

Codex는 관리형이 아닌 훅을 사용자가 정의 해시 단위로 한 번 검토·신뢰해야 실행합니다. LLM이 대신할 수 없습니다.

1. **CLI:** 새 터미널에서 `codex`를 엽니다. 훅 검토 경고가 나오면 `/hooks`를 입력해 `oche 게이트 확인`(oche-gate.py)과
   `oche 하청 모델 확인`(oche-sync.py)을 검토하고 신뢰합니다.
2. **ChatGPT 앱:** 새 Codex 채팅 입력창의 **Review hooks**를 누르거나 **Settings > Hooks**를 열어 같은 두 훅을 신뢰합니다.
   한쪽에서 신뢰했어도 다른 쪽에서 다시 물으면 거기서도 신뢰합니다. 반영이 안 되면 앱을 다시 시작합니다.
3. 새 채팅에서 "worker 하청 하나 띄워 봐"라고 요청해 `[oche 게이트]` 메시지로 막히면 정상입니다.

`hooks.json`의 훅 **명령**이 바뀌면(예: python 경로가 바뀌어 재설치) 다시 신뢰해야 합니다. 스크립트 파일 내용만 바뀌는 업데이트는 해당하지 않습니다.
설치기는 훅 항목이 바뀌었을 때만 "다시 신뢰해야 합니다"라고 알립니다.

## hooks.json 항목

```json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "^(apply_patch|.*spawn_agent|Agent)$",
       "hooks": [{"type": "command",
                  "command": "\"/usr/local/bin/python3\" \"/home/me/.codex/oche/hooks/oche-gate.py\"",
                  "commandWindows": "py -3 \"C:\\Users\\me\\.codex\\oche\\hooks\\oche-gate.py\"",
                  "timeout": 10, "statusMessage": "oche 게이트 확인"}]}
    ],
    "SessionStart": [
      {"matcher": "startup|resume",
       "hooks": [{"type": "command", "command": "… oche-sync.py", "commandWindows": "… oche-sync.py",
                  "timeout": 10, "statusMessage": "oche 하청 모델 확인"}]}
    ]
  }
}
```

(경로는 예시입니다.) 다른 훅은 그대로 두고 이 두 항목만 더합니다. `config.toml`에 인라인 `[hooks]`가 있으면 Codex가 둘 다 읽고
시작 때 경고하므로, 설치기가 경고만 합니다.

## 지침 파일

전역 지침은 비어 있지 않은 `AGENTS.override.md`가 있으면 그쪽, 아니면 `AGENTS.md`입니다. `oche on`은 그 파일 끝에 표시 구역을 넣고,
`oche off`는 두 파일 모두에서 구역을 지웁니다. 구역 밖의 사용자 내용은 건드리지 않습니다. 지침 합계는 32 KiB 제한이 있어,
넘으면 `oche status`가 경고합니다.

## 하청 정의

`~/.codex/agents/{executor,deep-reasoner,runner}.toml`. 하청 이름은 Codex 관례대로 밑줄을 씁니다(`deep_reasoner`). 파일 첫 줄의
`# oche-managed` 표시로 oche가 만든 파일을 알아보고, 표시가 없는 파일은 sync·명령이 건드리지 않습니다.

```toml
# oche-managed: oche가 만든 파일입니다. 모델·강도는 터미널에서 `oche executor`로 바꿉니다.
name = "executor"
description = '…'
model = "gpt-6.2-sol"
model_reasoning_effort = "high"
developer_instructions = """…"""
```

실제 Codex 0.171.0의 훅 입력에서 하청 생성 도구 이름은 `collaborationspawn_agent`이고(이름공간이 붙음), 입력은
`{agent_type, model, reasoning_effort, task_name, fork_turns, message(암호화됨)}`입니다. 게이트는 이름이 `spawn_agent`로 끝나는 도구를 모두
하청 생성으로 봅니다. `spawn_agent`를 부를 때 `agent_type`에 `executor`·`deep_reasoner`·`runner` 중 하나를 넣어야 합니다. 비우거나 내장 하청을 고르면 게이트가 막습니다.

## 저하 모드

게이트는 하청 안의 호출을 입력의 `agent_id`/`agent_type`으로 알아봅니다. 이 필드는 Codex 0.171.0 소스 기준입니다.
CLI나 앱 엔진 중 하나라도 0.171.0 미만이면(알파 표기 `0.171.0-alpha.N`은 0.171.0으로 봄) 설치기가 `oche/gate.json`에
`{"subagent_fields": false}`를 씁니다. 이때 게이트는:

- 재하청 차단과 메인의 수정 개수 세기를 끕니다(하청의 호출과 구별할 수 없어 잘못 막을 수 있으므로).
- 타입·모델·강도 검사는 그대로 합니다.

Codex를 업데이트한 뒤 `python3 install.py install --only codex`를 다시 실행하면 정상 모드로 돌아갑니다.

## ultra 모드

Codex의 `ultra`는 메인 강도 설정으로, 켜면 모델이 스스로 하청을 여럿 띄웁니다(Claude Code의 ultracode에 해당). 도구 호출이 아니라
훅이 볼 수 없으므로 규칙 문서로만 막습니다. 게이트는 `ultra`가 띄우는 하청의 타입·모델·강도는 막지만 개수는 막지 못합니다.
동시 하청 수를 강제하고 싶다면 `config.toml`의 `[agents]` 아래 `max_concurrent_threads_per_session = 1`을 사용자가 직접 넣을 수 있습니다
(스위치와 무관하게 늘 적용됩니다).
