#!/usr/bin/env python3
"""suhan-orchestration 설치기.

  python3 install.py plan        아무것도 바꾸지 않고 감지 결과·버전·할 일·충돌을 보여 준다
  python3 install.py install     설치(기본: 설치 뒤 켜 둠)
  python3 install.py verify      설치본 시험(oche selftest)
  python3 install.py uninstall   oche가 넣은 것만 뺀다(사용자 내용은 남김)

플래그: --only claude|codex, --migrate-legacy, --force-agents, --codex-models sol=..,terra=..,astra=..,
       --off, --command-name <이름>, --add-to-path
"""
import argparse
import importlib.util
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.abspath(__file__))


def _load_lib():
    path = os.path.join(REPO, "oche", "bin", "oche.py")
    spec = importlib.util.spec_from_file_location("oche_lib", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


L = _load_lib()
tilde = L.tilde


# ======================================================================
# 감지·충돌 검사
# ======================================================================

def legacy_claude(info):
    """옛 fable 설치본. (작동 중, 남은 흔적) 두 목록을 돌려준다.

    작동 중: CLAUDE.md 의 fable/active.md 불러오기 줄, settings.json 의 orchestration-gate 훅.
    남은 흔적: <claude>/fable/ 폴더, ~/.local/bin/fable. --migrate-legacy 뒤에도 일부러 남겨 두는 것들이라
    이것만 있으면 충돌이 아니다."""
    d = info["dir"]
    p = L.cpaths(d)
    active, residue = [], []
    if "fable/active.md" in (L.read_text(p["claude_md"]) or ""):
        active.append(p["claude_md"] + " (fable/active.md 불러오기 줄)")
    s = L.read_json(p["settings"], {})
    pre = ((s or {}).get("hooks") or {}).get("PreToolUse") if isinstance(s, dict) else None
    if L.has_hook(pre, "orchestration-gate"):
        active.append(p["settings"] + " (orchestration-gate 훅)")
    if os.path.isdir(os.path.join(d, "fable")):
        residue.append(os.path.join(d, "fable") + os.sep)
    fb = os.path.join(L.local_bin(), "fable")
    if os.path.lexists(fb):
        residue.append(fb)
    return active, residue


def legacy_residue_note(residue):
    return "옛 fable 파일이 남아 있지만 더는 쓰이지 않습니다. 필요 없으면 지워도 됩니다: %s" % ", ".join(tilde(x) for x in residue)


ENV_SH_NOTE = "셸 설정(~/.zshrc 등)에 `fable/env.sh`를 불러오는 줄이 있으면 더는 필요 없습니다. 지워도 됩니다."
SHELL_RCS = (".zshrc", ".zprofile", ".bashrc", ".bash_profile", ".profile")


def legacy_env_sh():
    """셸 설정 파일에 옛 fable/env.sh 를 불러오는 줄이 실제로 있는가(읽기만 한다)."""
    return [os.path.join(L.home(), n) for n in SHELL_RCS if "fable/env.sh" in (L.read_text(os.path.join(L.home(), n)) or "")]


def legacy_agent_link(path):
    try:
        return os.path.islink(path) and "fable" in os.readlink(path)
    except OSError:
        return False


def parse_codex_models(spec):
    out = {}
    if not spec:
        return out
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise SystemExit("--codex-models 형식은 sol=<ID>,terra=<ID>,astra=<ID> 입니다: %s" % part)
        k, v = part.split("=", 1)
        k = k.strip().lower()
        if k not in ("sol", "terra", "astra"):
            raise SystemExit("--codex-models 의 키는 sol·terra·astra 중 하나입니다: %s" % k)
        out[k] = v.strip()
    return out


def codex_roles_for(cfg, overrides):
    t = cfg.get("targets", {}).get("codex", {})
    roles = {}
    for r in L.ROLES:
        rc = (t.get("roles") or {}).get(r)
        roles[r] = dict(rc) if isinstance(rc, dict) and rc.get("model") else dict(L.DEFAULT_ROLES["codex"][r])
    if overrides.get("sol"):
        roles["executor"]["model"] = overrides["sol"]
        roles["deep-reasoner"]["model"] = overrides["sol"]
    if overrides.get("terra"):
        roles["runner"]["model"] = overrides["terra"]
    return roles


def gather(args, live=True):
    info = L.detect()
    cfg = L.load_config()
    ctx = {"info": info, "cfg": cfg, "targets": [], "skipped": [], "conflicts": {}, "notes": {}, "warn": {},
           "todo": {}, "codex": None}
    for t in L.TARGETS:
        ctx["conflicts"][t], ctx["notes"][t], ctx["warn"][t], ctx["todo"][t] = [], [], [], []
        if args.only and args.only != t:
            continue
        if info[t]["detected"]:
            ctx["targets"].append(t)
        else:
            ctx["skipped"].append(t)

    # 명령 이름
    name = args.command_name or cfg.get("command_name") or L.DEFAULT_NAME
    if not L.NAME_RE.match(name):
        raise SystemExit("--command-name 은 영문·숫자·-·_ 만 쓸 수 있습니다: %s" % name)
    ctx["name"] = name
    ctx["name_conflicts"] = L.name_conflicts(name)
    ctx["name_suggest"] = L.suggest_names(exclude=(name,)) if ctx["name_conflicts"] else []
    ctx["path_ok"] = L.path_has_local_bin()

    if "claude" in ctx["targets"]:
        ci = info["claude"]
        p = L.cpaths(ci["dir"])
        active, residue = legacy_claude(ci)
        ctx["legacy"] = active + residue
        ctx["legacy_active"], ctx["legacy_residue"] = active, residue
        if active:
            if args.migrate_legacy:
                ctx["notes"]["claude"].append("옛 fable 설치본을 옮깁니다(백업 후 옛 불러오기 줄·훅·하청 심링크를 빼고 .fable-state 를 off 로). "
                                              "%s/fable/ 과 ~/.local/bin/fable 은 건드리지 않습니다." % tilde(ci["dir"]))
            else:
                ctx["conflicts"]["claude"].append("옛 fable 설치본이 있습니다: %s → --migrate-legacy 로 옮기세요."
                                                  % ", ".join(tilde(x) for x in active + residue))
        elif residue:
            ctx["notes"]["claude"].append(legacy_residue_note(residue))
        envs = legacy_env_sh()
        if envs:
            ctx["notes"]["claude"].append(ENV_SH_NOTE + " (찾은 곳: %s)" % ", ".join(tilde(x) for x in envs))
        s = L.read_text(p["settings"])
        if s is not None and L.read_json(p["settings"], None) is None:
            ctx["conflicts"]["claude"].append("%s 이 올바른 JSON이 아닙니다. 고친 뒤 다시 실행하세요." % tilde(p["settings"]))
        for r in L.ROLES:
            dst = os.path.join(p["agents"], r + ".md")
            if legacy_agent_link(dst) and (args.migrate_legacy or active):
                continue
            if legacy_agent_link(dst):
                ctx["conflicts"]["claude"].append("%s 가 옛 fable 하청 심링크입니다 → --migrate-legacy 로 옮기세요." % tilde(dst))
                continue
            if not L.claude_agent_owned(p, r):
                if args.force_agents:
                    ctx["notes"]["claude"].append("%s 는 oche 것이 아니지만 --force-agents 로 백업 후 교체합니다." % tilde(dst))
                else:
                    ctx["conflicts"]["claude"].append("%s 가 이미 있고 oche 것이 아닙니다 → --force-agents 로 백업 후 교체." % tilde(dst))
        ctx["todo"]["claude"] = [
            "%s/oche/ 에 규칙·빈 파일·active.md(복사본)·게이트·하청 원본·roles.json 쓰기" % tilde(ci["dir"]),
            "%s/agents/{executor,deep-reasoner,runner}.md 쓰기(실제 파일)" % tilde(ci["dir"]),
            "%s 끝에 불러오기 두 줄 더하기(이미 있으면 생략)" % tilde(p["claude_md"]),
            "%s 의 PreToolUse 에 게이트 훅 병합" % tilde(p["settings"]),
            "스위치 %s" % ("off 로 둠(--off)" if args.off else "on"),
        ]

    if "codex" in ctx["targets"]:
        xi = info["codex"]
        p = L.xpaths(xi["dir"])
        overrides = parse_codex_models(args.codex_models)
        roles = codex_roles_for(cfg, overrides)
        source, models, app = L.codex_models(xi["dir"], xi.get("exe"), xi.get("app_engine"), live=live,
                                             app_version=xi.get("app_version") or "")
        if app and app.get("stale_note"):
            ctx["warn"]["codex"].append(app["stale_note"])
        res, warnings, failed = L.resolve_codex_roles(roles, models, app)
        ctx["codex"] = {"roles": roles, "res": res, "source": source, "failed": failed, "overrides": overrides,
                        "subagent_fields": L.codex_subagent_fields(xi)}
        ctx["warn"]["codex"].extend(warnings)
        if failed:
            ctx["conflicts"]["codex"].append(
                "Codex 모델을 정하지 못했습니다(%s). 찾은 모델: %s → --codex-models sol=<ID>,terra=<ID> 로 지정하세요."
                % (", ".join(failed), ", ".join(L.sync_mod().candidate_slugs(models)) or "없음"))
        if not ctx["codex"]["subagent_fields"]:
            ctx["warn"]["codex"].append("Codex CLI나 앱 엔진이 0.171.0 미만입니다. 게이트를 저하 모드로 둡니다"
                                        "(재하청 차단·수정 개수 세기 끔, 타입·모델·강도 검사는 유지). Codex를 업데이트한 뒤 다시 설치하세요.")
        if xi.get("version") is None and xi.get("exe"):
            ctx["warn"]["codex"].append("codex --version 을 읽지 못했습니다.")
        if xi.get("app_engine") and xi.get("app_version") is None:
            ctx["warn"]["codex"].append("ChatGPT 앱의 Codex 엔진 버전을 읽지 못했습니다.")
        import re as _re
        if _re.search(r"(?m)^\s*\[\[?hooks[\].]", L.read_text(p["config_toml"]) or ""):
            ctx["warn"]["codex"].append("%s 에 인라인 [hooks] 가 있습니다. hooks.json 과 함께 쓰면 Codex가 둘 다 읽고 경고합니다."
                                        % tilde(p["config_toml"]))
        h = L.read_text(p["hooks"])
        if h is not None and L.read_json(p["hooks"], None) is None:
            ctx["conflicts"]["codex"].append("%s 이 올바른 JSON이 아닙니다. 고친 뒤 다시 실행하세요." % tilde(p["hooks"]))
        for r in L.ROLES:
            if not L.codex_toml_owned(p["tomls"][r]):
                if args.force_agents:
                    ctx["notes"]["codex"].append("%s 는 oche 것이 아니지만 --force-agents 로 백업 후 교체합니다." % tilde(p["tomls"][r]))
                else:
                    ctx["conflicts"]["codex"].append("%s 가 이미 있고 oche 것이 아닙니다 → --force-agents 로 백업 후 교체." % tilde(p["tomls"][r]))
        ctx["todo"]["codex"] = [
            "%s/oche/ 에 규칙·게이트·sync·models.json·gate.json 쓰기" % tilde(xi["dir"]),
            "%s/agents/{executor,deep-reasoner,runner}.toml 쓰기" % tilde(xi["dir"]),
            "%s 에 PreToolUse(게이트)·SessionStart(sync) 병합 (command + commandWindows)" % tilde(p["hooks"]),
            "스위치 %s — 규칙 구역 위치: %s" % ("off 로 둠(--off)" if args.off else "on", tilde(L.agents_target(p))),
        ]
    return ctx


def print_plan(ctx, args):
    info = ctx["info"]
    print("suhan-orchestration %s 설치 계획 (plan은 아무것도 바꾸지 않습니다)" % L.VERSION)
    plat = "Windows" if L.is_windows() else sys.platform
    if L.is_windows() and os.name != "nt":
        plat += " (흉내 모드: ORCH_FORCE_WINDOWS=1)"
    print("환경: %s · Python %s · 명령 이름: %s" % (plat, sys.version.split()[0], ctx["name"]))
    for t in L.TARGETS:
        i = info[t]
        if t in ctx["skipped"]:
            print("\n[%s] 감지 안 됨 — 건너뜀" % L.TARGET_LABEL[t])
            continue
        if t not in ctx["targets"]:
            print("\n[%s] --only 로 제외" % L.TARGET_LABEL[t])
            continue
        if t == "claude":
            ver = "claude %s" % (i["version"] or ("실행 파일 없음" if not i["exe"] else "버전 읽기 실패"))
        else:
            ver = "CLI %s" % (i["version"] or ("없음" if not i["exe"] else "버전 읽기 실패"))
            ver += ", 앱 엔진 %s" % ((i["app_version"] or "버전 읽기 실패") if i.get("app_engine") else "없음")
        print("\n[%s] 감지됨 — %s (%s)" % (L.TARGET_LABEL[t], tilde(i["dir"]), ver))
        if t == "codex" and ctx["codex"]:
            c = ctx["codex"]
            print("  모델 결정 출처: %s" % (c["source"] or "없음"))
            for r in L.ROLES:
                rr = c["res"].get(r)
                if rr:
                    extra = " (다리 → Claude %s)" % rr["bridge"]["model"] if rr.get("bridge") else ""
                    print("    %-14s %s → %s, 강도 %s%s" % (r, L.model_label("codex", c["roles"][r]["model"]), rr["model"], rr["effort"], extra))
        if t == "claude":
            cfg_roles = (ctx["cfg"].get("targets", {}).get("claude", {}) or {}).get("roles") or {}
            for r in L.ROLES:
                rc = cfg_roles.get(r) or L.DEFAULT_ROLES["claude"][r]
                print("    %-14s %s, 강도 %s" % (r, rc["model"], rc["effort"]))
        for x in ctx["todo"][t]:
            print("  할 일: " + x)
        for x in ctx["notes"][t]:
            print("  안내: " + x)
        for x in ctx["warn"][t]:
            print("  경고: " + x)
        for x in ctx["conflicts"][t]:
            print("  충돌: " + x)
    print("\n[공용]")
    print("  할 일: %s/ 에 config.json·log.txt·assets/ 두기, 명령 %s 만들기"
          % (tilde(L.oche_home()), ", ".join(tilde(x) for x in L.wrapper_files(ctx["name"]))))
    if ctx["name_conflicts"]:
        for x in ctx["name_conflicts"]:
            print("  이름 충돌: %s" % tilde(x))
        print("  → 다른 이름으로 설치하세요: python3 install.py install --command-name <이름>  (비어 있는 후보: %s)"
              % (", ".join(ctx["name_suggest"]) or "없음"))
    if ctx["path_ok"]:
        print("  PATH: %s 있음" % tilde(L.local_bin()))
    else:
        print("  PATH: %s 가 PATH에 없습니다. --add-to-path 로 추가하거나(셸 설정 파일/사용자 PATH, 백업 포함) 전체 경로로 실행하세요."
              % tilde(L.local_bin()))
    ok = [t for t in ctx["targets"] if not ctx["conflicts"][t]]
    bad = [t for t in ctx["targets"] if ctx["conflicts"][t]]
    print("\n요약: 설치 가능 %s · 거부될 대상 %s%s" % (
        ", ".join(L.TARGET_LABEL[t] for t in ok) or "없음",
        ", ".join(L.TARGET_LABEL[t] for t in bad) or "없음",
        " · 명령 이름 충돌로 install 거부" if ctx["name_conflicts"] else ""))


# ======================================================================
# 설치
# ======================================================================

SHIM = '''#!/usr/bin/env python3
# oche-wrapper (suhan-orchestration): ~/.oche/assets/oche/bin/oche.py 를 실행한다.
import os
import runpy
import sys

here = os.path.dirname(os.path.abspath(__file__))
target = os.path.join(os.path.dirname(here), "assets", "oche", "bin", "oche.py")
sys.argv[0] = target
runpy.run_path(target, run_name="__main__")
'''


def copy_assets():
    dst = os.path.join(L.oche_home(), "assets")
    if os.path.isdir(dst) and L.same_path(os.path.realpath(dst), os.path.realpath(REPO)):
        return dst
    os.makedirs(L.oche_home(), exist_ok=True)
    tmp = dst + ".new-" + L.stamp()
    ign = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    shutil.copytree(os.path.join(REPO, "oche"), os.path.join(tmp, "oche"), ignore=ign)
    shutil.copy2(os.path.abspath(__file__), os.path.join(tmp, "install.py"))
    for extra in ("LICENSE",):
        if os.path.isfile(os.path.join(REPO, extra)):
            shutil.copy2(os.path.join(REPO, extra), os.path.join(tmp, extra))
    old = None
    if os.path.isdir(dst):
        old = dst + ".old-" + L.stamp()
        os.rename(dst, old)
    os.rename(tmp, dst)
    if old:
        shutil.rmtree(old, ignore_errors=True)
    return dst


def install_common(ctx, cfg, args, backup):
    copy_assets()
    L.atomic_write(L.cli_path(), SHIM, mode=0o755)
    old_name = cfg.get("command_name")
    made = L.write_wrappers(ctx["name"])
    if old_name and old_name != ctx["name"]:
        gone = L.remove_wrappers(old_name)
        if gone:
            print("옛 이름 명령을 지웠습니다: %s" % ", ".join(tilde(x) for x in gone))
    cfg["command_name"] = ctx["name"]
    cfg["oche_version"] = L.VERSION
    cfg["python"] = L.win_python_prefix() if L.is_windows() else L.posix_python()
    cfg["platform"] = "windows" if L.is_windows() else sys.platform
    cfg["installed_at"] = L.stamp()
    return made


def migrate_legacy(p, backup):
    done = []
    t = L.read_text(p["claude_md"])
    if t and "fable/active.md" in t:
        lines = t.split("\n")
        out = []
        for l in lines:
            if "fable/active.md" in l and l.strip().startswith("@"):
                if out and out[-1].strip().startswith("<!--") and "loader" in out[-1] and "fable" in out[-1]:
                    out.pop()
                continue
            out.append(l)
        backup(p["claude_md"])
        L.write_user_file(p["claude_md"], "\n".join(out))
        done.append("CLAUDE.md 의 옛 불러오기 줄을 뺐습니다")
    s = L.read_json(p["settings"], None)
    if isinstance(s, dict):
        pre = (s.get("hooks") or {}).get("PreToolUse")
        if L.has_hook(pre, "orchestration-gate"):
            s["hooks"]["PreToolUse"] = L.remove_hook(pre, "orchestration-gate")
            backup(p["settings"])
            L.write_user_file(p["settings"], L.json.dumps(s, ensure_ascii=False, indent=2) + "\n")
            done.append("settings.json 의 옛 orchestration-gate 훅을 뺐습니다")
    if os.path.isdir(p["agents"]):
        for fn in sorted(os.listdir(p["agents"])):
            f = os.path.join(p["agents"], fn)
            if legacy_agent_link(f):
                os.remove(f)
                done.append("옛 하청 심링크를 지웠습니다: %s" % tilde(f))
    fs = os.path.join(p["dir"], ".fable-state")
    if os.path.exists(fs) and (L.read_text(fs) or "").strip() != "off":
        backup(fs)
        L.atomic_write(fs, "off\n")
        done.append(".fable-state 를 off 로 두었습니다")
    return done


def install_claude(ctx, cfg, args, backup):
    ci = ctx["info"]["claude"]
    p = L.cpaths(ci["dir"])
    msgs = []
    if args.migrate_legacy and ctx.get("legacy"):
        msgs.extend(migrate_legacy(p, backup))
    if args.migrate_legacy and ctx.get("legacy_active"):
        msgs.append("%s/fable/ 과 ~/.local/bin/fable 은 그대로 두었습니다. 더는 쓰지 않으니 필요 없으면 직접 지우세요."
                    % tilde(ci["dir"]))
    elif ctx.get("legacy_residue"):
        msgs.append("안내: " + legacy_residue_note(ctx["legacy_residue"]))
    if ctx.get("legacy") and legacy_env_sh():
        msgs.append(ENV_SH_NOTE)
    t = cfg["targets"].setdefault("claude", {})
    t.update({"dir": ci["dir"], "exe": ci["exe"], "version": ci["version"]})
    for r in L.ROLES:
        L.role_cfg(cfg, "claude", r)
    for sub in ("hooks", "state", "agents"):
        os.makedirs(os.path.join(p["oche"], sub), exist_ok=True)
    os.makedirs(p["agents"], exist_ok=True)
    a = L.asset_root()
    L.atomic_write(p["rules"], L.read_text(os.path.join(a, "claude", "rules.md")))
    L.atomic_write(p["empty"], L.read_text(os.path.join(a, "claude", "empty.md")))
    L.atomic_write(p["gate"], L.read_text(os.path.join(a, "claude", "gate.py")), mode=0o755)
    L.write_claude_agents(p, cfg, force=args.force_agents, backup=backup)
    text = L.read_text(p["claude_md"])
    if not L.has_loader(text):
        if text is not None:
            backup(p["claude_md"])
        body = text or ""
        add = L.claude_loader_comment(ctx["name"]) + "\n" + L.claude_loader_line(ci["dir"]) + "\n"
        body = body + ("" if not body or body.endswith("\n") else "\n") + ("\n" if body.strip() else "") + add
        L.write_user_file(p["claude_md"], body)
        msgs.append("CLAUDE.md 에 불러오기 줄을 더했습니다")
    s = L.read_json(p["settings"], {}) if os.path.exists(p["settings"]) else {}
    if not isinstance(s, dict):
        s = {}
    before = L.json.dumps(s, sort_keys=True)
    hooks = s.setdefault("hooks", {})
    hooks["PreToolUse"] = L.upsert_hook(hooks.get("PreToolUse"), L.CLAUDE_MATCHER, L.claude_hook_entry(p), "oche-gate")
    if L.json.dumps(s, sort_keys=True) != before:
        backup(p["settings"])
        L.write_user_file(p["settings"], L.json.dumps(s, ensure_ascii=False, indent=2) + "\n")
        msgs.append("settings.json 에 게이트 훅을 병합했습니다")
    L.claude_set_switch(p, not args.off)
    return msgs


def install_codex(ctx, cfg, args, backup):
    xi = ctx["info"]["codex"]
    c = ctx["codex"]
    p = L.xpaths(xi["dir"])
    msgs = []
    t = cfg["targets"].setdefault("codex", {})
    t.update({"dir": xi["dir"], "exe": xi["exe"], "version": xi["version"], "app_engine": xi.get("app_engine"),
              "app_version": xi.get("app_version"), "subagent_fields": c["subagent_fields"]})
    t.setdefault("auto_update", True)
    t["roles"] = c["roles"]
    if c["overrides"].get("astra"):
        t["main_model"] = c["overrides"]["astra"]
    for sub in ("hooks", "state"):
        os.makedirs(os.path.join(p["oche"], sub), exist_ok=True)
    os.makedirs(os.path.dirname(p["tomls"]["executor"]), exist_ok=True)
    a = L.asset_root()
    L.atomic_write(p["rules"], L.read_text(os.path.join(a, "codex", "rules.md")))
    L.atomic_write(p["gate"], L.read_text(os.path.join(a, "codex", "gate.py")), mode=0o755)
    L.atomic_write(p["sync"], L.read_text(os.path.join(a, "codex", "sync.py")), mode=0o755)
    L.write_json(p["gate_json"], {"subagent_fields": c["subagent_fields"]})
    L.write_codex_agents(p, cfg, c["res"], force=args.force_agents, backup=backup, source=c["source"])
    # 훅 모델 갱신이 설치 직후 더 낡은 캐시로 되돌리지 않게 도장을 찍어 둔다.
    L.atomic_write(os.path.join(p["state_dir"], "sync.stamp"), L.stamp() + "\n")
    for f in (p["override"], p["agents_md"]):
        if os.path.exists(f) and "<!-- oche:begin" not in (L.read_text(f) or ""):
            backup(f)
    h = L.read_json(p["hooks"], {}) if os.path.exists(p["hooks"]) else {}
    if not isinstance(h, dict):
        h = {}
    before = L.json.dumps(h, sort_keys=True)
    hk = h.setdefault("hooks", {})
    gate_e, sync_e = L.codex_hook_entries(p)
    hk["PreToolUse"] = L.upsert_hook(hk.get("PreToolUse"), L.CODEX_PRE_MATCHER, gate_e, "oche-gate")
    hk["SessionStart"] = L.upsert_hook(hk.get("SessionStart"), L.CODEX_START_MATCHER, sync_e, "oche-sync")
    if L.json.dumps(h, sort_keys=True) != before:
        backup(p["hooks"])
        L.write_user_file(p["hooks"], L.json.dumps(h, ensure_ascii=False, indent=2) + "\n")
        msgs.append("hooks.json 에 게이트·sync 훅을 병합했습니다(훅 정의가 바뀌었으니 다시 신뢰해야 합니다)")
    L.codex_set_switch(p, not args.off)
    return msgs


def choose_targets(args):
    """--only/--all 이 없을 때: 사람이 터미널에서 돌리면 묻고, 아니면 None(=plan 만 보이고 끝)."""
    if args.only or args.all:
        return True
    info = L.detect()
    found = [t for t in L.TARGETS if info[t]["detected"]]
    try:
        tty = sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):
        tty = False
    if not tty or os.environ.get("ORCH_NO_PROMPT") == "1":
        return None
    if not found:
        return True
    for t in L.TARGETS:
        if t not in found:
            print("%s: 설치돼 있지 않음" % L.TARGET_LABEL[t])
    opts = [(L.TARGET_LABEL[t], t) for t in found]
    if len(found) == 2:
        opts.append(("둘 다", "all"))
    print("어디에 설치할까요?")
    for i, (label, _) in enumerate(opts, 1):
        print("  %d) %s" % (i, label))
    while True:
        sys.stdout.write("번호: ")
        sys.stdout.flush()
        a = sys.stdin.readline().strip()
        if a.isdigit() and 1 <= int(a) <= len(opts):
            v = opts[int(a) - 1][1]
            if v == "all":
                args.all = True
            else:
                args.only = v
            return True
        if not a:
            return False


