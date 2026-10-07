#!/usr/bin/env python3
"""Generate every SVG used by the profile README (dark + light variants).

    python scripts/build.py            # header, sections, cards, stack, buttons, footer
    python scripts/build.py --stats    # also refresh assets/stats-*.svg from the GitHub API

Requires `pip install fonttools brotli`. The stats step reads a token from
GITHUB_TOKEN, falling back to `gh auth token`; only public repositories are
used for languages, so the result is the same locally and in GitHub Actions.

Edit the PROFILE / PROJECTS / STACK blocks below, run the script, commit `assets/`.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import io
import json
import math
import os
import re
import subprocess
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "scripts" / "fonts"
ICON_DIR = ROOT / "scripts" / "icons"
OUT = ROOT / "assets"

USER = "bamba9928"

# --------------------------------------------------------------------------- content

PROFILE = {
    "name": "Bamba Dieng",
    "kicker": "FULL-STACK ENGINEER · FOUNDER OF HORUS GLOBAL SERVICE",
    "tagline": "I build secure business platforms for insurance, real estate "
               "and services, from the database schema to the mobile app.",
    "typing": [
        "shipping Django + Next.js platforms to production",
        "digitizing insurance for the Senegalese market",
        "hardening apps against the OWASP Top 10",
        "building desktop tools in Rust with Tauri",
    ],
    "pills": [("live", "Open to freelance & contracts"), ("pin", "Dakar, Senegal"), (None, "FR · EN")],
}

# status: "live" (link to the product) or "oss" (link to the repository)
PROJECTS = [
    {
        "slug": "horus-digital-assurances",
        "category": "INSURTECH · B2B",
        "title": "Horus Digital Assurances",
        "desc": "Motor-insurance platform for Senegal: quotes, payments, certificates "
                "issued from a phone and broker commissions, wired to the A.S.S partner API.",
        "stack": [("django", "Django 6"), ("django", "DRF"), ("nextdotjs", "Next.js"), ("expo", "Expo")],
        "status": "live", "footer": "horus-assur.digital", "note": "Private codebase",
        "url": "https://horus-assur.digital/",
    },
    {
        "slug": "sencontact",
        "category": "MARKETPLACE",
        "title": "SenContact",
        "desc": "Connects clients with verified tradespeople across Senegal's 14 regions: "
                "pro profiles, search, subscriptions, billing and moderation.",
        "stack": [("django", "Django REST"), ("nextdotjs", "Next.js"), ("postgresql", "PostgreSQL"), ("docker", "Docker")],
        "status": "live", "footer": "sencontact.com", "note": "Private codebase",
        "url": "https://sencontact.com/",
    },
    {
        "slug": "horus-insurance-manager",
        "category": "DESKTOP · INSURTECH",
        "title": "Horus Insurance Manager",
        "desc": "Desktop app for motor-insurance brokers: quotes, clients, vehicles, "
                "policies, payments, arrears and renewal alerts in one tool.",
        "stack": [("tauri", "Tauri"), ("rust", "Rust"), ("react", "React"), ("typescript", "TypeScript")],
        "status": "oss", "footer": "bamba9928/horus-insurance-manager", "note": "Source on GitHub",
        "url": f"https://github.com/{USER}/horus-insurance-manager",
    },
    {
        "slug": "mada-immo",
        "category": "PROPTECH",
        "title": "MADA IMMO",
        "desc": "Property management in one place: properties, tenants, monthly rent runs, "
                "PDF receipts, maintenance tracking and a live dashboard.",
        "stack": [("django", "Django"), ("tailwindcss", "Tailwind"), ("postgresql", "PostgreSQL"), ("celery", "Celery")],
        "status": "oss", "footer": "bamba9928/gestion_immobiliere", "note": "Live at madagroupe.com",
        "url": f"https://github.com/{USER}/gestion_immobiliere",
    },
    {
        "slug": "bwhite-digital",
        "category": "INSURTECH · B2C",
        "title": "BWHITE DIGITAL",
        "desc": "Digital insurance: online policy subscription, a secure customer area to "
                "follow claims, and a reseller partnership programme.",
        "stack": [("django", "Django"), ("tailwindcss", "Tailwind"), ("javascript", "JavaScript"), ("postgresql", "PostgreSQL")],
        "status": "live", "footer": "bwhitedigital.net", "note": "Private codebase",
        "url": "https://bwhitedigital.net/",
    },
    {
        "slug": "horus-cyber-lab",
        "category": "OFFENSIVE SECURITY · LAB",
        "title": "Horus Cyber Lab",
        "desc": "A reproducible pentest lab on a dedicated VPS: hardening, Docker isolation, "
                "vulnerable targets, real CVEs and an AI-assisted workflow.",
        "stack": [("docker", "Docker"), ("linux", "Linux"), ("kalilinux", "Kali"), ("owasp", "OWASP")],
        "status": "oss", "footer": "bamba9928/horus-cyber-lab", "note": "Educational use",
        "url": f"https://github.com/{USER}/horus-cyber-lab",
    },
]

STACK = [
    ("BACKEND", [("python", "Python"), ("django", "Django"), ("django", "Django REST"),
                 ("celery", "Celery"), ("rust", "Rust"), ("pytest", "Pytest")]),
    ("FRONTEND & APPS", [("typescript", "TypeScript"), ("javascript", "JavaScript"), ("react", "React"),
                         ("nextdotjs", "Next.js"), ("expo", "Expo"), ("tauri", "Tauri"),
                         ("tailwindcss", "Tailwind CSS")]),
    ("DATA & DEVOPS", [("postgresql", "PostgreSQL"), ("redis", "Redis"), ("sqlite", "SQLite"),
                       ("docker", "Docker"), ("nginx", "Nginx"), ("linux", "Linux"),
                       ("githubactions", "GitHub Actions")]),
    ("SECURITY", [("owasp", "OWASP Top 10"), ("jsonwebtokens", "JWT & RBAC"), ("kalilinux", "Kali Linux"),
                  ("wireshark", "Wireshark"), ("openapiinitiative", "OpenAPI")]),
]

SECTIONS = [
    ("about", "01", "About", "who I am"),
    ("work", "02", "Selected work", "shipped to production"),
    ("stack", "03", "Toolbox", "what I build with"),
    ("activity", "04", "Activity", "updated daily"),
    ("contact", "05", "Let's build", "freelance & contracts"),
]

BUTTONS = [
    ("start", "Start a project", None, True),
    ("website", "horuservices.cloud", "globe", False),
    ("linkedin", "LinkedIn", "linkedin", False),
    ("x", "@horuservices", "x", False),
]

# Languages that describe markup or tooling rather than the code itself.
LANG_SKIP = {"HTML", "CSS", "SCSS", "Dockerfile", "Makefile", "Procfile", "Batchfile", "PowerShell"}

# --------------------------------------------------------------------------- theme

THEMES = {
    "dark": dict(
        bg="#0B0B0E", surface="#111115", border="#26262D", text="#F3EFE7", muted="#A3A3AD",
        faint="#878791", gold="#D6A85C", gold2="#EBCB8B", live="#3FB950", ink="#0B0B0E",
        grid="#FFFFFF", track="#1D1D23",
        heat=["#1A1A20", "#5E4A2A", "#8A6A33", "#B98A44", "#EBCB8B"],
    ),
    "light": dict(
        bg="#FBF8F2", surface="#FFFDF9", border="#E4DCCD", text="#16161A", muted="#55555F",
        faint="#696973", gold="#8C6421", gold2="#A87B30", live="#1A7F37", ink="#FFFDF9",
        grid="#000000", track="#EFE8DA",
        heat=["#EFE9DE", "#D4B06A", "#B98A3A", "#8F6522", "#5C3F10"],
    ),
}

# --------------------------------------------------------------------------- fonts

FONT_STACKS = {
    "display-800": ("'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif", 800),
    "display-700": ("'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif", 700),
    "body-400": ("Inter, 'Segoe UI', system-ui, sans-serif", 400),
    "body-500": ("Inter, 'Segoe UI', system-ui, sans-serif", 500),
    "mono-500": ("'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", 500),
}


class Font:
    _cache: dict[str, "Font"] = {}

    def __init__(self, key: str):
        self.key = key
        self.path = FONT_DIR / f"{key}.woff2"
        tt = TTFont(self.path)
        self.cmap = tt.getBestCmap()
        self.hmtx = tt["hmtx"]
        self.upm = tt["head"].unitsPerEm

    @classmethod
    def get(cls, key: str) -> "Font":
        if key not in cls._cache:
            cls._cache[key] = Font(key)
        return cls._cache[key]

    def width(self, s: str, size: float, ls: float = 0.0) -> float:
        units = sum(self.hmtx[self.cmap[ord(c)]][0] if ord(c) in self.cmap else self.upm * 0.6 for c in s)
        return units * size / self.upm + ls * len(s)


def wrap(s: str, font: str, size: float, max_w: float) -> list[str]:
    f, lines, line = Font.get(font), [], ""
    for word in s.split():
        trial = f"{line} {word}".strip()
        if line and f.width(trial, size) > max_w:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + ([line] if line else [])


def font_face(key: str, chars: set[str]) -> str:
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga", "calt", "tnum"]
    opts.name_IDs = [1, 2]
    opts.notdef_outline = True
    tt = TTFont(FONT_DIR / f"{key}.woff2", recalcTimestamp=False)  # keep output byte-stable between runs
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(sorted(chars | {" "})))
    sub.subset(tt)
    buf = io.BytesIO()
    tt.flavor = "woff2"
    tt.save(buf)
    data = base64.b64encode(buf.getvalue()).decode()
    return f"@font-face{{font-family:'hg-{key}';src:url(data:font/woff2;base64,{data}) format('woff2');}}"


# --------------------------------------------------------------------------- icons

def icon_path(slug: str) -> str:
    if slug == "globe":  # not a brand: a simple wireframe globe drawn on a 24px grid
        return ("M12 1.5a10.5 10.5 0 1 0 0 21 10.5 10.5 0 0 0 0-21Zm7.9 9.75h-3.4a16.5 16.5 0 0 0-1.6-6.9 "
                "9 9 0 0 1 5 6.9ZM12 3.05c.9 1 2.6 3.6 3 8.2H9c.4-4.6 2.1-7.2 3-8.2Zm-2.9 1.3a16.5 16.5 0 0 0-1.6 "
                "6.9H4.1a9 9 0 0 1 5-6.9ZM4.1 12.75h3.4a16.5 16.5 0 0 0 1.6 6.9 9 9 0 0 1-5-6.9ZM12 20.95c-.9-1-2.6-3.6-3"
                "-8.2h6c-.4 4.6-2.1 7.2-3 8.2Zm2.9-1.3a16.5 16.5 0 0 0 1.6-6.9h3.4a9 9 0 0 1-5 6.9Z")
    svg = (ICON_DIR / f"{slug}.svg").read_text()
    return re.search(r'<path d="([^"]+)"', svg).group(1)


def icon(x: float, y: float, size: float, slug: str, fill: str, opacity: float = 1.0) -> str:
    k = size / 24
    op = f' fill-opacity="{opacity}"' if opacity != 1 else ""
    return f'<path transform="translate({x:.2f} {y:.2f}) scale({k:.4f})" d="{icon_path(slug)}" fill="{fill}"{op}/>'


# --------------------------------------------------------------------------- svg document

def n(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


class Svg:
    def __init__(self, w: float, h: float, title: str, theme: str):
        self.w, self.h, self.title = w, h, title
        self.t = THEMES[theme]
        self.parts: list[str] = []
        self.defs: list[str] = []
        self.css: list[str] = []
        self.used: dict[str, set[str]] = {}

    def use(self, font: str, s: str) -> str:
        self.used.setdefault(font, set()).update(s)
        return f"f-{font}"

    def text(self, x, y, s, font, size, fill, anchor="start", ls=0.0, extra="") -> None:
        cls = self.use(font, s)
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        l = f' letter-spacing="{n(ls)}"' if ls else ""
        self.parts.append(
            f'<text x="{n(x)}" y="{n(y)}" class="{cls}" font-size="{n(size)}" fill="{fill}"{a}{l}{extra}>{escape(s)}</text>')

    def add(self, raw: str) -> None:
        self.parts.append(raw)

    def render(self) -> str:
        faces = "".join(font_face(k, c) for k, c in sorted(self.used.items()))
        classes = "".join(
            f".f-{k}{{font-family:'hg-{k}',{FONT_STACKS[k][0]};font-weight:{FONT_STACKS[k][1]}}}"
            for k in sorted(self.used))
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{n(self.w)}" height="{n(self.h)}" '
            f'viewBox="0 0 {n(self.w)} {n(self.h)}" fill="none" role="img" aria-label="{escape(self.title)}">'
            f"<title>{escape(self.title)}</title>"
            f"<style>{faces}{classes}text{{font-kerning:normal}}{''.join(self.css)}</style>"
            f"<defs>{''.join(self.defs)}</defs>{''.join(self.parts)}</svg>\n")


def save(name: str, svg: Svg) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(svg.render())


def card_frame(s: Svg, w: float, h: float, glow_x: float, glow_y: float, uid: str) -> None:
    t = s.t
    s.defs.append(
        f'<radialGradient id="glow-{uid}" cx="{n(glow_x)}" cy="{n(glow_y)}" r="{n(max(w, h) * .55)}" '
        f'gradientUnits="userSpaceOnUse"><stop stop-color="{t["gold"]}" stop-opacity=".16"/>'
        f'<stop offset="1" stop-color="{t["gold"]}" stop-opacity="0"/></radialGradient>')
    s.add(f'<rect x=".5" y=".5" width="{n(w - 1)}" height="{n(h - 1)}" rx="16" fill="{t["surface"]}" stroke="{t["border"]}"/>')
    s.add(f'<rect x=".5" y=".5" width="{n(w - 1)}" height="{n(h - 1)}" rx="16" fill="url(#glow-{uid})"/>')


def pill(s: Svg, x, y, label, kind, font="body-500", size=13.5, h=30) -> float:
    """Outlined pill; returns its width. kind: 'live' (pulsing dot), 'pin' or None."""
    t = s.t
    lead = 22 if kind else 0
    w = Font.get(font).width(label, size) + 28 + lead
    s.add(f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{h}" rx="{h / 2}" fill="{t["surface"]}" '
          f'fill-opacity=".7" stroke="{t["border"]}"/>')
    cy = y + h / 2
    if kind == "live":
        s.add(f'<circle cx="{n(x + 20)}" cy="{n(cy)}" r="4" fill="{t["live"]}"/>'
              f'<circle cx="{n(x + 20)}" cy="{n(cy)}" r="4" fill="none" stroke="{t["live"]}" class="ping"/>')
    elif kind == "pin":
        s.add(f'<path transform="translate({n(x + 14)} {n(cy - 7)})" d="M6 0a5 5 0 0 0-5 5c0 3.6 5 9 5 9s5-5.4 '
              f'5-9a5 5 0 0 0-5-5Zm0 6.8A1.8 1.8 0 1 1 6 3.2a1.8 1.8 0 0 1 0 3.6Z" fill="{t["gold"]}"/>')
    s.text(x + 14 + lead, cy + size * .36, label, font, size, t["text"])
    return w


# --------------------------------------------------------------------------- header

def build_header(theme: str) -> None:
    W, H = 1000, 360
    s = Svg(W, H, f'{PROFILE["name"]}: full-stack engineer, founder of Horus Global Service, Dakar', theme)
    t = s.t
    gx, gy, R = 800, 178, 118

    s.defs.append(
        f'<pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse">'
        f'<path d="M28 0H0V28" stroke="{t["grid"]}" stroke-opacity=".05"/></pattern>'
        f'<linearGradient id="fade" x1="0" x2="1"><stop offset=".3" stop-color="#fff" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="#fff"/></linearGradient>'
        f'<mask id="gridmask"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask>'
        f'<radialGradient id="halo" cx="{gx}" cy="{gy}" r="300" gradientUnits="userSpaceOnUse">'
        f'<stop stop-color="{t["gold"]}" stop-opacity=".22"/><stop offset="1" stop-color="{t["gold"]}" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="sphere" cx="{gx - R * .35}" cy="{gy - R * .4}" r="{R * 1.5}" gradientUnits="userSpaceOnUse">'
        f'<stop stop-color="{t["gold"]}" stop-opacity=".18"/><stop offset="1" stop-color="{t["gold"]}" stop-opacity="0"/></radialGradient>'
        f'<clipPath id="frame"><rect width="{W}" height="{H}" rx="20"/></clipPath>'
        f'<clipPath id="ball"><circle cx="{gx}" cy="{gy}" r="{R}"/></clipPath>')
    s.css.append(
        ".ping{transform-box:fill-box;transform-origin:center;animation:ping 2.4s cubic-bezier(0,0,.2,1) infinite}"
        "@keyframes ping{0%{transform:scale(1);opacity:.9}80%,100%{transform:scale(3.2);opacity:0}}"
        ".blink{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}"
        ".rise{animation:rise .9s cubic-bezier(.2,.7,.2,1) both}"
        "@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}"
        "@media (prefers-reduced-motion:reduce){.ping,.blink,.rise{animation:none}}")

    s.add('<g clip-path="url(#frame)">')
    s.add(f'<rect width="{W}" height="{H}" fill="{t["bg"]}"/>')
    s.add(f'<rect width="{W}" height="{H}" fill="url(#grid)" mask="url(#gridmask)"/>')
    s.add(f'<circle cx="{gx}" cy="{gy}" r="300" fill="url(#halo)"/>')

    # Wireframe globe, a nod to the Horus logo. Meridians spin by animating rx = R·|sin(θ + ωt)|.
    g = [f'<circle cx="{gx}" cy="{gy}" r="{R}" fill="url(#sphere)"/>', f'<g clip-path="url(#ball)" stroke="{t["gold"]}" fill="none">']
    for lat in (-60, -30, 0, 30, 60):
        y = gy - R * math.sin(math.radians(lat))
        rx = R * math.cos(math.radians(lat))
        op = .42 if lat == 0 else .2
        g.append(f'<ellipse cx="{gx}" cy="{n(y)}" rx="{n(rx)}" ry="{n(rx * .16)}" stroke-opacity="{op}"/>')
    steps = 48
    for k in range(6):
        phase = math.radians(k * 30 + 8)
        vals = ";".join(n(R * abs(math.sin(phase + 2 * math.pi * i / steps / 2))) for i in range(steps + 1))
        g.append(f'<ellipse cx="{gx}" cy="{gy}" rx="{n(R * abs(math.sin(phase)))}" ry="{R}" stroke-opacity=".26">'
                 f'<animate attributeName="rx" dur="30s" repeatCount="indefinite" values="{vals}"/></ellipse>')
    g.append("</g>")
    g.append(f'<circle cx="{gx}" cy="{gy}" r="{R}" stroke="{t["gold"]}" stroke-opacity=".6" stroke-width="1.2"/>')
    # Orbit with a travelling satellite
    orbit = f"M{gx - R * 1.42} {gy} a{R * 1.42} {R * .36} 0 1 0 {R * 2.84} 0 a{R * 1.42} {R * .36} 0 1 0 {-R * 2.84} 0"
    g.append(f'<path d="{orbit}" transform="rotate(-14 {gx} {gy})" stroke="{t["gold"]}" stroke-opacity=".35" '
             f'stroke-dasharray="2 6" stroke-linecap="round"/>')
    g.append(f'<g transform="rotate(-14 {gx} {gy})"><circle r="4" fill="{t["gold2"]}">'
             f'<animateMotion dur="14s" repeatCount="indefinite" path="{orbit}"/></circle></g>')
    # Dakar marker
    dx, dy = gx - R * .42, gy - R * .18
    g.append(f'<circle cx="{n(dx)}" cy="{n(dy)}" r="4.5" fill="{t["gold2"]}"/>'
             f'<circle cx="{n(dx)}" cy="{n(dy)}" r="4.5" fill="none" stroke="{t["gold2"]}" class="ping"/>')
    s.add("".join(g))
    s.text(W - 36, H - 30, "DAKAR · 14.69°N 17.44°W", "mono-500", 10.5, t["faint"], anchor="end", ls=1.2)

    # Identity column
    x0 = 56
    s.add('<g class="rise">')
    s.add(f'<rect x="{x0}" y="62" width="26" height="2" rx="1" fill="{t["gold"]}"/>')
    s.text(x0 + 38, 68, PROFILE["kicker"], "mono-500", 12, t["gold"], ls=2)
    s.text(x0 - 3, 136, PROFILE["name"], "display-800", 64, t["text"], ls=-1.6)
    lines = wrap(PROFILE["tagline"], "body-400", 17.5, 560)
    assert len(lines) <= 2, f"tagline wraps to {len(lines)} lines: shorten it"
    for i, line in enumerate(lines):
        s.text(x0, 178 + i * 26, line, "body-400", 17.5, t["muted"])
    s.add("</g>")

    # Terminal line with a typed, rotating phrase
    ty, size = 252, 15  # 15px JetBrains Mono = exactly 9px per glyph, so clip steps match glyph edges
    mono = Font.get("mono-500")
    cw = mono.width("a", size)
    s.text(x0, ty, "$", "mono-500", size, t["gold"])
    tx = x0 + cw * 2
    events, period, clock = [], 0.0, 0.0
    plan = []
    for phrase in PROFILE["typing"]:
        type_t, hold, erase_t, gap = 0.055 * len(phrase), 2.4, 0.018 * len(phrase), 0.45
        plan.append((phrase, clock, type_t, hold, erase_t))
        clock += type_t + hold + erase_t + gap
    period = clock
    cursor_events: list[tuple[float, float]] = [(0.0, 0.0)]
    for idx, (phrase, start, type_t, hold, erase_t) in enumerate(plan):
        n_ch = len(phrase)
        ev = [(0.0, 0.0)]
        for k in range(1, n_ch + 1):
            ev.append((start + type_t * k / n_ch, k * cw))
        for k in range(n_ch - 1, -1, -1):
            ev.append((start + type_t + hold + erase_t * (n_ch - k) / n_ch, k * cw))
        cursor_events += ev[1:]
        key_times = ";".join(f"{e[0] / period:.4f}" for e in ev)
        values = ";".join(n(e[1]) for e in ev)
        s.defs.append(
            f'<clipPath id="type{idx}"><rect x="{n(tx)}" y="{ty - 20}" width="0" height="28">'
            f'<animate attributeName="width" dur="{period:.2f}s" repeatCount="indefinite" calcMode="discrete" '
            f'keyTimes="{key_times}" values="{values}"/></rect></clipPath>')
        cls = s.use("mono-500", phrase)
        s.add(f'<text x="{n(tx)}" y="{ty}" class="{cls}" font-size="{size}" fill="{t["text"]}" '
              f'clip-path="url(#type{idx})">{escape(phrase)}</text>')
    cursor_events.sort()
    key_times = ";".join(f"{e[0] / period:.4f}" for e in cursor_events)
    values = ";".join(n(tx + e[1] + 2) for e in cursor_events)
    s.add(f'<rect x="{n(tx + 2)}" y="{ty - 14}" width="{n(cw * .62)}" height="18" rx="1" fill="{t["gold"]}" class="blink">'
          f'<animate attributeName="x" dur="{period:.2f}s" repeatCount="indefinite" calcMode="discrete" '
          f'keyTimes="{key_times}" values="{values}"/></rect>')

    x = x0
    for kind, label in PROFILE["pills"]:
        x += pill(s, x, 284, label, kind) + 10

    s.add("</g>")
    s.add(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="19.5" stroke="{t["border"]}"/>')
    save(f"header-{theme}.svg", s)


# --------------------------------------------------------------------------- section titles

def build_section(theme: str, key: str, num: str, title: str, caption: str) -> None:
    W, H = 1000, 56
    s = Svg(W, H, title, theme)
    t = s.t
    s.text(0, 37, num, "mono-500", 13, t["gold"], ls=1)
    s.text(34, 39, title, "display-700", 26, t["text"], ls=-.4)
    end = 34 + Font.get("display-700").width(title, 26, -.4) + 22
    cap_w = Font.get("mono-500").width(caption.upper(), 11, 1.6)
    s.defs.append(f'<linearGradient id="rule" x1="{n(end)}" x2="{n(W - cap_w - 20)}" gradientUnits="userSpaceOnUse">'
                  f'<stop stop-color="{t["gold"]}" stop-opacity=".7"/><stop offset="1" stop-color="{t["gold"]}" stop-opacity=".08"/>'
                  f'</linearGradient>')
    s.add(f'<rect x="{n(end)}" y="30" width="{n(W - cap_w - 20 - end)}" height="1.2" fill="url(#rule)"/>')
    s.text(W, 35, caption.upper(), "mono-500", 11, t["faint"], anchor="end", ls=1.6)
    save(f"section-{key}-{theme}.svg", s)


# --------------------------------------------------------------------------- project cards

def build_card(theme: str, p: dict) -> None:
    W, H = 500, 284
    s = Svg(W, H, f'{p["title"]}: {p["desc"]}', theme)
    t = s.t
    card_frame(s, W, H, W - 40, 10, "c")
    px = 30

    s.text(px, 44, p["category"], "mono-500", 11, t["gold"], ls=1.8)
    if p["status"] == "live":
        label = "LIVE"
        lw = Font.get("mono-500").width(label, 10.5, 1.4) + 34
        s.add(f'<rect x="{n(W - px - lw)}" y="27" width="{n(lw)}" height="24" rx="12" fill="{t["live"]}" fill-opacity=".12" '
              f'stroke="{t["live"]}" stroke-opacity=".45"/>')
        s.add(f'<circle cx="{n(W - px - lw + 14)}" cy="39" r="3.5" fill="{t["live"]}"/>'
              f'<circle cx="{n(W - px - lw + 14)}" cy="39" r="3.5" fill="none" stroke="{t["live"]}" class="ping"/>')
        s.text(W - px - lw + 24, 43, label, "mono-500", 10.5, t["text"], ls=1.4)
        s.css.append(".ping{transform-box:fill-box;transform-origin:center;animation:ping 2.4s cubic-bezier(0,0,.2,1) infinite}"
                     "@keyframes ping{0%{transform:scale(1);opacity:.9}80%,100%{transform:scale(3);opacity:0}}"
                     "@media (prefers-reduced-motion:reduce){.ping{animation:none}}")
    else:
        label = "OPEN SOURCE"
        lw = Font.get("mono-500").width(label, 10.5, 1.4) + 40
        s.add(f'<rect x="{n(W - px - lw)}" y="27" width="{n(lw)}" height="24" rx="12" fill="none" stroke="{t["border"]}"/>')
        s.add(icon(W - px - lw + 9, 32, 14, "github", t["text"]) if (ICON_DIR / "github.svg").exists() else "")
        s.text(W - px - lw + 28, 43, label, "mono-500", 10.5, t["text"], ls=1.4)

    s.text(px, 88, p["title"], "display-700", 25, t["text"], ls=-.4)
    for i, line in enumerate(wrap(p["desc"], "body-400", 14.5, W - px * 2)[:3]):
        s.text(px, 120 + i * 22, line, "body-400", 14.5, t["muted"])

    x = px
    for slug, name in p["stack"]:
        w = Font.get("body-500").width(name, 12.5) + 40
        s.add(f'<rect x="{n(x)}" y="190" width="{n(w)}" height="28" rx="8" fill="{t["bg"]}" fill-opacity=".55" stroke="{t["border"]}"/>')
        s.add(icon(x + 10, 197, 14, slug, t["gold2"] if theme == "dark" else t["gold"]))
        s.text(x + 30, 208.5, name, "body-500", 12.5, t["text"])
        x += w + 8

    s.add(f'<rect x="{px}" y="236" width="{W - px * 2}" height="1" fill="{t["border"]}"/>')
    s.text(px, 262, p["footer"] + "  ↗", "mono-500", 12, t["gold2"] if theme == "dark" else t["gold"])
    s.text(W - px, 262, p["note"], "body-400", 12.5, t["faint"], anchor="end")
    save(f'card-{p["slug"]}-{theme}.svg', s)


# --------------------------------------------------------------------------- stack

def build_stack(theme: str) -> None:
    W, pad, label_w, row_h, chip_h, gap = 1000, 32, 172, 58, 36, 8
    body = Font.get("body-500")
    size = 14.0
    while size > 11 and any(sum(body.width(nm, size) + 46 + gap for _, nm in it) - gap > W - pad * 2 - label_w
                            for _, it in STACK):
        size -= .25
    rows, y = [], pad + 2
    for label, items in STACK:
        x, chips = pad + label_w, []
        for slug, name in items:
            w = body.width(name, size) + 46
            chips.append((x, y, w, slug, name))
            x += w + gap
        rows.append((label, chips))
        y += row_h
    H = y + pad - (row_h - chip_h)
    s = Svg(W, H, "Toolbox: " + "; ".join(f'{l.title()}: {", ".join(nm for _, nm in it)}' for l, it in STACK), theme)
    t = s.t
    card_frame(s, W, H, 80, 0, "s")
    for i, (label, chips) in enumerate(rows):
        top = chips[0][1]
        s.text(pad, top + 23, label, "mono-500", 11, t["gold"], ls=1.8)
        for x, y, w, slug, name in chips:
            s.add(f'<rect x="{n(x)}" y="{n(y)}" width="{n(w)}" height="{chip_h}" rx="10" fill="{t["bg"]}" '
                  f'fill-opacity=".55" stroke="{t["border"]}"/>')
            s.add(icon(x + 13, y + 10, 16, slug, t["gold2"] if theme == "dark" else t["gold"]))
            s.text(x + 35, y + 23, name, "body-500", size, t["text"])
        if i < len(rows) - 1:
            s.add(f'<rect x="{pad}" y="{n(top + chip_h + (row_h - chip_h) / 2)}" width="{W - pad * 2}" height="1" '
                  f'fill="{t["border"]}" fill-opacity=".7"/>')
    save(f"stack-{theme}.svg", s)


# --------------------------------------------------------------------------- buttons & footer

def build_button(theme: str, key: str, label: str, slug: str | None, primary: bool) -> None:
    H, size = 44, 15
    f = Font.get("body-500")
    lead = 26 if slug else 0
    trail = 22 if primary else 0
    W = f.width(label, size) + 40 + lead + trail
    s = Svg(W, H, label, theme)
    t = s.t
    if primary:
        s.add(f'<rect width="{n(W)}" height="{H}" rx="12" fill="{t["gold"]}"/>')
        fg = t["ink"]
    else:
        s.add(f'<rect x=".5" y=".5" width="{n(W - 1)}" height="{H - 1}" rx="11.5" fill="{t["surface"]}" stroke="{t["border"]}"/>')
        fg = t["text"]
    if slug:
        s.add(icon(20, 14, 16, slug, fg))
    s.text(20 + lead, 27.5, label, "body-500", size, fg)
    if primary:
        ax = 20 + lead + f.width(label, size) + 10
        s.add(f'<path d="M{n(ax)} 22h11m-4.5-4.5L{n(ax + 11)} 22l-4.5 4.5" stroke="{fg}" stroke-width="1.8" '
              f'stroke-linecap="round" stroke-linejoin="round"/>')
    save(f"btn-{key}-{theme}.svg", s)


def build_footer(theme: str) -> None:
    W, H = 1000, 70
    s = Svg(W, H, "Bamba Dieng · Horus Global Service · Dakar, Senegal", theme)
    t = s.t
    s.defs.append(f'<linearGradient id="fl" x1="0" x2="1"><stop stop-color="{t["gold"]}" stop-opacity="0"/>'
                  f'<stop offset=".5" stop-color="{t["gold"]}" stop-opacity=".6"/>'
                  f'<stop offset="1" stop-color="{t["gold"]}" stop-opacity="0"/></linearGradient>')
    s.add(f'<rect x="200" y="18" width="600" height="1" fill="url(#fl)"/>')
    s.add(f'<rect x="{W / 2 - 4}" y="14" width="8" height="8" transform="rotate(45 {W / 2} 18)" fill="{t["bg"]}" stroke="{t["gold"]}"/>')
    s.text(W / 2, 52, "BAMBA DIENG  ·  HORUS GLOBAL SERVICE  ·  DAKAR, SENEGAL", "mono-500", 11, t["faint"], anchor="middle", ls=2)
    save(f"footer-{theme}.svg", s)


# --------------------------------------------------------------------------- stats

STATS_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false) {
      totalCount
      nodes { languages(first: 20) { edges { size node { name } } } }
    }
  }
}"""


