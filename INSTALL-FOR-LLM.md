# 설치 지시서 — LLM용

이 문서를 받은 LLM(Claude Code 또는 Codex)은 아래 절차대로 suhan-orchestration을 설치합니다.
사람은 이 문서를 주고 "이대로 설치해 줘"라고만 하면 됩니다.

## 복사해 쓰는 프롬프트

```text
https://github.com/suhan-dev/suhan-orchestration 의 INSTALL-FOR-LLM.md 를 읽고 그 절차대로 설치해 줘.
- 먼저 어디에(Claude Code / Codex / 둘 다) 설치할지 나에게 물어봐.
- 시작 전에 무엇을 할지 5줄 안으로 요약해 줘.
- 단계는 순서대로 실행하고, 저장소 파일이나 설정 파일을 임의로 고치지 마.
- 덮어쓰기·삭제가 필요하면 하기 전에 나에게 물어봐.
- Codex 샌드박스에서 작업 폴더 밖 쓰기가 막히면 우회하지 말고 권한을 요청해.
- 검증 출력은 그대로 붙여 보고해.
- 마지막에 내가 직접 할 일과, 터미널에서 켜기·끄기·상태 확인 명령을 알려 줘.
```

## LLM이 지킬 것

- 아래 단계를 순서대로 실행합니다. 건너뛰거나 합치지 않습니다.
- 저장소 파일과 사용자 설정 파일(`CLAUDE.md`, `settings.json`, `AGENTS.md`, `hooks.json`, 셸 설정)을 손으로 고치지 않습니다.
  바꾸는 일은 모두 `install.py`가 합니다(바꾸기 전에 `.bak_oche_<시각>` 백업을 만듭니다).
- `install.py`가 충돌을 보고하면 플래그(`--migrate-legacy`, `--force-agents`, `--command-name`)를 붙이기 전에 사용자에게 묻습니다.
- 무엇이든 지우거나 덮어쓰는 일은 사용자에게 먼저 묻습니다.
- Codex에서 실행 중이고 샌드박스가 `~/.claude`·`~/.codex`·`~/.oche`·`~/.local/bin` 쓰기를 막으면, 다른 경로로 우회하지 말고
  사용자에게 권한(승인)을 요청합니다.
- 검증 출력은 요약하지 말고 그대로 보고합니다. 실패는 실패라고 씁니다.

## 0. 받기

```bash
git clone https://github.com/suhan-dev/suhan-orchestration
cd suhan-orchestration
```

이미 받아 둔 폴더가 있으면 그 폴더에서 `git pull`만 합니다. Windows에서는 아래 `python3`를 `py -3`으로 바꿔 씁니다.

## 1. 감지하고 어디에 설치할지 묻기

```bash
python3 install.py plan
```

`plan`은 아무것도 바꾸지 않습니다. 출력을 보고 사용자에게 **반드시** 묻습니다(하나만 감지돼도 확인을 받습니다).

> "Claude Code / Codex / 둘 다 중 어디에 설치할까요?"

- 선택지는 `감지됨`으로 나온 것만 보입니다. `감지 안 됨`인 쪽은 "설치돼 있지 않음"이라고 알립니다.
- 묻지 않고 전부 설치하지 않습니다.

## 2. `oche` 이름 확인

설치할 명령 이름이 이미 쓰이는지 확인합니다. 셸 별칭·함수는 파이썬이 알 수 없어서 셸에서 직접 봅니다.

```bash
type oche                # macOS·Linux (bash·zsh)
```
```powershell
Get-Command oche         # PowerShell
```
```bat
where oche               :: cmd
```

- "not found"·오류면 그대로 진행합니다.
- 무언가 나오거나 `plan`에 `이름 충돌:` 줄이 있으면, 사용자에게 새 이름을 묻습니다. `plan`이 제안한 후보(예: `orch`, `oche2`, `oche-ai`)를
  보여 주고 고르게 합니다. 이후 모든 설치 명령에 `--command-name <이름>`을 붙입니다.

## 3. 사용자에게 5줄 요약

`plan` 출력을 바탕으로, 설치 전에 사용자에게 5줄 안으로 알립니다.

1. 설치 대상(사용자가 고른 것)과 감지된 버전
2. Codex라면 하청 모델 결정(예: executor 최신 sol → gpt-…, runner 최신 terra → gpt-…)
3. 바뀌는 사용자 파일(CLAUDE.md·settings.json / AGENTS.md·hooks.json)과 백업이 만들어진다는 것
4. 충돌·경고가 있으면 그 내용(옛 fable 설치본, 같은 이름 하청 정의, 저하 모드, PATH 미등록 등)
5. 명령 이름(`oche` 또는 고른 이름)