def cmd_install(args):
    picked = choose_targets(args)
    if picked is None:
        print_plan(gather(args), args)
        print("\n설치 대상을 정하지 않았습니다. 사용자에게 \"Claude Code / Codex / 둘 다 중 어디에 설치할까요?\"라고 묻고, "
              "답에 따라 install --only claude, install --only codex, install --all 중 하나로 다시 실행하세요.")
        return 4
    if picked is False:
        print("취소했습니다.")
        return 4
    ctx = gather(args)
    cfg = ctx["cfg"]
    name = ctx["name"]
    if ctx["name_conflicts"]:
        print("설치 거부: 명령 이름 '%s' 이(가) 이미 쓰이고 있습니다." % name)
        for x in ctx["name_conflicts"]:
            print("  이름 충돌: %s" % tilde(x))
        print("다른 이름으로 설치하세요: python3 install.py install --command-name <이름>  (비어 있는 후보: %s)"
              % (", ".join(ctx["name_suggest"]) or "없음"))
        return 3
    if not ctx["targets"]:
        print("설치할 대상이 없습니다(Claude Code·Codex 모두 감지 안 됨). python3 install.py plan 으로 확인하세요.")
        return 3
    ok = [t for t in ctx["targets"] if not ctx["conflicts"][t]]
    refused = [t for t in ctx["targets"] if ctx["conflicts"][t]]
    for t in refused:
        print("[%s] 설치 거부:" % L.TARGET_LABEL[t])
        for x in ctx["conflicts"][t]:
            print("  충돌: " + x)
    if not ok:
        return 3
    backup = L.Backup()
    install_common(ctx, cfg, args, backup)
    for t in ok:
        msgs = (install_claude if t == "claude" else install_codex)(ctx, cfg, args, backup)
        L.save_config(cfg)
        print("[%s] 설치 완료 — %s" % (L.TARGET_LABEL[t], tilde(ctx["info"][t]["dir"])))
        for m in msgs:
            print("  " + m)
        for w in ctx["warn"][t]:
            print("  경고: " + w)
    L.save_config(cfg)
    for n in L.refresh_catalog(cfg, live=False):
        pass
    L.log("install %s (name=%s, off=%s)" % (",".join(ok), name, args.off))
    if backup.done:
        print("백업: " + ", ".join(tilde(v) for v in backup.done.values()))
    if args.add_to_path:
        print("PATH: " + L.add_to_path(backup))
    elif not L.path_has_local_bin():
        print("PATH: %s 가 PATH에 없습니다. --add-to-path 로 다시 실행하거나 %s 처럼 전체 경로로 실행하세요."
              % (tilde(L.local_bin()), tilde(L.wrapper_files(name)[0])))
    print("")
    print("다음 할 일:")
    print("  1) 검증: python3 install.py verify")
    if "codex" in ok:
        print("  2) Codex 훅 신뢰(사람이 직접): CLI는 새 codex 세션에서 /hooks, ChatGPT 앱은 새 Codex 채팅 입력창의 "
              "Review hooks 또는 Settings > Hooks 에서 'oche 게이트 확인'·'oche 하청 모델 확인' 훅을 신뢰")
    print("  %s) 새 세션(Claude Code)·새 채팅(ChatGPT 앱)을 열어야 적용됩니다." % ("3" if "codex" in ok else "2"))
    print("  켜기: %s on   끄기: %s off   현황: %s" % (name, name, name))
    if not refused:
        print("")
        print("도움이 됐다면 저장소에 스타 하나 눌러 주세요: https://github.com/suhan-dev/suhan-orchestration")
    return 3 if refused else 0


