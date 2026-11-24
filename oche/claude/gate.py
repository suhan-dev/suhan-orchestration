#!/usr/bin/env python3
# <claude>/oche/hooks/oche-gate.py — oche 강제 게이트 (Claude Code PreToolUse 훅)
#
# - 상태 파일 <claude>/.oche-state 가 on 이 아니면 즉시 통과한다. 등록은 settings.json 에 1회, 동작 여부는 스위치가 정한다.
# - 메인이 한 턴(prompt_id)에 Edit/Write 로 직접 고치는 코드 파일을 2개까지만 허용하고 3개째부터 막는다.
#   Bash 를 통한 수정은 통과시킨다. prompt_id 가 없는 하네스 버전에서는 개수를 세지 않는다.
# - Workflow(ultracode)를 막는다.
# - 하청(Agent, 구버전 이름 Task)은 executor·deep-reasoner·runner 만 허용한다. 호출 때의 model·effort 는
#   비어 있거나 그 역할의 설정값과 같을 때만 통과시킨다(모델 계열 이름에 기대지 않는다).
# - 하청 안(입력에 agent_id/agent_type 이 있음)에서는 하청·Workflow 만 막고 나머지는 통과시킨다.
# - 환경변수 ORCH_BRIDGE=1(다리 하청이 띄운 CLI 안)이면 하청·Workflow 를 막고 수정 개수는 세지 않는다.
# 오류가 나면 통과시킨다(fail-open) — 게이트 버그가 세션을 마비시키지 않게 한다.
import json
import os
import re
import sys
import time

LIMIT = 2
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
OCHE_DIR = os.path.dirname(HOOKS_DIR)
CLAUDE_DIR = os.path.dirname(OCHE_DIR)
STATE_FILE = os.path.join(CLAUDE_DIR, ".oche-state")
GATE_STATE_DIR = os.path.join(OCHE_DIR, "state")
ROLES_FILE = os.path.join(OCHE_DIR, "roles.json")
ALLOWED_TYPES = ("executor", "deep-reasoner", "runner")
SPAWN_TOOLS = ("Agent", "Task")
EDIT_TOOLS = ("Edit", "Write", "NotebookEdit", "MultiEdit")
CODE_EXTS = {
    "ts", "tsx", "js", "jsx", "mjs", "cjs", "py", "go", "rs", "java", "kt",
    "kts", "swift", "c", "h", "cc", "cpp", "hpp", "cs", "rb", "php", "vue",
    "svelte", "astro", "css", "scss", "sass", "less", "html", "sh", "bash",
    "zsh", "sql", "lua", "dart", "scala", "ex", "exs", "zig", "ipynb", "ps1",
}
TOGGLE = "oche"


def allow():
    sys.exit(0)


def deny(msg):
    sys.stderr.write("[oche 게이트] " + msg)
    sys.stderr.flush()
    sys.exit(2)


def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, ValueError):
        return None


def load_roles():
    try:
        data = json.loads(read_text(ROLES_FILE) or "{}")
        if data.get("command_name"):
            global TOGGLE
            TOGGLE = str(data["command_name"])
        return data.get("roles") or {}
    except ValueError:
        return {}


def is_code(path):
    return path.rsplit(".", 1)[-1].lower() in CODE_EXTS if "." in path else False


def check_spawn(tool_input):
    roles = load_roles()
    stype = str(tool_input.get("subagent_type") or "")
    model = str(tool_input.get("model") or "").strip()
    effort = str(tool_input.get("effort") or "").strip().lower()
    if stype not in ALLOWED_TYPES:
        deny("하청 타입 '%s'은(는) 부모 세션의 모델을 물려받으므로 금지입니다. "
             "executor·deep-reasoner·runner 중 하나로 띄우세요." % (stype or "(없음)"))
    role = roles.get(stype) or {}
    if model:
        ok = {str(role.get(k) or "") for k in ("configured", "model")} - {""}
        if model not in ok:
            deny("하청 model 지정 '%s'은(는) 역할 %s의 설정과 다릅니다. 모델은 사용자가 터미널에서 `%s %s`로만 바꿉니다. "
                 "model 지정을 빼세요." % (model, stype, TOGGLE, stype))
    if effort:
        if effort == "ultra":
            deny("ultra는 하청 강도로 쓸 수 없습니다. effort 지정을 빼세요.")
        ok = {str(role.get(k) or "").lower() for k in ("configured_effort", "effort")} - {""}
        if effort not in ok:
            deny("하청 effort 지정 '%s'은(는) 역할 %s의 설정과 다릅니다. 강도는 사용자가 터미널에서 `%s %s`로만 바꿉니다. "
                 "effort 지정을 빼세요." % (effort, stype, TOGGLE, stype))
    allow()


