#!/usr/bin/env python3
"""oche 터미널 화면(TUI). 표준 라이브러리만 쓴다(macOS·Linux·Windows).

구조: render(state, width, height) -> 줄 목록, handle_key(state, key) -> state 는 화면·키 처리만 하고,
설정 변경은 비대화형 명령과 같은 함수(oche.py 의 set_role·cmd_switch·cmd_update·cmd_selftest)를 부른다.
입출력 루프(run)는 얇게 둔다.
"""
import contextlib
import importlib.util
import io
import os
import re
import sys
import time
import unicodedata

HERE = os.path.dirname(os.path.realpath(os.path.abspath(__file__)))


def _lib():
    mod = sys.modules.get("oche_lib")
    if mod is None:
        spec = importlib.util.spec_from_file_location("oche_lib", os.path.join(HERE, "oche.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["oche_lib"] = mod
        spec.loader.exec_module(mod)
    return mod


L = _lib()

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ACCENT = 209   # 주황 계열 강조색
DIM = 245
OK_C = 108
WARN_C = 179


# ======================================================================
# 글자 폭·자르기
# ======================================================================

def strip_ansi(s):
    return ANSI_RE.sub("", s)


def char_width(ch):
    if unicodedata.combining(ch):
        return 0
    if ch in ("​", "️"):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def text_width(s):
    return sum(char_width(c) for c in s)


def clip(s, width):
    """ANSI 를 보존하며 보이는 폭 width 까지 자른다."""
    if width <= 0:
        return ""
    out, w, i, colored = [], 0, 0, False
    while i < len(s):
        m = ANSI_RE.match(s, i)
        if m:
            out.append(m.group(0))
            colored = True
            i = m.end()
            continue
        cw = char_width(s[i])
        if w + cw > width:
            break
        out.append(s[i])
        w += cw
        i += 1
    r = "".join(out)
    if colored:
        r += "\x1b[0m"
    return r


def pad(s, width):
    c = clip(s, width)
    return c + " " * max(0, width - text_width(strip_ansi(c)))


# ======================================================================
# 상태
# ======================================================================

def default_ascii():
    if os.environ.get("OCHE_ASCII") == "1":
        return True
    enc = (getattr(sys.stdout, "encoding", None) or "").lower().replace("-", "")
    return enc not in ("utf8", "utf8sig")


def default_color():
    if os.environ.get("NO_COLOR") is not None:
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def snapshot():
    cfg = L.load_config()
    snap = {"name": L.cmd_name(cfg), "targets": L.installed_targets(cfg), "on": {}, "roles": {}, "path_ok": L.path_has_local_bin(),
            "degraded": False, "preset": L.preset_label_line(cfg) if L.installed_targets(cfg) else ""}
    cf = L.catalog_families("claude")
    for t in snap["targets"]:
        tc = cfg["targets"][t]
        if t == "claude":
            snap["on"][t] = L.claude_state(L.cpaths(tc["dir"]))
            cr = None
        else:
            p = L.xpaths(tc["dir"])
            snap["on"][t] = L.codex_state(p)
            cr = (L.read_json(p["models"], {}) or {}).get("roles") or {}
            snap["degraded"] = tc.get("subagent_fields") is False
        snap["roles"][t] = {}
        for r in L.ROLES:
            rc = L.role_cfg(cfg, t, r)
            snap["roles"][t][r] = {"model": rc["model"], "effort": rc["effort"],
                                   "actual": L.actual_model(t, rc, cfg, cf if t == "claude" else None, cr, r)}
    return snap


def initial_state(target=None, role=None):
    st = {"screen": "home", "cursor": 0, "mcursor": 0, "ecursor": 0, "tcursor": 0, "pcursor": 0, "status": "", "ascii": default_ascii(),
          "color": default_color(), "target": target, "role": role, "model_choice": None, "input": "", "quit": False,
          "single": False, "snap": snapshot()}
    if role:
        st["single"] = True
        targets = st["snap"]["targets"]
        if target is None and len(targets) == 1:
            st["target"] = targets[0]
        if st["target"]:
            open_model(st)
        else:
            st["screen"] = "target"
    elif target:
        ids = [it["id"] for it in menu_items(st)]
        if "switch:" + target in ids:
            st["cursor"] = ids.index("switch:" + target)
    return st


def menu_items(st):
    snap = st["snap"]
    items = []
    for t in snap["targets"]:
        items.append({"id": "switch:" + t, "label": L.TARGET_LABEL[t], "detail": "ON" if snap["on"][t] else "OFF", "kind": "switch"})
        for r in L.ROLES:
            rv = snap["roles"][t][r]
            items.append({"id": "role:%s:%s" % (t, r), "label": "  " + r,
                          "detail": "%s · %s" % (short_model(t, rv["model"]), rv["effort"]), "kind": "role"})
    items.append({"id": "preset", "label": "프리셋", "detail": snap.get("preset", "").replace("프리셋: ", ""), "kind": "action"})
    items.append({"id": "update", "label": "모델 목록 갱신", "detail": "", "kind": "action"})
    items.append({"id": "selftest", "label": "자가 시험", "detail": "", "kind": "action"})
    items.append({"id": "quit", "label": "나가기", "detail": "", "kind": "action"})
    return items


def short_model(t, m):
    if t == "codex" and m.startswith("latest:"):
        return "최신 " + m.split(":", 1)[1]
    return m


def model_options_for(st):
    cfg = L.load_config()
    out = []
    cur = st["snap"]["roles"][st["target"]][st["role"]]["model"]
    for label, value, desc in L.model_options(st["target"], cfg):
        out.append({"label": label, "value": value, "desc": desc, "current": value == cur})
    return out


def effort_options_for(st):
    cfg = L.load_config()
    cur = st["snap"]["roles"][st["target"]][st["role"]]["effort"]
    return [{"label": L.effort_label(e), "value": e, "current": e == cur}
            for e in L.effort_options(st["target"], st["model_choice"], cfg)]


def preset_options_for(st):
    cfg = L.load_config()
    cur = L.current_preset(cfg)
    out = []
    for pid, label, d, builtin in L.preset_list(cfg):
        desc = " · ".join("%s %s" % (L.TARGET_LABEL[t], L.describe_preset(cfg, pid, t)) for t in st["snap"]["targets"])
        out.append({"label": label if builtin else pid, "value": pid, "desc": desc if builtin else "(사용자) " + desc,
                    "current": bool(cur and cur[0] == pid)})
    out.append({"label": "지금 설정 저장", "value": "__save__", "desc": "이름을 붙여 사용자 프리셋으로", "current": False})
    return out


def open_model(st):
    st["screen"] = "model"
    opts = model_options_for(st)
    cur = [i for i, o in enumerate(opts) if o["current"]]
    st["mcursor"] = cur[0] if cur else 0


def open_effort(st, model):
    st["model_choice"] = model
    st["screen"] = "effort"
    opts = effort_options_for(st)
    cur = [i for i, o in enumerate(opts) if o["current"]]
    st["ecursor"] = cur[0] if cur else 0


def capture(fn, *a):
    buf = io.StringIO()
    err = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
        try:
            code = fn(*a)
        except L.UserError as e:
            err.write(str(e))
            code = 2
    return code, buf.getvalue(), err.getvalue()


# ======================================================================
# 키 처리 (순수에 가깝게: 화면 상태만 바꾸고, 설정 변경은 oche 함수에 맡긴다)
# ======================================================================

def nav(key):
    return {"k": "up", "j": "down"}.get(key, key)


def handle_key(st, key):
    st = dict(st)
    scr = st["screen"]
    if key == "ctrl-c":
        st["quit"] = True
        return st
    if scr in ("input", "preset_input"):
        if key == "enter":
            if scr == "preset_input":
                code, out, err = capture(L.cmd_preset, L.load_config(), ["save", st["input"]])
                st["status"] = out.strip().splitlines()[-1] if code == 0 and out.strip() else (err.strip() or "저장 실패")
                if code == 0:
                    st["snap"] = snapshot()
                    st["screen"] = "preset"
                return st
            try:
                m = L.norm_model(st["target"], st["input"], L.load_config())
                open_effort(st, m)
                st["status"] = ""
            except L.UserError as e:
                st["status"] = str(e)
        elif key in ("esc", "left"):
            st["screen"] = "model" if scr == "input" else "preset"
        elif key == "backspace":
            st["input"] = st["input"][:-1]
        elif len(key) == 1 and key.isprintable():
            st["input"] += key
        return st
    key = nav(key)
    if scr == "home":
        items = menu_items(st)
        if key == "up":
            st["cursor"] = (st["cursor"] - 1) % len(items)
        elif key == "down":
            st["cursor"] = (st["cursor"] + 1) % len(items)
        elif key == "q":
            st["quit"] = True
        elif key in ("enter", "right"):
            it = items[min(st["cursor"], len(items) - 1)]
            act = it["id"]
            if act == "quit":
                st["quit"] = True
            elif act.startswith("switch:"):
                t = act.split(":", 1)[1]
                on = not st["snap"]["on"][t]
                code, out, err = capture(L.cmd_switch, L.load_config(), on, t)
                st["status"] = ("%s %s — 다음 세션부터" % (L.TARGET_LABEL[t], "ON" if on else "OFF")) if code == 0 else err.strip()
                st["snap"] = snapshot()
            elif act.startswith("role:"):
                _, t, r = act.split(":")
                st["target"], st["role"] = t, r
                open_model(st)
            elif act == "preset":
                st["screen"] = "preset"
                opts = preset_options_for(st)
                cur = [i for i, o in enumerate(opts) if o["current"]]
                st["pcursor"] = cur[0] if cur else 0
            elif act == "update":
                code, out, err = capture(L.cmd_update, L.load_config(), None)
                notes = [l for l in out.splitlines() if l.startswith("알림:")]
                st["status"] = (notes[0][4:].strip() if notes else "모델 목록 갱신됨") if code == 0 else err.strip()
                st["snap"] = snapshot()
            elif act == "selftest":
                code, out, err = capture(L.cmd_selftest, L.load_config(), None)
                last = [l for l in out.splitlines() if l.startswith("selftest:")]
                st["status"] = "자가 시험 " + (last[-1].split(":", 1)[1].strip() if last else "실패")
                st["snap"] = snapshot()
        return st
    if scr == "preset":
        opts = preset_options_for(st)
        if key == "up":
            st["pcursor"] = (st["pcursor"] - 1) % len(opts)
        elif key == "down":
            st["pcursor"] = (st["pcursor"] + 1) % len(opts)
        elif key in ("esc", "left", "q"):
            st["screen"] = "home"
        elif key in ("enter", "right"):
            v = opts[st["pcursor"]]["value"]
            if v == "__save__":
                st["screen"] = "preset_input"
                st["input"] = ""
            else:
                code, out, err = capture(L.cmd_preset, L.load_config(), ["use", v])
                if code == 0:
                    st["status"] = "프리셋 '%s' 적용됨 — 다음 세션부터" % opts[st["pcursor"]]["label"]
                    st["snap"] = snapshot()
                    st["screen"] = "home"
                else:
                    st["status"] = err.strip() or "적용 실패"
        return st
    if scr == "target":
        targets = st["snap"]["targets"]
        if key == "up":
            st["tcursor"] = (st["tcursor"] - 1) % len(targets)
        elif key == "down":
            st["tcursor"] = (st["tcursor"] + 1) % len(targets)
        elif key in ("esc", "left", "q"):
            st["quit"] = True
        elif key in ("enter", "right"):
            st["target"] = targets[st["tcursor"]]
            open_model(st)
        return st
    if scr == "model":
        opts = model_options_for(st)
        if key == "up":
            st["mcursor"] = (st["mcursor"] - 1) % len(opts)
        elif key == "down":
            st["mcursor"] = (st["mcursor"] + 1) % len(opts)
        elif key in ("esc", "left", "q"):
            if st["single"]:
                st["quit"] = True
            else:
                st["screen"] = "home"
        elif key in ("enter", "right"):
            v = opts[st["mcursor"]]["value"]
            if v == "__custom__":
                st["screen"] = "input"
                st["input"] = ""
            else:
                open_effort(st, v)
        return st
    if scr == "effort":
        opts = effort_options_for(st)
        if key == "up":
            st["ecursor"] = (st["ecursor"] - 1) % len(opts)
        elif key == "down":
            st["ecursor"] = (st["ecursor"] + 1) % len(opts)
        elif key in ("esc", "left", "q"):
            st["screen"] = "model"
        elif key == "enter":
            e = opts[st["ecursor"]]["value"]
            code, out, err = capture(L.set_role, L.load_config(), st["target"], st["role"], st["model_choice"], e)
            if code == 0:
                notes = [l for l in out.splitlines() if l.startswith("안내:")]
                st["status"] = "적용됨 — 다음 세션부터" + (" · " + notes[0][3:].strip() if notes else "")
                st["snap"] = snapshot()
                if st["single"]:
                    st["quit"] = True
                st["screen"] = "home"
            else:
                st["status"] = err.strip() or "적용 실패"
        return st
    return st


# ======================================================================
# 그리기
# ======================================================================

class Paint(object):
    def __init__(self, st):
        self.color = st["color"]
        self.ascii = st["ascii"]
        if self.ascii:
            self.tl, self.tr, self.bl, self.br, self.h, self.v = "+", "+", "+", "+", "-", "|"
            self.cur, self.check, self.arrow, self.down = ">", "*", "->", "v"
        else:
            self.tl, self.tr, self.bl, self.br, self.h, self.v = "╭", "╮", "╰", "╯", "─", "│"
            self.cur, self.check, self.arrow, self.down = "❯", "✔", "→", "↓"

    def c(self, code, s):
        return "\x1b[38;5;%dm%s\x1b[0m" % (code, s) if self.color and s else s

    def bold(self, s):
        return "\x1b[1m%s\x1b[0m" % s if self.color and s else s

    def dim(self, s):
        return self.c(DIM, s)

    def acc(self, s):
        return self.c(ACCENT, s)

    def box(self, lines, width, color=None):
        """둥근 테두리 상자. width 는 바깥 폭."""
        inner = max(1, width - 2)
        top = self.tl + self.h * inner + self.tr
        bot = self.bl + self.h * inner + self.br
        out = [self.c(color, top) if color else self.dim(top)]
        for l in lines:
            body = pad(l, inner)
            side = self.c(color, self.v) if color else self.dim(self.v)
            out.append(side + body + side)
        out.append(self.c(color, bot) if color else self.dim(bot))
        return out


def focus_target(st):
    items = menu_items(st)
    if st.get("target"):
        return st["target"]
    it = items[min(st["cursor"], len(items) - 1)]["id"]
    if it.startswith(("switch:", "role:")):
        return it.split(":")[1]
    return (st["snap"]["targets"] or [None])[0]


def center(s, width):
    w = text_width(strip_ansi(s))
    left = max(0, (width - w) // 2)
    return " " * left + s


def diagram(st, width, P):
    t = focus_target(st)
    snap = st["snap"]
    if not t or width < 30:
        return []
    on = snap["on"][t]
    out = []
    mw = min(width, 28)
    for l in P.box([center("사용자", mw - 2)], mw):
        out.append(center(l, width))
    out.append(center(P.dim(P.down), width))
    for l in P.box([center("메인 · " + L.TARGET_LABEL[t], mw - 2)], mw, ACCENT):
        out.append(center(l, width))
    out.append(center(P.dim(P.down), width))
    gate = "게이트 " + ("ON" if on else "OFF")
    for l in P.box([center(P.c(OK_C, gate) if on else P.c(WARN_C, gate), mw - 2)], mw):
        out.append(center(l, width))
    bw = max(10, min(22, (width - 2) // 3))
    gap = 1 if bw * 3 + 2 <= width else 0
    arrows = (" " * (bw // 2) + P.dim(P.down) + " " * (bw - bw // 2 - 1) + " " * gap) * 3
    out.append(arrows)
    boxes = []
    for r in L.ROLES:
        rv = snap["roles"][t][r]
        name = "deep_reasoner" if (t == "codex" and r == "deep-reasoner") else r
        boxes.append(P.box([P.bold(name), rv["actual"] if not rv["actual"].startswith("다리") else rv["model"],
                            P.dim(L.effort_label(rv["effort"]))], bw))
    for i in range(len(boxes[0])):
        out.append((" " * gap).join(b[i] for b in boxes))
    if not on:
        out.append(P.dim("꺼져 있으면 규칙을 불러오지 않고 게이트도 모두 통과시킵니다"))
    out.append(P.dim("막는 것: 세 타입 밖 하청 · 설정과 다른 model/effort · 재하청"))
    return out


def menu_lines(st, width, P):
    out = []
    items = menu_items(st)
    for i, it in enumerate(items):
        sel = i == st["cursor"] and st["screen"] == "home"
        mark = P.acc(P.cur) if sel else " "
        label = it["label"]
        if it["kind"] == "switch":
            det = P.c(OK_C, "● ON") if it["detail"] == "ON" else P.c(WARN_C, "○ OFF")
            if P.ascii:
                det = P.c(OK_C, "[ON]") if it["detail"] == "ON" else P.c(WARN_C, "[OFF]")
            text = P.bold(label)
        else:
            det = P.dim(it["detail"])
            text = label
        if sel:
            text = P.acc(strip_ansi(text))
        left = "%s %s" % (mark, text)
        lw = text_width(strip_ansi(left))
        dw = text_width(strip_ansi(det))
        if det and lw + 2 + dw <= width:
            out.append(left + " " * (width - lw - dw) + det)
        elif det:
            out.append(left + "  " + det)
        else:
            out.append(left)
        if it["kind"] == "role" and it["id"].endswith(":runner"):
            out.append("")
    return out


def list_lines(opts, cursor, width, P, desc=True):
    out = []
    lw_max = max([text_width(o["label"]) for o in opts] + [0]) + 2
    for i, o in enumerate(opts):
        sel = i == cursor
        mark = P.acc(P.cur) if sel else " "
        num = "%2d." % (i + 1)
        cur = (P.c(OK_C, P.check) + " ") if o.get("current") else "  "
        lab = o["label"] + " " * (lw_max - text_width(o["label"])) if desc else o["label"]
        label = P.acc(lab) if sel else lab
        line = "%s %s %s%s" % (mark, P.dim(num), cur, label)
        if desc and o.get("desc"):
            lw = text_width(strip_ansi(line))
            if lw + 3 < width:
                line += P.dim(o["desc"])
        out.append(line)
    return out


def window(lines, cursor, height):
    """cursor 줄이 보이도록 height 줄만 고른다."""
    if len(lines) <= height:
        return lines
    start = max(0, min(cursor - height // 2, len(lines) - height))
    return lines[start:start + height]


def footer(st, P):
    scr = st["screen"]
    if scr == "home":
        keys = "↑↓ 이동 · Enter 선택 · q 나가기"
    elif scr in ("input", "preset_input"):
        keys = ("모델 ID" if scr == "input" else "이름") + " 입력 · Enter 확인 · Esc 뒤로"
    else:
        keys = "↑↓ 이동 · Enter 선택 · Esc 뒤로"
    if P.ascii:
        keys = keys.replace("↑↓", "up/down")
    return P.dim(keys)


def render(st, width, height):
    P = Paint(st)
    W, H = max(1, width), max(1, height)
    snap = st["snap"]
    name = snap["name"]
    head = P.acc(P.bold("%s" % name)) + P.dim(" · 하청 오케스트레이션 %s" % L.VERSION)
    if snap.get("preset"):
        head += P.dim("  ·  ") + snap["preset"]
    body = []
    scr = st["screen"]
    if not snap["targets"]:
        body = ["설치된 대상이 없습니다. 저장소의 install.py 로 설치하세요."]
    elif scr == "home":
        menu_w = min(46, W - 2)
        menu = menu_lines(st, menu_w, P)
        avail = H - 4
        wide = W >= 100 and H >= 20
        if wide:
            dw = W - menu_w - 4
            dg = diagram(st, dw, P)
            n = max(len(menu), len(dg))
            for i in range(n):
                left = pad(menu[i] if i < len(menu) else "", menu_w)
                right = dg[i] if i < len(dg) else ""
                body.append(" " + left + "   " + right)
        else:
            body = [" " + l for l in menu]
            if W >= 60 and H >= len(menu) + 20:
                body.append("")
                body.extend(" " + l for l in diagram(st, W - 2, P))
        body = window(body, st["cursor"], avail)
    elif scr in ("preset", "preset_input"):
        body.append(" " + P.bold("프리셋") + P.dim(" — 역할 3개의 모델·강도 묶음 · %s 지금 설정과 일치" % P.check))
        body.append("")
        avail = max(1, H - 4 - len(body))
        if scr == "preset":
            lines = list_lines(preset_options_for(st), st["pcursor"], W - 2, P)
            body.extend(" " + l for l in window(lines, st["pcursor"], avail))
        else:
            body.append(" " + P.dim("지금 설정을 저장할 이름(공백 없이, 내장 이름 default·saver·max·기본·절약·최대는 못 씀)"))
            fw = max(4, min(W - 4, 40))
            for l in P.box([st["input"] + P.acc("_")], fw, ACCENT):
                body.append(" " + l)
    elif scr == "target":
        body.append(P.bold(" 어느 쪽 하청을 바꿀까요? (%s)" % (st["role"] or "")))
        body.append("")
        opts = [{"label": L.TARGET_LABEL[t], "value": t} for t in snap["targets"]]
        body.extend(" " + l for l in list_lines(opts, st["tcursor"], W - 2, P, desc=False))
    elif scr in ("model", "effort", "input"):
        t, r = st["target"], st["role"]
        rv = snap["roles"][t][r]
        title = "모델 선택" if scr != "effort" else "강도 선택"
        body.append(" " + P.bold(title) + P.dim(" — %s · %s" % (L.TARGET_LABEL[t], r)))
        body.append(" " + P.dim("지금: %s %s %s · %s" % (short_model(t, rv["model"]), P.arrow, rv["actual"], L.effort_label(rv["effort"]))))
        if scr == "effort":
            body.append(" " + P.dim("모델: %s · 이 모델이 지원하는 강도만 보입니다 (ultra는 강도가 아니라 뺐습니다)" % st["model_choice"]))
        body.append("")
        avail = max(1, H - 4 - len(body))
        if scr == "model":
            lines = list_lines(model_options_for(st), st["mcursor"], W - 2, P)
            body.extend(" " + l for l in window(lines, st["mcursor"], avail))
        elif scr == "effort":
            lines = list_lines(effort_options_for(st), st["ecursor"], W - 2, P, desc=False)
            body.extend(" " + l for l in window(lines, st["ecursor"], avail))
        else:
            fw = max(4, min(W - 4, 60))
            for l in P.box([st["input"] + (P.acc("_"))], fw, ACCENT):
                body.append(" " + l)
            body.append(" " + P.dim("예: claude-opus-5-5 · gpt-6.2-sol · codex:gpt-6.2-sol · claude:haiku"))
    status = st.get("status") or ""
    warn = []
    if not snap["path_ok"]:
        warn.append("~/.local/bin 이 PATH에 없음")
    if snap["degraded"]:
        warn.append("Codex 저하 모드")
    if "codex" in snap["targets"]:
        warn.append("Codex 훅은 /hooks·Review hooks 에서 신뢰 필요")
    lines = [" " + head, ""]
    room = max(0, H - len(lines) - 2)
    lines.extend(body[:room])
    while len(lines) < H - 2:
        lines.append("")
    good = status.startswith("적용됨") or "적용됨" in status or "ON" in status[:20] or "저장" in status[:30]
    stat = P.c(OK_C, status) if good else (P.c(WARN_C, status) if status else P.dim(" · ".join(warn)))
    lines.append(" " + stat)
    lines.append(" " + footer(st, P))
    lines = lines[-H:] if len(lines) > H else lines
    return [clip(l, W) for l in lines[:H]]


# ======================================================================
# 키 해석
# ======================================================================

def decode_posix(b):
    table = {b"\x1b[A": "up", b"\x1b[B": "down", b"\x1b[C": "right", b"\x1b[D": "left",
             b"\x1bOA": "up", b"\x1bOB": "down", b"\x1bOC": "right", b"\x1bOD": "left",
             b"\r": "enter", b"\n": "enter", b"\x1b": "esc", b"\x7f": "backspace", b"\x08": "backspace",
             b"\x03": "ctrl-c"}
    if b in table:
        return table[b]
    if b.startswith(b"\x1b"):
        return "unknown"
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return "unknown"


def decode_windows(b):
    if len(b) == 2 and b[:1] in (b"\xe0", b"\x00"):
        return {b"H": "up", b"P": "down", b"K": "left", b"M": "right"}.get(b[1:], "unknown")
    table = {b"\r": "enter", b"\n": "enter", b"\x1b": "esc", b"\x08": "backspace", b"\x03": "ctrl-c"}
    if b in table:
        return table[b]
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return "unknown"


# ======================================================================
# 입출력 루프
# ======================================================================

class Terminal(object):
    def __init__(self):
        self.win = os.name == "nt"
        self.saved = None
        self.out = sys.stdout

    def enter(self):
        if self.win:
            try:
                import ctypes
                k = ctypes.windll.kernel32
                h = k.GetStdHandle(-11)
                mode = ctypes.c_uint32()
                if k.GetConsoleMode(h, ctypes.byref(mode)):
                    k.SetConsoleMode(h, mode.value | 0x0004)
            except Exception:
                pass
        else:
            import termios
            import tty
            fd = sys.stdin.fileno()
            self.saved = termios.tcgetattr(fd)
            tty.setcbreak(fd)
        self.out.write("\x1b[?1049h\x1b[?25l\x1b[H\x1b[2J")
        self.out.flush()

    def exit(self):
        try:
            self.out.write("\x1b[0m\x1b[?25h\x1b[?1049l")
            self.out.flush()
        finally:
            if self.saved is not None:
                import termios
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.saved)
                self.saved = None

    def size(self):
        try:
            s = os.get_terminal_size(sys.stdout.fileno())
            cols, rows = s.columns, s.lines
        except OSError:
            cols, rows = 0, 0
        if cols <= 0 or rows <= 0:  # 크기를 알려 주지 않는 터미널
            try:
                cols, rows = int(os.environ.get("COLUMNS", 80)), int(os.environ.get("LINES", 24))
            except ValueError:
                cols, rows = 80, 24
        return max(20, cols), max(8, rows)

    def draw(self, lines):
        self.out.write("\x1b[H" + "\x1b[K\r\n".join(lines) + "\x1b[K\x1b[J")
        self.out.flush()

    def read_key(self, timeout=0.25):
        if self.win:
            import msvcrt
            end = time.time() + timeout
            while time.time() < end:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch in ("\x00", "\xe0"):
                        return decode_windows((ch + msvcrt.getwch()).encode("latin-1"))
                    return decode_windows(ch.encode("utf-8"))
                time.sleep(0.02)
            return None
        import select
        fd = sys.stdin.fileno()
        r, _, _ = select.select([fd], [], [], timeout)
        if not r:
            return None
        b = os.read(fd, 1)
        if b == b"\x1b":
            while True:
                r, _, _ = select.select([fd], [], [], 0.03)
                if not r:
                    break
                b += os.read(fd, 1)
                if len(b) >= 3 and (b[-1:].isalpha() or b[-1:] == b"~"):
                    break
        elif b and b[0] >= 0xC0:
            need = 1 if b[0] < 0xE0 else (2 if b[0] < 0xF0 else 3)
            b += os.read(fd, need)
        return decode_posix(b)


def parse_args(argv):
    target, role = None, None
    for a in argv:
        if a in L.TARGETS:
            target = a
        elif a.lower() in L.ROLE_ALIASES:
            role = L.ROLE_ALIASES[a.lower()]
    return target, role


def run(argv=()):
    target, role = parse_args(argv)
    st = initial_state(target, role)
    term = Terminal()
    resized = [False]
    if not term.win:
        import signal
        try:
            signal.signal(signal.SIGWINCH, lambda *a: resized.__setitem__(0, True))
        except (AttributeError, ValueError):
            pass
    term.enter()
    last = None
    try:
        while not st["quit"]:
            size = term.size()
            frame = render(st, size[0], size[1])
            if frame != last or resized[0]:
                term.draw(frame)
                last = frame
                resized[0] = False
            key = term.read_key()
            if key is None:
                continue
            st = handle_key(st, key)
    except KeyboardInterrupt:
        pass
    finally:
        term.exit()
    if st.get("status"):
        print("%s: %s" % (st["snap"]["name"], st["status"]))
    return 0
