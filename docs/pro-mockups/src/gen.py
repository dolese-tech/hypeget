"""Builds the Pro UI mockup pages (HTML) from the app's real CSS. Run: python3 gen.py"""
import math, random

UI = "../../../hypeget/ui"
random.seed(7)

def svg_icon(d):
    return f'<svg class="ico" viewBox="0 0 24 24"><path d="{d}"/></svg>'

I = {
    "all": "M4 6h16M4 12h16M4 18h16", "zip": "M6 3h9l3 3v15H6zM11 3v4M11 9v2M11 13v2",
    "doc": "M6 3h8l4 4v14H6zM9 12h6M9 16h6", "music": "M9 18V6l10-2v12M9 18a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0zM19 16a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0",
    "prog": "M4 5h16v11H4zM9 20h6M12 16v4", "video": "M4 6h12v12H4zM16 10l5-3v10l-5-3",
    "queue": "M4 6h16M4 12h10M4 18h7M17 14l4 4-4 4", "moon": "M20 14A8 8 0 1 1 10 4a7 7 0 0 0 10 10z",
    "list": "M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01", "chart": "M4 20V10M10 20V4M16 20v-7M22 20H2",
    "shield": "M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z", "bell": "M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 21h4", "key": "M14 10a4 4 0 1 0-3.5 4L9 16v3h3v-2h2v-2l.5-.5A4 4 0 0 0 14 10z", "globe": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18", "grab": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18",
}

def nav(label, count, icon=None, sel=False, live=False):
    ic = svg_icon(I[icon]) if icon else ""
    return (f'<button class="nav-item{" sel" if sel else ""}"><span class="lbl">{ic}{label}</span>'
            f'<span class="count{" live" if live else ""}">{count}</span></button>')

