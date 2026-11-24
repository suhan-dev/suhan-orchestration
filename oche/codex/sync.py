#!/usr/bin/env python3
# <codex>/oche/hooks/oche-sync.py — Codex 하청 모델 자동 최신화 (SessionStart 훅) + 모델 결정 라이브러리
#
# 훅으로 돌 때:
# - 1시간에 한 번만 돈다(state/sync.stamp). 하위 프로세스·네트워크 없이 Codex가 이미 받아 둔 모델 캐시만 읽는다.
# - "최신 계열"로 정해진 역할(configured = latest:<계열>)의 모델이 바뀌면 하청 정의 TOML 의 model 줄을 다시 쓰고
#   models.json 을 갱신하고 ~/.oche/log.txt 에 남긴다. 그때만 stdout 에 사용자 표시용 systemMessage 한 줄을 낸다.
# - 그 밖에는 아무것도 출력하지 않는다. stderr 는 쓰지 않고 늘 exit 0 으로 끝난다. 스위치가 꺼져 있어도 돈다.
# oche 명령과 install.py 도 이 파일을 라이브러리로 불러 같은 규칙으로 모델을 정한다.
import calendar
import glob
import json
import os
import re
import sys
import tempfile
import time

EFFORT_ORDER = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]
SLUG_RE = re.compile(r"^gpt-(\d+(?:\.\d+)*)-([a-z]+)$")  # 계열 이름을 나열하지 않는다(새 계열도 잡힌다)
ROLES = ("executor", "deep-reasoner", "runner")
TOML_FILE = {"executor": "executor.toml", "deep-reasoner": "deep-reasoner.toml", "runner": "runner.toml"}
AGENT_NAME = {"executor": "executor", "deep-reasoner": "deep_reasoner", "runner": "runner"}
MARKER = "# oche-managed"
APP_CACHE = "models_cache.codex_work_desktop.json"
APP_FRESH_SECONDS = 14 * 86400
SYNC_INTERVAL = 3600
BRIDGE_FAMILY = "terra"  # 다리 하청 정의에 쓰는 계열 = runner 기본 계열


# ---------- 모델 목록 다루기 ----------

def parse_slug(slug):
    m = SLUG_RE.match(str(slug or ""))
    if not m:
        return None
    return m.group(2), tuple(int(x) for x in m.group(1).split("."))


def listed(entry):
    vis = entry.get("visibility")
    return vis is None or vis == "list"


def effort_levels(entry):
    out = []
    for x in (entry or {}).get("supported_reasoning_levels") or []:
        if isinstance(x, dict):
            x = x.get("effort")
        if isinstance(x, str) and x:
            out.append(x.lower())
    return out


def fit_effort(target, levels):
    """target 을 지원하면 그대로, 아니면 EFFORT_ORDER 에서 가장 가까운 아래 값. ultra 는 절대 고르지 않는다."""
    target = (target or "").lower()
    usable = [x for x in levels if x in EFFORT_ORDER]
    if not usable or target not in EFFORT_ORDER:
        return target
    if target in usable:
        return target
    rank = EFFORT_ORDER.index(target)
    below = [x for x in usable if EFFORT_ORDER.index(x) < rank]
    if below:
        return max(below, key=EFFORT_ORDER.index)
    return min(usable, key=EFFORT_ORDER.index)


def by_slug(models):
    return {m.get("slug"): m for m in models or [] if isinstance(m, dict) and m.get("slug")}


def latest_by_family(models):
    best = {}
    for m in models or []:
        if not isinstance(m, dict) or not listed(m):
            continue
        p = parse_slug(m.get("slug"))
        if not p:
            continue
        fam, ver = p
        if fam not in best or ver > best[fam][0]:
            best[fam] = (ver, m["slug"])
    return {f: v[1] for f, v in best.items()}


def candidate_slugs(models):
    return sorted(m.get("slug") for m in models or [] if isinstance(m, dict) and listed(m) and parse_slug(m.get("slug")))


def parse_models_json(text):
    """`codex debug models` 출력이나 캐시 파일에서 models 목록을 꺼낸다."""
    text = text or ""
    i = text.find("{")
    if i < 0:
        return None
    try:
        data = json.loads(text[i:])
    except ValueError:
        try:
            data, _ = json.JSONDecoder().raw_decode(text[i:])
        except ValueError:
            return None
    models = data.get("models") if isinstance(data, dict) else None
    return models if isinstance(models, list) else None


