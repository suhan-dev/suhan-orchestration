#!/usr/bin/env python3
# <codex>/oche/hooks/oche-gate.py — oche 강제 게이트 (Codex PreToolUse 훅, CLI와 ChatGPT 앱 공용)
#
# - 상태 파일 <codex>/.oche-state 가 on 이 아니면 즉시 통과한다. 등록은 hooks.json 에 1회, 동작 여부는 스위치가 정한다.
# - 메인이 한 턴(turn_id)에 apply_patch 로 직접 고치는 코드 파일을 2개까지만 허용하고 3개째부터 막는다.
#   셸을 통한 수정은 통과시킨다. turn_id 가 없으면 개수를 세지 않는다.
# - spawn_agent 는 executor·deep_reasoner·runner 만 허용한다. agent_type 을 비우거나 내장 하청(default·worker·explorer)을
#   고르면 부모 모델을 물려받으므로 막는다. 호출 때의 model·reasoning_effort 는 비어 있거나 그 역할의
#   설정값과 같을 때만 통과시킨다(모델 계열 이름에 기대지 않는다). ultra 강도는 늘 막는다.
# - 하청 안(입력에 agent_id/agent_type 이 있음)에서는 spawn_agent 만 막는다.
# - gate.json 의 subagent_fields 가 false 면(Codex 0.171.0 미만) 저하 모드: 하청 안 판별과 수정 개수 세기를 끈다.
# - 환경변수 ORCH_BRIDGE=1(다리 하청이 띄운 CLI 안)이면 spawn_agent 를 막고 수정 개수는 세지 않는다.
# 오류가 나면 통과시킨다(fail-open). Codex 문서도 훅을 완전한 강제 경계가 아니라 가드레일로 규정한다.
import json
import os
import re
import sys
import time

LIMIT = 2
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
OCHE_DIR = os.path.dirname(HOOKS_DIR)
CODEX_DIR = os.path.dirname(OCHE_DIR)
STATE_FILE = os.path.join(CODEX_DIR, ".oche-state")
GATE_STATE_DIR = os.path.join(OCHE_DIR, "state")
MODELS_FILE = os.path.join(OCHE_DIR, "models.json")
GATE_FILE = os.path.join(OCHE_DIR, "gate.json")
ROLE_OF_TYPE = {"executor": "executor", "deep_reasoner": "deep-reasoner", "runner": "runner"}
SPAWN_TOOLS = ("spawn_agent", "Agent")  # 실제 0.171.0 은 이름공간이 붙은 "collaborationspawn_agent" 로 보낸다


def is_spawn(tool):
    return tool in SPAWN_TOOLS or tool.endswith("spawn_agent")
PATCH_TOOLS = ("apply_patch", "Edit", "Write")
CODE_EXTS = {
    "ts", "tsx", "js", "jsx", "mjs", "cjs", "py", "go", "rs", "java", "kt",
    "kts", "swift", "c", "h", "cc", "cpp", "hpp", "cs", "rb", "php", "vue",
    "svelte", "astro", "css", "scss", "sass", "less", "html", "sh", "bash",
    "zsh", "sql", "lua", "dart", "scala", "ex", "exs", "zig", "ipynb", "ps1",
}
PATCH_PATH = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$")


def allow():
    sys.exit(0)


def deny(msg):
    sys.stderr.write("[oche 게이트] " + msg)
    sys.stderr.flush()
    sys.exit(2)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def is_code(path):
    return path.rsplit(".", 1)[-1].lower() in CODE_EXTS if "." in path else False


def patch_paths(patch):
    out = []
    for line in patch.splitlines():
        m = PATCH_PATH.match(line.strip())
        if m:
            out.append(m.group(1).strip())
    return out