# ======================================================================
# 검증·제거
# ======================================================================

def cmd_verify(args):
    cfg = L.load_config()
    if not L.installed_targets(cfg):
        print("설치된 대상이 없습니다.")
        return 1
    name = L.cmd_name(cfg)
    bad = 0
    for w in L.wrapper_files(name):
        ok = os.path.isfile(w) and L.is_our_wrapper(w)
        bad += 0 if ok else 1
        print("%s  명령 파일 %s" % ("OK   " if ok else "FAIL ", tilde(w)))
    ok = os.path.isfile(L.cli_path())
    bad += 0 if ok else 1
    print("%s  %s" % ("OK   " if ok else "FAIL ", tilde(L.cli_path())))
    argv = [sys.executable, L.cli_path(), "selftest"]
    if args.only:
        argv.append(args.only)
    p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    sys.stdout.write(p.stdout.decode("utf-8", "replace"))
    if not L.path_has_local_bin():
        print("안내: %s 가 PATH에 없습니다(명령은 전체 경로로 실행)." % tilde(L.local_bin()))
    return 1 if (bad or p.returncode) else 0


def remove_loader(text):
    lines = (text or "").split("\n")
    out = []
    for l in lines:
        s = l.strip()
        if s.startswith("@") and s.endswith("oche/active.md"):
            if out and "oche-loader" in out[-1]:
                out.pop()
            continue
        out.append(l)
    while len(out) > 1 and out[-1] == "" and out[-2] == "":
        out.pop()
    return "\n".join(out)