def spark(vals, w=180, h=34, color="var(--blue)"):
    mx = max(vals)
    pts = [(i * w / (len(vals) - 1), h - 2 - v / mx * (h - 6)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return (f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none"><polygon points="0,{h} {line} {w},{h}" fill="{color}" opacity=".13"/>'
            f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.6"/></svg>')

def sidebar(sel="all", stats_sel=False):
    return f"""
    <aside class="sidebar" id="sidebar">
      <h3>CATEGORIES</h3>
      {nav("All downloads", 14, "all", sel == "all")}
      {nav("Compressed", 3, "zip")}{nav("Documents", 2, "doc")}{nav("Music", 1, "music")}
      {nav("Programs", 2, "prog")}{nav("Video", 6, "video", sel == "video")}
      <h3 class="second">QUEUES &amp; LISTS</h3>
      {nav("Main queue", 4, "queue", live=True)}
      {nav("Night · 02:00", 3, "moon")}
      {nav("Physics lectures", "8/12", "list", sel == "playlist")}
      {nav("Statistics", "", "chart", stats_sel)}
      <div class="side-card"><div class="k">TODAY</div><div class="v">6.8 GB</div>
        <div class="s">23 files · avg 7.4 MB/s</div>
        {spark([2,3,2,4,6,5,7,9,8,6,7,10,12,11,9,12,14,13,15,12])}</div>
    </aside>"""

def titlebar():
    return f"""
  <header class="titlebar">
    <img class="logo" src="{UI}/icons/logo-small.svg" width="22" height="22" alt="">
    <div class="title">HyperGet Downloader<span class="pro-pill"><svg viewBox="0 0 10 10"><path d="M5 0l1.3 3.4L10 3.8 7.2 6.1 8.1 10 5 7.9 1.9 10l.9-3.9L0 3.8l3.7-.4z" fill="currentColor"/></svg>PRO</span></div>
    <span class="lic">Licensed to Dolese Tech · 2 of 3 PCs</span>
    <div class="win-controls" style="display:flex">
      <button><svg viewBox="0 0 12 12"><path d="M1 6h10" stroke="currentColor" stroke-width="1.2"/></svg></button>
      <button><svg viewBox="0 0 12 12"><rect x="1.5" y="1.5" width="9" height="9" fill="none" stroke="currentColor" stroke-width="1.1"/></svg></button>
      <button class="close"><svg viewBox="0 0 12 12"><path d="M1.5 1.5l9 9M10.5 1.5l-9 9" stroke="currentColor" stroke-width="1.2"/></svg></button>
    </div>
  </header>"""

MENUS = "".join(f'<div class="menu"><button>{m}</button></div>' for m in ["Tasks", "File", "Downloads", "View", "Help", "Account"])

def tool(label, d, cls=""):
    return f'<button class="tool {cls}"><span class="ic"><svg viewBox="0 0 24 24"><path d="{d}"/></svg></span>{label}</button>'

TOOLBAR = f"""
  <div class="toolbar">
    {tool("Add URL","M12 5v14M5 12h14")}{tool("Resume","M7 4.5v15l12-7.5z")}{tool("Pause","M9 5v14M15 5v14")}
    {tool("Stop all","M6 6h12v12H6z")}{tool("Delete","M4 7h16M10 11v6M14 11v6M5.5 7l1 12a2 2 0 0 0 2 2h7a2 2 0 0 0 2-2l1-12M9 7V4h6v3")}
    {tool("Scheduler","M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2")}{tool("Queue","M4 6h16M4 12h16M4 18h11")}
    {tool("Grabber","M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18")}
    {tool("Statistics","M4 20V10M10 20V4M16 20v-7M22 20H2")}
    {tool("Options","M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7zM12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8")}
    <div class="spacer"></div>
    <div class="speed-limit menu"><span>Speed limit</span><button class="select-btn"><span>Unlimited</span><i class="caret"></i></button></div>
  </div>"""

THUMBS = ["linear-gradient(135deg,#0ea5e9,#1e3a8a)", "linear-gradient(135deg,#f59e0b,#7c2d12)",
          "linear-gradient(135deg,#22c55e,#14532d)", "linear-gradient(135deg,#ec4899,#4c1d95)",
          "linear-gradient(135deg,#64748b,#0f172a)"]

def row(name, host, size, prog, label, st="downloading", speed="—", eta="—", added="Today", badge="ZIP",
        sel=False, chips="", thumb=None, cls="", segs=None):
    icon = f'<span class="thumb" style="background:{thumb}"></span>' if thumb else f'<span class="badge">{badge}</span>'
    bar = (f'<div class="segmap-mini">{segs}</div>' if segs else f'<div class="bar"><i style="width:{prog}%"></i></div>')
    muted = "" if st == "downloading" else " muted"
    return f"""<div class="grid-row row {cls}{" sel" if sel else ""}">
      <div class="cell-name">{icon}<div class="name-wrap"><div class="fname">{name}{chips}</div><div class="fhost">{host}</div></div></div>
      <div class="cell c-size">{size}</div>
      <div class="prog st-{st}">{bar}<div class="label">{label}</div></div>
      <div class="cell c-speed{muted}">{speed}</div><div class="cell col-eta{muted}">{eta}</div><div class="cell col-added">{added}</div></div>"""

def mini_segs(done, active, total=40):
    return "".join('<i class="d"></i>' if i < done else ('<i class="a"></i>' if i < done + active else "<i></i>") for i in range(total))

THEAD = """<div class="grid-row thead"><div>File name</div><div>Size</div><div>Progress</div><div>Speed</div><div class="col-eta">Time left</div><div class="col-added">Added</div></div>"""

def speed_graph(w=420, h=92):
    vals, v = [], 4.0
    for i in range(60):
        v = max(1.5, min(13, v + random.uniform(-1.1, 1.5) + (0.25 if i < 20 else 0)))
        vals.append(v)
    mx = 14
    pts = [(i * w / 59, h - 4 - val / mx * (h - 12)) for i, val in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    grid = "".join(f'<line x1="0" x2="{w}" y1="{y}" y2="{y}" stroke="var(--border)" stroke-dasharray="3 3"/>' for y in (h * .25, h * .5, h * .75))
    labels = "".join(f'<text x="{w-2}" y="{y-3}" text-anchor="end" font-size="9.5" fill="var(--text-4)">{t}</text>' for y, t in ((h*.25,"10 MB/s"),(h*.5,"5 MB/s")))
    return (f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none">{grid}{labels}'
            f'<defs><linearGradient id="gf" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="var(--blue)" stop-opacity=".28"/><stop offset="1" stop-color="var(--blue)" stop-opacity="0"/></linearGradient></defs>'
            f'<polygon points="0,{h} {line} {w},{h}" fill="url(#gf)"/><polyline points="{line}" fill="none" stroke="var(--blue)" stroke-width="1.8"/>'
            f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="3.2" fill="var(--blue)"/></svg>')

def segmap(n=96, done=58):
    out = []
    for i in range(n):
        if i < done or (i % 12 < 7 and i < 84): c = "d"
        elif i % 12 in (7, 8) and i < 96: c = "a"
        else: c = ""
        out.append(f'<i class="{c}"></i>')
    return "".join(out)

def details_pro(title, url, kv, legend):
    rows = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in kv)
    return f"""<section class="card details pro">
      <div style="min-width:0"><div class="d-title">{title}</div><div class="d-url">{url}</div><dl class="kv">{rows}</dl></div>
      <div class="graph-wrap"><div class="conn-head"><span>SPEED · LAST 60 S</span><span class="actions"><button class="link-btn">Pause</button></span></div>
        {speed_graph()}<div class="legend">{legend}</div></div>
      <div style="min-width:0"><div class="conn-head"><span>FILE MAP · 8 CONNECTIONS</span></div>
        <div class="segmap">{segmap()}</div>
        <div class="seg-note"><span>Done</span><span class="a">Downloading</span><span class="w">Waiting</span></div></div>
    </section>"""

def page(theme, body, overlay="", title="HyperGet Pro mockup"):
    return f"""<!doctype html><html lang="en" data-theme="{theme}"><head><meta charset="utf-8"><title>{title}</title>
<link rel="stylesheet" href="{UI}/css/tokens.css"><link rel="stylesheet" href="{UI}/css/app.css"><link rel="stylesheet" href="pro.css"></head>
<body><div class="frame"><div class="app">{titlebar()}<nav class="menubar">{MENUS}</nav>{TOOLBAR}
<div class="body">{body.split('<footer class="statusbar">')[0]}</div><footer class="statusbar">{body.split('<footer class="statusbar">')[1]}{overlay}</div></div></body></html>"""

def statusbar(extra=""):
    return f"""<footer class="statusbar"><span><b>3</b> active</span><span>Total speed <b>18.4 MB/s</b></span><span>Queue: <b>4</b> waiting</span>
      {extra}<span class="right">Scheduler 02:00–07:00</span></footer>"""

def main_rows(sel_first=True):
    return "".join([
        row("Ubuntu-24.04.2-desktop-amd64.iso", "releases.ubuntu.com", "5.9 GB", 61, "61% · 8 connections", speed="11.2 MB/s", eta="3m 28s", badge="ISO", sel=sel_first, chips='<span class="chip">8×</span>', segs=mini_segs(24, 4)),
        row("Physics Lecture 7 — Thermodynamics", "youtube.com · Physics lectures", "412 MB", 34, "34% · Downloading", speed="5.1 MB/s", eta="54s", thumb=THUMBS[0], chips='<span class="chip q">1080p</span><span class="chip g">SRT</span>'),
        row("Blender-4.3-windows-x64.msi", "download.blender.org", "389 MB", 100, "Complete · SHA-256 verified ✓", st="complete", badge="MSI", chips='<span class="chip g">Safe</span>'),
        row("Afro Beats Mix 2026.mp3", "youtube.com", "96 MB", 100, "Complete", st="complete", badge="MP3", added="Yesterday"),
        row("Dataset_Q3_2026.zip", "files.example.org", "2.4 GB", 47, "Link expired · Refreshing from page…", st="paused", badge="ZIP", added="Yesterday", chips='<span class="chip o">Auto-fix</span>'),
        row("Annual-Report-2025.pdf", "dolese.tech", "8.2 MB", 0, "Queued · Night queue", st="queued", badge="PDF", added="Yesterday"),
        row("Physics Lecture 8 — Entropy", "youtube.com · Physics lectures", "~ 440 MB", 0, "Queued · Physics lectures", st="queued", thumb=THUMBS[3], chips='<span class="chip q">1080p</span>', added="Yesterday"),
    ])

# ---------------------------------------------------------------- 1. main, light
s1 = page("light", sidebar("all") + f"""
<main class="main">
  <form class="search"><input type="text" placeholder="Search downloads or paste a link to add..."><button type="button" class="btn-primary">Add URL</button></form>
  <div></div>
  <section class="card table-card">{THEAD}<div class="tbody">{main_rows()}</div></section>
  {details_pro("Ubuntu-24.04.2-desktop-amd64.iso", "releases.ubuntu.com/24.04/ubuntu-24.04.2-desktop-amd64.iso",
     [("Downloaded","3.6 GB of 5.9 GB"),("Resume","Supported"),("Checksum","SHA-256 will be verified"),("Queue","Main queue"),("Save to","D:\\Downloads\\Programs")],
     "<span>Now <b>11.2 MB/s</b></span><span>Average <b>9.8 MB/s</b></span><span>Peak <b>13.1 MB/s</b></span>")}
</main>""" + statusbar('<span class="sb-chip b">Working hours · 1 MB/s from 08:00</span><span class="sb-chip">When done: Shut down</span>'))

# ---------------------------------------------------------------- 2. playlist, dark
pl_rows = row("Physics lectures — Prof. Mwakyusa", "youtube.com/playlist · 12 videos · 1080p · subtitles: Kiswahili", "5.0 GB", 58,
              "8 of 12 done · 2 downloading", speed="9.6 MB/s", eta="6m 10s", cls="group", badge="▾ 12", chips='<span class="chip q">PLAYLIST</span>')
names = ["Introduction & units", "Kinematics", "Newton's laws", "Work and energy", "Momentum", "Rotation", "Thermodynamics", "Entropy", "Waves", "Sound"]
for i, n in enumerate(names):
    if i < 6:
        pl_rows += row(f"{i+1:02d} · {n}", "1080p · MP4 · Kiswahili SRT", f"{380+i*13} MB", 100, "Complete", st="complete", thumb=THUMBS[i % 5], cls="child", added="Today")
    elif i < 8:
        pl_rows += row(f"{i+1:02d} · {n}", "1080p · MP4 · Kiswahili SRT", f"{410+i*7} MB", 34 + i * 6, f"{34+i*6}% · Downloading", speed=f"{4.1+i*.3:.1f} MB/s", eta=f"{70-i*5}s", thumb=THUMBS[i % 5], cls="child", sel=(i == 6))
    else:
        pl_rows += row(f"{i+1:02d} · {n}", "1080p · MP4", "~ 420 MB", 0, "Queued", st="queued", thumb=THUMBS[i % 5], cls="child")
s2 = page("dark", sidebar("playlist") + f"""
<main class="main">
  <form class="search"><input type="text" placeholder="Search downloads or paste a link to add..."><button type="button" class="btn-primary">Add URL</button></form>
  <div class="banner" style="grid-row:2"><span>All downloads finished in <b>Night queue</b>. Shutting down the computer in 42 s…</span><button class="btn">Cancel</button></div>
  <section class="card table-card">{THEAD}<div class="tbody">{pl_rows}</div></section>
  {details_pro("07 · Thermodynamics", "youtube.com/watch?v=Qm3x… · Physics lectures (7 of 12)",
     [("Downloaded","148 MB of 436 MB"),("Quality","1080p · H.264 · MP4"),("Subtitles","Kiswahili (SRT)"),("Playlist","Physics lectures"),("Save to","D:\\Video\\Physics lectures")],
     "<span>Now <b>5.9 MB/s</b></span><span>Average <b>5.2 MB/s</b></span><span>Playlist <b>9.6 MB/s</b></span>")}
</main>""" + statusbar('<span class="sb-chip">When done: Shut down</span>'))

# ---------------------------------------------------------------- 3. video quality picker
def qcard(r, small, t, sz, sel=False, tag=None):
    tg = f'<span class="tag{" p" if tag in ("4K","HDR") else ""}">{tag}</span>' if tag else ""
    return f'<div class="qcard{" sel" if sel else ""}">{tg}<div class="r">{r}<small>{small}</small></div><div class="t">{t}</div><div class="sz">{sz}</div></div>'

quality = f"""
<div class="overlay"><div class="dialog xl">
  <header><h2>Download video</h2><button class="x">×</button></header>
  <div class="tabsbar"><span class="on">Video</span><span>Audio</span><span>Playlist (12)</span></div>
  <div class="content" style="padding-top:16px">
    <div class="vid"><div class="poster"><div class="play"><i><svg width="14" height="14" viewBox="0 0 24 24"><path d="M7 4.5v15l12-7.5z" fill="#111"/></svg></i></div><span class="dur">24:18</span></div>
      <div><h3>Physics Lecture 7 — Thermodynamics explained simply</h3>
        <div class="meta">Prof. Mwakyusa · youtube.com · 1.2M views</div>
        <div class="tags"><span class="chip">Up to 4K</span><span class="chip q">60 fps</span><span class="chip g">Subtitles: 3 languages</span><span class="chip o">Part of a playlist · 12 videos</span></div>
        <div class="callout" style="margin-top:12px">Tip: open the <b>Playlist</b> tab to get all 12 lectures with the same settings.</div></div></div>
    <div class="field"><label>Quality</label><div class="qgrid">
      {qcard("2160p","4K","VP9 · MKV · 60 fps","≈ 2.9 GB",tag="4K")}
      {qcard("1440p","2K","VP9 · MKV · 60 fps","≈ 1.3 GB")}
      {qcard("1080p","Full HD","H.264 · MP4 · 60 fps","≈ 436 MB",sel=True,tag="BEST FIT")}
      {qcard("720p","HD","H.264 · MP4","≈ 212 MB")}
      {qcard("480p","","H.264 · MP4","≈ 118 MB")}
      {qcard("360p","","H.264 · MP4","≈ 74 MB")}
      {qcard("Audio","M4A","AAC · 129 kbps","≈ 23 MB")}
      {qcard("MP3","","192 kbps · tagged","≈ 34 MB")}
    </div></div>
    <div class="opts3">
      <div class="field"><label>Subtitles</label><select><option>Kiswahili</option></select>
        <div class="toggle"><span class="sw on"></span>Embed in the video</div></div>
      <div class="field"><label>Save to</label><input type="text" value="D:\\Video\\Physics lectures">
        <div class="toggle"><span class="sw on"></span>Remember for youtube.com</div></div>
      <div class="field"><label>When</label><div class="seg"><span class="on">Now</span><span>Main queue</span><span>Night</span></div>
        <div class="toggle"><span class="sw"></span>Cut a part (start / end time)</div></div>
    </div>
  </div>
  <footer><span class="left">File name: Physics Lecture 7 — Thermodynamics_1080p.mp4</span><button class="btn">Cancel</button><button class="btn-primary">Download 436 MB</button></footer>
</div></div>"""
s3 = page("light", sidebar("video") + f"""
<main class="main"><form class="search"><input type="text"><button type="button" class="btn-primary">Add URL</button></form><div></div>
  <section class="card table-card">{THEAD}<div class="tbody">{main_rows(False)}</div></section></main>""" + statusbar(), quality)

# ---------------------------------------------------------------- 4. upgrade / plans
plans = """
<div class="overlay"><div class="dialog xl">
  <header><h2>Upgrade to HyperGet Pro</h2><button class="x">×</button></header>
  <div class="content" style="padding-top:2px">
    <p style="margin:0 0 20px;color:var(--text-3);font-size:13px">Free stays free forever. Pro adds the tools for people who download every day.</p>
    <div class="plans">
      <div class="plan"><h4>Free</h4><div class="price">TSh 0</div><div class="alt">For everyone</div>
        <ul><li>Up to 8 connections per file</li><li>Pause, resume, queue, scheduler</li><li>Browser extension</li><li>Video up to 1080p</li>
          <li class="no">Playlists and channels</li><li class="no">4K, subtitles, MP3</li><li class="no">Speed rules, when-done actions</li><li class="no">Link refresh, saved logins</li></ul>
        <button class="btn">Your current plan</button></div>
      <div class="plan best"><span class="ribbon">MOST POPULAR</span><h4>Pro · 1 year</h4><div class="price">TSh 25,000 <small>/ year</small></div><div class="alt">≈ $10 · 3 PCs · all updates</div>
        <ul><li>Everything in Free</li><li>Up to 32 connections per file</li><li>Playlists, channels, 4K &amp; 8K</li><li>Subtitles, MP3, cut a part</li>
          <li>Speed rules &amp; when-done actions</li><li>Expired-link refresh, saved logins</li><li>Checksum &amp; virus scan</li><li>Statistics, priority support</li></ul>
        <button class="btn-primary">Get Pro</button></div>
      <div class="plan"><h4>Pro · Lifetime</h4><div class="price">TSh 60,000</div><div class="alt">≈ $24 · pay once · 3 PCs</div>
        <ul><li>Everything in Pro</li><li>All future versions</li><li>Move licence to a new PC</li><li>Early access to new features</li></ul>
        <button class="btn">Buy lifetime</button></div>
    </div>
    <div class="pay">Pay with <span class="m">M-Pesa</span><span class="m">Tigo Pesa</span><span class="m">Airtel Money</span><span class="m">Visa / Mastercard</span><span class="m">PayPal</span></div>
  </div>
  <footer><span class="left">Already paid? <a style="color:var(--blue);font-weight:600">Enter licence key</a> · 14-day money-back · Prices are examples</span><button class="btn">Maybe later</button></footer>
</div></div>"""
s4 = page("light", sidebar("all") + f"""
<main class="main"><form class="search"><input type="text"><button type="button" class="btn-primary">Add URL</button></form><div></div>
  <section class="card table-card">{THEAD}<div class="tbody">{main_rows(False)}</div></section></main>""" + statusbar(), plans)

# ---------------------------------------------------------------- 5. statistics
days = [("Mon", 3.1), ("Tue", 5.4), ("Wed", 2.2), ("Thu", 7.9), ("Fri", 6.1), ("Sat", 11.4), ("Sun", 6.8)]
W, H = 560, 200
bars = ""
for i, (d, v) in enumerate(days):
    bw = 46; x = 30 + i * (W - 40) / 7; bh = v / 12 * (H - 40)
    col = "var(--blue)" if d != "Sun" else "url(#pg)"
    bars += f'<rect x="{x:.0f}" y="{H-22-bh:.0f}" width="{bw}" height="{bh:.0f}" rx="5" fill="{col}" opacity="{1 if d=="Sun" else .82}"/>'
    bars += f'<text x="{x+bw/2:.0f}" y="{H-6}" text-anchor="middle" font-size="11" fill="var(--text-3)">{d}</text>'
    bars += f'<text x="{x+bw/2:.0f}" y="{H-28-bh:.0f}" text-anchor="middle" font-size="10.5" font-weight="600" fill="var(--text-2)">{v} GB</text>'
week = (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:200px"><defs><linearGradient id="pg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#7c3aed"/><stop offset="1" stop-color="#1d4ed8"/></linearGradient></defs>'
        + "".join(f'<line x1="20" x2="{W}" y1="{y}" y2="{y}" stroke="var(--border)" stroke-dasharray="3 3"/>' for y in (40, 86, 132)) + bars + "</svg>")
sites = [("youtube.com", 82, "18.2 GB", "var(--red)"), ("releases.ubuntu.com", 41, "9.1 GB", "var(--orange)"), ("drive.google.com", 27, "6.0 GB", "var(--green)"),
         ("download.blender.org", 12, "2.6 GB", "var(--blue)"), ("dolese.tech", 6, "1.3 GB", "var(--purple)")]
site_rows = "".join(f'<div class="hbar"><span>{s}</span><div class="bar"><i style="width:{p}%;background:{c}"></i></div><span class="n">{g}</span></div>' for s, p, g, c in sites)
types = [("Video", 58, "var(--purple)"), ("Programs", 21, "var(--blue)"), ("Compressed", 13, "var(--orange)"), ("Music", 5, "var(--green)"), ("Documents", 3, "var(--slate)")]
r, cx, cy, acc, arcs = 52, 70, 70, 0, ""
for n, p, c in types:
    a0, a1 = acc / 100 * 2 * math.pi, (acc + p) / 100 * 2 * math.pi; acc += p
    x0, y0, x1, y1 = cx + r * math.sin(a0), cy - r * math.cos(a0), cx + r * math.sin(a1), cy - r * math.cos(a1)
    arcs += f'<path d="M{x0:.1f},{y0:.1f} A{r},{r} 0 {1 if p > 50 else 0} 1 {x1:.1f},{y1:.1f}" stroke="{c}" stroke-width="20" fill="none"/>'
donut = (f'<div style="display:flex;gap:18px;align-items:center"><svg width="140" height="140" viewBox="0 0 140 140">{arcs}'
         f'<text x="70" y="68" text-anchor="middle" font-size="18" font-weight="700" fill="var(--text)">42.9</text><text x="70" y="85" text-anchor="middle" font-size="11" fill="var(--text-3)">GB this week</text></svg>'
         f'<div style="font-size:12.5px;display:grid;gap:6px">' + "".join(f'<span><i style="display:inline-block;width:9px;height:9px;border-radius:2px;background:{c};margin-right:7px"></i>{n} <b style="margin-left:4px">{p}%</b></span>' for n, p, c in types) + "</div></div>")
s5 = page("light", sidebar("none", stats_sel=True) + f"""
<main class="main">
  <form class="search"><input type="text" placeholder="Search downloads or paste a link to add..."><button type="button" class="btn-primary">Add URL</button></form>
  <div class="stats">
    <div class="kpis">
      <div class="card kpi"><div class="k">Downloaded this week</div><div class="v">42.9 GB</div><div class="d">▲ 18% vs last week</div></div>
      <div class="card kpi"><div class="k">Files</div><div class="v">137</div><div class="d n">4 failed · all retried OK</div></div>
      <div class="card kpi"><div class="k">Average speed</div><div class="v">8.6 MB/s</div><div class="d">5.4× faster than one connection</div></div>
      <div class="card kpi"><div class="k">Time saved</div><div class="v">3 h 12 min</div><div class="d">thanks to 8 connections</div></div>
    </div>
    <div class="two">
      <div class="card panel"><h4>Downloaded per day <div class="tabs"><span class="on">Week</span><span>Month</span><span>Year</span></div></h4>{week}</div>
      <div class="card panel"><h4>By type <span>this week</span></h4>{donut}</div>
    </div>
    <div class="two" style="grid-template-columns:1.6fr 1fr">
      <div class="card panel"><h4>Top sites <span>this week</span></h4>{site_rows}</div>
      <div class="card panel"><h4>Busiest hours <span>speed you get</span></h4>
        <div style="display:grid;grid-template-columns:repeat(12,1fr);gap:3px">{"".join(f'<i style="height:22px;border-radius:3px;background:color-mix(in srgb,var(--blue) {p}%,var(--track))"></i>' for p in [90,95,100,92,70,45,30,25,35,40,60,80,85,88,75,50,30,20,22,30,45,60,70,82])}</div>
        <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-3);margin-top:6px"><span>00:00</span><span>12:00</span><span>23:00</span></div>
        <div class="callout" style="margin-top:12px">Fastest between <b>00:00 and 04:00</b>. Move big files to the <b>Night queue</b>?</div></div>
    </div>
  </div>
</main>""" + statusbar())

# ---------------------------------------------------------------- 6. settings
settings = f"""
<div class="overlay"><div class="dialog lg" style="width:880px">
  <header><h2>Settings</h2><button class="x">×</button></header>
  <div class="settings">
    <nav>
      {nav("General", "", "all")}{nav("Connections", "", "grab")}<button class="nav-item sel"><span class="lbl">{svg_icon(I["chart"])}Speed rules</span><span class="count"></span></button>
      {nav("Video sites", "", "video")}{nav("Saved logins", "", "key")}{nav("Safety", "", "shield")}{nav("Browser", "", "prog")}
      {nav("Notifications", "", "bell")}{nav("Language", "Kiswahili", "globe")}
      <div style="height:1px;background:var(--border);margin:8px 4px"></div>
      <button class="nav-item"><span class="lbl">Licence<span class="pro-pill">PRO</span></span></button>
    </nav>
    <div class="pane">
      <h5>Speed rules</h5>
      <p style="margin:0 0 12px;font-size:12.5px;color:var(--text-3)">Keep the internet usable for others. The first rule that matches the current time wins.</p>
      <div class="rule"><span class="sw on"></span><div><div class="t">Working hours</div><div class="s">Others in the office need the line</div></div>
        <div class="week"><i class="on">M</i><i class="on">T</i><i class="on">W</i><i class="on">T</i><i class="on">F</i><i>S</i><i>S</i></div><b style="font-size:12.5px">08:00–17:00 · 1 MB/s</b></div>
      <div class="rule"><span class="sw on"></span><div><div class="t">Evening streaming</div><div class="s">Leave room for TV and calls</div></div>
        <div class="week"><i class="on">M</i><i class="on">T</i><i class="on">W</i><i class="on">T</i><i class="on">F</i><i class="on">S</i><i class="on">S</i></div><b style="font-size:12.5px">19:00–22:00 · 3 MB/s</b></div>
      <div class="rule"><span class="sw"></span><div><div class="t">Night bundle</div><div class="s">Cheap data from your provider</div></div>
        <div class="week"><i class="on">M</i><i class="on">T</i><i class="on">W</i><i class="on">T</i><i class="on">F</i><i class="on">S</i><i class="on">S</i></div><b style="font-size:12.5px">00:00–06:00 · Unlimited</b></div>
      <button class="btn" style="margin:4px 0 16px">+ Add rule</button>
      <h5>When all downloads finish</h5>
      <div class="seg"><span>Do nothing</span><span>Sleep</span><span class="on">Shut down</span><span>Exit HyperGet</span></div>
      <div class="toggle" style="margin-top:10px"><span class="sw on"></span>Wait 60 seconds and show a Cancel button first</div>
      <h5>Data cap</h5>
      <div class="row2"><div class="field"><label>Monthly limit</label><input type="text" value="50 GB"></div>
        <div class="field"><label>When reached</label><select><option>Pause and ask me</option></select></div></div>
      <div class="callout">Used this month: <b>31.4 GB of 50 GB</b> — resets on 1 December.</div>
    </div>
  </div>
  <footer><button class="btn">Cancel</button><button class="btn-primary">Save</button></footer>
</div></div>"""
s6 = page("light", sidebar("all") + f"""
<main class="main"><form class="search"><input type="text"><button type="button" class="btn-primary">Add URL</button></form><div></div>
  <section class="card table-card">{THEAD}<div class="tbody">{main_rows(False)}</div></section></main>""" + statusbar(), settings)

for name, html in [("1-main-pro", s1), ("2-playlist-dark", s2), ("3-video-quality", s3), ("4-upgrade-plans", s4), ("5-statistics", s5), ("6-settings", s6)]:
    open(f"{name}.html", "w").write(html)
print("ok")