def parse_time(value):
    s = str(value or "")
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})", s)
    if not m:
        return 0.0
    try:
        return float(calendar.timegm(time.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M:%S")))
    except ValueError:
        return 0.0


def load_cache(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        return None
    return {"path": path, "fetched_at": parse_time(data.get("fetched_at")), "models": data["models"],
            "client_version": data.get("client_version")}


def caches(codex_dir):
    out = []
    for p in sorted(glob.glob(os.path.join(codex_dir, "models_cache*.json"))):
        c = load_cache(p)
        if c:
            out.append(c)
    return out


def newest_cache(codex_dir):
    cs = caches(codex_dir)
    return max(cs, key=lambda c: c["fetched_at"]) if cs else None


APP_STALE_NOTE = "앱 모델 캐시가 낡아 무시함 — ChatGPT 앱에서 새 Codex 채팅을 한 번 열면 갱신됨"


def vtuple(v):
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", str(v or ""))
    return tuple(int(x) for x in m.groups()) if m else None


def app_cache(codex_dir, now=None, engine_version=None):
    """ChatGPT 앱의 모델 캐시. 14일 안에 받았고 client_version 이 지금 앱 엔진 버전과 같을 때만(알파 접미사 무시) 쓴다."""
    c = load_cache(os.path.join(codex_dir, APP_CACHE))
    if not c:
        return None
    now = time.time() if now is None else now
    recent = c["fetched_at"] > 0 and now - c["fetched_at"] <= APP_FRESH_SECONDS
    cv, ev = vtuple(c.get("client_version")), vtuple(engine_version)
    c["fresh"] = bool(recent and cv is not None and cv == ev)
    c["stale_note"] = None if c["fresh"] else APP_STALE_NOTE
    return c


# ---------- 역할 하나의 모델 결정 ----------

def pick_latest(family, models, app=None, warnings=None):
    latest = latest_by_family(models).get(family)
    if not latest:
        return None
    if app and app.get("fresh"):
        app_slugs = set(by_slug(app["models"]))
        if latest not in app_slugs:
            both = [m for m in models if isinstance(m, dict) and m.get("slug") in app_slugs]
            alt = latest_by_family(both).get(family)
            if alt:
                if warnings is not None:
                    warnings.append("ChatGPT 앱의 모델 캐시(14일 이내)에 %s가 없어 앱과 CLI 모두에 있는 %s를 씁니다." % (latest, alt))
                return alt
            if warnings is not None:
                warnings.append("ChatGPT 앱의 모델 캐시에 %s 계열이 없습니다. 앱에서는 %s가 거부될 수 있습니다." % (family, latest))
    return latest


def resolve_role(configured, configured_effort, models, app=None, warnings=None):
    """설정값 하나를 실제 정의 파일 값으로 바꾼다. 못 정하면 None."""
    configured = str(configured or "")
    idx = by_slug(models)
    bridge = None
    if configured.startswith("claude:"):
        bridge = {"model": configured.split(":", 1)[1], "effort": configured_effort}
        model = pick_latest(BRIDGE_FAMILY, models, app, warnings)
        target_effort = "low"
    elif configured.startswith("latest:"):
        model = pick_latest(configured.split(":", 1)[1], models, app, warnings)
        target_effort = configured_effort
    else:
        model = configured
        target_effort = configured_effort
    if not model:
        return None
    effort = fit_effort(target_effort, effort_levels(idx.get(model)))
    if effort == "ultra":
        effort = "max"
    if warnings is not None and effort != target_effort and not bridge:
        warnings.append("%s는 강도 %s를 지원하지 않아 %s를 씁니다." % (model, target_effort, effort))
    return {"configured": configured, "configured_effort": configured_effort, "model": model,
            "effort": effort, "bridge": bridge}


# ---------- 파일 쓰기 ----------

def atomic_write(path, text):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".oche-tmp-", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(path):
            try:
                os.chmod(tmp, os.stat(path).st_mode & 0o7777)
            except OSError:
                pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def update_toml_text(text, model, effort):
    text = re.sub(r'(?m)^model = ".*"$', lambda _: 'model = "%s"' % model, text, count=1)
    text = re.sub(r'(?m)^model_reasoning_effort = ".*"$', lambda _: 'model_reasoning_effort = "%s"' % effort, text, count=1)
    return text


def oche_home():
    return os.environ.get("OCHE_HOME") or os.path.join(os.path.expanduser("~"), ".oche")


def log(line):
    try:
        os.makedirs(oche_home(), exist_ok=True)
        with open(os.path.join(oche_home(), "log.txt"), "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), line))
    except OSError:
        pass


def sync_from(codex_dir, data, models, app, source):
    """models.json 내용(data)의 자동 역할을 models 목록으로 다시 정한다. 바뀐 내용 목록을 돌려준다."""
    changes = []
    roles = data.get("roles") or {}
    for role in ROLES:
        cur = roles.get(role)
        if not isinstance(cur, dict):
            continue
        conf = str(cur.get("configured") or "")
        if not (conf.startswith("latest:") or conf.startswith("claude:")):
            continue  # 사용자가 고정한 ID 는 건드리지 않는다
        new = resolve_role(conf, cur.get("configured_effort") or cur.get("effort"), models, app)
        if not new or (new["model"] == cur.get("model") and new["effort"] == cur.get("effort")):
            continue
        a, b = parse_slug(cur.get("model")), parse_slug(new["model"])
        if a and b and a[0] == b[0] and b[1] <= a[1]:
            continue  # 캐시가 더 낡았을 수 있으므로 훅은 올리기만 한다(내리기는 oche update 로)
        path = os.path.join(codex_dir, "agents", TOML_FILE[role])
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        if MARKER not in text:
            continue  # 사용자가 바꿔 둔 파일은 건드리지 않는다
        atomic_write(path, update_toml_text(text, new["model"], new["effort"]))
        msg = "%s %s → %s" % (role, cur.get("model"), new["model"])
        if new["effort"] != cur.get("effort"):
            msg += " (강도 %s → %s)" % (cur.get("effort"), new["effort"])
        changes.append(msg)
        cur.update({"model": new["model"], "effort": new["effort"]})
    if changes:
        data["roles"] = roles
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        data["source"] = source
        atomic_write(os.path.join(codex_dir, "oche", "models.json"), json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        log("sync(%s): %s" % (source, "; ".join(changes)))
    return changes


# ---------- 모델 목록 표(catalog.json) ----------

def catalog_entry(models, source):
    efforts = {}
    for m in models or []:
        if isinstance(m, dict) and listed(m) and parse_slug(m.get("slug")):
            efforts[m["slug"]] = [x for x in effort_levels(m) if x != "ultra"]
    return {"families": latest_by_family(models), "models": candidate_slugs(models), "efforts": efforts,
            "source": source, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}


def newer(a, b):
    """Codex slug a 가 b 보다 새것인가."""
    pa, pb = parse_slug(a), parse_slug(b)
    return bool(pa and pb and pa[1] > pb[1])


def merge_catalog(old, new, merge=True):
    """old 위에 new 를 얹는다. merge=True(캐시 기반)면 더 낡은 값으로 되돌리지 않는다. (결과, 알림 목록)."""
    old = old if isinstance(old, dict) else {}
    of = old.get("families") or {}
    nf = dict(new.get("families") or {})
    notices = []
    for fam, mid in sorted(nf.items()):
        if fam not in of:
            if of:
                notices.append("새 계열 발견: %s (%s)" % (fam, mid))
        elif of[fam] != mid:
            if newer(mid, of[fam]) or not merge:
                if newer(mid, of[fam]):
                    notices.append("새 최신: %s %s → %s" % (fam, of[fam], mid))
            else:
                nf[fam] = of[fam]
    out = dict(old)
    if merge:
        fams = dict(of)
        fams.update(nf)
        out["families"] = fams
        out["models"] = sorted(set(old.get("models") or []) | set(new.get("models") or []))
        eff = dict(old.get("efforts") or {})
        eff.update(new.get("efforts") or {})
        out["efforts"] = eff
    else:
        out["families"] = nf
        out["models"] = new.get("models") or []
        out["efforts"] = new.get("efforts") or {}
    for k in ("source", "updated_at", "tool_version"):
        if k in new:
            out[k] = new[k]
    return out, notices


def update_catalog(target, entry, merge=True):
    path = os.path.join(oche_home(), "catalog.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    old = data.get(target)
    new, notices = merge_catalog(old, entry, merge)
    if old is not None and {k: v for k, v in new.items() if k not in ("updated_at", "source")} == \
            {k: v for k, v in old.items() if k not in ("updated_at", "source")}:
        return notices
    data[target] = new
    os.makedirs(oche_home(), exist_ok=True)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    if notices:
        log("catalog(%s): %s" % (target, "; ".join(notices)))
    return notices


def hook_main():
    oche_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    codex_dir = os.path.dirname(oche_dir)
    state_dir = os.path.join(oche_dir, "state")
    stamp = os.path.join(state_dir, "sync.stamp")
    now = time.time()
    try:
        if now - os.path.getmtime(stamp) < SYNC_INTERVAL:
            return
    except OSError:
        pass
    os.makedirs(state_dir, exist_ok=True)
    with open(stamp, "w", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S\n"))
    try:
        with open(os.path.join(oche_dir, "models.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(data, dict):
        return
    if data.get("auto_update") is False:
        return
    cache = newest_cache(codex_dir)
    if not cache:
        return
    source = "cache:" + os.path.basename(cache["path"])
    changes = sync_from(codex_dir, data, cache["models"], app_cache(codex_dir, now, data.get("app_version")), source)
    notices = update_catalog("codex", catalog_entry(cache["models"], source), merge=True)
    parts = []
    if changes:
        parts.append("하청 모델 갱신 — " + "; ".join(changes))
    if notices:
        parts.append("; ".join(notices) + " (역할을 옮기려면 터미널에서 직접 바꾸세요)")
    if parts:
        sys.stdout.write(json.dumps({"systemMessage": "oche: " + " · ".join(parts)}, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        sys.stderr = open(os.devnull, "w")
    except OSError:
        pass
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        hook_main()
    except BaseException:
        pass
    os._exit(0)
