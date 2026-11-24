#!/usr/bin/env python3
"""suhan-orchestration 시험. 실제 HOME 은 건드리지 않는다(임시 HOME·가짜 claude/codex·임시 PATH).

    python3 tests/run_tests.py            # 전부
    python3 tests/run_tests.py sync tui   # 이름에 해당 낱말이 든 시나리오만
"""
import calendar
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
RESULTS = []
LATEST_LINE = 'latest_per_family:{fable:"claude-fable-5-2",opus:"claude-opus-5-5",sonnet:"claude-sonnet-5-5",haiku:"claude-haiku-5-5"}'


def check(name, cond, detail=""):
    RESULTS.append((bool(cond), name, detail))
    print(("OK    " if cond else "FAIL  ") + name + ("" if cond or not detail else "\n        " + str(detail)[:1500]))


def lv(*xs, **kw):
    if kw.get("strings"):
        return list(xs)
    return [{"effort": x, "description": x} for x in xs]


FULL = ("low", "medium", "high", "xhigh", "max", "ultra")


def default_models():
    return [
        {"slug": "gpt-6.2-sol", "visibility": "list", "priority": 1, "supported_reasoning_levels": lv(*FULL)},
        {"slug": "gpt-6.2-astra", "visibility": "list", "priority": 2, "supported_reasoning_levels": lv(*FULL)},
        {"slug": "gpt-6.1-terra", "visibility": "list", "priority": 3,
         "supported_reasoning_levels": lv("none", "low", "medium", "high", "xhigh", "max", "ultra", strings=True)},
        {"slug": "gpt-6.1-sol", "visibility": "list", "priority": 4, "supported_reasoning_levels": lv(*FULL)},
        {"slug": "gpt-6-luna", "visibility": "list", "priority": 5, "supported_reasoning_levels": lv("low", "medium", "high", "xhigh", "max")},
        {"slug": "gpt-5.6-sol", "visibility": "list", "priority": 6, "supported_reasoning_levels": lv(*FULL)},
        {"slug": "gpt-6.9-sol", "visibility": "hide", "priority": 7, "supported_reasoning_levels": lv(*FULL)},
        {"slug": "gpt-reserve", "visibility": "hide", "priority": 8, "supported_reasoning_levels": lv(*FULL)},
        {"slug": "codex-auto-review", "visibility": "hide", "priority": 9, "supported_reasoning_levels": lv("low")},
    ]


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime(ts))


