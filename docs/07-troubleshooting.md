# 07. 문제 해결

먼저 상태를 봅니다.

```bash
oche status          # 부품 점검 [OK]/[--], 마지막 sync, 경고
oche selftest        # 게이트 시험 행렬
tail -n 30 ~/.oche/log.txt
```

## 설치

| 증상 | 원인 | 해결 |
|---|---|---|
| `install`이 종료 코드 4로 plan만 보이고 끝남 | 대상(`--only`/`--all`)을 정하지 않음 | `python3 install.py install --only claude` 등으로 다시 |
| `[Claude Code] 설치 거부: 옛 fable 설치본` | 옛 설치본 흔적 | `--migrate-legacy` ([01](01-install.md#옛-fable-설치본에서-옮기기)) |
| `… 가 이미 있고 oche 것이 아닙니다` | 같은 이름의 하청 정의 | 내용을 확인하고 `--force-agents`(백업 후 교체) |
| `이름 충돌: …` | 같은 이름의 명령이 있음 | `--command-name <다른 이름>` ([01](01-install.md#oche가-이미-쓰이고-있을-때)) |
| `Codex 모델을 정하지 못했습니다` | 목록·캐시에 쓸 만한 slug가 없음 | 출력의 slug 목록에서 골라 `--codex-models sol=<ID>,terra=<ID>` |
| `settings.json 이 올바른 JSON이 아닙니다` | 사용자 설정 파일 문법 오류 | 파일을 고친 뒤 다시 |
| `oche: command not found` | `~/.local/bin`이 PATH에 없음 | `--add-to-path`로 재설치하거나 `~/.local/bin/oche` 전체 경로 |

## Claude Code

| 증상 | 확인 | 해결 |
|---|---|---|
| 새 세션에서 규칙이 안 보임 | `oche status`의 "규칙 불러오기 줄", "active.md 내용" | `oche on` 후 **새 세션** |
| 게이트가 안 막음 | `settings.json`에 `oche-gate` 항목, `.oche-state`가 `on` | 재설치 후 새 세션. 훅 명령을 직접 돌려 보기(아래) |
| `/agents`에 세 하청이 없음 | `~/.claude/agents/*.md` | `python3 install.py install --only claude` |
| 하청이 엉뚱한 모델로 돎 | `oche models` | `oche claude <역할> <모델> <강도>` |

훅 명령을 직접 실행해 보기(차단이면 종료 코드 2와 `[oche 게이트]` 메시지):

```bash
echo '{"tool_name":"Agent","tool_input":{"subagent_type":"general-purpose"}}' \
  | python3 ~/.claude/oche/hooks/oche-gate.py; echo "exit $?"
```

## Codex

| 증상 | 확인 | 해결 |
|---|---|---|
| 게이트가 안 돎 | 훅을 신뢰했는지 | CLI `/hooks`, 앱 Review hooks·Settings > Hooks ([06](06-codex-and-chatgpt-app.md#훅-신뢰)) |
| 앱에서만 안 돎 | 앱을 다시 시작했는지, 앱 엔진 버전 | 앱 재시작, 앱 업데이트 |
| `python3`를 못 찾는다는 훅 오류(앱) | `hooks.json`의 `command`가 절대경로인지 | 재설치(설치기는 `which python3`의 절대경로를 씀). pyenv shim이면 실제 경로로 바꿔 설치 |
| 시작 때 훅 경고가 두 번 | `config.toml`의 인라인 `[hooks]` | 한쪽으로 정리 |
| 규칙이 안 보임 | `AGENTS.override.md`가 있는지 | 있으면 그쪽에 규칙 구역이 들어감. `oche status`로 위치 확인 |
| "지침이 잘릴 수 있습니다" | 지침 파일 32 KiB 초과 | 사용자 지침을 줄이기 |
| 하청 모델이 앱에서 거부됨 | 앱 캐시에 그 모델이 없음 | `oche update codex` 또는 `oche codex <역할> <ID>`로 고정 |
| 저하 모드 경고 | CLI·앱 엔진 0.171.0 미만 | 업데이트 후 `install --only codex` 재실행 |

```bash
echo '{"tool_name":"spawn_agent","tool_input":{"agent_type":"worker"}}' \
  | python3 ~/.codex/oche/hooks/oche-gate.py; echo "exit $?"
```

## TUI

| 증상 | 해결 |
|---|---|
| 상자 문자가 2칸으로 밀림·깨짐 | `OCHE_ASCII=1 oche` |
| 색이 이상함 | `NO_COLOR=1 oche` |
| 화면이 안 뜨고 텍스트만 나옴 | 터미널이 아님(파이프·리다이렉트). 정상 동작. `--plain`을 붙였는지도 확인 |
| 터미널이 이상해짐(드묾) | `reset` 입력 |

## Windows (실기기 시험 전)

| 증상 | 해결 |
|---|---|
| `oche.ps1`이 실행 정책으로 막힘 | `oche.cmd`를 쓰거나 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `py`가 없다는 오류 | python.org 설치기로 py 런처를 넣거나, 재설치(그때는 python.exe 절대경로를 씀) |
| 한글이 깨짐 | Windows Terminal 사용, 또는 `chcp 65001` 후 실행 |

## 실제 훅 입력 보기

게이트는 환경변수 `OCHE_HOOK_DUMP=<파일>`이 있으면 받은 훅 입력 JSON을 한 줄씩 그 파일에 덧붙입니다(디버그용). 훅 명령 앞에 붙이는 것이 가장 확실합니다.

```bash
# hooks.json / settings.json 의 훅 command 를 잠시 이렇게 바꿔 본다(시험이 끝나면 되돌림)
OCHE_HOOK_DUMP=/tmp/oche-dump.jsonl "/usr/local/bin/python3" "/home/me/.codex/oche/hooks/oche-gate.py"
```

## 되돌리기

모든 변경 전에 `<파일>.bak_oche_<시각>` 백업이 있습니다. 완전히 빼려면 `python3 install.py uninstall`.