def dump(raw):
    """OCHE_HOOK_DUMP=<파일> 이면 받은 훅 입력을 한 줄씩 덧붙인다(실제 필드 확인용 디버그)."""
    path = os.environ.get("OCHE_HOOK_DUMP")
    if path:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(raw.strip().replace("\n", " ") + "\n")
        except OSError:
            pass


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    dump(raw)
    state = (read_text(STATE_FILE) or "off").strip()
    if state != "on":
        allow()

    data = json.loads(raw or "{}")
    tool = str(data.get("tool_name") or "")
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    # 다리 하청이 띄운 CLI 안: 직접 수행만 한다.
    if os.environ.get("ORCH_BRIDGE") == "1":
        if tool in SPAWN_TOOLS or tool == "Workflow":
            deny("다리 실행 중에는 하청·Workflow를 띄우지 않고 직접 수행합니다.")
        allow()

    # 하청 안: 재하청·워크플로만 막는다.
    if data.get("agent_id") or data.get("agent_type"):
        if tool == "Workflow":
            deny("하청 안에서 Workflow는 금지입니다.")
        if tool in SPAWN_TOOLS:
            deny("하청 안에서 다시 하청을 띄우는 것은 금지입니다. 필요한 일은 결과 보고에 적어 오케스트레이터에게 돌려보내세요.")
        allow()

    if tool == "Workflow":
        deny("다중 에이전트 워크플로(ultracode)는 이 설정에서 금지입니다. 대신 Agent 도구로 executor에게 차례로 위임하세요. "
             "정말 필요하면 사용자에게 먼저 확인하고 `%s off` 상태에서만 쓰세요." % TOGGLE)

    if tool in SPAWN_TOOLS:
        check_spawn(tool_input)

    if tool not in EDIT_TOOLS:
        allow()  # Bash 등은 통과 — 게이트는 Edit/Write 경로의 파일 수만 센다

    path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    if not path or not is_code(path):
        allow()  # 설정·문서 등 비코드 파일은 직접 수정 허용

    prompt = str(data.get("prompt_id") or "")
    if not prompt:
        allow()  # 턴 id가 없는 하네스 버전에서는 개수를 세지 않는다(잘못 막지 않게)
    session = re.sub(r"[^a-zA-Z0-9-]", "", str(data.get("session_id") or "nosession")) or "nosession"
    os.makedirs(GATE_STATE_DIR, exist_ok=True)
    gate_file = os.path.join(GATE_STATE_DIR, session + ".json")

    gate = {"prompt_id": prompt, "files": []}
    try:
        saved = json.loads(read_text(gate_file) or "")
        if saved.get("prompt_id") == prompt:
            gate = saved
        else:  # 새 턴 — 카운터 리셋 + 하루 넘은 세션 상태 정리
            now = time.time()
            for fn in os.listdir(GATE_STATE_DIR):
                p = os.path.join(GATE_STATE_DIR, fn)
                if fn.endswith(".json") and now - os.path.getmtime(p) > 86400:
                    os.remove(p)
    except (OSError, ValueError):
        pass

    if path in gate["files"]:
        allow()  # 같은 파일 재수정은 개수에 안 침
    if len(gate["files"]) < LIMIT:
        gate["files"].append(path)
        with open(gate_file, "w", encoding="utf-8") as f:
            json.dump(gate, f)
        allow()

    deny("이번 턴에 메인이 직접 수정한 코드 파일이 이미 %d개입니다 (%s). "
         "추가 코드 수정은 하청에 위임하세요: 구현·수정·테스트·리뷰 → executor, "
         "심층 추론·설계 대안·근본원인 → deep-reasoner, 단순 명령·조회 → runner. "
         "지금 하려던 수정(%s)을 목표·대상·완료 기준과 함께 Agent 도구로 위임하면 됩니다."
         % (LIMIT, ", ".join(gate["files"]), path))


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail-open