def check_spawn(cfg, ti):
    toggle = str(cfg.get("command_name") or "oche")
    roles = cfg.get("roles") or {}
    stype = str(ti.get("agent_type") or "")
    model = str(ti.get("model") or "").strip()
    effort = str(ti.get("reasoning_effort") or "").strip().lower()
    if stype not in ROLE_OF_TYPE:
        deny("하청 타입 '%s'은(는) 금지입니다. agent_type을 비우거나 내장 하청(default·worker·explorer)을 고르면 "
             "부모 모델을 물려받습니다. agent_type에 executor·deep_reasoner·runner 중 하나를 넣으세요." % (stype or "(없음)"))
    role = roles.get(ROLE_OF_TYPE[stype]) or {}
    if model and model not in ({str(role.get(k) or "") for k in ("configured", "model")} - {""}):
        deny("하청 model 지정 '%s'은(는) 역할 %s의 설정과 다릅니다. 모델은 사용자가 터미널에서 `%s %s`로만 바꿉니다. "
             "model 지정을 빼세요." % (model, stype, toggle, ROLE_OF_TYPE[stype]))
    if effort == "ultra":
        deny("ultra는 강도가 아니라 다중 에이전트 모드라서 하청에 쓸 수 없습니다. reasoning_effort 지정을 빼세요.")
    if effort and effort not in ({str(role.get(k) or "").lower() for k in ("configured_effort", "effort")} - {""}):
        deny("하청 reasoning_effort 지정 '%s'은(는) 역할 %s의 설정과 다릅니다. 강도는 사용자가 터미널에서 `%s %s`로만 "
             "바꿉니다. effort 지정을 빼세요." % (effort, stype, toggle, ROLE_OF_TYPE[stype]))
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
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            state = f.read().strip()
    except OSError:
        state = "off"
    if state != "on":
        allow()

    data = json.loads(raw or "{}")
    tool = str(data.get("tool_name") or "")
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        ti = {}
    cfg = read_json(MODELS_FILE)
    subagent_fields = read_json(GATE_FILE).get("subagent_fields", True) is not False

    if os.environ.get("ORCH_BRIDGE") == "1":
        if is_spawn(tool):
            deny("다리 실행 중에는 하청을 띄우지 않고 직접 수행합니다.")
        allow()

    if subagent_fields and (data.get("agent_id") or data.get("agent_type")):
        if is_spawn(tool):
            deny("하청 안에서 다시 하청(spawn_agent)을 띄우는 것은 금지입니다. "
                 "필요한 일은 결과 보고에 적어 오케스트레이터에게 돌려보내세요.")
        allow()

    if is_spawn(tool):
        check_spawn(cfg, ti)

    if tool not in PATCH_TOOLS or not subagent_fields:
        allow()  # 저하 모드에서는 하청의 수정과 구별할 수 없으므로 세지 않는다
    patch = ti.get("command")
    if not isinstance(patch, str):
        allow()
    code = list(dict.fromkeys(p for p in patch_paths(patch) if is_code(p)))
    if not code:
        allow()  # 설정·문서 등 비코드 파일은 직접 수정 허용
    turn = str(data.get("turn_id") or "")
    if not turn:
        allow()

    session = re.sub(r"[^a-zA-Z0-9-]", "", str(data.get("session_id") or "nosession")) or "nosession"
    os.makedirs(GATE_STATE_DIR, exist_ok=True)
    gate_file = os.path.join(GATE_STATE_DIR, session + ".json")
    gate = {"turn_id": turn, "files": []}
    saved = read_json(gate_file)
    if saved.get("turn_id") == turn:
        gate = saved
    else:  # 새 턴 — 카운터 리셋 + 하루 넘은 세션 상태 정리
        now = time.time()
        try:
            for fn in os.listdir(GATE_STATE_DIR):
                p = os.path.join(GATE_STATE_DIR, fn)
                if fn.endswith(".json") and now - os.path.getmtime(p) > 86400:
                    os.remove(p)
        except OSError:
            pass

    new = [p for p in code if p not in gate["files"]]
    if not new:
        allow()  # 같은 파일 재수정은 개수에 안 침
    if len(gate["files"]) + len(new) <= LIMIT:
        gate["files"].extend(new)
        with open(gate_file, "w", encoding="utf-8") as f:
            json.dump(gate, f)
        allow()

    deny("메인이 이번 턴에 직접 고친 코드 파일은 %d개이고, 이 패치가 %d개를 더합니다 (%s). "
         "메인의 직접 코드 수정은 턴당 %d개까지입니다. 이 수정은 spawn_agent로 위임하세요: "
         "구현·수정·테스트·리뷰 → executor, 심층 추론·설계 대안·근본원인 → deep_reasoner, 단순 명령·조회 → runner."
         % (len(gate["files"]), len(new), ", ".join(new), LIMIT))


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