def cmd_uninstall(args):
    cfg = L.load_config()
    backup = L.Backup()
    targets = [args.only] if args.only else (L.installed_targets(cfg) or
                                               [t for t in L.TARGETS if os.path.isdir(os.path.join(
                                                   L.claude_dir() if t == "claude" else L.codex_dir(), "oche"))])
    for t in targets:
        d = (cfg["targets"].get(t) or {}).get("dir") or (L.claude_dir() if t == "claude" else L.codex_dir())
        removed = []
        if t == "claude":
            p = L.cpaths(d)
            text = L.read_text(p["claude_md"])
            if text is not None and L.has_loader(text):
                backup(p["claude_md"])
                L.write_user_file(p["claude_md"], remove_loader(text))
                removed.append("CLAUDE.md 불러오기 줄")
            s = L.read_json(p["settings"], None)
            if isinstance(s, dict) and L.has_hook((s.get("hooks") or {}).get("PreToolUse"), "oche-gate"):
                backup(p["settings"])
                s["hooks"]["PreToolUse"] = L.remove_hook(s["hooks"]["PreToolUse"], "oche-gate")
                L.write_user_file(p["settings"], L.json.dumps(s, ensure_ascii=False, indent=2) + "\n")
                removed.append("settings.json 게이트 훅")
            for r in L.ROLES:
                f = os.path.join(p["agents"], r + ".md")
                if os.path.isfile(f) and L.claude_agent_owned(p, r):
                    os.remove(f)
                    removed.append(tilde(f))
        else:
            p = L.xpaths(d)
            for f in (p["override"], p["agents_md"]):
                if "<!-- oche:begin" in (L.read_text(f) or ""):
                    backup(f)
                    L.strip_block(f)
                    removed.append("%s 규칙 구역" % tilde(f))
            h = L.read_json(p["hooks"], None)
            if isinstance(h, dict) and isinstance(h.get("hooks"), dict):
                hk = h["hooks"]
                if L.has_hook(hk.get("PreToolUse"), "oche-gate") or L.has_hook(hk.get("SessionStart"), "oche-sync"):
                    backup(p["hooks"])
                    for ev, mk in (("PreToolUse", "oche-gate"), ("SessionStart", "oche-sync")):
                        if ev in hk:
                            hk[ev] = L.remove_hook(hk[ev], mk)
                            if not hk[ev]:
                                del hk[ev]
                    L.write_user_file(p["hooks"], L.json.dumps(h, ensure_ascii=False, indent=2) + "\n")
                    removed.append("hooks.json 훅 2개")
            for r in L.ROLES:
                f = p["tomls"][r]
                if os.path.isfile(f) and L.codex_toml_owned(f):
                    os.remove(f)
                    removed.append(tilde(f))
        if os.path.isdir(p["oche"]):
            shutil.rmtree(p["oche"], ignore_errors=True)
            removed.append(tilde(p["oche"]) + os.sep)
        if os.path.exists(p["state"]):
            os.remove(p["state"])
            removed.append(tilde(p["state"]))
        cfg["targets"].pop(t, None)
        print("[%s] 제거: %s" % (L.TARGET_LABEL[t], ", ".join(removed) or "없음"))
    if not L.installed_targets(cfg):
        name = L.cmd_name(cfg)
        gone = L.remove_wrappers(name)
        if gone:
            print("명령 제거: %s" % ", ".join(tilde(x) for x in gone))
        rcs = L.remove_path_lines(backup)
        if rcs:
            print("PATH 줄 제거: %s" % ", ".join(tilde(x) for x in rcs))
        if L.is_windows():
            print("안내: Windows 사용자 PATH에 넣은 %s 는 그대로 두었습니다(다른 도구도 쓸 수 있어서)." % L.local_bin())
        if os.path.isdir(L.oche_home()):
            shutil.rmtree(L.oche_home(), ignore_errors=True)
            print("제거: %s/" % tilde(L.oche_home()))
    else:
        L.save_config(cfg)
    if backup.done:
        print("백업: " + ", ".join(tilde(v) for v in backup.done.values()))
    print("사용자 내용(그 밖의 CLAUDE.md·settings.json·AGENTS.md·hooks.json 내용)은 그대로 두었습니다.")
    return 0