class Env(object):
    def __init__(self, name, claude=True, codex=True, codex_version="0.171.0", models=None, windows=False, extra_env=None,
                 app_version=None):
        self.name = name
        self.root = tempfile.mkdtemp(prefix="oche-test-%s-" % name)
        self.home = os.path.join(self.root, "home")
        self.bin = os.path.join(self.root, "fakebin")
        os.makedirs(self.home)
        os.makedirs(self.bin)
        os.symlink(PY, os.path.join(self.bin, "python3"))
        self.windows = windows
        self.extra_env = dict(extra_env or {})
        if claude:
            self.set_claude("2.1.321", LATEST_LINE)
        if codex:
            self.models = models if models is not None else default_models()
            self.write(os.path.join(self.bin, "codex.version"), codex_version + "\n")
            self.write(os.path.join(self.bin, "codex.models.json"), json.dumps({"models": self.models}))
            self.codex_script = """#!%s
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
a = sys.argv[1:]
if a == ["--version"]:
    print("codex-cli " + open(os.path.join(here, "codex.version")).read().strip()); sys.exit(0)
if a[:2] == ["debug", "models"]:
    sys.stdout.write(open(os.path.join(here, "codex.models.json")).read()); sys.exit(0)
sys.exit(1)
""" % PY
            self.write(os.path.join(self.bin, "codex"), self.codex_script, 0o755)
        if app_version:
            ad = os.path.join(self.root, "app")
            self.write(os.path.join(ad, "codex.version"), app_version + "\n")
            self.write(os.path.join(ad, "codex.models.json"), json.dumps({"models": self.models}))
            self.write(os.path.join(ad, "codex"), self.codex_script, 0o755)
            self.extra_env["OCHE_CODEX_APP_ENGINE"] = os.path.join(ad, "codex")

    def set_claude(self, version, latest_line):
        self.write(os.path.join(self.bin, "claude"),
                   "#!%s\n# %s\nimport sys\nprint('%s (Claude Code)')\n" % (PY, latest_line, version), 0o755)

    def set_codex_models(self, models):
        self.write(os.path.join(self.bin, "codex.models.json"), json.dumps({"models": models}))

    def write(self, path, text, mode=None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        if mode:
            os.chmod(path, mode)

    def read(self, rel):
        try:
            with open(self.p(rel), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None

    def p(self, rel):
        return os.path.join(self.home, rel)

    def env(self, extra=None):
        e = {k: v for k, v in os.environ.items()
             if not k.startswith(("ORCH_", "OCHE_", "CODEX_", "CLAUDE_")) and k not in ("NO_COLOR",)}
        e.update({"HOME": self.home, "USERPROFILE": self.home, "PATH": self.bin + ":/usr/bin:/bin",
                  "OCHE_CODEX_APP_ENGINE": "", "SHELL": "/bin/zsh", "LANG": "en_US.UTF-8"})
        if self.windows:
            e["ORCH_FORCE_WINDOWS"] = "1"
        e.update(self.extra_env)
        e.update(extra or {})
        return e

    def run(self, argv, stdin=None, extra=None, timeout=120):
        p = subprocess.run(argv, input=(stdin or "").encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=self.env(extra), cwd=self.root, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")

    def install(self, *args, **kw):
        args = list(args)
        if args and args[0] == "install" and "--only" not in args and "--all" not in args and not kw.pop("raw", False):
            args.append("--all")
        c, o, e = self.run([PY, os.path.join(REPO, "install.py")] + list(args), **kw)
        return c, o + e

    def oche(self, *args, **kw):
        c, o, e = self.run([PY, self.p(".oche/bin/oche.py")] + list(args), **kw)
        return c, o + e

    def cache(self, models, fetched_at=None, name="models_cache.json", client="0.171.0"):
        self.write(self.p(".codex/" + name), json.dumps({"fetched_at": iso(fetched_at or time.time()), "etag": "x",
                                                        "client_version": client, "models": models}))

    def toml(self, role):
        t = self.read(".codex/agents/%s.toml" % role) or ""
        out = {}
        for line in t.splitlines():
            for k in ("name", "model", "model_reasoning_effort"):
                if line.startswith(k + " = "):
                    out[k] = line.split(" = ", 1)[1].strip().strip('"')
        return out

    def gate(self, target, payload, extra=None):
        g = self.p(".claude/oche/hooks/oche-gate.py" if target == "claude" else ".codex/oche/hooks/oche-gate.py")
        c, o, e = self.run([PY, g], stdin=json.dumps(payload), extra=extra)
        return c

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def nofail(out):
    return not any(l.startswith("FAIL") for l in out.splitlines())


def frontmatter(text, key):
    for line in (text or "").splitlines():
        if line.startswith(key + ":"):
            return line.split(":", 1)[1].strip()
    return None


def no_symlinks(root):
    bad = []
    for d, dirs, files in os.walk(root):
        for n in dirs + files:
            if os.path.islink(os.path.join(d, n)):
                bad.append(os.path.join(d, n))
    return bad


# ======================================================================
# 시나리오
# ======================================================================

def s01_claude_only():
    e = Env("claude-only", codex=False)
    c, out = e.install("plan")
    check("1 Claude만: plan 성공, Codex 건너뜀", c == 0 and "[Codex] 감지 안 됨" in out, out)
    check("1 Claude만: 셸 설정에 fable/env.sh 가 없으면 env.sh 안내 없음", "fable/env.sh" not in out, out)
    c, out = e.install("install")
    check("1 Claude만: install 성공", c == 0, out)
    for r in ("executor", "deep-reasoner", "runner"):
        f = e.p(".claude/agents/%s.md" % r)
        check("1 Claude만: 하청 %s 은 실제 파일(심링크 아님)" % r, os.path.isfile(f) and not os.path.islink(f))
    ex = e.read(".claude/agents/executor.md")
    check("1 Claude만: executor = opus/high", frontmatter(ex, "model") == "opus" and frontmatter(ex, "effort") == "high", ex)
    check("1 Claude만: deep-reasoner = opus/xhigh", frontmatter(e.read(".claude/agents/deep-reasoner.md"), "effort") == "xhigh")
    check("1 Claude만: runner = haiku/low", frontmatter(e.read(".claude/agents/runner.md"), "model") == "haiku")
    check("1 Claude만: active.md = 규칙 복사본", e.read(".claude/oche/active.md") == e.read(".claude/oche/rules.md"))
    check("1 Claude만: CLAUDE.md 불러오기 줄", "@~/.claude/oche/active.md" in (e.read(".claude/CLAUDE.md") or ""))
    s = json.loads(e.read(".claude/settings.json"))
    cmds = [h["command"] for x in s["hooks"]["PreToolUse"] for h in x["hooks"]]
    check("1 Claude만: settings 게이트 훅(Agent|Task 포함)", any("oche-gate" in x for x in cmds)
          and "Task" in s["hooks"]["PreToolUse"][0]["matcher"], s)
    check("1 Claude만: Codex 폴더 안 만듦", not os.path.exists(e.p(".codex")))
    check("1 Claude만: ~/.local/bin/oche 래퍼", os.path.isfile(e.p(".local/bin/oche")) and not os.path.islink(e.p(".local/bin/oche")))
    check("1 Claude만: 심링크 없음", not no_symlinks(e.home), no_symlinks(e.home))
    c, out = e.install("verify")
    check("1 Claude만: verify 통과", c == 0 and nofail(out), out)
    c, out = e.oche()
    check("1 Claude만: 현황판", c == 0 and "[Claude Code] ON" in out and "opus → claude-opus-5-5" in out
          and "[Codex]" not in out, out)
    c, out = e.run([os.path.join(e.home, ".local/bin/oche"), "version"])[0:2]
    check("1 Claude만: 래퍼로 실행", c == 0 and "oche 1." in out, out)
    e.cleanup()


def s02_codex_only():
    e = Env("codex-only", claude=False)
    c, out = e.install("plan")
    check("2 Codex만: plan 이 모델 결정 표시(숨김 slug 제외)", c == 0 and "gpt-6.2-sol" in out and "gpt-6.9-sol" not in out
          and "[Claude Code] 감지 안 됨" in out, out)
    c, out = e.install("install")
    check("2 Codex만: install 성공", c == 0, out)
    check("2 Codex만: executor = gpt-6.2-sol/high", e.toml("executor") == {"name": "executor", "model": "gpt-6.2-sol",
                                                                          "model_reasoning_effort": "high"}, e.toml("executor"))
    check("2 Codex만: deep_reasoner = gpt-6.2-sol/xhigh", e.toml("deep-reasoner").get("model_reasoning_effort") == "xhigh"
          and e.toml("deep-reasoner").get("name") == "deep_reasoner")
    check("2 Codex만: runner = gpt-6.1-terra/low (문자열 강도 목록)", e.toml("runner").get("model") == "gpt-6.1-terra"
          and e.toml("runner").get("model_reasoning_effort") == "low")
    h = json.loads(e.read(".codex/hooks.json"))
    pre = h["hooks"]["PreToolUse"][0]
    st = h["hooks"]["SessionStart"][0]
    check("2 Codex만: hooks.json PreToolUse(matcher·timeout·statusMessage·commandWindows)",
          pre["matcher"] == "^(apply_patch|.*spawn_agent|Agent)$" and pre["hooks"][0]["timeout"] == 10
          and pre["hooks"][0]["statusMessage"] == "oche 게이트 확인" and "commandWindows" in pre["hooks"][0], pre)
    check("2 Codex만: hooks.json SessionStart sync", st["matcher"] == "startup|resume" and "oche-sync" in st["hooks"][0]["command"], st)
    check("2 Codex만: AGENTS.md 규칙 구역", "<!-- oche:begin" in (e.read(".codex/AGENTS.md") or ""))
    mj = json.loads(e.read(".codex/oche/models.json"))
    check("2 Codex만: models.json 기록(출처·역할)", mj["roles"]["executor"]["model"] == "gpt-6.2-sol" and mj.get("source", "").startswith("live"), mj)
    try:
        import tomllib  # noqa
        ok = True
        for r in ("executor", "deep-reasoner", "runner"):
            with open(e.p(".codex/agents/%s.toml" % r), "rb") as f:
                d = tomllib.load(f)
            ok = ok and all(d.get(k) for k in ("name", "description", "developer_instructions", "model", "model_reasoning_effort"))
        check("2 Codex만: TOML 문법(tomllib)", ok)
    except ImportError:
        check("2 Codex만: TOML 문법 — tomllib 없음(건너뜀)", True)
    c, out = e.install("verify")
    check("2 Codex만: verify 통과", c == 0 and nofail(out), out)
    c, out = e.oche()
    check("2 Codex만: 현황판에 훅 신뢰 안내", "Review hooks" in out and "[Claude Code]" not in out, out)
    e.cleanup()

    # 앱 캐시 규칙: 14일 이내 + client_version 이 앱 엔진 버전과 같을 때만(알파 접미사 무시)
    e = Env("codex-appcache", claude=False, app_version="0.171.0-alpha.13.2")
    os.makedirs(e.p(".codex"))
    app = [m for m in default_models() if m["slug"] != "gpt-6.2-sol"]
    e.cache(app, time.time() - 3 * 86400, name="models_cache.codex_work_desktop.json", client="0.171.0")
    c, out = e.install("plan")
    check("2b 앱 캐시(14일 이내·버전 같음)에 없는 slug → 둘 다 있는 gpt-6.1-sol + 경고", "→ gpt-6.1-sol" in out
          and "ChatGPT 앱의 모델 캐시" in out and "앱 모델 캐시가 낡아" not in out, out)
    e.cache(app, time.time() - 3 * 86400, name="models_cache.codex_work_desktop.json", client="0.167.0")
    c, out = e.install("plan")
    check("2c 앱 캐시 버전이 앱 엔진과 다르면 무시 → gpt-6.2-sol + '낡아 무시함' 안내", "→ gpt-6.2-sol" in out
          and "앱 모델 캐시가 낡아 무시함 — ChatGPT 앱에서 새 Codex 채팅을 한 번 열면 갱신됨" in out, out)
    e.install("install")
    c, out = e.oche("status")
    check("2c status 에도 '낡아 무시함' 안내", "앱 모델 캐시가 낡아 무시함" in out and e.toml("executor")["model"] == "gpt-6.2-sol", out)
    e.cache(app, time.time() - 20 * 86400, name="models_cache.codex_work_desktop.json", client="0.171.0")
    c, out = e.install("plan")
    check("2c' 날짜가 낡은 앱 캐시(20일)도 무시 → gpt-6.2-sol", "→ gpt-6.2-sol" in out and "앱 모델 캐시가 낡아" in out, out)
    e.cleanup()

    e = Env("codex-nomodels", claude=False, models=[{"slug": "gpt-reserve", "visibility": "hide"}])
    c, out = e.install("install")
    check("2d 모델을 못 정하면 --codex-models 안내하며 거부", c == 3 and "--codex-models" in out, out)
    c, out = e.install("install", "--codex-models", "sol=gpt-7-sol,terra=gpt-7-terra,astra=gpt-7-astra")
    check("2d --codex-models 로 설치", c == 0 and e.toml("executor").get("model") == "gpt-7-sol"
          and e.toml("runner").get("model") == "gpt-7-terra", out)
    e.cleanup()


def legacy_setup(e):
    fd = e.p(".claude/fable")
    e.write(os.path.join(fd, "fable.md"), "old rules\n")
    e.write(os.path.join(fd, "agents/executor.md"), "---\nname: executor\nmodel: opus\n---\nold\n")
    e.write(os.path.join(fd, "hooks/orchestration-gate.py"), "print('old')\n", 0o755)
    os.makedirs(e.p(".claude/agents"), exist_ok=True)
    os.symlink(os.path.join(fd, "agents/executor.md"), e.p(".claude/agents/executor.md"))
    e.write(e.p(".claude/CLAUDE.md"), "# 내 메모\n사용자 줄\n<!-- fable-loader: 토글은 fable on/off, 이 줄은 그대로 둡니다 -->\n@%s/.claude/fable/active.md\n" % e.home)
    e.write(e.p(".claude/settings.json"), json.dumps({"model": "x", "hooks": {"PreToolUse": [
        {"matcher": "Write|Edit|Bash|Workflow|Agent", "hooks": [{"type": "command", "command": fd + "/hooks/orchestration-gate.py"}]}]}}))
    e.write(e.p(".claude/.fable-state"), "on\n")
    e.write(e.p(".local/bin/fable"), "#!/bin/sh\necho old\n", 0o755)
    e.write(e.p(".zshrc"), "# 내 zshrc\nsource ~/.claude/fable/env.sh\n")


def s03_legacy():
    e = Env("legacy")
    legacy_setup(e)
    c, out = e.install("plan")
    check("3 옛 설치본: plan 이 충돌 표시", "옛 fable 설치본" in out and "--migrate-legacy" in out, out)
    check("3 옛 env.sh: plan 안내", "`fable/env.sh`를 불러오는 줄이 있으면 더는 필요 없습니다" in out, out)
    c, out = e.install("install")
    check("3 옛 설치본: 플래그 없이 install → Claude 거부(코드 3), Codex는 설치", c == 3 and "[Claude Code] 설치 거부" in out
          and os.path.isfile(e.p(".codex/agents/executor.toml")) and not os.path.exists(e.p(".claude/oche")), out)
    c, out = e.install("install", "--migrate-legacy")
    check("3 옛 설치본: --migrate-legacy 로 설치", c == 0, out)
    check("3 옛 env.sh: migrate 출력에 안내, 셸 설정은 그대로", "더는 필요 없습니다" in out
          and e.read(".zshrc") == "# 내 zshrc\nsource ~/.claude/fable/env.sh\n", out)
    md = e.read(".claude/CLAUDE.md")
    check("3 옛 설치본: 옛 불러오기 줄·주석 제거, 사용자 줄 유지", "fable/active.md" not in md and "fable-loader" not in md
          and "사용자 줄" in md and "@~/.claude/oche/active.md" in md, md)
    s = json.loads(e.read(".claude/settings.json"))
    cmds = json.dumps(s)
    check("3 옛 설치본: 옛 훅 제거·새 훅 추가·다른 키 유지", "orchestration-gate" not in cmds and "oche-gate" in cmds and s.get("model") == "x", s)
    check("3 옛 설치본: 하청 심링크 → 실제 파일", os.path.isfile(e.p(".claude/agents/executor.md"))
          and not os.path.islink(e.p(".claude/agents/executor.md")))
    check("3 옛 설치본: .fable-state off", (e.read(".claude/.fable-state") or "").strip() == "off")
    check("3 옛 설치본: 옛 폴더·옛 명령은 그대로", os.path.isfile(e.p(".claude/fable/fable.md")) and os.path.isfile(e.p(".local/bin/fable")))
    check("3 옛 설치본: 백업 파일 생김", any(".bak_oche_" in n for n in os.listdir(e.p(".claude"))))
    c, out = e.install("verify")
    check("3 옛 설치본: verify 통과", c == 0 and nofail(out), out)
    c, out = e.install("install", "--only", "claude")
    check("3b 옮긴 뒤 재설치: 플래그 없이 성공", c == 0 and "설치 거부" not in out and "충돌" not in out, out)
    check("3b 옮긴 뒤 재설치: 남은 흔적 안내", "안내: 옛 fable 파일이 남아 있지만 더는 쓰이지 않습니다. 필요 없으면 지워도 됩니다:" in out
          and "~/.claude/fable/" in out and "~/.local/bin/fable" in out, out)
    check("3b 옮긴 뒤 재설치: 옛 폴더·옛 명령은 그대로", os.path.isfile(e.p(".claude/fable/fable.md")) and os.path.isfile(e.p(".local/bin/fable")))
    e.cleanup()


def s03c_legacy_residue():
    e = Env("legacy-residue")
    e.write(e.p(".claude/fable/fable.md"), "old rules\n")
    e.write(e.p(".local/bin/fable"), "#!/bin/sh\necho old\n", 0o755)
    c, out = e.install("plan", "--only", "claude")
    check("3c 흔적만: plan 에 충돌 없음·안내만", "충돌" not in out
          and "안내: 옛 fable 파일이 남아 있지만 더는 쓰이지 않습니다. 필요 없으면 지워도 됩니다: ~/.claude/fable/, ~/.local/bin/fable" in out, out)
    c, out = e.install("install", "--only", "claude")
    check("3c 흔적만: install 성공 + 안내", c == 0 and "설치 거부" not in out and "옛 fable 파일이 남아 있지만" in out
          and os.path.isfile(e.p(".claude/agents/executor.md")), out)
    check("3c 흔적만: 옛 폴더·옛 명령은 그대로", os.path.isfile(e.p(".claude/fable/fable.md")) and os.path.isfile(e.p(".local/bin/fable")))
    c, out = e.install("install", "--only", "claude", "--migrate-legacy")
    check("3c 흔적만: --migrate-legacy 를 줘도 오류 없이 지나감", c == 0 and "설치 거부" not in out, out)
    e.cleanup()
    e = Env("legacy-hookonly")
    fd = e.p(".claude/fable")
    e.write(e.p(".claude/settings.json"), json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Agent", "hooks": [{"type": "command", "command": fd + "/hooks/orchestration-gate.py"}]}]}}))
    c, out = e.install("install", "--only", "claude")
    check("3c 작동 중(훅만): 플래그 없이 거부", c == 3 and "[Claude Code] 설치 거부" in out and "--migrate-legacy" in out, out)
    e.cleanup()
    e = Env("legacy-loaderonly")
    e.write(e.p(".claude/CLAUDE.md"), "@%s/.claude/fable/active.md\n" % e.home)
    c, out = e.install("install", "--only", "claude")
    check("3c 작동 중(불러오기 줄만): 플래그 없이 거부", c == 3 and "[Claude Code] 설치 거부" in out and "--migrate-legacy" in out, out)
    e.cleanup()


def s04_idempotent():
    e = Env("idempotent")
    e.install("install")
    snap = {f: e.read(f) for f in (".claude/CLAUDE.md", ".claude/settings.json", ".codex/hooks.json", ".codex/AGENTS.md",
                                   ".claude/agents/executor.md", ".codex/agents/executor.toml")}
    c, out = e.install("install")
    check("4 재설치: 성공", c == 0, out)
    same = {f: e.read(f) == v for f, v in snap.items()}
    check("4 재설치: 파일 내용 그대로(중복 없음)", all(same.values()), same)
    s = json.loads(e.read(".claude/settings.json"))
    check("4 재설치: settings 훅 1개", sum("oche-gate" in h["command"] for x in s["hooks"]["PreToolUse"] for h in x["hooks"]) == 1)
    check("4 재설치: CLAUDE.md 불러오기 1줄", e.read(".claude/CLAUDE.md").count("oche/active.md") == 1)
    check("4 재설치: AGENTS.md 구역 1개", e.read(".codex/AGENTS.md").count("oche:begin") == 1)
    e.cleanup()


def s05_switch_and_gate():
    e = Env("switch")
    e.install("install")
    c, out = e.oche("off")
    check("5 off(전부)", c == 0 and e.read(".claude/oche/active.md") == e.read(".claude/oche/empty.md")
          and "oche:begin" not in (e.read(".codex/AGENTS.md") or "")
          and e.read(".claude/.oche-state").strip() == "off" and e.read(".codex/.oche-state").strip() == "off", out)
    check("5 off: 게이트 통과", e.gate("claude", {"tool_name": "Agent", "tool_input": {"subagent_type": "general-purpose"}}) == 0
          and e.gate("codex", {"tool_name": "spawn_agent", "tool_input": {"agent_type": "worker"}}) == 0)
    c, out = e.oche("on", "claude")
    check("5 on claude 만", c == 0 and e.read(".claude/.oche-state").strip() == "on" and e.read(".codex/.oche-state").strip() == "off", out)
    check("5 claude on: general-purpose 차단", e.gate("claude", {"tool_name": "Agent", "tool_input": {"subagent_type": "general-purpose"}}) == 2)
    c, out = e.oche("on")
    c, out = e.oche("off", "codex")
    check("5 off codex 만", e.read(".claude/.oche-state").strip() == "on" and e.read(".codex/.oche-state").strip() == "off")
    c, out = e.oche("selftest")
    check("5 selftest(Claude+Codex) 통과", c == 0 and nofail(out) and "Claude" in out and "Codex" in out, out)
    check("5 selftest 뒤 원래 상태 복구", e.read(".claude/.oche-state").strip() == "on" and e.read(".codex/.oche-state").strip() == "off")
    check("5 selftest 상태 파일 정리", not [f for d in (".claude/oche/state", ".codex/oche/state")
                                        for f in os.listdir(e.p(d)) if "selftest" in f])
    # 역할 설정에 맞춘 모델·강도 게이트
    g = lambda ti: e.gate("claude", {"tool_name": "Agent", "tool_input": ti})
    check("5 게이트: 설정과 같은 모델 통과", g({"subagent_type": "executor", "model": "opus"}) == 0)
    check("5 게이트: 옛 ID 차단", g({"subagent_type": "executor", "model": "claude-opus-5-4"}) == 2)
    check("5 게이트: 다른 별칭 차단", g({"subagent_type": "runner", "model": "opus"}) == 2)
    check("5 게이트: 같은 강도 통과", g({"subagent_type": "deep-reasoner", "effort": "xhigh"}) == 0)
    check("5 게이트: 높은 강도 차단", g({"subagent_type": "executor", "effort": "max"}) == 2)
    check("5 게이트: 낮은 강도 차단", g({"subagent_type": "executor", "effort": "low"}) == 2)
    check("5 게이트: ultra 차단", g({"subagent_type": "executor", "effort": "ultra"}) == 2)
    check("5 게이트: ORCH_BRIDGE=1 이면 하청 차단", e.gate("claude", {"tool_name": "Agent", "tool_input": {"subagent_type": "executor"}},
                                                     {"ORCH_BRIDGE": "1"}) == 2)
    e.oche("on", "codex")
    x = lambda ti: e.gate("codex", {"tool_name": "spawn_agent", "tool_input": ti})
    check("5 Codex 게이트: 설정 모델 통과·옛 ID 차단", x({"agent_type": "executor", "model": "gpt-6.2-sol"}) == 0
          and x({"agent_type": "executor", "model": "gpt-6.1-sol"}) == 2)
    check("5 Codex 게이트: 강도 같으면 통과·다르면 차단", x({"agent_type": "runner", "reasoning_effort": "low"}) == 0
          and x({"agent_type": "runner", "reasoning_effort": "medium"}) == 2 and x({"agent_type": "runner", "reasoning_effort": "none"}) == 2)
    y = lambda ti: e.gate("codex", {"tool_name": "collaborationspawn_agent", "tool_input": ti})
    check("5 Codex 게이트: 실제 도구 이름 collaborationspawn_agent 도 판정(worker 차단·executor 통과)",
          y({"agent_type": "worker", "task_name": "t", "message": "x"}) == 2 and y({"agent_type": "executor", "message": "x"}) == 0)
    import re as _re
    check("5 Codex matcher 가 실제 도구 이름에 맞음", all(_re.fullmatch("^(apply_patch|.*spawn_agent|Agent)$", n)
          for n in ("collaborationspawn_agent", "spawn_agent", "apply_patch", "Agent")))
    dumpf = os.path.join(e.root, "dump.jsonl")
    e.gate("codex", {"tool_name": "apply_patch", "turn_id": "t9", "tool_input": {"command": "*** Begin Patch\n*** Add File: z.md\n+x\n*** End Patch"}},
           {"OCHE_HOOK_DUMP": dumpf})
    e.gate("claude", {"tool_name": "Agent", "prompt_id": "p9", "tool_input": {"subagent_type": "executor"}}, {"OCHE_HOOK_DUMP": dumpf})
    lines = open(dumpf, encoding="utf-8").read().splitlines() if os.path.exists(dumpf) else []
    check("5 OCHE_HOOK_DUMP: 두 게이트가 받은 입력을 한 줄씩 남김", len(lines) == 2 and json.loads(lines[0])["tool_name"] == "apply_patch"
          and json.loads(lines[1])["prompt_id"] == "p9", lines)
    check("5 Codex 게이트: ORCH_BRIDGE=1 이면 spawn 차단", e.gate("codex", {"tool_name": "spawn_agent", "tool_input": {"agent_type": "executor"}},
                                                            {"ORCH_BRIDGE": "1"}) == 2)
    e.cleanup()


def s06_sync():
    e = Env("sync", claude=False)
    e.install("install")
    sync = e.p(".codex/oche/hooks/oche-sync.py")
    stamp = e.p(".codex/oche/state/sync.stamp")
    m = default_models() + [{"slug": "gpt-6.3-sol", "visibility": "list", "supported_reasoning_levels": lv(*FULL)}]
    e.cache(m)
    c, out, err = e.run([PY, sync])
    check("6 sync: 설치 직후 1시간 안에는 아무것도 안 함", c == 0 and out == "" and err == "" and e.toml("executor")["model"] == "gpt-6.2-sol", out)
    os.remove(stamp)
    t0 = time.time()
    c, out, err = e.run([PY, sync])
    dt = time.time() - t0
    check("6 sync: gpt-6.3-sol 로 갱신 + systemMessage 한 줄", c == 0 and err == "" and out.count("\n") == 1
          and json.loads(out)["systemMessage"].startswith("oche: 하청 모델 갱신 — executor gpt-6.2-sol → gpt-6.3-sol"), out + err)
    check("6 sync: 1초 안에 끝남 (%.2fs)" % dt, dt < 1.0)
    check("6 sync: TOML 갱신(executor·deep_reasoner), runner 그대로", e.toml("executor")["model"] == "gpt-6.3-sol"
          and e.toml("deep-reasoner")["model"] == "gpt-6.3-sol" and e.toml("runner")["model"] == "gpt-6.1-terra")
    check("6 sync: models.json·log.txt 기록", json.loads(e.read(".codex/oche/models.json"))["roles"]["executor"]["model"] == "gpt-6.3-sol"
          and "gpt-6.3-sol" in (e.read(".oche/log.txt") or ""))
    check("6 sync: additionalContext 없음", "additionalContext" not in out)
    m2 = m + [{"slug": "gpt-6.4-sol", "visibility": "list", "supported_reasoning_levels": lv(*FULL)}]
    e.cache(m2)
    c, out, err = e.run([PY, sync])
    check("6 sync: 1시간 제한 존중", out == "" and e.toml("executor")["model"] == "gpt-6.3-sol", out)
    c, out = e.oche("pin", "codex", "executor", "gpt-6.3-sol")
    check("6 pin: 바로 반영", c == 0 and e.toml("executor")["model"] == "gpt-6.3-sol", out)
    os.remove(stamp)
    c, out, err = e.run([PY, sync])
    check("6 sync: pin 존중(executor 고정, deep_reasoner 만 6.4)", e.toml("executor")["model"] == "gpt-6.3-sol"
          and e.toml("deep-reasoner")["model"] == "gpt-6.4-sol" and "deep-reasoner" in out and "executor gpt" not in out, out)
    e.oche("off")
    e.cache(m2 + [{"slug": "gpt-6.5-sol", "visibility": "list", "supported_reasoning_levels": lv(*FULL)}])
    os.remove(stamp)
    c, out, err = e.run([PY, sync])
    check("6 sync: 스위치가 꺼져 있어도 돈다", e.toml("deep-reasoner")["model"] == "gpt-6.5-sol", out)
    c, out = e.oche("unpin", "codex", "executor")
    check("6 unpin: 최신으로 복귀", e.toml("executor")["model"] in ("gpt-6.4-sol", "gpt-6.2-sol", "gpt-6.5-sol"), out)
    e.write(e.p(".codex/oche/models.json"), "{broken")
    os.remove(stamp)
    c, out, err = e.run([PY, sync])
    check("6 sync: 깨진 models.json 이어도 exit 0·출력 없음", c == 0 and out == "" and err == "", out + err)
    e.cleanup()


def s07_effort_downgrade():
    m = default_models()
    for x in m:
        if x["slug"] == "gpt-6.2-sol":
            x["supported_reasoning_levels"] = lv("low", "medium", "high", "max")
    e = Env("effort", claude=False, models=m)
    c, out = e.install("install")
    check("7 강도 강등: xhigh 미지원 → high", c == 0 and e.toml("deep-reasoner").get("model_reasoning_effort") == "high", out)
    c, out = e.oche()
    check("7 강도 강등: 현황판에 표시", "모델 미지원 → high" in out, out)
    e.cleanup()
    spec = importlib.util.spec_from_file_location("s", os.path.join(REPO, "oche", "codex", "sync.py"))
    s = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(s)
    check("7 fit_effort: ultra 는 고르지 않음", s.fit_effort("high", ["ultra", "max"]) == "max" and s.fit_effort("ultra", ["ultra"]) == "ultra"
          or s.fit_effort("high", ["ultra", "max"]) == "max")
    check("7 fit_effort: 가까운 아래 값", s.fit_effort("xhigh", ["low", "medium"]) == "medium" and s.fit_effort("low", ["none", "low"]) == "low")


def s08_override():
    e = Env("override", claude=False)
    e.write(e.p(".codex/AGENTS.override.md"), "# 내 override\n")
    e.write(e.p(".codex/AGENTS.md"), "# 내 AGENTS\n")
    c, out = e.install("install")
    check("8 override: 규칙 구역이 override 에 들어감", "oche:begin" in e.read(".codex/AGENTS.override.md")
          and "oche:begin" not in e.read(".codex/AGENTS.md") and e.read(".codex/AGENTS.md") == "# 내 AGENTS\n", out)
    c, out = e.oche("off")
    check("8 override: off 면 구역 제거·내용 유지", e.read(".codex/AGENTS.override.md").strip() == "# 내 override")
    c, out = e.install("verify")
    check("8 override: verify 통과", c == 0 and nofail(out), out)
    e.cleanup()


def user_content(e):
    e.write(e.p(".claude/CLAUDE.md"), "# 내 전역 지침\n- 한국어로 답하기\n")
    e.write(e.p(".claude/settings.json"), json.dumps({"theme": "dark", "hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}], "Stop": [{"hooks": [{"type": "command", "command": "echo stop"}]}]}}))
    e.write(e.p(".codex/AGENTS.md"), "# 내 Codex 지침\n")
    e.write(e.p(".codex/hooks.json"), json.dumps({"hooks": {"PreToolUse": [{"matcher": "shell", "hooks": [{"type": "command", "command": "echo mine"}]}],
                                                            "Stop": [{"hooks": [{"type": "command", "command": "echo s"}]}]}}))


def s09_preserve_and_s11_uninstall():
    e = Env("preserve")
    user_content(e)
    c, out = e.install("install")
    check("9 보존: install 성공", c == 0, out)
    md = e.read(".claude/CLAUDE.md")
    s = json.loads(e.read(".claude/settings.json"))
    check("9 보존: CLAUDE.md 사용자 내용", md.startswith("# 내 전역 지침\n- 한국어로 답하기\n") and "oche/active.md" in md, md)
    check("9 보존: settings 다른 키·훅", s["theme"] == "dark" and s["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo mine"
          and "Stop" in s["hooks"] and len(s["hooks"]["PreToolUse"]) == 2, s)
    check("9 보존: AGENTS.md 사용자 내용", e.read(".codex/AGENTS.md").startswith("# 내 Codex 지침\n"))
    h = json.loads(e.read(".codex/hooks.json"))
    check("9 보존: hooks.json 다른 훅", h["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo mine" and "Stop" in h["hooks"], h)
    check("9 보존: 바꾸기 전 백업", any(".bak_oche_" in n for n in os.listdir(e.p(".claude")))
          and any(".bak_oche_" in n for n in os.listdir(e.p(".codex"))))
    c, out = e.install("uninstall")
    check("11 uninstall: 성공", c == 0, out)
    check("11 uninstall: CLAUDE.md 사용자 내용만 남음", e.read(".claude/CLAUDE.md").rstrip("\n") == "# 내 전역 지침\n- 한국어로 답하기", e.read(".claude/CLAUDE.md"))
    s = json.loads(e.read(".claude/settings.json"))
    check("11 uninstall: settings 다른 훅 유지·oche 훅 제거", "oche-gate" not in json.dumps(s) and s["theme"] == "dark"
          and s["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo mine", s)
    check("11 uninstall: AGENTS.md 사용자 내용만", e.read(".codex/AGENTS.md").strip() == "# 내 Codex 지침")
    h = json.loads(e.read(".codex/hooks.json"))
    check("11 uninstall: hooks.json 다른 훅 유지", "oche" not in json.dumps(h) and h["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo mine", h)
    check("11 uninstall: oche 파일 제거", not os.path.exists(e.p(".oche")) and not os.path.exists(e.p(".local/bin/oche"))
          and not os.path.exists(e.p(".claude/agents/executor.md")) and not os.path.exists(e.p(".codex/agents/executor.toml"))
          and not os.path.exists(e.p(".claude/oche")) and not os.path.exists(e.p(".codex/oche")))
    e.cleanup()


def s10_hook_path():
    e = Env("hookpath")
    e.install("install")
    s = json.loads(e.read(".claude/settings.json"))
    ccmd = [h["command"] for x in s["hooks"]["PreToolUse"] for h in x["hooks"] if "oche-gate" in h["command"]][0]
    h = json.loads(e.read(".codex/hooks.json"))
    xcmd = h["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    scmd = h["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    env = {"PATH": "/usr/bin:/bin", "HOME": e.home}

    def sh(cmd, payload):
        p = subprocess.run(["/bin/sh", "-c", cmd], input=json.dumps(payload).encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        return p.returncode, p.stdout.decode(), p.stderr.decode()
    r = sh(ccmd, {"tool_name": "Agent", "tool_input": {"subagent_type": "general-purpose"}})
    check("10 PATH=/usr/bin:/bin: Claude 훅 명령 실행(차단 2)", r[0] == 2 and "[oche 게이트]" in r[2], r)
    r = sh(xcmd, {"tool_name": "spawn_agent", "tool_input": {"agent_type": "worker"}})
    check("10 PATH=/usr/bin:/bin: Codex 훅 명령 실행(차단 2)", r[0] == 2, r)
    r = sh(scmd, {"hook_event_name": "SessionStart"})
    check("10 PATH=/usr/bin:/bin: sync 훅 명령 exit 0", r[0] == 0 and r[2] == "", r)
    check("10 훅 명령은 절대경로 python", ccmd.startswith('"/') and xcmd.startswith('"/'), (ccmd, xcmd))
    e.cleanup()


def s12_degraded():
    e = Env("degraded", claude=False, codex_version="0.160.0")
    c, out = e.install("plan")
    check("12 저하 모드: plan 경고", "0.171.0 미만" in out, out)
    c, out = e.install("install")
    check("12 저하 모드: gate.json subagent_fields=false", c == 0 and json.loads(e.read(".codex/oche/gate.json")) == {"subagent_fields": False}, out)
    check("12 저하 모드: 하청 안 판별 끔(타입 검사만)", e.gate("codex", {"tool_name": "spawn_agent", "agent_id": "a", "tool_input": {"agent_type": "runner"}}) == 0
          and e.gate("codex", {"tool_name": "spawn_agent", "agent_id": "a", "tool_input": {"agent_type": "worker"}}) == 2)
    c, out = e.install("verify")
    check("12 저하 모드: verify 통과", c == 0 and nofail(out), out)
    c, out = e.oche()
    check("12 저하 모드: 현황판 경고", "저하 모드" in out, out)
    e.cleanup()


def s13_windows():
    e = Env("windows", windows=True)
    c, out = e.install("install")
    check("13 Windows 흉내: install 성공", c == 0, out)
    check("13 Windows 흉내: 심링크 없음", not no_symlinks(e.home), no_symlinks(e.home))
    check("13 Windows 흉내: oche.cmd·oche.ps1 생성, POSIX 래퍼 없음", os.path.isfile(e.p(".local/bin/oche.cmd"))
          and os.path.isfile(e.p(".local/bin/oche.ps1")) and not os.path.exists(e.p(".local/bin/oche")))
    cmd = open(e.p(".local/bin/oche.cmd"), "rb").read()
    check("13 Windows 흉내: .cmd 는 CRLF·ASCII 경로(%~dp0)", b"\r\n" in cmd and b"%~dp0" in cmd and b"oche-wrapper" in cmd, cmd)
    h = json.loads(e.read(".codex/hooks.json"))
    hw = h["hooks"]["PreToolUse"][0]["hooks"][0]
    check("13 Windows 흉내: hooks.json commandWindows", "commandWindows" in hw and "oche-gate.py" in hw["commandWindows"], hw)
    s = json.loads(e.read(".claude/settings.json"))
    ch = s["hooks"]["PreToolUse"][0]["hooks"][0]
    check("13 Windows 흉내: Claude 훅은 py 런처 또는 powershell+& 형식", ch["command"].startswith("py -3 ")
          or (ch.get("shell") == "powershell" and ch["command"].startswith("& ")), ch)
    check("13 Windows 흉내: active.md 복사본", e.read(".claude/oche/active.md") == e.read(".claude/oche/rules.md"))
    c, out = e.install("verify")
    check("13 Windows 흉내: verify 통과", c == 0 and nofail(out), out)
    c, out = e.oche("preset", "use", "saver")
    check("13 Windows 흉내: preset use saver", c == 0 and e.toml("runner")["model"] == "gpt-6-luna", out)
    c, out = e.oche("preset")
    check("13 Windows 흉내: preset 목록 ✔ saver", "✔ saver" in out, out)
    c, out = e.install("install", "--command-name", "orch")
    check("13 Windows 흉내: --command-name orch → orch.cmd, 옛 oche.cmd 제거", c == 0 and os.path.isfile(e.p(".local/bin/orch.cmd"))
          and not os.path.exists(e.p(".local/bin/oche.cmd")), out)
    e.cleanup()


def s14_command_name():
    e = Env("cmdname")
    e.write(os.path.join(e.bin, "oche"), "#!/bin/sh\necho someone else\n", 0o755)
    c, out = e.install("plan")
    check("14 이름 충돌: plan 이 보고·후보 제시", "이름 충돌" in out and "orch" in out, out)
    c, out = e.install("install")
    check("14 이름 충돌: 플래그 없이 install 거부", c == 3 and not os.path.exists(e.p(".oche")), out)
    c, out = e.install("install", "--command-name", "bad name!")
    check("14 이름 검사: 잘못된 이름 거부", c != 0, out)
    c, out = e.install("install", "--command-name", "orch")
    check("14 --command-name orch: 설치", c == 0 and os.path.isfile(e.p(".local/bin/orch")) and not os.path.exists(e.p(".local/bin/oche")), out)
    c, out, err = e.run([e.p(".local/bin/orch"), "help"])
    check("14 orch: 도움말에 orch 표시", c == 0 and "orch on|off" in out and "oche on" not in out, out)
    c, out, err = e.run([e.p(".local/bin/orch")])
    check("14 orch: 현황판에 orch 표시", "명령 이름: orch" in out and "orch <역할>" in out, out)
    check("14 orch: 규칙·훅 안내에도 orch", "orch" in json.dumps(json.loads(e.read(".claude/oche/roles.json"))))
    c, out = e.install("uninstall")
    check("14 uninstall: orch 제거, 남의 oche 는 그대로", not os.path.exists(e.p(".local/bin/orch")) and os.path.isfile(os.path.join(e.bin, "oche")), out)
    e.cleanup()


def s15_roles():
    e = Env("roles")
    e.install("install")
    c, out = e.oche("executor", "sonnet", "medium")
    check("15 역할: 두 대상이면 대상 지정 요구", c == 2 and "claude executor" in out, out)
    c, out = e.oche("claude", "executor", "sonnet", "medium")
    ex = e.read(".claude/agents/executor.md")
    check("15 역할: claude executor sonnet medium 즉시 반영", c == 0 and frontmatter(ex, "model") == "sonnet"
          and frontmatter(ex, "effort") == "medium" and "다음 세션부터" in out, out)
    g = lambda ti: e.gate("claude", {"tool_name": "Agent", "tool_input": ti})
    check("15 역할 변경 뒤 게이트: sonnet 통과·opus 차단", g({"subagent_type": "executor", "model": "sonnet"}) == 0
          and g({"subagent_type": "executor", "model": "opus"}) == 2)
    check("15 역할 변경 뒤 게이트: medium 통과·high/low 차단", g({"subagent_type": "executor", "effort": "medium"}) == 0
          and g({"subagent_type": "executor", "effort": "high"}) == 2 and g({"subagent_type": "executor", "effort": "low"}) == 2)
    c, out = e.oche("claude", "runner", "claude-haiku-4-5", "low")
    check("15 옛 ID: 재확인 없이 적용 + '최신 아님' 안내", c == 0 and "최신 아님(최신: claude-haiku-5-5)" in out
          and frontmatter(e.read(".claude/agents/runner.md"), "model") == "claude-haiku-4-5", out)
    c, out = e.oche("claude", "deep", "fable", "max")
    check("15 fable·max: 재확인 없이 적용 + 안내", c == 0 and "가장 비싼 강도" in out
          and frontmatter(e.read(".claude/agents/deep-reasoner.md"), "model") == "fable", out)
    check("15 역할을 fable 로 정하면 fable 지정·지정 없음 통과, 다른 모델 차단", g({"subagent_type": "deep-reasoner", "model": "fable"}) == 0
          and g({"subagent_type": "deep-reasoner"}) == 0 and g({"subagent_type": "deep-reasoner", "model": "opus"}) == 2)
    c, out = e.oche("claude", "runner", "haiku", "ultra")
    check("15 ultra 는 강도 선택지 아님", c == 2 and "ultra" in out, out)
    c, out = e.oche("codex", "runner", "sol", "medium")
    check("15 Codex runner sol medium", c == 0 and e.toml("runner") == {"name": "runner", "model": "gpt-6.2-sol", "model_reasoning_effort": "medium"}, out)
    c, out = e.oche("codex", "executor", "gpt-5.6-sol")
    check("15 Codex 옛 ID 안내·적용(강도 유지)", c == 0 and "최신 아님" in out and e.toml("executor")["model"] == "gpt-5.6-sol"
          and e.toml("executor")["model_reasoning_effort"] == "high", out)
    c, out = e.oche("models")
    check("15 models 표", "sonnet" in out and "최신 sol" in out, out)
    c, out = e.oche("reset", "claude")
    check("15 reset claude: 기본값", c == 0 and frontmatter(e.read(".claude/agents/executor.md"), "model") == "opus"
          and frontmatter(e.read(".claude/agents/executor.md"), "effort") == "high", out)
    c, out = e.oche("reset", "codex", "runner")
    check("15 reset codex runner", e.toml("runner")["model"] == "gpt-6.1-terra" and e.toml("executor")["model"] == "gpt-5.6-sol", out)
    c, out = e.oche("claude", "runner")
    check("15 TTY 아님 + 정보 부족 → 실패 안내", c == 2 and "모델" in out, out)
    c, out = e.oche("selftest")
    check("15 역할 변경 뒤 selftest 통과", c == 0 and nofail(out), out)
    e.cleanup()


def s16_interactive_and_dashboard():
    e = Env("interactive")
    e.install("install")
    # 줄 입력 대화형(ORCH_FORCE_TTY=1): 대상 1(Claude) → 모델 2(sonnet) → 강도 2(medium)
    c, out = e.oche("runner", stdin="1\nsonnet\n2\n", extra={"ORCH_FORCE_TTY": "1"})
    r = e.read(".claude/agents/runner.md")
    check("16 대화형(줄 입력): Claude runner → sonnet/medium", c == 0 and frontmatter(r, "model") == "sonnet"
          and frontmatter(r, "effort") == "medium", out)
    c, out = e.oche()
    check("16 현황판(인자 없음, TTY 아님): 표·ON 표시", c == 0 and "역할" in out and "모델(설정 → 실제)" in out
          and "[Claude Code] ON" in out and "[Codex] ON" in out and "xhigh (extra)" in out and "최신 sol → gpt-6.2-sol" in out, out)
    c, out = e.oche("status")
    check("16 status: 부품 점검", "[OK] 게이트 훅 등록" in out and "[--]" not in out.split("경고")[0], out)
    e.cleanup()


def s18_bridge():
    e = Env("bridge")
    e.install("install")
    c, out = e.oche("claude", "executor", "codex:gpt-6.2-sol", "high")
    ex = e.read(".claude/agents/executor.md")
    check("18 다리: Claude executor → Codex, 정의는 haiku/low 다리", c == 0 and frontmatter(ex, "model") == "haiku"
          and frontmatter(ex, "effort") == "low" and "bridge codex executor" in ex and "실험적" in out, out)
    t = os.path.join(e.root, "task.txt")
    e.write(t, "do it")
    c, out = e.oche("bridge", "codex", "executor", "--task", t, "--out", "/tmp/o.txt", "--cwd", "/work dir",
                    extra={"ORCH_BRIDGE_DRYRUN": "1"})
    check("18 다리(dry-run): codex exec 명령 조립", c == 0 and out.startswith("ORCH_BRIDGE=1 ") and " exec -m gpt-6.2-sol " in out
          and "-c 'model_reasoning_effort=\"high\"'" in out and "-s workspace-write" in out and "-C '/work dir'" in out
          and "--skip-git-repo-check --ephemeral -o /tmp/o.txt - < " in out, out)
    check("18 다리: 게이트는 정의 모델(haiku) 지정 통과", e.gate("claude", {"tool_name": "Agent", "tool_input": {"subagent_type": "executor", "model": "haiku"}}) == 0)
    c, out = e.oche("codex", "runner", "claude:haiku", "low")
    check("18 다리: Codex runner → Claude, 정의는 최신 terra/low", c == 0 and e.toml("runner")["model"] == "gpt-6.1-terra"
          and "bridge claude runner" in (e.read(".codex/agents/runner.toml") or ""), out)
    c, out = e.oche("bridge", "claude", "runner", "--task", t, "--out", "/tmp/o.txt", extra={"ORCH_BRIDGE_DRYRUN": "1"})
    check("18 다리(dry-run): claude -p 명령 조립", c == 0 and " -p --model haiku --effort low --output-format text --permission-mode acceptEdits < " in out, out)
    try:
        import tomllib
        with open(e.p(".codex/agents/runner.toml"), "rb") as f:
            tomllib.load(f)
        check("18 다리 TOML 문법", True)
    except ImportError:
        check("18 다리 TOML 문법 — tomllib 없음(건너뜀)", True)
    except Exception as ex2:
        check("18 다리 TOML 문법", False, ex2)
    c, out = e.oche("selftest")
    check("18 다리 설정에서도 selftest 통과", c == 0 and nofail(out), out)
    e.cleanup()


def s19_tui_units():
    spec = importlib.util.spec_from_file_location("ochetui", os.path.join(REPO, "oche", "bin", "oche.py"))
    if not os.path.isfile(os.path.join(REPO, "oche", "bin", "tui.py")):
        check("19 TUI: tui.py 없음", False)
        return
    e = Env("tui")
    e.install("install")
    code = r'''
import json, os, sys
sys.path.insert(0, os.path.join(os.environ["HOME"], ".oche", "assets", "oche", "bin"))
import tui
fails = []
def w(s): return tui.text_width(tui.strip_ansi(s))
st = tui.initial_state()
for ascii_mode in (False, True):
    for W in (40, 60, 80, 100, 140, 200):
        for H in (15, 24, 40):
            st2 = tui.initial_state(); st2["ascii"] = ascii_mode
            for screen in ("home", "model", "effort", "input", "preset", "preset_input"):
                st2["screen"] = screen
                if screen != "home":
                    st2["target"], st2["role"] = "claude", "executor"
                    st2["model_choice"] = "opus"
                lines = tui.render(st2, W, H)
                if len(lines) > H: fails.append("height %d>%d at %dx%d %s" % (len(lines), H, W, H, screen))
                for l in lines:
                    if w(l) > W: fails.append("width %d>%d at %dx%d %s ascii=%s: %r" % (w(l), W, W, H, screen, ascii_mode, tui.strip_ansi(l)))
                    if ascii_mode and any(ch in tui.strip_ansi(l) for ch in "╭╮╰╯│─❯✔"): fails.append("box char in ascii %dx%d" % (W, H))
print(json.dumps({"render_fails": fails[:10], "n": len(fails)}))
# handle_key 흐름
st = tui.initial_state()
items = [it["id"] for it in tui.menu_items(st)]
st["cursor"] = items.index("role:claude:executor")
st = tui.handle_key(st, "enter")
s1 = st["screen"]
opts = [o["value"] for o in tui.model_options_for(st)]
st["mcursor"] = opts.index("sonnet")
st = tui.handle_key(st, "enter")
s2 = st["screen"]
effs = [o["value"] for o in tui.effort_options_for(st)]
st["ecursor"] = effs.index("medium")
st = tui.handle_key(st, "enter")
import importlib.util
cfg = json.load(open(os.path.join(os.environ["HOME"], ".oche", "config.json")))
r = cfg["targets"]["claude"]["roles"]["executor"]
st = tui.initial_state(); st["cursor"] = items.index("role:claude:runner")
st = tui.handle_key(st, "enter"); back = tui.handle_key(st, "esc")["screen"]
st = tui.initial_state(); st["cursor"] = items.index("switch:claude")
before = open(os.path.join(os.environ["HOME"], ".claude", ".oche-state")).read().strip()
st = tui.handle_key(st, "enter")
after = open(os.path.join(os.environ["HOME"], ".claude", ".oche-state")).read().strip()
st = tui.handle_key(st, "enter")
again = open(os.path.join(os.environ["HOME"], ".claude", ".oche-state")).read().strip()
q = tui.handle_key(tui.initial_state(), "q").get("quit")
st = tui.initial_state(); ids = [it["id"] for it in tui.menu_items(st)]
order = [i for i in ids if not i.startswith(("switch:", "role:"))]
st["cursor"] = ids.index("preset"); st = tui.handle_key(st, "enter"); ps = st["screen"]
popts = [o["value"] for o in tui.preset_options_for(st)]
st["pcursor"] = popts.index("saver"); st = tui.handle_key(st, "enter")
cfgp = json.load(open(os.path.join(os.environ["HOME"], ".oche", "config.json")))
pres = {"screen": st["screen"], "status": st["status"], "ex": cfgp["targets"]["claude"]["roles"]["executor"], "head": tui.strip_ansi(tui.render(st, 100, 24)[0])}
st["cursor"] = ids.index("preset"); st = tui.handle_key(st, "enter")
st["pcursor"] = len(tui.preset_options_for(st)) - 1; st = tui.handle_key(st, "enter"); pin = st["screen"]
for ch in "내설정": st = tui.handle_key(st, ch)
st = tui.handle_key(st, "enter"); saved = "내설정" in json.load(open(os.path.join(os.environ["HOME"], ".oche", "config.json"))).get("presets", {})
psave = st["screen"]; st = tui.handle_key(st, "esc"); pback = st["screen"]
print(json.dumps({"order": order, "ps": ps, "pres": pres, "pin": pin, "saved": saved, "psave": psave, "pback": pback}, ensure_ascii=False))
keys = [tui.decode_windows(b) for b in (b"\xe0H", b"\xe0P", b"\x00H", b"\r", b"\x1b", b"q", b"k", b"j", b"\xe0K")]
posix = [tui.decode_posix(b) for b in (b"\x1b[A", b"\x1b[B", b"\x1bOA", b"\r", b"\n", b"\x1b", b"\x1b[D", b"q")]
print(json.dumps({"s1": s1, "s2": s2, "model": r["model"], "effort": r["effort"], "status": st.get("status", ""),
                  "back": back, "toggle": [before, after, again], "quit": q, "win": keys, "posix": posix}, ensure_ascii=False))
'''
    c, out, err = e.run([PY, "-c", code])
    lines = out.strip().splitlines()
    try:
        a = json.loads(lines[0])
        b = json.loads(lines[2])
    except Exception:
        check("19 TUI 단위 시험 실행", False, out + err)
        e.cleanup()
        return
    check("19 TUI render: 폭 40~200·높이 15~40 에서 넘침 없음(한글 폭 포함), ASCII 모드에 상자 문자 없음", a["n"] == 0, a)
    check("19 TUI handle_key: 홈 → executor → 모델 → 강도 → 적용", b["s1"] == "model" and b["s2"] == "effort"
          and b["model"] == "sonnet" and b["effort"] == "medium", b)
    check("19 TUI handle_key: Esc 로 뒤로", b["back"] == "home", b)
    try:
        c3 = json.loads(lines[1])
    except Exception:
        c3 = {}
    check("19 TUI 홈 메뉴 순서: 역할 → 프리셋 → 모델 목록 갱신 → 자가 시험 → 나가기",
          c3.get("order") == ["preset", "update", "selftest", "quit"], c3)
    check("19 TUI 프리셋: 목록 → saver Enter → 적용·홈 복귀·상태줄·상단 표시",
          c3.get("ps") == "preset" and c3["pres"]["screen"] == "home" and "적용됨" in c3["pres"]["status"]
          and c3["pres"]["ex"] == {"model": "sonnet", "effort": "medium"} and "프리셋: 절약" in c3["pres"]["head"], c3)
    check("19 TUI 프리셋: '지금 설정 저장' → 이름 입력 → 저장 → Esc 로 홈", c3.get("pin") == "preset_input" and c3.get("saved")
          and c3.get("psave") == "preset" and c3.get("pback") == "home", c3)
    check("19 TUI handle_key: ON/OFF 토글", b["toggle"] == ["on", "off", "on"], b)
    check("19 TUI handle_key: 홈에서 q 종료", b["quit"] is True, b)
    check("19 TUI Windows 키 해석", b["win"] == ["up", "down", "up", "enter", "esc", "q", "k", "j", "left"], b)
    check("19 TUI POSIX 키 해석", b["posix"] == ["up", "down", "up", "enter", "enter", "esc", "left", "q"], b)
    e.cleanup()


def s20_tui_pty():
    if os.name == "nt":
        check("20 TUI pty — Windows 라 건너뜀", True)
        return
    import pty
    import select
    e = Env("tuipty", codex=False)
    e.install("install")
    pid, fd = pty.fork()
    if pid == 0:
        env = e.env({"TERM": "xterm-256color", "COLUMNS": "100", "LINES": "30"})
        os.chdir(e.root)
        os.execve(PY, [PY, e.p(".oche/bin/oche.py")], env)
    import fcntl
    import struct
    import termios
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 110, 0, 0))
    buf = b""

    def pump(t):
        nonlocal buf
        end = time.time() + t
        while time.time() < end:
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                try:
                    d = os.read(fd, 65536)
                except OSError:
                    return
                if not d:
                    return
                buf += d
    pump(1.5)
    for k in (b"\x1b[B", b"\x1b[A", b"j", b"k"):
        os.write(fd, k)
        pump(0.2)
    os.write(fd, b"q")
    pump(1.0)
    status = None
    for _ in range(40):
        wp, st = os.waitpid(pid, os.WNOHANG)
        if wp:
            status = st
            break
        time.sleep(0.05)
    if status is None:
        os.kill(pid, 9)
        os.waitpid(pid, 0)
    entered = b"\x1b[?1049h" in buf
    left = buf.rfind(b"\x1b[?1049l") > buf.rfind(b"\x1b[?1049h")
    cursor = buf.rfind(b"\x1b[?25h") > buf.rfind(b"\x1b[?25l")
    check("20 TUI pty: 대체 화면 진입·해제, 커서 복구, 정상 종료",
          entered and left and cursor and status is not None and os.WEXITSTATUS(status) == 0,
          (entered, left, cursor, status, buf[-300:]))
    check("20 TUI pty: 메뉴·구성도 그림", b"executor" in buf and b"Claude Code" in buf, buf[:500])
    e.cleanup()


def s21_plain_flag():
    e = Env("plain", codex=False)
    e.install("install")
    c, out = e.oche("--plain")
    check("21 --plain: 텍스트 현황판", c == 0 and "[Claude Code] ON" in out and "\x1b[?1049h" not in out, out)
    e.cleanup()


def s22_catalog():
    e = Env("catalog")
    c, out = e.install("install", raw=True)
    check("22 설치 대상 미지정(TTY 아님) → plan 만 보이고 묻도록 안내(코드 4)", c == 4 and "어디에 설치할까요" in out
          and not os.path.exists(e.p(".oche")), out)
    e.install("install")
    cat = json.loads(e.read(".oche/catalog.json"))
    check("22 catalog.json: Claude 계열표(실행 파일에서)·Codex 계열표", cat["claude"]["families"].get("opus") == "claude-opus-5-5"
          and cat["claude"]["source"] != "builtin" and cat["codex"]["families"].get("sol") == "gpt-6.2-sol"
          and "gpt-6.9-sol" not in cat["codex"]["models"], cat)
    e.set_claude("2.1.400", LATEST_LINE.replace("}", ',nova:"claude-nova-1"}'))
    c, out = e.oche("models")
    check("22 도구 버전이 바뀌면 자동 갱신 + 새 계열 알림(Claude nova)", "새 계열 발견: nova (claude-nova-1)" in out
          and "nova=claude-nova-1" in out, out)
    check("22 새 계열이 나와도 역할은 그대로", frontmatter(e.read(".claude/agents/executor.md"), "model") == "opus")
    c, out = e.oche("claude", "executor", "nova", "high")
    check("22 새 계열(nova)로 역할 변경", c == 0 and frontmatter(e.read(".claude/agents/executor.md"), "model") == "nova", out)
    g = lambda ti: e.gate("claude", {"tool_name": "Agent", "tool_input": ti})
    check("22 nova 역할: 게이트 통과(지정 없음·nova), opus 차단", g({"subagent_type": "executor"}) == 0
          and g({"subagent_type": "executor", "model": "nova"}) == 0 and g({"subagent_type": "executor", "model": "opus"}) == 2)
    e.set_codex_models(default_models() + [{"slug": "gpt-7-vega", "visibility": "list", "supported_reasoning_levels": lv("low", "medium", "high")}])
    c, out = e.oche("update")
    check("22 oche update: Codex 새 계열 알림(vega)", "새 계열 발견: vega (gpt-7-vega)" in out, out)
    check("22 update 뒤에도 Codex 역할 계열은 그대로", e.toml("executor")["model"] == "gpt-6.2-sol")
    c, out = e.oche("codex", "executor", "vega", "high")
    check("22 새 계열(vega)로 Codex 역할 변경", c == 0 and e.toml("executor")["model"] == "gpt-7-vega", out)
    c, out = e.oche("codex", "deep-reasoner", "vega", "xhigh")
    check("22 vega 가 지원하지 않는 강도는 거부", c == 2 and "low·medium·high" in out, out)
    x = lambda ti: e.gate("codex", {"tool_name": "spawn_agent", "tool_input": ti})
    check("22 vega 역할: 게이트 통과, 다른 모델 차단", x({"agent_type": "executor", "model": "gpt-7-vega"}) == 0
          and x({"agent_type": "executor", "model": "gpt-6.2-sol"}) == 2)
    e.cleanup()


def s23_off_and_path():
    e = Env("offpath")
    e.write(e.p(".zshrc"), "# 내 zshrc\n")
    e.write(e.p(".codex/config.toml"), "[hooks]\nfoo = 1\n")
    c, out = e.install("install", "--off", "--add-to-path")
    check("23 --off: 설치하되 꺼 둠", c == 0 and e.read(".claude/.oche-state").strip() == "off"
          and e.read(".codex/.oche-state").strip() == "off" and e.read(".claude/oche/active.md") == e.read(".claude/oche/empty.md"), out)
    check("23 config.toml 인라인 [hooks] 경고", "인라인 [hooks]" in out, out)
    z = e.read(".zshrc")
    check("23 --add-to-path: ~/.zshrc 에 PATH 줄(백업 포함)", "# 내 zshrc" in z and 'export PATH="$HOME/.local/bin:$PATH"' in z
          and any(n.startswith(".zshrc.bak_oche_") for n in os.listdir(e.home)), z)
    e.install("install", "--off", "--add-to-path")
    check("23 --add-to-path 두 번: 줄 1개", e.read(".zshrc").count(".local/bin:$PATH") == 1)
    c, out = e.install("uninstall")
    check("23 uninstall: PATH 줄 제거·사용자 줄 유지", e.read(".zshrc").strip() == "# 내 zshrc", e.read(".zshrc"))
    e.cleanup()


def s24_presets():
    e = Env("presets")
    e.install("install")
    c, out = e.oche("preset")
    check("24 preset 목록: 내장 3종, 기본값과 일치 ✔", c == 0 and "✔ default (기본)" in out and "saver (절약)" in out
          and "max (최대)" in out, out)
    c, out = e.oche("--plain")
    check("24 현황판 상단: 프리셋: 기본", "프리셋: 기본" in out, out)
    c, out = e.oche("preset", "use", "saver")
    ex, dr, rn = (e.read(".claude/agents/%s.md" % r) for r in ("executor", "deep-reasoner", "runner"))
    check("24 saver(절약) 적용 — Claude 정의 파일", c == 0 and (frontmatter(ex, "model"), frontmatter(ex, "effort")) == ("sonnet", "medium")
          and (frontmatter(dr, "model"), frontmatter(dr, "effort")) == ("opus", "high")
          and (frontmatter(rn, "model"), frontmatter(rn, "effort")) == ("haiku", "low") and "다음 세션부터" in out, out)
    check("24 saver 적용 — Codex TOML", e.toml("executor") == {"name": "executor", "model": "gpt-6.1-terra", "model_reasoning_effort": "medium"}
          and e.toml("deep-reasoner")["model_reasoning_effort"] == "high" and e.toml("runner")["model"] == "gpt-6-luna")
    check("24 saver 적용 — 게이트도 새 값으로", e.gate("claude", {"tool_name": "Agent", "tool_input": {"subagent_type": "executor", "model": "sonnet", "effort": "medium"}}) == 0
          and e.gate("claude", {"tool_name": "Agent", "tool_input": {"subagent_type": "executor", "model": "opus"}}) == 2)
    c, out = e.oche("--plain")
    check("24 현황판: 프리셋: 절약", "프리셋: 절약" in out, out)
    c, out = e.oche("preset", "use", "max", "codex")
    check("24 max(최대)를 Codex에만 적용", c == 0 and e.toml("deep-reasoner")["model_reasoning_effort"] == "max"
          and e.toml("runner")["model_reasoning_effort"] == "medium" and frontmatter(e.read(".claude/agents/executor.md"), "model") == "sonnet", out)
    c, out = e.oche("--plain")
    check("24 대상마다 다르면 프리셋: 사용자 지정", "프리셋: 사용자 지정" in out, out)
    c, out = e.oche("preset", "save", "내조합")
    check("24 save 한글 이름", c == 0 and "내조합" in json.loads(e.read(".oche/config.json"))["presets"], out)
    c, out = e.oche("preset")
    check("24 사용자 프리셋이 지금 설정과 일치 ✔", "✔ 내조합 (사용자)" in out, out)
    for bad in ("saver", "절약", "default", "내 것"):
        c, out = e.oche("preset", "save", bad)
        check("24 save 거부: '%s'" % bad, c == 2, out)
    e.oche("preset", "use", "default")
    c, out = e.oche("preset", "use", "내조합")
    check("24 use 사용자 프리셋", c == 0 and e.toml("deep-reasoner")["model_reasoning_effort"] == "max"
          and frontmatter(e.read(".claude/agents/executor.md"), "model") == "sonnet", out)
    c, out = e.oche("preset", "delete", "max")
    check("24 내장 프리셋은 지울 수 없음", c == 2, out)
    c, out = e.oche("preset", "delete", "내조합")
    check("24 delete 사용자 프리셋", c == 0 and "내조합" not in json.loads(e.read(".oche/config.json")).get("presets", {}), out)
    c, out = e.oche("preset", "use", "없는것")
    check("24 없는 프리셋 거부", c == 2, out)
    c, out = e.oche("selftest")
    check("24 프리셋 적용 뒤 selftest 통과", c == 0 and nofail(out), out)
    e.cleanup()

    # 계열 없음 대체 + 강도 강등
    m = [x for x in default_models() if not x["slug"].endswith("-luna")]
    for x in m:
        if x["slug"] == "gpt-6.2-sol":
            x["supported_reasoning_levels"] = lv("low", "medium", "high", "xhigh")
    e = Env("presets-fallback", claude=False, models=m)
    e.install("install")
    c, out = e.oche("preset", "use", "saver")
    check("24 목록에 luna 계열이 없으면 runner 만 기본값(최신 terra)으로 + 안내", c == 0 and e.toml("runner")["model"] == "gpt-6.1-terra"
          and "luna 계열이 없어 runner는 기본값" in out, out)
    c, out = e.oche("preset", "use", "max")
    check("24 모델이 max 를 지원하지 않으면 강등(xhigh)", c == 0 and e.toml("deep-reasoner")["model_reasoning_effort"] == "xhigh", out)
    c, out = e.oche("preset")
    check("24 강등된 값으로도 max 와 일치 ✔", "✔ max (최대)" in out, out)
    e.cleanup()


SCENARIOS = [
    ("claude_only", s01_claude_only), ("codex_only", s02_codex_only), ("legacy", s03_legacy), ("legacy_residue", s03c_legacy_residue),
    ("idempotent", s04_idempotent), ("switch_gate", s05_switch_and_gate), ("sync", s06_sync),
    ("effort", s07_effort_downgrade), ("override", s08_override), ("preserve_uninstall", s09_preserve_and_s11_uninstall),
    ("hook_path", s10_hook_path), ("degraded", s12_degraded), ("windows", s13_windows), ("command_name", s14_command_name),
    ("roles", s15_roles), ("interactive", s16_interactive_and_dashboard), ("bridge", s18_bridge),
    ("catalog", s22_catalog), ("presets", s24_presets), ("off_path", s23_off_and_path), ("tui_units", s19_tui_units), ("tui_pty", s20_tui_pty), ("plain", s21_plain_flag),
]


def main():
    want = sys.argv[1:]
    for name, fn in SCENARIOS:
        if want and not any(w in name for w in want):
            continue
        print("== %s" % name)
        try:
            fn()
        except Exception as ex:
            import traceback
            check("%s: 예외 없이 끝남" % name, False, traceback.format_exc())
    bad = [r for r in RESULTS if not r[0]]
    print("\n결과: OK %d, FAIL %d" % (len(RESULTS) - len(bad), len(bad)))
    for ok, n, d in bad:
        print("  FAIL " + n)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
