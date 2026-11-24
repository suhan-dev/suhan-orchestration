#!/usr/bin/env python3
"""oche — 하청 오케스트레이션 스위치·관리 명령 (suhan-orchestration).

설치 뒤에는 ~/.oche/assets/oche/bin/oche.py 에 있고, ~/.local/bin/oche(Windows는 oche.cmd·oche.ps1) 래퍼가 부른다.
install.py 도 이 파일을 라이브러리로 불러 쓴다. 파이썬 3.8+ 표준 라이브러리만 쓴다.
"""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

VERSION = "1.1.0"
PROJECT = "suhan-orchestration"
WRAPPER_MARK = "oche-wrapper"
DEFAULT_NAME = "oche"
ROLES = ("executor", "deep-reasoner", "runner")
ROLE_ALIASES = {"executor": "executor", "exec": "executor", "deep-reasoner": "deep-reasoner",
                "deep_reasoner": "deep-reasoner", "deep": "deep-reasoner", "runner": "runner"}
ROLE_DESC = {"executor": "범위가 정해진 실행 전담.", "deep-reasoner": "국소적으로 어려운 기술 난제 전담.",
             "runner": "판단이 필요 없는 잡무 전담."}
TARGETS = ("claude", "codex")
TARGET_LABEL = {"claude": "Claude Code", "codex": "Codex"}
CLAUDE_EFFORTS = ["low", "medium", "high", "xhigh", "max"]
CODEX_DEFAULT_EFFORTS = ["low", "medium", "high", "xhigh", "max"]
EFFORT_NICK = {"xhigh": "xhigh (extra)", "max": "max (Claude판 ultra)"}
DEFAULT_ROLES = {
    "claude": {"executor": {"model": "opus", "effort": "high"},
               "deep-reasoner": {"model": "opus", "effort": "xhigh"},
               "runner": {"model": "haiku", "effort": "low"}},
    "codex": {"executor": {"model": "latest:sol", "effort": "high"},
              "deep-reasoner": {"model": "latest:sol", "effort": "xhigh"},
              "runner": {"model": "latest:terra", "effort": "low"}},
}
MIN_CODEX = (0, 171, 0)
MAC_APP_ENGINE = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"
AGENTS_BEGIN = "<!-- oche:begin (on/off 스위치가 관리하는 구역입니다. 손으로 고치지 마세요) -->"
AGENTS_END = "<!-- oche:end -->"
AGENTS_BLOCK = re.compile(r"\n*<!-- oche:begin[^\n]*-->.*?<!-- oche:end -->\n?", re.S)
AGENTS_MAX_BYTES = 32 * 1024
PATH_MARK = "# oche: ~/.local/bin을 PATH에 추가 (suhan-orchestration)"
BRIDGE_PREFIX = "너는 하청 실행자다. 하청을 띄우지 말고 직접 수행하라.\n\n"


def setup_utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


# ======================================================================
# 경로·플랫폼
# ======================================================================

def is_windows():
    return os.name == "nt" or os.environ.get("ORCH_FORCE_WINDOWS") == "1"


def home():
    return os.path.expanduser("~")


def oche_home():
    return os.environ.get("OCHE_HOME") or os.path.join(home(), ".oche")


def claude_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(home(), ".claude")


def codex_dir():
    return os.environ.get("CODEX_HOME") or os.path.join(home(), ".codex")


def local_bin():
    return os.path.join(home(), ".local", "bin")


def asset_root():
    """claude/·codex/ 자산이 있는 폴더. 저장소에서는 <repo>/oche, 설치본에서는 ~/.oche/assets/oche."""
    return os.path.dirname(os.path.dirname(os.path.realpath(os.path.abspath(__file__))))


def cli_path():
    return os.path.join(oche_home(), "bin", "oche.py")


def tilde(p):
    h = home()
    p = str(p)
    if p == h:
        return "~"
    if p.startswith(h + os.sep) or p.startswith(h + "/"):
        return "~" + p[len(h):]
    return p


def fwd(p):
    return str(p).replace("\\", "/")


def same_path(a, b):
    na = os.path.normcase(os.path.normpath(os.path.abspath(a)))
    nb = os.path.normcase(os.path.normpath(os.path.abspath(b)))
    return na == nb


def posix_python():
    return shutil.which("python3") or sys.executable


def win_py_launcher():
    return shutil.which("py") is not None


def win_python_prefix():
    """Windows에서 파이썬을 부르는 앞부분. py 런처 우선, 없으면 sys.executable."""
    if win_py_launcher():
        return "py -3"
    return '"%s"' % sys.executable


def stamp():
    return time.strftime("%Y%m%d-%H%M%S")


# ======================================================================
# 파일 다루기
# ======================================================================

def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, ValueError):
        return None


def atomic_write(path, text, mode=None, newline="\n"):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".oche-tmp-", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        elif os.path.isfile(path):
            try:
                os.chmod(tmp, os.stat(path).st_mode & 0o7777)
            except OSError:
                pass
        else:
            os.chmod(tmp, 0o644)
        if os.path.islink(path):
            os.remove(path)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def write_user_file(path, text):
    """사용자 파일(CLAUDE.md·settings.json 등)은 심링크면 원본을 고친다."""
    atomic_write(os.path.realpath(path), text)


def read_json(path, default=None):
    t = read_text(path)
    if t is None:
        return default
    try:
        return json.loads(t)
    except ValueError:
        return default


def write_json(path, data):
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


