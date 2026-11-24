# 01. 설치

## 준비물

| 항목 | 조건 |
|---|---|
| Python | 3.8 이상(표준 라이브러리만 씀). macOS·Linux는 `python3`, Windows는 `py -3` 또는 `python` |
| Claude Code | 설치돼 있으면 감지(`~/.claude` 폴더 또는 PATH의 `claude`) |
| Codex | 설치돼 있으면 감지(`~/.codex` 또는 `$CODEX_HOME`, PATH의 `codex`, ChatGPT 앱 안의 Codex 엔진) |
| Codex 버전 | CLI·앱 엔진 모두 0.171.0 이상 권장(미만이면 [저하 모드](06-codex-and-chatgpt-app.md#저하-모드)) |

## 받기

```bash
git clone https://github.com/suhan-dev/suhan-orchestration
cd suhan-orchestration
```

## 1단계: plan — 아무것도 바꾸지 않고 보기

```bash
python3 install.py plan
```

보여 주는 것:

- 대상별 감지 결과와 버전(Claude Code, Codex CLI, ChatGPT 앱 엔진)
- 역할별 모델·강도(Codex는 실제로 고른 모델 ID와 출처)
- 할 일 목록(어떤 파일을 쓰고 어디에 병합하는지)
- 충돌·경고(옛 fable 설치본, 같은 이름의 남의 하청 정의, 명령 이름 충돌, 저하 모드, 인라인 `[hooks]`, PATH)

## 2단계: install — 대상 고르기

```bash
python3 install.py install --only claude    # Claude Code만
python3 install.py install --only codex     # Codex만(CLI와 ChatGPT 앱이 같은 ~/.codex 를 씀)
python3 install.py install --all            # 감지된 것 전부
```

- `--only`·`--all` 없이 사람이 터미널에서 실행하면 "어디에 설치할까요?"라고 묻습니다.
- 터미널이 아닐 때(LLM이 실행할 때 등) `--only`·`--all`이 없으면 plan만 보이고 종료 코드 4로 끝납니다. LLM이 사용자에게 묻게 하려는 것입니다.
- 설치가 끝나면 스위치는 켜져 있습니다. 꺼 둔 채 설치하려면 `--off`.

| 플래그 | 뜻 |
|---|---|
| `--only claude\|codex` / `--all` | 설치 대상 |
| `--off` | 설치하되 꺼 둠 |
| `--migrate-legacy` | 옛 fable 설치본 옮기기(아래) |
| `--force-agents` | 같은 이름의 하청 정의가 oche 것이 아니면 백업 후 교체 |
| `--codex-models sol=<ID>,terra=<ID>,astra=<ID>` | Codex 모델을 직접 지정(sol → executor·deep-reasoner, terra → runner, astra → 표시용 메인) |
| `--command-name <이름>` | 터미널 명령 이름(기본 `oche`, 영문·숫자·`-`·`_`) |
| `--add-to-path` | `~/.local/bin`을 PATH에 추가(아래) |

종료 코드: 0 성공, 3 일부 또는 전체 거부(충돌), 4 대상 미지정.

## 3단계: verify

```bash
python3 install.py verify
```

명령 파일, `~/.oche/bin/oche.py`, 대상별 게이트 시험 행렬(켜짐·꺼짐 양쪽)을 돌립니다. 시험 뒤에는 원래 on/off 상태로 되돌리고
시험용 상태 파일을 지웁니다. `FAIL`로 시작하는 줄이 없어야 합니다.

## 4단계: 사람이 할 일

- 새 세션을 엽니다. 열려 있던 세션에는 적용되지 않습니다.
- Codex를 설치했다면 훅을 신뢰합니다. CLI: 새 `codex` 세션에서 `/hooks`. ChatGPT 앱: 새 Codex 채팅 입력창의 **Review hooks** 또는
  **Settings > Hooks**. 자세한 것은 [06](06-codex-and-chatgpt-app.md#훅-신뢰).

## oche가 이미 쓰이고 있을 때

설치 전에 같은 이름이 있는지 봅니다. 셸 별칭·함수는 설치기가 알 수 없으니 직접 확인합니다.

```bash
type oche            # macOS·Linux
```
```powershell
Get-Command oche     # PowerShell
```
```bat
where oche           :: cmd
```

설치기도 두 가지를 검사합니다: PATH에서 찾은 `oche`가 이 프로젝트 것이 아닐 때, 그리고 설치할 폴더(`~/.local/bin`)에 같은 이름의 남의 파일이
있을 때(Windows는 `.cmd`·`.ps1`·`.exe`·`.bat` 포함). 충돌이면 plan에 `이름 충돌: <경로>`와 비어 있는 후보가 나오고, install은 거부합니다.
남의 파일은 절대 덮어쓰지 않습니다.

다른 이름으로 설치합니다.

```bash
python3 install.py install --all --command-name orch
```

- 그 뒤로는 모든 문서의 `oche`를 `orch`로 바꿔 읽습니다(`orch on`, `orch executor`, `orch status` …). 현황판·도움말·안내 문구도 그 이름으로 나옵니다.
- 이름을 나중에 바꾸려면 새 이름으로 다시 설치합니다. 옛 이름의 oche 명령 파일은 지워지고, 역할 설정은 유지됩니다.
- 이 프로젝트가 예전에 설치한 같은 이름의 명령은 그대로 갱신합니다(표시 `oche-wrapper`로 알아봅니다).

## PATH

명령은 `~/.local/bin`(Windows는 `%USERPROFILE%\.local\bin`)에 만듭니다. 그 폴더가 PATH에 없으면:

```bash
python3 install.py install --all --add-to-path
```

- macOS·Linux: 쓰는 셸(`$SHELL`이 zsh면 `~/.zshrc`, bash면 `~/.bashrc`) 끝에 표시 주석과 `export PATH="$HOME/.local/bin:$PATH"`를
  덧붙입니다(백업 후). 다른 셸이면 바꾸지 않고 안내만 합니다. 새 터미널부터 적용됩니다.
- Windows: 사용자 PATH에만 추가합니다(PowerShell `[Environment]::SetEnvironmentVariable(..., 'User')`). 시스템 PATH는 건드리지 않습니다.
- 플래그를 주지 않으면 바꾸지 않고 안내만 합니다. 그때는 `~/.local/bin/oche on`처럼 전체 경로로 씁니다.

## 옛 fable 설치본에서 옮기기

`CLAUDE.md`의 `fable/active.md` 줄이나 `settings.json`의 `orchestration-gate` 훅이 있으면 작동 중인 옛 설치본으로 봅니다.
이때 plain `install`은 Claude 대상을 거부합니다. `~/.claude/fable/` 폴더와 `~/.local/bin/fable`만 남아 있으면(옮긴 뒤가 그렇습니다)
재설치를 막지 않고, plan과 install 출력에 "옛 fable 파일이 남아 있지만 더는 쓰이지 않습니다"라는 안내만 나옵니다.

```bash
python3 install.py install --only claude --migrate-legacy
```

셸 설정(`~/.zshrc` 등)에 옛 `fable/env.sh`를 불러오는 줄이 실제로 있으면 plan과 옮기기 출력에 "더는 필요 없습니다. 지워도 됩니다"라는
안내가 나옵니다. 셸 설정은 고치지 않습니다.

하는 일: 바꾸기 전에 백업하고, `CLAUDE.md`의 옛 불러오기 줄(바로 위 `fable-loader` 주석 포함)과 `settings.json`의 옛 훅 항목을 빼고,
`~/.claude/agents/`에서 fable 쪽을 가리키는 심링크를 지우고, `.fable-state`가 있으면 `off`로 둡니다. `~/.claude/fable/`과
`~/.local/bin/fable`은 건드리지 않습니다(더는 쓰지 않으니 필요 없으면 직접 지웁니다).

## 다른 쪽을 나중에 추가하기

```bash
python3 install.py install --only codex     # 예: Claude만 깔았다가 Codex 추가
```

이미 설치된 대상의 설정(역할별 모델·강도, 명령 이름)은 유지됩니다.

## 업데이트

```bash
cd suhan-orchestration
git pull
python3 install.py install --all     # 또는 설치했던 --only 대상
python3 install.py verify
```

여러 번 실행해도 줄·훅 항목이 중복되지 않습니다. 역할 설정은 유지됩니다.

## 제거

```bash
python3 install.py uninstall                 # 전부
python3 install.py uninstall --only codex    # 한쪽만
python3 ~/.oche/assets/install.py uninstall  # 저장소 폴더를 지웠을 때
```

oche가 넣은 것만 뺍니다: 불러오기 줄, 훅 항목, 규칙 구역, oche 하청 정의, `<도구 폴더>/oche/`, 상태 파일. 마지막 대상까지 빼면
명령 파일, PATH 표시 줄, `~/.oche/`도 지웁니다. 사용자 내용은 남기고, 바꾼 파일은 먼저 백업합니다.
Windows 사용자 PATH에 넣은 항목은 다른 도구도 쓸 수 있어 그대로 둡니다.

## 설치되는 곳

| 경로 | 내용 |
|---|---|
| `~/.oche/config.json` | 설치 대상·경로·버전·역할별 모델·강도·명령 이름·자동 갱신 여부 |
| `~/.oche/catalog.json` | 대상별 모델 목록 표(계열별 최신, 강도) |
| `~/.oche/log.txt` | 설치·전환·모델 갱신 기록 |
| `~/.oche/assets/` | 설치기·자산 사본(저장소를 지워도 돌게) |
| `~/.oche/bin/oche.py` | 명령 본체를 부르는 작은 파일 |
| `~/.local/bin/oche` (Windows `oche.cmd`·`oche.ps1`) | 터미널 명령 |

대상별 파일은 [03-architecture](03-architecture.md#파일-배치)에 있습니다.