def main():
    L.setup_utf8()
    ap = argparse.ArgumentParser(description="suhan-orchestration 설치기")
    ap.add_argument("command", choices=["plan", "install", "verify", "uninstall"])
    ap.add_argument("--only", choices=["claude", "codex"])
    ap.add_argument("--all", action="store_true", help="감지된 대상 전부에 설치")
    ap.add_argument("--migrate-legacy", action="store_true", help="옛 fable 설치본을 옮긴다")
    ap.add_argument("--force-agents", action="store_true", help="oche 것이 아닌 같은 이름의 하청 정의를 백업 후 교체")
    ap.add_argument("--codex-models", default="", help="sol=<ID>,terra=<ID>,astra=<ID>")
    ap.add_argument("--off", action="store_true", help="설치하되 꺼 둔다")
    ap.add_argument("--command-name", default=None, help="터미널 명령 이름(기본 oche)")
    ap.add_argument("--add-to-path", action="store_true", help="~/.local/bin 을 PATH에 추가")
    args = ap.parse_args()
    if args.command == "plan":
        print_plan(gather(args), args)
        return 0
    if args.command == "install":
        return cmd_install(args)
    if args.command == "verify":
        return cmd_verify(args)
    return cmd_uninstall(args)


if __name__ == "__main__":
    sys.exit(main())