충돌이 있으면 여기서 어떻게 할지 묻습니다.

| plan의 충돌 | 물어볼 것 | 동의하면 붙일 플래그 |
|---|---|---|
| 옛 fable 설치본 | "옛 설치본을 옮길까요? 옛 폴더와 옛 명령은 지우지 않습니다" | `--migrate-legacy` |
| 같은 이름의 하청 정의가 oche 것이 아님 | "백업하고 교체할까요?" | `--force-agents` |
| 이름 충돌 | "어떤 이름으로 설치할까요?" | `--command-name <이름>` |
| PATH에 `~/.local/bin` 없음 | "셸 설정(또는 Windows 사용자 PATH)에 추가할까요? 백업합니다" | `--add-to-path` |
| Codex 모델을 정하지 못함 | 출력에 나온 slug 목록을 보여 주고 고르게 함 | `--codex-models sol=<ID>,terra=<ID>` |

## 4. 설치

사용자의 답에 맞춰 하나만 실행합니다(필요한 플래그를 덧붙입니다).

```bash
python3 install.py install --only claude
python3 install.py install --only codex
python3 install.py install --all
```

종료 코드 0이면 성공, 3이면 일부 대상이 충돌로 거부된 것(출력의 `충돌:` 줄을 사용자에게 보여 주고 3단계로 돌아갑니다),
4면 대상을 정하지 않은 것입니다.

## 5. 검증 — 출력을 그대로 보고

```bash
python3 install.py verify
```

`OK`/`FAIL`로 시작하는 줄이 모두 `OK`여야 합니다. 마지막 `selftest: OK n, FAIL 0` 줄까지 그대로 붙여 보고합니다.
하나라도 `FAIL`이면 그 줄을 그대로 보고하고 멈춥니다.

## 6. 사람이 할 일 안내

설치한 대상에 맞춰 아래를 그대로 알립니다.

- **공통:** 이미 열려 있는 세션에는 적용되지 않습니다. 새 세션(Claude Code), 새 `codex` 세션(CLI), 새 Codex 채팅(ChatGPT 앱)을 엽니다.
- **Codex CLI:** 새 `codex` 세션에서 `/hooks`를 입력해 `oche 게이트 확인`과 `oche 하청 모델 확인` 훅을 검토하고 신뢰합니다.
- **ChatGPT 앱의 Codex:** 새 Codex 채팅 입력창의 **Review hooks**를 누르거나 **Settings > Hooks**에서 같은 두 훅을 신뢰합니다.
  한쪽에서 신뢰했어도 다른 쪽에서 다시 물으면 거기서도 신뢰합니다. 반영이 안 되면 앱을 다시 시작합니다.
- **확인:** 새 세션에서 "general-purpose 하청 하나 띄워 봐"(Claude) 또는 "worker 하청 하나 띄워 봐"(Codex)라고 요청해
  `[oche 게이트]` 메시지로 막히면 정상입니다.
- **다른 쪽을 나중에 추가:** 같은 폴더에서 `python3 install.py install --only <claude|codex>`를 다시 실행합니다. 기존 설정은 유지됩니다.
- **이름을 바꿔 설치했다면:** "이 컴퓨터에서는 `oche` 대신 `<이름>`으로 칩니다"라고 분명히 알립니다.

## 7. 터미널 명령 안내 (복사해 쓰게)

이름을 바꿨다면 `oche`를 그 이름으로 바꿔서 알립니다.

```bash
oche on
```
```bash
oche off
```
```bash
oche
```
```bash
oche status
```

- `oche`: 터미널이면 키보드 화면(TUI), 아니면 현황판
- `oche executor` / `oche deep-reasoner` / `oche runner`: 그 역할의 모델·강도 고르기
- `oche preset`: 프리셋 목록, `oche preset use saver`(절약)·`oche preset use max`(최대)·`oche preset use default`(기본)로 한 번에 바꾸기
- `~/.local/bin`이 PATH에 없으면 `~/.local/bin/oche on`처럼 전체 경로로 칩니다(Windows: `%USERPROFILE%\.local\bin\oche.cmd on`).

## 참고

- 설치 위치·바뀌는 파일: [docs/03-architecture.md](docs/03-architecture.md)
- 문제 해결: [docs/07-troubleshooting.md](docs/07-troubleshooting.md)
- 제거: `python3 install.py uninstall` (저장소 폴더를 지웠다면 `python3 ~/.oche/assets/install.py uninstall`)