def token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        return tok
    return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


def fetch_stats() -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": STATS_QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {token()}", "Content-Type": "application/json", "User-Agent": USER})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise SystemExit(f"GitHub API error: {payload['errors']}")
    u = payload["data"]["user"]
    cal = u["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]

    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] else 0
        longest = max(longest, run)
    langs: dict[str, int] = {}
    for repo in u["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            if e["node"]["name"] not in LANG_SKIP:
                langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    return {
        "total": cal["totalContributions"],
        "active_days": sum(1 for d in days if d["contributionCount"]),
        "longest_streak": longest,
        "public_repos": u["repositories"]["totalCount"],
        "weeks": [[(d["date"], d["contributionCount"]) for d in w["contributionDays"]] for w in cal["weeks"]],
        "languages": sorted(langs.items(), key=lambda kv: -kv[1]),
    }


def build_stats(theme: str, st: dict) -> None:
    W, H, pad = 1000, 448, 32
    s = Svg(W, H, f'GitHub activity: {st["total"]} contributions in the last 12 months, '
                  f'{st["active_days"]} active days; most used languages in public repositories', theme)
    t = s.t
    card_frame(s, W, H, W - 60, 0, "st")
    s.css.append(".cell{animation:pop .5s ease-out both}@keyframes pop{from{opacity:0}to{opacity:1}}"
                 "@media (prefers-reduced-motion:reduce){.cell{animation:none}}")

    # Stat tiles
    tiles = [(f'{st["total"]:,}', "Contributions, last 12 months"),
             (str(st["active_days"]), "Active days"),
             (str(st["longest_streak"]), "Longest streak (days)"),
             (str(st["public_repos"]), "Public repositories")]
    tw = (W - pad * 2) / len(tiles)
    for i, (value, label) in enumerate(tiles):
        x = pad + i * tw
        if i:
            s.add(f'<rect x="{n(x - 1)}" y="{pad + 4}" width="1" height="62" fill="{t["border"]}"/>')
        ox = x + (22 if i else 0)
        s.text(ox, pad + 44, value, "body-500", 38, t["text"], ls=-1)
        s.text(ox, pad + 68, label, "body-400", 13, t["muted"])

    # Contribution heatmap (sequential: one gold ramp, level 0 sits on the surface)
    top = 150
    weeks = st["weeks"][-53:]
    peak = max((c for w in weeks for _, c in w), default=0) or 1
    cell, gap = 12.5, 3.2
    grid_w = len(weeks) * (cell + gap) - gap
    left = W - pad - grid_w
    s.text(pad, top - 14, "Contributions", "body-500", 13.5, t["text"])
    for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        s.text(left - 10, top + row * (cell + gap) + cell - 2.5, name, "body-400", 11, t["faint"], anchor="end")
    last_month = None
    for wi, week in enumerate(weeks):
        month = dt.date.fromisoformat(week[0][0]).strftime("%b")
        if month != last_month and wi < len(weeks) - 2:
            if last_month is not None:
                s.text(left + wi * (cell + gap), top - 14, month, "body-400", 11, t["faint"])
            last_month = month
        for date, count in week:
            di = dt.date.fromisoformat(date).isoweekday() % 7  # Sunday first, like GitHub
            level = 0 if count == 0 else min(4, 1 + int(3.999 * math.sqrt(count / peak)))
            s.add(f'<rect class="cell" style="animation-delay:{wi * 14}ms" x="{n(left + wi * (cell + gap))}" '
                  f'y="{n(top + di * (cell + gap))}" width="{cell}" height="{cell}" rx="2.5" fill="{t["heat"][level]}"/>')
    ly = top + 7 * (cell + gap) + 16
    lx = W - pad - Font.get("body-400").width("More", 11) - 6 - 5 * (cell + gap) + gap
    s.text(lx - 10, ly + cell - 2.5, "Less", "body-400", 11, t["faint"], anchor="end")
    for i, c in enumerate(t["heat"]):
        s.add(f'<rect x="{n(lx + i * (cell + gap))}" y="{n(ly)}" width="{cell}" height="{cell}" rx="2.5" fill="{c}"/>')
    s.text(lx + 5 * (cell + gap) + 6, ly + cell - 2.5, "More", "body-400", 11, t["faint"])

    # Languages: one series, so every bar takes the same hue; values stay in text ink.
    ltop = ly + 52
    s.add(f'<rect x="{pad}" y="{n(ltop - 30)}" width="{W - pad * 2}" height="1" fill="{t["border"]}"/>')
    s.text(pad, ltop, "Languages in public repositories", "body-500", 13.5, t["text"])
    langs = st["languages"][:6]
    total = sum(v for _, v in st["languages"]) or 1
    cols, col_gap = 3, 40
    col_w = (W - pad * 2 - col_gap * (cols - 1)) / cols
    name_w, value_w = 92, 52
    bar_w = col_w - name_w - value_w
    for i, (name, size) in enumerate(langs):
        share = size / total
        cx = pad + (i % cols) * (col_w + col_gap)
        cy = ltop + 32 + (i // cols) * 34
        s.text(cx, cy, name, "body-400", 13, t["text"])
        s.text(cx + col_w, cy, f"{share * 100:.1f}%", "body-500", 13, t["muted"], anchor="end")
        s.add(f'<rect x="{n(cx + name_w)}" y="{n(cy - 7)}" width="{n(bar_w)}" height="6" rx="3" fill="{t["track"]}"/>')
        s.add(f'<rect x="{n(cx + name_w)}" y="{n(cy - 7)}" width="{n(max(6, bar_w * share))}" '
              f'height="6" rx="3" fill="{t["gold"]}"/>')

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    s.text(W - pad, H - 18, f"Updated {stamp} by GitHub Actions", "mono-500", 10, t["faint"], anchor="end", ls=.6)
    save(f"stats-{theme}.svg", s)


# --------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stats", action="store_true", help="refresh the GitHub activity card")
    ap.add_argument("--stats-only", action="store_true", help="only refresh the GitHub activity card")
    args = ap.parse_args()

    stats = fetch_stats() if (args.stats or args.stats_only) else None
    for theme in THEMES:
        if not args.stats_only:
            build_header(theme)
            for key, num, title, caption in SECTIONS:
                build_section(theme, key, num, title, caption)
            for p in PROJECTS:
                build_card(theme, p)
            build_stack(theme)
            for key, label, slug, primary in BUTTONS:
                build_button(theme, key, label, slug, primary)
            build_footer(theme)
        if stats:
            build_stats(theme, stats)
    print(f"wrote {len(list(OUT.glob('*.svg')))} SVGs to {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
