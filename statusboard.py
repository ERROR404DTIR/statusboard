#!/usr/bin/env python3
"""statusboard - check URLs and render an animated SVG status card. Zero dependencies."""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse
from xml.sax.saxutils import escape

THEMES = {
    "dark": dict(bg="#0d1117", line="#30363d", text="#e6edf3", sub="#8b949e", up="#3fb950", warn="#d29922", down="#f85149", track="#21262d"),
    "light": dict(bg="#ffffff", line="#d0d7de", text="#1f2328", sub="#656d76", up="#1a7f37", warn="#9a6700", down="#cf222e", track="#eaeef2"),
}
FONT = "-apple-system,Segoe UI,Helvetica,Arial,sans-serif"
DEMO = [
    {"name": "Website", "url": "example.com", "up": True, "code": 200, "ms": 112},
    {"name": "API", "url": "api.example.com", "up": True, "code": 200, "ms": 286},
    {"name": "Docs", "url": "docs.example.com", "up": True, "code": 200, "ms": 640},
    {"name": "Legacy", "url": "old.example.com", "up": False, "code": 0, "ms": None},
]


def norm(url):
    return url if "://" in url else "https://" + url


def check(target, timeout):
    name, url = target
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(norm(url), headers={"User-Agent": "statusboard/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception:
        return {"name": name, "url": url, "up": False, "code": 0, "ms": None}
    ms = round((time.perf_counter() - t0) * 1000)
    return {"name": name, "url": url, "up": 200 <= code < 400, "code": code, "ms": ms}


def load_targets(urls, path):
    out = []
    lines = list(urls)
    if path:
        with open(path, encoding="utf-8") as fh:
            lines += [ln.strip() for ln in fh]
    for ln in lines:
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split(None, 1)
        if len(parts) == 2:
            out.append((parts[0], parts[1].strip()))
        else:
            out.append((urlparse(norm(parts[0])).netloc or parts[0], parts[0]))
    return out


def render(results, theme="dark", title="Service status"):
    c = THEMES[theme]
    n = len(results)
    W, head, rowh, foot = 560, 64, 38, 30
    H = head + rowh * n + foot
    up = sum(r["up"] for r in results)
    ok = up == n
    main = c["up"] if ok else (c["warn"] if up else c["down"])
    label = "All systems operational" if ok else f"{up}/{n} operational"
    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}" role="img" aria-label="{escape(title)}">',
        f'<title>{escape(title)}</title>',
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="{c["bg"]}" stroke="{c["line"]}"/>',
        f'<circle cx="28" cy="32" r="6" fill="{main}"/>',
        f'<circle cx="28" cy="32" r="6" fill="none" stroke="{main}" stroke-width="2"><animate attributeName="r" values="6;16" dur="2s" repeatCount="indefinite"/><animate attributeName="opacity" values=".8;0" dur="2s" repeatCount="indefinite"/></circle>',
        f'<text x="48" y="30" font-size="16" font-weight="700" fill="{c["text"]}">{escape(title)}</text>',
        f'<text x="48" y="48" font-size="12" fill="{main}">{label}</text>',
    ]
    for i, r in enumerate(results):
        y = head + i * rowh + rowh / 2
        col = c["up"] if r["up"] else c["down"]
        if r["up"] and r["ms"] is not None and r["ms"] >= 400:
            col = c["warn"]
        p.append(f'<line x1="20" y1="{y - rowh / 2}" x2="{W - 20}" y2="{y - rowh / 2}" stroke="{c["line"]}" stroke-opacity=".5"/>')
        if r["up"]:
            p.append(f'<circle cx="28" cy="{y}" r="5" fill="{col}"/>')
        else:
            p.append(f'<circle cx="28" cy="{y}" r="5" fill="{col}"><animate attributeName="opacity" values="1;.2;1" dur="1s" repeatCount="indefinite"/></circle>')
        p.append(f'<text x="48" y="{y + 4}" font-size="13" fill="{c["text"]}">{escape(r["name"])}</text>')
        if r["up"]:
            bw = max(4, min(r["ms"], 1000) / 1000 * 160)
            p.append(f'<rect x="270" y="{y - 3}" width="160" height="6" rx="3" fill="{c["track"]}"/>')
            p.append(f'<rect x="270" y="{y - 3}" width="0" height="6" rx="3" fill="{col}"><animate attributeName="width" from="0" to="{bw:.0f}" begin="{i * 0.12:.2f}s" dur=".9s" fill="freeze"/></rect>')
            p.append(f'<text x="{W - 24}" y="{y + 4}" font-size="12" text-anchor="end" fill="{c["sub"]}">{r["ms"]} ms</text>')
        else:
            p.append(f'<text x="{W - 24}" y="{y + 4}" font-size="12" font-weight="700" text-anchor="end" fill="{col}">DOWN</text>')
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    p.append(f'<text x="{W - 24}" y="{H - 10}" font-size="10" text-anchor="end" fill="{c["sub"]}">updated {stamp}</text>')
    p.append("</svg>\n")
    return "\n".join(p)


def main():
    ap = argparse.ArgumentParser(prog="statusboard", description="Check URLs and draw an animated SVG status card.")
    ap.add_argument("urls", nargs="*", help="URLs, or 'Name URL' pairs")
    ap.add_argument("-f", "--file", help="targets file: one 'Name URL' (or URL) per line, # for comments")
    ap.add_argument("-o", "--out", default="status.svg")
    ap.add_argument("-t", "--theme", choices=sorted(THEMES), default="dark")
    ap.add_argument("--title", default="Service status")
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--json", action="store_true", help="print results as JSON")
    ap.add_argument("--demo", action="store_true", help="render sample data (no network)")
    a = ap.parse_args()
    if a.demo:
        results = DEMO
    else:
        targets = load_targets(a.urls, a.file)
        if not targets:
            ap.error("give at least one URL or --file")
        with ThreadPoolExecutor(max_workers=min(16, len(targets))) as ex:
            results = list(ex.map(lambda t: check(t, a.timeout), targets))
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(render(results, a.theme, a.title))
    if a.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{'UP  ' if r['up'] else 'DOWN'} {r['name']:<24} {r['code'] or '-':>4} {str(r['ms']) + ' ms' if r['ms'] is not None else ''}")
        print(f"wrote {a.out}")
    return 0 if a.demo or all(r["up"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