class Backup(object):
    """한 번의 실행에서 바꾸는 원래 파일을 .bak_oche_<시각> 으로 한 번씩 복사해 둔다."""

    def __init__(self):
        self.ts = stamp()
        self.done = {}

    def __call__(self, path):
        if not os.path.exists(path):
            return None
        real = os.path.realpath(path)
        if real in self.done:
            return self.done[real]
        dst = path + ".bak_oche_" + self.ts
        if os.path.isdir(real):
            shutil.copytree(real, dst)
        else:
            shutil.copy2(real, dst)
        self.done[real] = dst
        return dst


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def log(line):
    try:
        os.makedirs(oche_home(), exist_ok=True)
        with open(os.path.join(oche_home(), "log.txt"), "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line))
    except OSError:
        pass


# ======================================================================
# 설정
# ======================================================================

def config_path():
    return os.path.join(oche_home(), "config.json")


def load_config():
    cfg = read_json(config_path(), {}) or {}
    cfg.setdefault("targets", {})
    return cfg


def save_config(cfg):
    write_json(config_path(), cfg)


def cmd_name(cfg=None):
    if cfg is None:
        cfg = load_config()
    return cfg.get("command_name") or DEFAULT_NAME


def installed_targets(cfg):
    return [t for t in TARGETS if t in cfg.get("targets", {})]


def role_cfg(cfg, target, role):
    roles = cfg["targets"][target].setdefault("roles", {})
    rc = roles.get(role)
    if not isinstance(rc, dict) or not rc.get("model") or not rc.get("effort"):
        rc = dict(DEFAULT_ROLES[target][role])
        roles[role] = rc
    return rc


# ======================================================================
# 감지
# ======================================================================

VERSION_RE = re.compile(r"(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)")


def run_version(exe, timeout=10):
    if not exe:
        return None
    try:
        p = subprocess.run([exe, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           stdin=subprocess.DEVNULL, timeout=timeout)
        out = (p.stdout or b"").decode("utf-8", "replace") + (p.stderr or b"").decode("utf-8", "replace")
        m = VERSION_RE.search(out)
        return m.group(1) if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def vtuple(v):
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", str(v or ""))
    return tuple(int(x) for x in m.groups()) if m else None


def app_engine_path():
    env = os.environ.get("OCHE_CODEX_APP_ENGINE")
    if env is not None:
        return env if env and os.path.isfile(env) else None
    if sys.platform == "darwin" and os.path.isfile(MAC_APP_ENGINE):
        return MAC_APP_ENGINE
    if os.name == "nt":
        import glob
        pats = []
        for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if not base:
                continue
            for mid in ("Programs\\*", "*", "*\\app-*", "Programs\\*\\app-*"):
                pats.append(os.path.join(base, mid, "resources", "codex-cli", "bin", "codex.exe"))
        found = []
        for p in pats:
            try:
                found.extend(glob.glob(p))
            except Exception:
                pass
        if found:
            return sorted(found)[-1]
    return None


def detect():
    cd, xd = claude_dir(), codex_dir()
    cexe = shutil.which("claude")
    xexe = shutil.which("codex")
    app = app_engine_path()
    info = {
        "claude": {"dir": cd, "dir_exists": os.path.isdir(cd), "exe": cexe, "version": run_version(cexe)},
        "codex": {"dir": xd, "dir_exists": os.path.isdir(xd), "exe": xexe, "version": run_version(xexe),
                  "app_engine": app, "app_version": run_version(app)},
    }
    info["claude"]["detected"] = bool(info["claude"]["dir_exists"] or cexe)
    info["codex"]["detected"] = bool(info["codex"]["dir_exists"] or xexe or app)
    return info


def codex_subagent_fields(info):
    for v in (info.get("version"), info.get("app_version")):
        t = vtuple(v)
        if t is not None and t < MIN_CODEX:
            return False
    return True


# ---------- Claude 최신표 (실행 파일 안의 latest_per_family) ----------

LATEST_RE = re.compile(rb"latest_per_family:\{([^}]{0,600})\}")
PAIR_RE = re.compile(rb'([A-Za-z]+)\s*:\s*"([^"]+)"')


CLAUDE_ID_RE = re.compile(r"^claude-([a-z]+)-(\d+(?:[-.]\d+)*)")


def claude_id_version(mid):
    m = CLAUDE_ID_RE.match(mid or "")
    if not m:
        return None
    nums = re.findall(r"\d+", m.group(2))
    return m.group(1), tuple(int(x) for x in nums[:2])


# ======================================================================
# Codex 모델 목록 (sync.py 를 라이브러리로 쓴다)
# ======================================================================

_SYNC = None


def sync_mod():
    global _SYNC
    if _SYNC is None:
        path = os.path.join(asset_root(), "codex", "sync.py")
        spec = importlib.util.spec_from_file_location("oche_codex_sync", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _SYNC = mod
    return _SYNC


def live_models(exe, timeout=20):
    if not exe:
        return None
    try:
        p = subprocess.run([exe, "debug", "models"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           stdin=subprocess.DEVNULL, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if p.returncode != 0:
        return None
    return sync_mod().parse_models_json((p.stdout or b"").decode("utf-8", "replace"))


def codex_models(xdir, exe=None, app_engine=None, live=True, app_version=None):
    """(출처, 목록, 앱 캐시). 실시간 목록 → 가장 최근 캐시 순서."""
    s = sync_mod()
    if app_version is None and app_engine:
        app_version = run_version(app_engine)
    app = s.app_cache(xdir, engine_version=app_version)
    if live:
        for e in (exe, app_engine):
            m = live_models(e)
            if m:
                return ("live:" + os.path.basename(e) + (" (앱 엔진)" if e == app_engine and e != exe else ""), m, app)
    c = s.newest_cache(xdir)
    if c:
        return ("cache:" + os.path.basename(c["path"]), c["models"], app)
    if not live:
        return codex_models(xdir, exe, app_engine, live=True, app_version=app_version)
    return (None, [], app)


def codex_cached_models(xdir):
    s = sync_mod()
    c = s.newest_cache(xdir)
    return c["models"] if c else []


def resolve_codex_roles(roles_cfg, models, app):
    s = sync_mod()
    res, warnings, failed = {}, [], []
    for role in ROLES:
        rc = roles_cfg[role]
        r = s.resolve_role(rc["model"], rc["effort"], models, app, warnings)
        if r is None:
            failed.append(role)
        else:
            res[role] = r
    return res, warnings, failed


# ======================================================================
# 모델 목록 표 (~/.oche/catalog.json) — 계열 이름을 코드에 박지 않는다
# ======================================================================

BUILTIN_CLAUDE_FAMILIES = ("fable", "opus", "sonnet", "haiku")  # 실행 파일을 못 읽을 때만 쓰는 기본값


def catalog_path():
    return os.path.join(oche_home(), "catalog.json")


def load_catalog():
    c = read_json(catalog_path(), {}) or {}
    return c if isinstance(c, dict) else {}


def scan_claude_latest(exe):
    """claude 실행 파일 안의 latest_per_family:{계열:"ID",...} 를 읽는다. 실패하면 {}."""
    if not exe:
        return {}
    try:
        real = os.path.realpath(exe)
        if os.path.getsize(real) > 2 * 1024 ** 3:
            return {}
        with open(real, "rb") as f:
            tail = b""
            while True:
                chunk = f.read(8 * 1024 * 1024)
                if not chunk:
                    return {}
                buf = tail + chunk
                m = LATEST_RE.search(buf)
                if m:
                    return {k.decode(): v.decode() for k, v in PAIR_RE.findall(m.group(1))}
                tail = buf[-700:]
    except OSError:
        return {}


def build_claude_catalog(exe, version):
    fams = scan_claude_latest(exe)
    source = "claude 실행 파일"
    if not fams:
        fams = {f: None for f in BUILTIN_CLAUDE_FAMILIES}
        source = "builtin"
    ids = [v for v in fams.values() if v]
    return {"families": fams, "models": ids, "efforts": {m: list(CLAUDE_EFFORTS) for m in ids},
            "source": source, "tool_version": version, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}


def refresh_catalog(cfg, which=None, live=True):
    """대상별 목록 표를 다시 만든다. 새 계열·새 최신 알림 목록을 돌려준다(역할은 바꾸지 않음)."""
    s = sync_mod()
    notices = []
    for target in installed_targets(cfg):
        if which and target != which:
            continue
        t = cfg["targets"][target]
        if target == "claude":
            exe = shutil.which("claude") or t.get("exe")
            entry = build_claude_catalog(exe, run_version(exe))
            old = (load_catalog().get("claude") or {}).get("families") or {}
            for fam, mid in sorted(entry["families"].items()):
                if old and fam not in old:
                    notices.append("Claude 새 계열 발견: %s (%s)" % (fam, mid or "?"))
                elif old.get(fam) and mid and old[fam] != mid:
                    notices.append("Claude 새 최신: %s %s → %s" % (fam, old[fam], mid))
            s.update_catalog("claude", entry, merge=False)
        else:
            exe = shutil.which("codex") or t.get("exe")
            ver = run_version(exe) or run_version(app_engine_path())
            source, models, _ = codex_models(t["dir"], exe, app_engine_path(), live=live)
            if not models:
                continue
            entry = s.catalog_entry(models, source)
            entry["tool_version"] = ver
            notices.extend("Codex " + n for n in s.update_catalog("codex", entry, merge=False))
    return notices


def ensure_catalog(cfg, quiet=False):
    """기록된 도구 버전이 지금과 다르거나 표가 없으면 자동으로 갱신한다."""
    cat = load_catalog()
    out = []
    for target in installed_targets(cfg):
        t = cfg["targets"][target]
        exe = shutil.which(target) or t.get("exe")
        ver = run_version(exe) if exe else None
        if target == "codex" and not ver:
            ver = run_version(app_engine_path())
        entry = cat.get(target)
        if not entry or entry.get("tool_version") != ver:
            out.extend(refresh_catalog(cfg, target, live=True))
    if not quiet:
        for n in out:
            print("알림: " + n + " — 역할을 옮기려면 `%s <역할>`로 직접 고르세요." % cmd_name(cfg))
    return out


def catalog_families(target):
    fams = (load_catalog().get(target) or {}).get("families")
    if isinstance(fams, dict) and fams:
        return fams
    if target == "claude":
        return {f: None for f in BUILTIN_CLAUDE_FAMILIES}
    return {}


def catalog_efforts(target, model_id):
    e = ((load_catalog().get(target) or {}).get("efforts") or {}).get(model_id)
    return [x for x in e if x != "ultra"] if isinstance(e, list) and e else None


# ======================================================================
# Claude 대상
# ======================================================================

def cpaths(d):
    o = os.path.join(d, "oche")
    return {
        "dir": d, "oche": o, "rules": os.path.join(o, "rules.md"), "empty": os.path.join(o, "empty.md"),
        "active": os.path.join(o, "active.md"), "gate": os.path.join(o, "hooks", "oche-gate.py"),
        "state_dir": os.path.join(o, "state"), "roles": os.path.join(o, "roles.json"),
        "manifest": os.path.join(o, "manifest.json"), "src_agents": os.path.join(o, "agents"),
        "agents": os.path.join(d, "agents"), "state": os.path.join(d, ".oche-state"),
        "claude_md": os.path.join(d, "CLAUDE.md"), "settings": os.path.join(d, "settings.json"),
    }


def claude_loader_line(d):
    if same_path(d, os.path.join(home(), ".claude")):
        return "@~/.claude/oche/active.md"
    return "@" + fwd(os.path.join(d, "oche", "active.md"))


def claude_loader_comment(name):
    return "<!-- oche-loader: 토글은 %s on/off, 이 줄은 그대로 둡니다 -->" % name


def has_loader(text):
    return any(l.strip().startswith("@") and l.strip().endswith("oche/active.md") for l in (text or "").splitlines())


def bridge_cmd_text():
    cli = cli_path()
    if is_windows():
        return "%s \"%s\" bridge" % (win_python_prefix(), fwd(cli))
    return "\"%s\" \"%s\" bridge" % (posix_python(), cli)


def claude_role_entry(rc):
    model, effort = rc["model"], rc["effort"]
    if model.startswith("codex:"):
        return {"configured": model, "configured_effort": effort, "model": "haiku", "effort": "low",
                "bridge": {"model": model.split(":", 1)[1], "effort": effort}}
    return {"configured": model, "configured_effort": effort, "model": model, "effort": effort, "bridge": None}


def render_claude_agent(role, rc):
    entry = claude_role_entry(rc)
    if entry["bridge"]:
        t = read_text(os.path.join(asset_root(), "claude", "bridge.md"))
        rep = {"@@NAME@@": role, "@@TARGET_MODEL@@": entry["bridge"]["model"], "@@TARGET_EFFORT@@": entry["bridge"]["effort"],
               "@@ROLE_DESC@@": ROLE_DESC[role], "@@BRIDGE_CMD@@": bridge_cmd_text(), "@@ROLE@@": role}
    else:
        t = read_text(os.path.join(asset_root(), "claude", "agents", role + ".md"))
        rep = {"@@MODEL@@": entry["model"], "@@EFFORT@@": entry["effort"]}
    for k, v in rep.items():
        t = t.replace(k, v)
    return t


def claude_agent_owned(p, role):
    dst = os.path.join(p["agents"], role + ".md")
    if not os.path.lexists(dst):
        return True
    if os.path.islink(dst):
        return False
    text = read_text(dst)
    if text is None:
        return False
    man = read_json(p["manifest"], {}) or {}
    if man.get(role + ".md") == sha256(text):
        return True
    return text == read_text(os.path.join(p["src_agents"], role + ".md"))


def write_claude_agents(p, cfg, roles=ROLES, force=False, backup=None):
    """정의 파일을 oche 원본과 <claude>/agents 복사본으로 쓴다. 남의 파일이면 건너뛰고 목록을 돌려준다."""
    skipped = []
    man = read_json(p["manifest"], {}) or {}
    for role in roles:
        rc = role_cfg(cfg, "claude", role)
        text = render_claude_agent(role, rc)
        owned = claude_agent_owned(p, role)
        dst = os.path.join(p["agents"], role + ".md")
        if not owned and not force:
            skipped.append(dst)
            continue
        if not owned and backup is not None:
            backup(dst)
        atomic_write(os.path.join(p["src_agents"], role + ".md"), text)
        atomic_write(dst, text)
        man[role + ".md"] = sha256(text)
    write_json(p["manifest"], man)
    write_claude_roles(p, cfg)
    return skipped


def gate_extras(cfg, target):
    """게이트가 함께 읽는 값(메시지에 쓰는 명령 이름)."""
    return {"command_name": cmd_name(cfg)}


def write_claude_roles(p, cfg):
    roles = {r: claude_role_entry(role_cfg(cfg, "claude", r)) for r in ROLES}
    data = {"roles": roles, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    data.update(gate_extras(cfg, "claude"))
    write_json(p["roles"], data)


def claude_set_switch(p, on):
    src = p["rules"] if on else p["empty"]
    atomic_write(p["active"], read_text(src) or "")
    atomic_write(p["state"], "on\n" if on else "off\n")


def claude_state(p):
    return (read_text(p["state"]) or "off").strip() == "on"


def claude_hook_entry(p):
    gate = p["gate"]
    if is_windows():
        if win_py_launcher():
            return {"type": "command", "command": 'py -3 "%s"' % fwd(gate)}
        return {"type": "command", "command": '& "%s" "%s"' % (fwd(sys.executable), fwd(gate)), "shell": "powershell"}
    return {"type": "command", "command": '"%s" "%s"' % (posix_python(), gate)}


CLAUDE_MATCHER = "Write|Edit|NotebookEdit|MultiEdit|Bash|Workflow|Agent|Task"


# ======================================================================
# 훅 항목 병합 (settings.json·hooks.json 공용)
# ======================================================================

def hook_is(h, marker):
    return isinstance(h, dict) and (marker in str(h.get("command", "")) or marker in str(h.get("commandWindows", "")))


def upsert_hook(entries, matcher, hook, marker):
    entries = entries if isinstance(entries, list) else []
    out, placed = [], False
    for e in entries:
        hooks = e.get("hooks") if isinstance(e, dict) and isinstance(e.get("hooks"), list) else None
        if hooks is None or not any(hook_is(h, marker) for h in hooks):
            out.append(e)
            continue
        rest = [h for h in hooks if not hook_is(h, marker)]
        if rest:
            ne = dict(e)
            ne["hooks"] = rest
            out.append(ne)
        if not placed:
            out.append({"matcher": matcher, "hooks": [hook]})
            placed = True
    if not placed:
        out.append({"matcher": matcher, "hooks": [hook]})
    return out


def remove_hook(entries, marker):
    out = []
    for e in entries if isinstance(entries, list) else []:
        hooks = e.get("hooks") if isinstance(e, dict) and isinstance(e.get("hooks"), list) else None
        if hooks is None or not any(hook_is(h, marker) for h in hooks):
            out.append(e)
            continue
        rest = [h for h in hooks if not hook_is(h, marker)]
        if rest:
            ne = dict(e)
            ne["hooks"] = rest
            out.append(ne)
    return out


def has_hook(entries, marker):
    for e in entries if isinstance(entries, list) else []:
        if isinstance(e, dict) and any(hook_is(h, marker) for h in (e.get("hooks") or [])):
            return True
    return False


# ======================================================================
# Codex 대상
# ======================================================================

def xpaths(d):
    o = os.path.join(d, "oche")
    s = sync_mod()
    return {
        "dir": d, "oche": o, "rules": os.path.join(o, "rules.md"), "gate": os.path.join(o, "hooks", "oche-gate.py"),
        "sync": os.path.join(o, "hooks", "oche-sync.py"), "state_dir": os.path.join(o, "state"),
        "models": os.path.join(o, "models.json"), "gate_json": os.path.join(o, "gate.json"),
        "state": os.path.join(d, ".oche-state"), "hooks": os.path.join(d, "hooks.json"),
        "override": os.path.join(d, "AGENTS.override.md"), "agents_md": os.path.join(d, "AGENTS.md"),
        "config_toml": os.path.join(d, "config.toml"),
        "tomls": {r: os.path.join(d, "agents", s.TOML_FILE[r]) for r in ROLES},
    }


def codex_toml_owned(path):
    if not os.path.lexists(path):
        return True
    t = read_text(path)
    return t is not None and not os.path.islink(path) and sync_mod().MARKER in t


def toml_escape_path(s):
    return fwd(s).replace('"', '\\"')


def render_codex_toml(role, res, name):
    s = sync_mod()
    if res.get("bridge"):
        t = read_text(os.path.join(asset_root(), "codex", "bridge.toml.in"))
        bcmd = bridge_cmd_text().replace("\\", "/")
        rep = {"@@NAME@@": s.AGENT_NAME[role], "@@TARGET_MODEL@@": res["bridge"]["model"],
               "@@TARGET_EFFORT@@": res["bridge"]["effort"], "@@ROLE_DESC@@": ROLE_DESC[role],
               "@@BRIDGE_CMD@@": bcmd, "@@ROLE@@": role}
    else:
        t = read_text(os.path.join(asset_root(), "codex", "agents", role + ".toml.in"))
        rep = {}
    rep.update({"@@MODEL@@": res["model"], "@@EFFORT@@": res["effort"], "@@CMD@@": name})
    for k, v in rep.items():
        t = t.replace(k, v)
    return t


def write_codex_agents(p, cfg, res, roles=ROLES, force=False, backup=None, source=None):
    name = cmd_name(cfg)
    skipped = []
    for role in roles:
        path = p["tomls"][role]
        if not codex_toml_owned(path):
            if not force:
                skipped.append(path)
                continue
            if backup is not None:
                backup(path)
        atomic_write(path, render_codex_toml(role, res[role], name))
    data = read_json(p["models"], {}) or {}
    data.setdefault("roles", {})
    for role in roles:
        data["roles"][role] = res[role]
    data["command_name"] = name
    data["auto_update"] = cfg["targets"]["codex"].get("auto_update", True)
    data["main_model"] = cfg["targets"]["codex"].get("main_model")
    data["app_version"] = cfg["targets"]["codex"].get("app_version")
    data.update(gate_extras(cfg, "codex"))
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    if source:
        data["source"] = source
    write_json(p["models"], data)
    return skipped


def agents_target(p):
    t = read_text(p["override"])
    return p["override"] if t and t.strip() else p["agents_md"]


def strip_block(path):
    t = read_text(path)
    if t is None or "<!-- oche:begin" not in t:
        return False
    t = AGENTS_BLOCK.sub("\n", t).strip("\n")
    write_user_file(path, t + "\n" if t else "")
    return True


def codex_set_switch(p, on):
    strip_block(p["override"])
    strip_block(p["agents_md"])
    if on:
        rules = read_text(p["rules"]) or ""
        path = agents_target(p)
        t = (read_text(path) or "").rstrip("\n")
        write_user_file(path, (t + "\n\n" if t else "") + AGENTS_BEGIN + "\n" + rules.strip("\n") + "\n" + AGENTS_END + "\n")
    atomic_write(p["state"], "on\n" if on else "off\n")


def codex_state(p):
    return (read_text(p["state"]) or "off").strip() == "on"


def codex_hook_entries(p):
    def entry(script, status):
        if is_windows():
            posix = 'python3 "%s"' % fwd(script)
        else:
            posix = '"%s" "%s"' % (posix_python(), script)
        win = '%s "%s"' % (win_python_prefix(), script.replace("/", "\\") if is_windows() else script)
        return {"type": "command", "command": posix, "commandWindows": win, "timeout": 10, "statusMessage": status}
    return entry(p["gate"], "oche 게이트 확인"), entry(p["sync"], "oche 하청 모델 확인")


CODEX_PRE_MATCHER = "^(apply_patch|.*spawn_agent|Agent)$"  # 실제 도구 이름: collaborationspawn_agent
CODEX_START_MATCHER = "startup|resume"


# ======================================================================
# 래퍼·PATH
# ======================================================================

def wrapper_files(name, bindir=None):
    b = bindir or local_bin()
    if is_windows():
        return [os.path.join(b, name + ".cmd"), os.path.join(b, name + ".ps1")]
    return [os.path.join(b, name)]


def is_our_wrapper(path):
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return False
    return WRAPPER_MARK.encode() in head


def name_conflicts(name, bindir=None):
    b = bindir or local_bin()
    out = []
    exts = ["", ".cmd", ".ps1", ".exe", ".bat"] if is_windows() else [""]
    for ext in exts:
        p = os.path.join(b, name + ext)
        if os.path.lexists(p) and not is_our_wrapper(p):
            out.append(p)
    w = shutil.which(name)
    if w and not is_our_wrapper(w) and not any(same_path(w, x) for x in out):
        out.append(w)
    return out


NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
NAME_CANDIDATES = ("orch", "oche2", "oche-ai")


def suggest_names(exclude=()):
    return [c for c in NAME_CANDIDATES if c not in exclude and not name_conflicts(c)]


def write_wrappers(name):
    b = local_bin()
    os.makedirs(b, exist_ok=True)
    made = []
    cli = cli_path()
    if is_windows():
        default_layout = same_path(oche_home(), os.path.join(home(), ".oche"))
        cmd_target = "%~dp0..\\..\\.oche\\bin\\oche.py" if default_layout else cli.replace("/", "\\")
        ps_target = "$PSScriptRoot\\..\\..\\.oche\\bin\\oche.py" if default_layout else cli.replace("/", "\\")
        prefix = win_python_prefix()
        cmd = ("@echo off\r\nrem %s (%s): %s 명령. 지우려면 install.py uninstall.\r\n%s \"%s\" %%*\r\n"
               % (WRAPPER_MARK, PROJECT, name, prefix, cmd_target))
        ps = ("# %s (%s): %s 명령. 지우려면 install.py uninstall.\n& %s \"%s\" @args\nexit $LASTEXITCODE\n"
              % (WRAPPER_MARK, PROJECT, name, prefix, ps_target))
        atomic_write(os.path.join(b, name + ".cmd"), cmd, newline="")
        atomic_write(os.path.join(b, name + ".ps1"), ps)
        made = [os.path.join(b, name + ".cmd"), os.path.join(b, name + ".ps1")]
    else:
        sh = ("#!/bin/sh\n# %s (%s): %s 명령. 지우려면 install.py uninstall.\nexec \"%s\" \"%s\" \"$@\"\n"
              % (WRAPPER_MARK, PROJECT, name, posix_python(), cli))
        atomic_write(os.path.join(b, name), sh, mode=0o755)
        made = [os.path.join(b, name)]
    return made


def remove_wrappers(name):
    gone = []
    b = local_bin()
    for ext in ("", ".cmd", ".ps1"):
        p = os.path.join(b, name + ext)
        if os.path.isfile(p) and is_our_wrapper(p):
            os.remove(p)
            gone.append(p)
    return gone


def path_has_local_bin():
    b = local_bin()
    for e in os.environ.get("PATH", "").split(os.pathsep):
        if e and same_path(os.path.expanduser(e), b):
            return True
    return False


def shell_rc():
    sh = os.path.basename(os.environ.get("SHELL", ""))
    if sh == "zsh":
        return os.path.join(home(), ".zshrc")
    if sh == "bash":
        return os.path.join(home(), ".bashrc")
    return None


def add_to_path(backup):
    if path_has_local_bin():
        return "이미 PATH에 있습니다: " + tilde(local_bin())
    if is_windows():
        b = local_bin()
        ps = ("$p=[Environment]::GetEnvironmentVariable('Path','User'); if(-not $p){$p=''}; "
              "if(-not (($p -split ';') -contains '%s')){[Environment]::SetEnvironmentVariable('Path', "
              "(($p.TrimEnd(';') + ';%s').TrimStart(';')), 'User')}" % (b, b))
        if os.name != "nt":
            return "(Windows 흉내 모드: 사용자 PATH 추가 명령은 실행하지 않음) powershell -NoProfile -Command \"%s\"" % ps
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, timeout=30)
            return "사용자 PATH에 %s를 추가했습니다(시스템 PATH는 그대로). 새 터미널부터 적용됩니다." % b
        except (OSError, subprocess.SubprocessError) as e:
            return "사용자 PATH 추가 실패: %s" % e
    rc = shell_rc()
    if not rc:
        return "쓰는 셸을 알 수 없어 PATH를 바꾸지 않았습니다. 셸 설정 파일에 export PATH=\"$HOME/.local/bin:$PATH\"를 넣으세요."
    t = read_text(rc) or ""
    if PATH_MARK in t:
        return "이미 %s에 PATH 줄이 있습니다(새 터미널부터 적용)." % tilde(rc)
    backup(rc)
    write_user_file(rc, t + ("" if not t or t.endswith("\n") else "\n") + "\n" + PATH_MARK + "\nexport PATH=\"$HOME/.local/bin:$PATH\"\n")
    return "%s에 PATH 줄을 덧붙였습니다. 새 터미널부터 적용됩니다." % tilde(rc)


def remove_path_lines(backup):
    out = []
    for rc in (os.path.join(home(), ".zshrc"), os.path.join(home(), ".bashrc")):
        t = read_text(rc)
        if not t or PATH_MARK not in t:
            continue
        lines = t.split("\n")
        keep, skip = [], False
        for l in lines:
            if l == PATH_MARK:
                skip = True
                if keep and keep[-1] == "":
                    keep.pop()
                continue
            if skip and l.startswith("export PATH=\"$HOME/.local/bin:$PATH\""):
                skip = False
                continue
            skip = False
            keep.append(l)
        backup(rc)
        write_user_file(rc, "\n".join(keep))
        out.append(rc)
    return out


# ======================================================================
# 역할 값 다루기 (모델·강도)
# ======================================================================

class UserError(Exception):
    pass


def norm_role(s):
    r = ROLE_ALIASES.get(str(s or "").strip().lower())
    if not r:
        raise UserError("역할은 executor·deep-reasoner·runner 중 하나입니다: %s" % s)
    return r


CLAUDE_ID = re.compile(r"^claude-[a-z0-9][a-z0-9.\-]*$")


def norm_model(target, value, cfg):
    v = str(value or "").strip()
    lv = v.lower()
    if not v:
        raise UserError("모델이 비어 있습니다.")
    cf = catalog_families("claude")
    xf = catalog_families("codex")
    if target == "claude":
        if lv.startswith("claude:"):
            return norm_model("claude", v.split(":", 1)[1], cfg)
        if lv in cf or CLAUDE_ID.match(lv):
            return lv
        if lv.startswith("codex:") or lv.startswith("gpt-"):
            rest = (v.split(":", 1)[1] if lv.startswith("codex:") else v).strip().lower()
            if rest.startswith("latest:"):
                rest = rest.split(":", 1)[1]
            if rest in xf:
                rest = xf[rest]
            elif not rest.startswith("gpt-"):
                raise UserError("Codex 모델 목록에 '%s' 계열이 없습니다. codex:<전체 ID>로 적거나 `%s update` 뒤 다시 하세요."
                                % (rest, cmd_name(cfg)))
            return "codex:" + rest
        raise UserError("Claude 대상의 모델은 %s|claude-…(전체 ID)|codex:<ID 또는 계열>(다리) 중 하나입니다: %s"
                        % ("|".join(cf), v))
    if lv.startswith("codex:"):
        return norm_model("codex", v.split(":", 1)[1], cfg)
    if lv in xf:
        return "latest:" + lv
    if lv.startswith("latest:") and re.match(r"^[a-z]+$", lv.split(":", 1)[1]):
        return lv
    if lv.startswith("claude:"):
        rest = v.split(":", 1)[1].strip().lower()
        if rest in cf or CLAUDE_ID.match(rest):
            return "claude:" + rest
        raise UserError("다리 모델은 claude:<%s> 또는 claude:<전체 ID>입니다: %s" % ("|".join(cf), v))
    if lv in cf or CLAUDE_ID.match(lv):
        return "claude:" + lv
    if re.match(r"^[a-z0-9][a-z0-9.\-_]*$", lv):
        return lv
    raise UserError("Codex 대상의 모델은 %s(계열 최신)|gpt-…(전체 ID)|claude:<별칭>(다리) 중 하나입니다: %s"
                    % ("|".join(xf) or "<계열>", v))


def codex_model_list(cfg):
    t = cfg.get("targets", {}).get("codex", {})
    d = t.get("dir") or codex_dir()
    models = codex_cached_models(d)
    if not models:
        _, models, _ = codex_models(d, t.get("exe") or shutil.which("codex"), app_engine_path(), live=True)
    return models or []


def effort_options(target, model, cfg):
    s = sync_mod()
    if target == "claude" and not model.startswith("codex:"):
        return list(CLAUDE_EFFORTS)
    if target == "codex" and model.startswith("claude:"):
        return list(CLAUDE_EFFORTS)
    mid = model.split(":", 1)[1] if model.startswith("codex:") else model
    if mid.startswith("latest:"):
        mid = catalog_families("codex").get(mid.split(":", 1)[1], "")
    lv = catalog_efforts("codex", mid)
    if lv is None:
        lv = s.effort_levels(s.by_slug(codex_model_list(cfg)).get(mid))
    lv = [x for x in lv if x != "ultra" and x in s.EFFORT_ORDER]
    return sorted(lv, key=s.EFFORT_ORDER.index) if lv else list(CODEX_DEFAULT_EFFORTS)


def norm_effort(value, options):
    v = str(value or "").strip().lower()
    if v == "extra":
        v = "xhigh"
    if v == "ultra":
        raise UserError("ultra는 강도 선택지가 아닙니다. Codex의 ultra는 다중 에이전트 모드(ultracode)이고, "
                        "Claude판 별명 ultra는 max입니다. max를 원하면 max라고 적으세요.")
    if v not in options:
        raise UserError("이 모델의 강도는 %s 중 하나입니다: %s" % ("·".join(options), value))
    return v


def model_notes(target, model, effort, role, cfg):
    """재확인 없이 출력만 하는 안내 줄. 계열 이름에 기대지 않는다."""
    notes = []
    s = sync_mod()
    lm = model.lower()
    if lm.startswith("codex:") or lm.startswith("claude:"):
        notes.append("안내: 다리 하청은 실험적 기능입니다. 다른 쪽 CLI(%s) 설치·로그인이 필요합니다."
                     % ("Codex" if lm.startswith("codex:") else "Claude Code"))
    cid = lm.split(":", 1)[1] if lm.startswith("claude:") else lm
    cv = claude_id_version(cid)
    if cv:
        latest = catalog_families("claude").get(cv[0])
        lv = claude_id_version(latest) if latest else None
        if lv and cv[1] < lv[1]:
            notes.append("안내: %s는 최신 아님(최신: %s)." % (cid, latest))
        elif not latest:
            notes.append("안내: Claude 모델 목록에 %s 계열의 최신 정보가 없어 최신 여부는 알 수 없습니다." % cv[0])
    xid = lm.split(":", 1)[1] if lm.startswith("codex:") else lm
    p = s.parse_slug(xid)
    if p:
        latest = catalog_families("codex").get(p[0])
        if latest and s.parse_slug(latest) and s.parse_slug(latest)[1] > p[1]:
            notes.append("안내: %s는 최신 아님(최신: %s)." % (xid, latest))
        known = (load_catalog().get("codex") or {}).get("models") or []
        if known and xid not in known:
            notes.append("안내: %s는 지금 모델 목록에 없습니다. Codex가 거부할 수 있습니다." % xid)
    if role == "runner" and effort in ("medium", "high", "xhigh", "max"):
        notes.append("안내: runner 강도를 low보다 높이면 잡무 비용이 커집니다.")
    if effort == "max":
        notes.append("안내: max는 가장 비싼 강도입니다.")
    return notes


def apply_target(cfg, target, roles=ROLES, live=False, quiet=False):
    """config 의 역할 값을 정의 파일·게이트가 읽는 파일에 반영한다."""
    t = cfg["targets"][target]
    if target == "claude":
        p = cpaths(t["dir"])
        skipped = write_claude_agents(p, cfg, roles)
    else:
        p = xpaths(t["dir"])
        source, models, app = codex_models(t["dir"], t.get("exe"), t.get("app_engine"), live=live,
                                           app_version=t.get("app_version") or "")
        roles_cfg = {r: role_cfg(cfg, "codex", r) for r in ROLES}
        res, warnings, failed = resolve_codex_roles(roles_cfg, models, app)
        if failed:
            raise UserError("Codex 모델을 정하지 못했습니다(%s). 찾은 모델: %s"
                            % (", ".join(failed), ", ".join(sync_mod().candidate_slugs(models)) or "없음"))
        old = (read_json(p["models"], {}) or {}).get("roles", {})
        skipped = write_codex_agents(p, cfg, res, roles, source=source)
        if not quiet:
            for w in warnings:
                print("경고: " + w)
        changes = []
        for r in roles:
            o = old.get(r) or {}
            if o.get("model") != res[r]["model"] or o.get("effort") != res[r]["effort"]:
                changes.append("%s %s → %s" % (r, o.get("model") or "(없음)", res[r]["model"]))
        if changes:
            log("codex 반영(%s): %s" % (source, "; ".join(changes)))
    for s_ in skipped:
        print("건너뜀(oche가 만든 파일이 아님): %s — install.py install --force-agents 로 백업 후 교체할 수 있습니다." % tilde(s_))
    return skipped


def set_role(cfg, target, role, model_in, effort_in, quiet=False, fit=False):
    """역할 하나의 모델·강도를 바꾸고 정의 파일·게이트 설정에 반영한다. quiet 면 안내 줄을 돌려준다.
    fit 이면 그 모델이 지원하지 않는 강도를 가장 가까운 아래 값으로 바꾼다(프리셋용)."""
    name = cmd_name(cfg)
    if target not in installed_targets(cfg):
        raise UserError("%s 대상은 설치되어 있지 않습니다." % TARGET_LABEL.get(target, target))
    rc = role_cfg(cfg, target, role)
    model = norm_model(target, model_in, cfg) if model_in else rc["model"]
    options = effort_options(target, model, cfg)
    if effort_in and fit and str(effort_in).lower() not in options:
        effort = sync_mod().fit_effort(str(effort_in).lower(), options)
    elif effort_in:
        effort = norm_effort(effort_in, options)
    elif rc["effort"] in options:
        effort = rc["effort"]
    else:
        effort = sync_mod().fit_effort(rc["effort"], options)
    notes = model_notes(target, model, effort, role, cfg)
    rc["model"], rc["effort"] = model, effort
    save_config(cfg)
    apply_target(cfg, target, (role,), quiet=quiet)
    if quiet:
        return notes
    for n in notes:
        print(n)
    print("적용: %s %s → 모델 %s, 강도 %s. 다음 세션부터 적용됩니다." % (TARGET_LABEL[target], role, model, effort_label(effort)))
    print("확인: %s" % name)


def effort_label(e):
    return EFFORT_NICK.get(e, e)


# ======================================================================
# 프리셋 — 역할 3개의 {model, effort} 묶음
# ======================================================================

def _r(m, e):
    return {"model": m, "effort": e}


BUILTIN_PRESETS = {
    "default": {"label": "기본",
                "claude": {"executor": _r("opus", "high"), "deep-reasoner": _r("opus", "xhigh"), "runner": _r("haiku", "low")},
                "codex": {"executor": _r("sol", "high"), "deep-reasoner": _r("sol", "xhigh"), "runner": _r("terra", "low")}},
    "saver": {"label": "절약",
              "claude": {"executor": _r("sonnet", "medium"), "deep-reasoner": _r("opus", "high"), "runner": _r("haiku", "low")},
              "codex": {"executor": _r("terra", "medium"), "deep-reasoner": _r("sol", "high"), "runner": _r("luna", "low")}},
    "max": {"label": "최대",
            "claude": {"executor": _r("opus", "xhigh"), "deep-reasoner": _r("opus", "max"), "runner": _r("haiku", "medium")},
            "codex": {"executor": _r("sol", "xhigh"), "deep-reasoner": _r("sol", "max"), "runner": _r("terra", "medium")}},
}
BUILTIN_ORDER = ("default", "saver", "max")


def user_presets(cfg):
    p = cfg.get("presets")
    return p if isinstance(p, dict) else {}


def preset_list(cfg):
    """[(id, 표시 이름, 정의, 내장 여부)]"""
    out = [(k, BUILTIN_PRESETS[k]["label"], BUILTIN_PRESETS[k], True) for k in BUILTIN_ORDER]
    for k in sorted(user_presets(cfg)):
        out.append((k, k, user_presets(cfg)[k], False))
    return out


def find_preset(cfg, name):
    n = str(name or "").strip()
    for pid, label, d, builtin in preset_list(cfg):
        if n in (pid, label) or (builtin and n.lower() == pid):
            return pid, label, d, builtin
    raise UserError("프리셋 '%s'이(가) 없습니다. `%s preset`으로 목록을 보세요." % (n, cmd_name(cfg)))


def _builtin_model(target, fam, fams):
    """내장 프리셋의 계열 이름을 그 대상의 설정값으로. 목록에 없으면 None."""
    if fam not in fams:
        return None
    return fam if target == "claude" else "latest:" + fam


def preset_values(cfg, pid, target, notes=None):
    """프리셋을 그 대상에 적용했을 때의 역할별 (모델, 강도). 대상 값이 없으면 None."""
    d = BUILTIN_PRESETS.get(pid) or user_presets(cfg).get(pid)
    if not d or not isinstance(d.get(target), dict):
        return None
    builtin = pid in BUILTIN_PRESETS
    fams = catalog_families(target)
    out = {}
    for role in ROLES:
        v = d[target].get(role) or {}
        model, effort = str(v.get("model") or ""), str(v.get("effort") or "")
        if builtin:
            m = _builtin_model(target, model, fams)
            if m is None:
                dv = BUILTIN_PRESETS["default"][target][role]
                m = _builtin_model(target, dv["model"], fams) or role_cfg(cfg, target, role)["model"]
                if notes is not None:
                    notes.append("안내: %s 모델 목록에 %s 계열이 없어 %s는 기본값(%s)으로 둡니다."
                                 % (TARGET_LABEL[target], model, role, model_label(target, m)))
                if effort not in effort_options(target, m, cfg):
                    effort = dv["effort"]
            model = m
        opts = effort_options(target, model, cfg)
        if effort not in opts:
            effort = sync_mod().fit_effort(effort, opts)
        out[role] = (model, effort)
    return out


def current_preset(cfg):
    """지금 설정과 일치하는 프리셋 (id, 표시 이름) 또는 None."""
    targets = installed_targets(cfg)
    if not targets:
        return None
    for pid, label, d, builtin in preset_list(cfg):
        ok = True
        for t in targets:
            vals = preset_values(cfg, pid, t)
            if vals is None or any((role_cfg(cfg, t, r)["model"], role_cfg(cfg, t, r)["effort"]) != vals[r] for r in ROLES):
                ok = False
                break
        if ok:
            return pid, label
    return None


def preset_label_line(cfg):
    cur = current_preset(cfg)
    return "프리셋: " + (cur[1] if cur else "사용자 지정")


def describe_preset(cfg, pid, target):
    vals = preset_values(cfg, pid, target)
    if not vals:
        return "(값 없음)"
    return " / ".join("%s·%s" % (model_label(target, vals[r][0]), vals[r][1]) for r in ROLES)


def apply_preset(cfg, name, which=None):
    pid, label, d, builtin = find_preset(cfg, name)
    targets = [which] if which else installed_targets(cfg)
    notes, done = [], []
    for t in targets:
        if t not in installed_targets(cfg):
            raise UserError("%s는 설치되어 있지 않습니다." % TARGET_LABEL.get(t, t))
        vals = preset_values(cfg, pid, t, notes)
        if vals is None:
            notes.append("안내: 프리셋 '%s'에는 %s 값이 없어 건너뜁니다." % (label, TARGET_LABEL[t]))
            continue
        for role in ROLES:
            for n in set_role(cfg, t, role, vals[role][0], vals[role][1], quiet=True, fit=True) or []:
                if n not in notes and "최신 아님" not in n:
                    notes.append(n)
        done.append("%s %s" % (TARGET_LABEL[t], describe_preset(cfg, pid, t)))
    log("preset use %s (%s)" % (pid, ",".join(targets)))
    return label, notes, done


def save_preset(cfg, name):
    n = str(name or "").strip()
    if not n or re.search(r"\s", n):
        raise UserError("프리셋 이름은 공백 없는 글자여야 합니다: '%s'" % name)
    reserved = set(BUILTIN_PRESETS) | {v["label"] for v in BUILTIN_PRESETS.values()}
    if n in reserved or n.lower() in reserved:
        raise UserError("'%s'은(는) 내장 프리셋 이름이라 쓸 수 없습니다." % n)
    d = {}
    for t in installed_targets(cfg):
        d[t] = {r: dict(role_cfg(cfg, t, r)) for r in ROLES}
    existed = n in user_presets(cfg)
    cfg.setdefault("presets", {})[n] = d
    save_config(cfg)
    return existed


def delete_preset(cfg, name):
    n = str(name or "").strip()
    if n in BUILTIN_PRESETS or n in {v["label"] for v in BUILTIN_PRESETS.values()}:
        raise UserError("내장 프리셋은 지울 수 없습니다: %s" % n)
    if n not in user_presets(cfg):
        raise UserError("사용자 프리셋 '%s'이(가) 없습니다." % n)
    del cfg["presets"][n]
    save_config(cfg)


def cmd_preset(cfg, args):
    name = cmd_name(cfg)
    if not args:
        cur = current_preset(cfg)
        print("프리셋 (✔ = 지금 설정과 일치)")
        for pid, label, d, builtin in preset_list(cfg):
            mark_ = "✔" if cur and cur[0] == pid else " "
            head = "%s (%s)" % (pid, label) if builtin else "%s (사용자)" % pid
            print(" %s %s" % (mark_, head))
            for t in installed_targets(cfg):
                print("      %-11s %s" % (TARGET_LABEL[t], describe_preset(cfg, pid, t)))
        if not cur:
            print("지금 설정: 사용자 지정")
        print("쓰기: %s preset use <이름> [claude|codex] · 저장: %s preset save <이름> · 지우기: %s preset delete <이름>"
              % (name, name, name))
        return 0
    sub_ = args[0]
    if sub_ == "use":
        if len(args) not in (2, 3) or (len(args) == 3 and args[2] not in TARGETS):
            raise UserError("사용법: %s preset use <이름> [claude|codex]" % name)
        label, notes, done = apply_preset(cfg, args[1], args[2] if len(args) == 3 else None)
        for n in notes:
            print(n)
        print("프리셋 '%s' 적용: %s. 다음 세션부터 적용됩니다." % (label, "; ".join(done) or "바뀐 대상 없음"))
        return 0
    if sub_ == "save":
        if len(args) != 2:
            raise UserError("사용법: %s preset save <이름>" % name)
        existed = save_preset(cfg, args[1])
        print("프리셋 '%s' %s: 지금 설정(%s)을 담았습니다." % (args[1], "덮어씀" if existed else "저장",
                                                       ", ".join(TARGET_LABEL[t] for t in installed_targets(cfg))))
        return 0
    if sub_ == "delete":
        if len(args) != 2:
            raise UserError("사용법: %s preset delete <이름>" % name)
        delete_preset(cfg, args[1])
        print("프리셋 '%s'을(를) 지웠습니다." % args[1])
        return 0
    raise UserError("사용법: %s preset [use <이름> [claude|codex] | save <이름> | delete <이름>]" % name)


# ======================================================================
# 현황판
# ======================================================================

def actual_model(target, rc, cfg, latest=None, codex_roles=None, role=None):
    m = rc["model"]
    if target == "claude":
        if m.startswith("codex:"):
            return "다리 → Codex %s" % m.split(":", 1)[1]
        if not m.startswith("claude-"):
            return (latest or {}).get(m) or "Claude Code가 정함(최신표 알 수 없음)"
        return m
    r = (codex_roles or {}).get(role) or {}
    if m.startswith("claude:"):
        return "다리 → Claude %s (정의: %s)" % (m.split(":", 1)[1], r.get("model") or "?")
    return r.get("model") or "(아직 결정 안 됨)"


def model_label(target, m):
    if target == "codex" and m.startswith("latest:"):
        return "최신 " + m.split(":", 1)[1]
    return m


def dashboard(cfg, full=False):
    name = cmd_name(cfg)
    s = sync_mod()
    print("%s %s — 하청 오케스트레이션 (명령 이름: %s)" % (name, VERSION, name))
    targets = installed_targets(cfg)
    if not targets:
        print("설치된 대상이 없습니다. 저장소의 install.py로 설치하세요.")
        return 1
    print(preset_label_line(cfg))
    warnings = []
    latest = None
    for target in targets:
        t = cfg["targets"][target]
        if target == "claude":
            p = cpaths(t["dir"])
            on = claude_state(p)
            latest = catalog_families("claude")
            ver = "Claude Code " + (t.get("version") or "?")
            codex_roles = None
        else:
            p = xpaths(t["dir"])
            on = codex_state(p)
            mj = read_json(p["models"], {}) or {}
            codex_roles = mj.get("roles") or {}
            ver = "CLI " + (t.get("version") or "없음")
            if t.get("app_engine"):
                ver += ", 앱 엔진 " + (t.get("app_version") or "?")
        print("")
        print("[%s] %s   (%s, %s)" % (TARGET_LABEL[target], "ON" if on else "OFF", tilde(t["dir"]), ver))
        rows = [("역할", "모델(설정 → 실제)", "강도")]
        for role in ROLES:
            rc = role_cfg(cfg, target, role)
            act = actual_model(target, rc, cfg, latest, codex_roles, role)
            eff = effort_label(rc["effort"])
            if target == "codex":
                r = codex_roles.get(role) or {}
                if r.get("effort") and r.get("effort") != rc["effort"] and not r.get("bridge"):
                    eff += " (모델 미지원 → %s)" % r["effort"]
            rows.append((role, "%s → %s" % (model_label(target, rc["model"]), act), eff))
            # 경고 모으기
            m = rc["model"].lower()
            if target == "claude":
                cv = claude_id_version(m)
                lt = (latest or {}).get(cv[0]) if cv else None
                if cv and lt and claude_id_version(lt) and cv[1] < claude_id_version(lt)[1]:
                    warnings.append("Claude %s: %s는 최신 아님(최신: %s)" % (role, m, lt))
            else:
                pp = s.parse_slug(m)
                if pp:
                    lt = catalog_families("codex").get(pp[0])
                    if lt and s.parse_slug(lt) and s.parse_slug(lt)[1] > pp[1]:
                        warnings.append("Codex %s: %s는 최신 아님(최신: %s)" % (role, m, lt))
        w0 = max(dwidth(r[0]) for r in rows) + 2
        w1 = max(dwidth(r[1]) for r in rows) + 2
        for r in rows:
            print("  " + dpad(r[0], w0) + dpad(r[1], w1) + r[2])
        if target == "codex":
            ac = s.app_cache(t["dir"], engine_version=t.get("app_version"))
            if ac and ac.get("stale_note"):
                warnings.append("Codex: " + ac["stale_note"])
            if t.get("subagent_fields") is False:
                warnings.append("Codex 저하 모드: CLI나 앱 엔진이 0.171.0 미만이라 재하청 차단과 수정 개수 세기가 꺼져 있습니다.")
            warnings.append("Codex 훅은 사람이 한 번 신뢰해야 돕니다: CLI는 /hooks, 앱은 입력창의 Review hooks 또는 Settings > Hooks.")
        if full:
            print_parts(target, cfg)
    if not path_has_local_bin():
        warnings.append("%s가 PATH에 없습니다. install.py install --add-to-path 로 넣거나 전체 경로로 실행하세요." % tilde(local_bin()))
    if warnings:
        print("")
        print("경고·안내:")
        for w in warnings:
            print("  - " + w)
    print("")
    print("바꾸기: %s <역할>   켜기/끄기: %s on|off   도움말: %s help" % (name, name, name))
    return 0


def dwidth(s):
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def dpad(s, n):
    return s + " " * max(0, n - dwidth(s))


def mark(ok):
    return "[OK]" if ok else "[--]"


def print_parts(target, cfg):
    t = cfg["targets"][target]
    if target == "claude":
        p = cpaths(t["dir"])
        on = claude_state(p)
        active = read_text(p["active"])
        settings = read_json(p["settings"], {}) or {}
        pre = (settings.get("hooks") or {}).get("PreToolUse") if isinstance(settings, dict) else None
        print("  부품 점검:")
        print("    %s 규칙 불러오기 줄  %s" % (mark(has_loader(read_text(p["claude_md"]))), tilde(p["claude_md"])))
        print("    %s active.md 내용(%s)  %s" % (mark(active is not None and active == read_text(p["rules"] if on else p["empty"])),
                                              "규칙" if on else "빈 파일", tilde(p["active"])))
        print("    %s 게이트 훅 등록  %s" % (mark(has_hook(pre, "oche-gate")), tilde(p["settings"])))
        print("    %s 게이트 스크립트  %s" % (mark(os.path.isfile(p["gate"])), tilde(p["gate"])))
        ok = all(os.path.isfile(os.path.join(p["agents"], r + ".md")) and claude_agent_owned(p, r) for r in ROLES)
        print("    %s 하청 정의 3개  %s" % (mark(ok), tilde(p["agents"])))
    else:
        p = xpaths(t["dir"])
        on = codex_state(p)
        hooks = read_json(p["hooks"], {}) or {}
        hk = hooks.get("hooks") or {} if isinstance(hooks, dict) else {}
        target_md = agents_target(p)
        print("  부품 점검:")
        print("    %s 규칙 구역(켜졌을 때만 OK)  %s" % (mark("<!-- oche:begin" in (read_text(target_md) or "")), tilde(target_md)))
        print("    %s 게이트 훅 등록  %s" % (mark(has_hook(hk.get("PreToolUse"), "oche-gate")), tilde(p["hooks"])))
        print("    %s 모델 갱신 훅 등록  %s" % (mark(has_hook(hk.get("SessionStart"), "oche-sync")), tilde(p["hooks"])))
        print("    %s 게이트·갱신 스크립트  %s" % (mark(os.path.isfile(p["gate"]) and os.path.isfile(p["sync"])), tilde(os.path.dirname(p["gate"]))))
        ok = all(os.path.isfile(p["tomls"][r]) and codex_toml_owned(p["tomls"][r]) for r in ROLES)
        print("    %s 하청 정의 3개  %s" % (mark(ok), tilde(os.path.dirname(p["tomls"]["executor"]))))
        st = os.path.join(p["state_dir"], "sync.stamp")
        last = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(st))) if os.path.exists(st) else "아직 없음"
        mj = read_json(p["models"], {}) or {}
        print("    마지막 sync: %s · 모델 결정 출처: %s · 자동 갱신: %s"
              % (last, mj.get("source") or "?", "켜짐" if mj.get("auto_update", True) else "꺼짐"))
        if on and "<!-- oche:begin" not in (read_text(target_md) or ""):
            print("    주의: 켜져 있는데 지금 읽히는 지침 파일에 규칙 구역이 없습니다. %s on 을 다시 실행하세요." % cmd_name(cfg))
        if len((read_text(target_md) or "").encode("utf-8")) > AGENTS_MAX_BYTES:
            print("    주의: %s가 32 KiB를 넘습니다. 지침이 잘릴 수 있습니다." % tilde(target_md))


# ======================================================================
# selftest
# ======================================================================

def run_gate(gate, payload, env_extra=None):
    env = dict(os.environ)
    env.pop("ORCH_BRIDGE", None)
    if env_extra:
        env.update(env_extra)
    p = subprocess.run([sys.executable, gate], input=json.dumps(payload).encode("utf-8"),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=30)
    return p.returncode


def other_efforts(cur, options, same=()):
    """설정과 다른 강도 하나씩(위·아래). same 에 든 값(설정과 같다고 보는 값)은 뺀다."""
    same = set(same) | {cur}
    out = []
    if cur in options:
        i = options.index(cur)
        up = [x for x in options[i + 1:] if x not in same]
        down = [x for x in options[:i] if x not in same]
        if up:
            out.append(("높은", up[0]))
        if down:
            out.append(("낮은", down[-1]))
    if not out:
        out.extend(("다른", x) for x in options if x not in same)
        out = out[:1]
    return out


def selftest_claude(cfg, results):
    p = cpaths(cfg["targets"]["claude"]["dir"])
    gate = p["gate"]
    roles = (read_json(p["roles"], {}) or {}).get("roles") or {}
    ex = roles.get("executor") or {}
    sid = "oche-selftest-%d" % os.getpid()
    sfile = os.path.join(p["state_dir"], sid + ".json")

    def t(name, expect, payload, env=None):
        r = run_gate(gate, payload, env)
        results.append((r == expect, "Claude  %s (exit %s, 기대 %s)" % (name, r, expect)))

    def ag(stype=None, **kw):
        ti = dict(kw)
        if stype is not None:
            ti["subagent_type"] = stype
        return {"tool_name": "Agent", "tool_input": ti}

    def ed(path, prompt="p1"):
        d = {"tool_name": "Edit", "session_id": sid, "tool_input": {"file_path": path}}
        if prompt:
            d["prompt_id"] = prompt
        return d

    orig = claude_state(p)
    try:
        claude_set_switch(p, True)
        results.append((read_text(p["active"]) == read_text(p["rules"]), "Claude  ON: active.md = 규칙"))
        t("executor 하청 허용", 0, ag("executor"))
        t("deep-reasoner 하청 허용(옛 도구 이름 Task)", 0, {"tool_name": "Task", "tool_input": {"subagent_type": "deep-reasoner"}})
        t("runner 하청 허용", 0, ag("runner"))
        t("general-purpose 하청 차단", 2, ag("general-purpose"))
        t("타입 없는 하청 차단", 2, ag())
        t("설정과 같은 모델 지정 허용", 0, ag("executor", model=ex.get("model") or "opus"))
        t("옛 모델 ID 지정 차단", 2, ag("executor", model="claude-opus-4-0" if ex.get("model") != "claude-opus-4-0" else "claude-opus-3-0"))
        t("설정과 다른 별칭 지정 차단", 2, ag("executor", model="sonnet" if ex.get("model") != "sonnet" else "haiku"))
        t("설정과 같은 강도 지정 허용", 0, ag("executor", effort=ex.get("effort") or "high"))
        for kind, e in other_efforts(ex.get("effort") or "high", CLAUDE_EFFORTS):
            t("설정보다 %s 강도(%s) 차단" % (kind, e), 2, ag("executor", effort=e))
        t("ultra 강도 차단", 2, ag("executor", effort="ultra"))
        t("Workflow 차단", 2, {"tool_name": "Workflow", "tool_input": {}})
        t("하청 안의 재하청 차단", 2, {"tool_name": "Agent", "agent_id": "a1", "agent_type": "executor",
                                     "tool_input": {"subagent_type": "runner"}})
        t("하청 안의 Workflow 차단", 2, {"tool_name": "Workflow", "agent_id": "a1", "tool_input": {}})
        t("하청 안의 코드 수정 허용", 0, {"tool_name": "Edit", "agent_id": "a1", "tool_input": {"file_path": "x.py"}})
        t("다리 실행(ORCH_BRIDGE=1) 중 하청 차단", 2, ag("executor"), {"ORCH_BRIDGE": "1"})
        t("Bash 허용", 0, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
        t("문서 직접 수정 허용", 0, ed("notes.md"))
        t("코드 직접 수정 1개째 허용", 0, ed("a.py"))
        t("코드 직접 수정 2개째 허용", 0, ed("b.ts"))
        t("코드 직접 수정 3개째 차단", 2, ed("c.go"))
        t("같은 파일 재수정 허용", 0, ed("a.py"))
        t("다리 실행 중에는 수정 개수 안 셈", 0, ed("d.py"), {"ORCH_BRIDGE": "1"})
        t("prompt_id 없으면 개수 안 셈", 0, ed("e.py", prompt=None))
        claude_set_switch(p, False)
        results.append((read_text(p["active"]) == read_text(p["empty"]), "Claude  OFF: active.md = 빈 파일"))
        t("OFF: general-purpose 통과", 0, ag("general-purpose"))
        t("OFF: Workflow 통과", 0, {"tool_name": "Workflow", "tool_input": {}})
        t("OFF: 코드 3개째 통과", 0, ed("f.py", prompt="p2"))
    finally:
        claude_set_switch(p, orig)
        try:
            os.remove(sfile)
        except OSError:
            pass


def selftest_codex(cfg, results):
    p = xpaths(cfg["targets"]["codex"]["dir"])
    gate = p["gate"]
    mj = read_json(p["models"], {}) or {}
    ex = (mj.get("roles") or {}).get("executor") or {}
    full = (read_json(p["gate_json"], {}) or {}).get("subagent_fields", True) is not False
    sid = "oche-selftest-%d" % os.getpid()
    sfile = os.path.join(p["state_dir"], sid + ".json")

    def t(name, expect, payload, env=None):
        r = run_gate(gate, payload, env)
        results.append((r == expect, "Codex   %s (exit %s, 기대 %s)" % (name, r, expect)))

    def sp(**ti):
        return {"tool_name": "spawn_agent", "session_id": sid, "turn_id": "t0", "tool_input": ti}

    def pt(turn, *files, **kw):
        body = "".join("*** Update File: %s\n" % f for f in files)
        d = {"tool_name": "apply_patch", "session_id": sid, "tool_input": {"command": "*** Begin Patch\n" + body + "*** End Patch\n"}}
        if turn:
            d["turn_id"] = turn
        d.update(kw)
        return d

    orig = codex_state(p)
    try:
        codex_set_switch(p, True)
        results.append(("<!-- oche:begin" in (read_text(agents_target(p)) or ""), "Codex   ON: 규칙 구역 있음 (%s)" % tilde(agents_target(p))))
        t("executor 하청 허용", 0, sp(agent_type="executor", message="x"))
        t("deep_reasoner 하청 허용", 0, sp(agent_type="deep_reasoner", message="x"))
        t("runner 하청 허용", 0, sp(agent_type="runner", message="x"))
        t("agent_type 비움 차단", 2, sp(message="x"))
        t("내장 worker 차단", 2, sp(agent_type="worker"))
        t("실제 도구 이름(collaborationspawn_agent)으로 worker 차단", 2,
          {"tool_name": "collaborationspawn_agent", "session_id": sid, "turn_id": "t0",
           "tool_input": {"agent_type": "worker", "task_name": "t", "message": "x"}})
        t("설정과 다른 계열 지정 차단", 2, sp(agent_type="executor",
                                         model="gpt-0-other" if ex.get("model") != "gpt-0-other" else "gpt-0-else"))
        t("설정과 같은 모델 지정 허용", 0, sp(agent_type="executor", model=ex.get("model") or "x"))
        t("옛 모델 ID 지정 차단", 2, sp(agent_type="executor", model="gpt-5.6-sol" if ex.get("model") != "gpt-5.6-sol" else "gpt-5.5-sol"))
        t("설정과 같은 강도 지정 허용", 0, sp(agent_type="executor", reasoning_effort=ex.get("effort") or "high"))
        for kind, e in other_efforts(ex.get("effort") or "high", CODEX_DEFAULT_EFFORTS, [ex.get("configured_effort")]):
            t("설정보다 %s 강도(%s) 차단" % (kind, e), 2, sp(agent_type="executor", reasoning_effort=e))
        t("ultra 강도 차단", 2, sp(agent_type="executor", reasoning_effort="ultra"))
        t("다리 실행(ORCH_BRIDGE=1) 중 하청 차단", 2, sp(agent_type="executor"), {"ORCH_BRIDGE": "1"})
        if full:
            t("하청 안의 재하청 차단", 2, {"tool_name": "spawn_agent", "agent_id": "a1", "agent_type": "executor",
                                         "tool_input": {"agent_type": "runner"}})
            t("하청 안의 파일 수정 허용", 0, {"tool_name": "apply_patch", "agent_id": "a1", "agent_type": "executor",
                                           "tool_input": {"command": "*** Update File: x.py\n"}})
            t("문서 직접 수정 허용", 0, pt("t1", "notes.md"))
            t("코드 직접 수정 1개째 허용", 0, pt("t1", "a.py"))
            t("코드 직접 수정 2개째 허용", 0, pt("t1", "b.ts"))
            t("코드 직접 수정 3개째 차단", 2, pt("t1", "c.go"))
            t("같은 파일 재수정 허용", 0, pt("t1", "a.py"))
            t("새 턴: 한 패치에 3개 차단", 2, pt("t2", "a.py", "b.py", "c.py"))
            t("turn_id 없으면 개수 안 셈", 0, pt(None, "a.py", "b.py", "c.py"))
        else:
            t("저하 모드: 하청 판별 없이 타입 검사만(허용)", 0, {"tool_name": "spawn_agent", "agent_id": "a1",
                                                       "tool_input": {"agent_type": "runner"}})
            t("저하 모드: 코드 3개째도 통과", 0, pt("t1", "a.py", "b.py", "c.py"))
        codex_set_switch(p, False)
        results.append(("<!-- oche:begin" not in (read_text(p["agents_md"]) or "") + (read_text(p["override"]) or ""),
                        "Codex   OFF: 규칙 구역 지워짐"))
        t("OFF: 내장 worker 통과", 0, sp(agent_type="worker"))
    finally:
        codex_set_switch(p, orig)
        try:
            os.remove(sfile)
        except OSError:
            pass


def cmd_selftest(cfg, which=None):
    results = []
    targets = [which] if which else installed_targets(cfg)
    for target in targets:
        if target not in installed_targets(cfg):
            print("%s는 설치되어 있지 않습니다." % TARGET_LABEL.get(target, target))
            return 1
        (selftest_claude if target == "claude" else selftest_codex)(cfg, results)
    bad = 0
    for ok, line in results:
        print(("OK    " if ok else "FAIL  ") + line)
        bad += 0 if ok else 1
    print("selftest: OK %d, FAIL %d" % (len(results) - bad, bad))
    return 1 if bad else 0


# ======================================================================
# 다리 하청 실행
# ======================================================================

def cmd_bridge(cfg, argv):
    if len(argv) < 2 or argv[0] not in ("codex", "claude"):
        raise UserError("사용법: %s bridge codex|claude <역할> --task <작업파일> --out <결과파일> [--cwd <폴더>]" % cmd_name(cfg))
    side, role = argv[0], norm_role(argv[1])
    opts = {"--task": None, "--out": None, "--cwd": os.getcwd()}
    i = 2
    while i < len(argv):
        if argv[i] in opts and i + 1 < len(argv):
            opts[argv[i]] = argv[i + 1]
            i += 2
        else:
            raise UserError("알 수 없는 인자: %s" % argv[i])
    if not opts["--task"] or not opts["--out"]:
        raise UserError("--task 와 --out 이 필요합니다.")
    if side == "codex":
        rc = role_cfg(cfg, "claude", role) if "claude" in cfg["targets"] else {}
        m = rc.get("model", "")
        if not m.startswith("codex:"):
            raise UserError("Claude %s 역할은 Codex 모델로 정해져 있지 않습니다(지금: %s)." % (role, m or "없음"))
        exe = shutil.which("codex") or app_engine_path() or "codex"
        argv2 = [exe, "exec", "-m", m.split(":", 1)[1], "-c", 'model_reasoning_effort="%s"' % rc["effort"],
                 "-s", "workspace-write", "-C", opts["--cwd"], "--skip-git-repo-check", "--ephemeral",
                 "-o", opts["--out"], "-"]
    else:
        rc = role_cfg(cfg, "codex", role) if "codex" in cfg["targets"] else {}
        m = rc.get("model", "")
        if not m.startswith("claude:"):
            raise UserError("Codex %s 역할은 Claude 모델로 정해져 있지 않습니다(지금: %s)." % (role, m or "없음"))
        exe = shutil.which("claude") or "claude"
        argv2 = [exe, "-p", "--model", m.split(":", 1)[1], "--effort", rc["effort"], "--output-format", "text",
                 "--permission-mode", "acceptEdits"]
    if os.environ.get("ORCH_BRIDGE_DRYRUN") == "1":
        print("ORCH_BRIDGE=1 " + " ".join(quote_arg(a) for a in argv2) + " < " + quote_arg(opts["--task"]))
        return 0
    task = read_text(opts["--task"])
    if task is None:
        raise UserError("작업 파일을 읽지 못했습니다: %s" % opts["--task"])
    env = dict(os.environ)
    env["ORCH_BRIDGE"] = "1"
    p = subprocess.run(argv2, input=(BRIDGE_PREFIX + task).encode("utf-8"), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, env=env, cwd=opts["--cwd"] if side == "claude" else None)
    if side == "claude":
        atomic_write(opts["--out"], (p.stdout or b"").decode("utf-8", "replace"))
    out = read_text(opts["--out"]) or ""
    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")
    if p.returncode != 0:
        sys.stdout.write((p.stderr or b"").decode("utf-8", "replace")[-4000:])
    print("종료 코드: %d" % p.returncode)
    return p.returncode


def quote_arg(a):
    a = str(a)
    if re.match(r"^[A-Za-z0-9_./:=@%+,-]+$", a):
        return a
    return "'" + a.replace("'", "'\"'\"'") + "'"


# ======================================================================
# 대화형
# ======================================================================

def tui_available():
    """진짜 터미널이고 TUI 파일이 있을 때만."""
    if os.environ.get("ORCH_NO_TUI") == "1":
        return False
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
    except (AttributeError, ValueError):
        return False
    return os.path.isfile(os.path.join(os.path.dirname(os.path.realpath(os.path.abspath(__file__))), "tui.py"))


def import_tui():
    here = os.path.dirname(os.path.realpath(os.path.abspath(__file__)))
    if here not in sys.path:
        sys.path.insert(0, here)
    import tui
    return tui


def is_tty():
    return os.environ.get("ORCH_FORCE_TTY") == "1" or (sys.stdin.isatty() and sys.stdout.isatty())


def ask(prompt):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        raise UserError("입력이 끝났습니다.")
    return line.strip()


def choose(title, options, default=None):
    """options: [(라벨, 값)]. 번호 또는 값을 직접 받는다."""
    print(title)
    for i, (label, _) in enumerate(options, 1):
        print("  %d) %s" % (i, label))
    while True:
        a = ask("번호를 고르세요%s: " % (" (엔터 = %s)" % default if default else ""))
        if not a and default:
            return default
        if a.isdigit() and 1 <= int(a) <= len(options):
            return options[int(a) - 1][1]
        for _, v in options:
            if a == v:
                return v
        print("  다시 고르세요.")


def model_options(target, cfg):
    """[(라벨, 값, 설명)] — catalog.json 에서 만든다."""
    cf = catalog_families("claude")
    xf = catalog_families("codex")
    opts = []
    if target == "claude":
        for fam, mid in cf.items():
            opts.append((fam, fam, "최신 %s%s · Claude Code가 업데이트되면 저절로 최신" % (fam, " (지금 " + mid + ")" if mid else "")))
        for fam, mid in xf.items():
            opts.append(("codex:" + mid, "codex:" + mid, "다리·실험적 — Codex CLI로 위임"))
    else:
        for fam, mid in xf.items():
            opts.append(("최신 " + fam, "latest:" + fam, "지금 %s · 같은 계열 새 버전은 자동 반영" % mid))
        for fam, mid in cf.items():
            opts.append(("claude:" + fam, "claude:" + fam, "다리·실험적 — Claude Code CLI로 위임"))
    opts.append(("직접 입력", "__custom__", "전체 모델 ID를 적습니다"))
    return opts


def interactive(cfg, target, role):
    targets = installed_targets(cfg)
    if not targets:
        raise UserError("설치된 대상이 없습니다.")
    if target is None:
        if len(targets) == 1:
            target = targets[0]
        else:
            target = choose("어느 쪽 하청을 바꿀까요?", [(TARGET_LABEL[t], t) for t in targets])
    if role is None:
        role = choose("어느 역할을 바꿀까요?", [(r, r) for r in ROLES])
    rc = role_cfg(cfg, target, role)
    print("[%s] %s — 지금: 모델 %s, 강도 %s" % (TARGET_LABEL[target], role, model_label(target, rc["model"]), effort_label(rc["effort"])))
    m = choose("모델:", [("%s — %s" % (o[0], o[2]), o[1]) for o in model_options(target, cfg)])
    if m == "__custom__":
        m = ask("모델 ID: ")
    model = norm_model(target, m, cfg)
    opts = effort_options(target, model, cfg)
    default = rc["effort"] if rc["effort"] in opts else None
    e = choose("강도 (이 모델이 지원하는 것만; ultra는 강도가 아니라 빠져 있습니다):",
               [(effort_label(x), x) for x in opts], default)
    set_role(cfg, target, role, model, e)
    return 0


# ======================================================================
# 명령
# ======================================================================

def help_text(name):
    return """사용법: {n} [명령]

  {n}                         터미널이면 화면(TUI), 아니면 현황판(대상별 ON/OFF, 역할 | 모델(설정 → 실제) | 강도)
  {n} --plain                 TUI 대신 텍스트 현황판
  {n} on|off [claude|codex|all]  오케스트레이션 켜기/끄기(다음 세션·새 채팅부터)
  {n} status                  현황판 + 부품 점검
  {n} models                  역할별 모델·강도 표
  {n} <역할>                   대화형으로 모델·강도 바꾸기 (executor | deep-reasoner | runner)
  {n} [claude|codex] <역할> <모델> [<강도>]   바로 바꾸기
                               모델: <계열 별칭>|claude-…(전체 ID)|codex:<ID>   (Claude 대상)
                                     <계열>(최신)|gpt-…(전체 ID)|claude:<별칭>   (Codex 대상)
                                     쓸 수 있는 계열은 `{n} models` 로 봅니다
                               강도: low|medium|high|xhigh(extra)|max  — ultra는 선택지가 아님
  {n} reset [claude|codex] [<역할>]  기본값으로 되돌리기
  {n} preset                  프리셋 목록(default 기본 · saver 절약 · max 최대 · 사용자), 지금 설정과 일치하면 ✔
  {n} preset use <이름> [claude|codex] / save <이름> / delete <이름>
  {n} update [claude|codex]   모델 목록 갱신(새 계열 알림) + Codex 최신 계열 다시 정함
  {n} pin <claude|codex> <역할> <모델ID> / {n} unpin <claude|codex> <역할>
  {n} selftest [claude|codex] 게이트 시험(켜짐·꺼짐 모두, 원래 상태로 되돌림)
  {n} version
""".format(n=name)


def parse_target_role(args):
    target = None
    if args and args[0] in TARGETS:
        target = args[0]
        args = args[1:]
    return target, args


def single_target(cfg, target, role_word):
    targets = installed_targets(cfg)
    if target:
        return target
    if len(targets) == 1:
        return targets[0]
    raise UserError("Claude Code와 Codex가 모두 설치되어 있습니다. `%s claude %s ...` 또는 `%s codex %s ...`처럼 대상을 적어 주세요."
                    % (cmd_name(cfg), role_word, cmd_name(cfg), role_word))


def cmd_switch(cfg, on, which):
    name = cmd_name(cfg)
    targets = installed_targets(cfg) if which in (None, "all") else [which]
    for t in targets:
        if t not in installed_targets(cfg):
            raise UserError("%s는 설치되어 있지 않습니다." % TARGET_LABEL.get(t, t))
        if t == "claude":
            claude_set_switch(cpaths(cfg["targets"][t]["dir"]), on)
            print("Claude Code: %s ON/OFF → %s. 다음 claude 세션부터 적용됩니다." % (name, "ON" if on else "OFF"))
        else:
            p = xpaths(cfg["targets"][t]["dir"])
            codex_set_switch(p, on)
            where = " (규칙 위치: %s)" % tilde(agents_target(p)) if on else ""
            print("Codex: %s → %s. 다음 codex 세션(앱은 새 채팅)부터 적용됩니다.%s" % (name, "ON" if on else "OFF", where))
    log("switch %s %s" % ("on" if on else "off", ",".join(targets)))
    return 0


def cmd_models(cfg):
    cat = load_catalog()
    for target in installed_targets(cfg):
        fams = catalog_families(target)
        src = (cat.get(target) or {}).get("source") or "?"
        print("[%s] 계열별 최신 (출처: %s)" % (TARGET_LABEL[target], src))
        print("  " + (", ".join("%s=%s" % (f, m or "?") for f, m in fams.items()) or "(없음)"))
        cr = None
        if target == "codex":
            cr = (read_json(xpaths(cfg["targets"][target]["dir"])["models"], {}) or {}).get("roles") or {}
        print("  역할:")
        for role in ROLES:
            rc = role_cfg(cfg, target, role)
            print("    %-14s %s → %s   강도 %s" % (role, model_label(target, rc["model"]),
                                               actual_model(target, rc, cfg, fams if target == "claude" else None, cr, role),
                                               effort_label(rc["effort"])))
    return 0


def cmd_update(cfg, which):
    if which not in (None, "codex", "claude", "all"):
        raise UserError("사용법: %s update [codex]" % cmd_name(cfg))
    for n in refresh_catalog(cfg, None if which in (None, "all") else which, live=True):
        print("알림: " + n + " — 역할을 옮기려면 `%s <역할>`로 직접 고르세요." % cmd_name(cfg))
    if "claude" in installed_targets(cfg) and which in (None, "claude", "all"):
        fams = catalog_families("claude")
        print("Claude Code: 모델 목록 갱신(%s). 별칭은 Claude Code가 업데이트될 때 스스로 최신으로 바뀝니다." % ", ".join(fams))
    if "codex" in installed_targets(cfg) and which in (None, "codex", "all"):
        p = xpaths(cfg["targets"]["codex"]["dir"])
        before = (read_json(p["models"], {}) or {}).get("roles") or {}
        apply_target(cfg, "codex", live=True)
        after = (read_json(p["models"], {}) or {}).get("roles") or {}
        ch = ["%s %s → %s" % (r, (before.get(r) or {}).get("model"), (after.get(r) or {}).get("model"))
              for r in ROLES if (before.get(r) or {}).get("model") != (after.get(r) or {}).get("model")]
        print("Codex: " + ("; ".join(ch) if ch else "바뀐 모델 없음") + ". 다음 세션부터 적용됩니다.")
    return 0


def cmd_reset(cfg, args):
    target, args = parse_target_role(args)
    role = norm_role(args[0]) if args else None
    targets = [target] if target else installed_targets(cfg)
    for t in targets:
        if t not in installed_targets(cfg):
            raise UserError("%s는 설치되어 있지 않습니다." % TARGET_LABEL.get(t, t))
        roles = [role] if role else list(ROLES)
        for r in roles:
            cfg["targets"][t].setdefault("roles", {})[r] = dict(DEFAULT_ROLES[t][r])
        save_config(cfg)
        apply_target(cfg, t, tuple(roles))
        print("%s: %s 기본값으로 되돌림. 다음 세션부터 적용됩니다." % (TARGET_LABEL[t], ", ".join(roles)))
    return 0


def main(argv=None):
    setup_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    plain = "--plain" in argv
    argv = [a for a in argv if a != "--plain"]
    cfg = load_config()
    name = cmd_name(cfg)
    try:
        if not argv or (argv[0] in ROLE_ALIASES or (argv[0] in TARGETS and len(argv) <= 2)) and len(argv) <= 2:
            if installed_targets(cfg):
                ensure_catalog(cfg)
            if not plain and tui_available():
                import_tui().run(argv)
                return 0
        if not argv:
            return dashboard(cfg)
        c = argv[0]
        if c in ("help", "-h", "--help"):
            print(help_text(name))
            return 0
        if c in ("version", "--version"):
            print("%s %s (%s)" % (name, VERSION, PROJECT))
            return 0
        if not installed_targets(cfg):
            print("설치된 대상이 없습니다. 저장소의 install.py로 설치하세요.")
            return 1
        if c in ("on", "off"):
            which = argv[1] if len(argv) > 1 else None
            if which not in (None, "all") + TARGETS:
                raise UserError("사용법: %s on|off [claude|codex|all]" % name)
            return cmd_switch(cfg, c == "on", which)
        if c == "status":
            ensure_catalog(cfg)
            return dashboard(cfg, full=True)
        if c == "models":
            ensure_catalog(cfg)
            return cmd_models(cfg)
        if c == "update":
            return cmd_update(cfg, argv[1] if len(argv) > 1 else None)
        if c == "selftest":
            return cmd_selftest(cfg, argv[1] if len(argv) > 1 else None)
        if c == "reset":
            return cmd_reset(cfg, argv[1:])
        if c == "preset":
            return cmd_preset(cfg, argv[1:])
        if c == "bridge":
            return cmd_bridge(cfg, argv[1:])
        if c == "pin":
            if len(argv) != 4 or argv[1] not in TARGETS:
                raise UserError("사용법: %s pin <claude|codex> <역할> <모델ID>" % name)
            set_role(cfg, argv[1], norm_role(argv[2]), argv[3], None)
            return 0
        if c == "unpin":
            if len(argv) != 3 or argv[1] not in TARGETS:
                raise UserError("사용법: %s unpin <claude|codex> <역할>" % name)
            set_role(cfg, argv[1], norm_role(argv[2]), DEFAULT_ROLES[argv[1]][norm_role(argv[2])]["model"], None)
            return 0
        # 역할 명령
        target, rest = parse_target_role(argv)
        if not rest:
            if is_tty():
                return interactive(cfg, target, None)
            raise UserError("역할이 필요합니다. 예: %s executor opus high" % name)
        if rest[0].lower() not in ROLE_ALIASES:
            raise UserError("알 수 없는 명령: %s\n%s" % (" ".join(argv), help_text(name)))
        role = norm_role(rest[0])
        if len(rest) == 1:
            if is_tty():
                return interactive(cfg, target, role)
            raise UserError("터미널이 아니라 대화형으로 물을 수 없습니다. 모델(과 강도)을 함께 적으세요. 예: %s %s opus high" % (name, role))
        if len(rest) > 3:
            raise UserError("인자가 너무 많습니다. 예: %s %s <모델> [<강도>]" % (name, role))
        t = single_target(cfg, target, role)
        set_role(cfg, t, role, rest[1], rest[2] if len(rest) == 3 else None)
        return 0
    except UserError as e:
        sys.stderr.write("%s: %s\n" % (name, e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
