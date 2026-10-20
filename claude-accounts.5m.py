#!/usr/bin/python3
# <swiftbar.title>Claude Accounts</swiftbar.title>
# <swiftbar.version>1.0.0</swiftbar.version>
# <swiftbar.desc>Switch Claude Code accounts and see plan usage from the macOS menu bar</swiftbar.desc>
# <swiftbar.dependencies>python3</swiftbar.dependencies>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
# <swiftbar.hideSwiftBar>true</swiftbar.hideSwiftBar>
"""Menu bar plugin for running several Claude Code accounts side by side.

Each account lives in its own CLAUDE_CONFIG_DIR (for example ~/.claude-work).
Claude Code stores that account's OAuth token in the macOS Keychain under
"Claude Code-credentials-<first 8 hex chars of sha256(config dir)>". Usage is
read from the same (undocumented) endpoint the /usage command uses.

Switching accounts updates two places:
  - the CLAUDE_CONFIG_DIR entry in VS Code's claudeCode.environmentVariables
  - ~/.claude-active, which your shell reads (see README)

Tokens are only ever sent to api.anthropic.com.
"""

import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

HOME = os.path.expanduser("~")

# Leave empty to auto-discover every ~/.claude-* directory that has a logged-in
# account. To pin names or order, list them explicitly:
#   ACCOUNTS = [("work", f"{HOME}/.claude-work"), ("personal", f"{HOME}/.claude-personal")]
ACCOUNTS = []

ACTIVE_FILE = f"{HOME}/.claude-active"
VSCODE_SETTINGS = f"{HOME}/Library/Application Support/Code/User/settings.json"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
SELF = os.path.abspath(__file__)
ENV_RE = r'("CLAUDE_CONFIG_DIR"\s*,\s*"value"\s*:\s*")([^"]*)(")'


def discover():
    found = []
    for d in sorted(glob.glob(f"{HOME}/.claude-*")):
        if not os.path.isdir(d):
            continue
        try:
            with open(os.path.join(d, ".claude.json")) as f:
                email = json.load(f).get("oauthAccount", {}).get("emailAddress")
        except (OSError, ValueError):
            continue
        if email:
            found.append((email.split("@")[0], d))
    return found


def active_dir():
    try:
        with open(VSCODE_SETTINGS) as f:
            m = re.search(ENV_RE, f.read())
            if m:
                return m.group(2)
    except OSError:
        pass
    try:
        with open(ACTIVE_FILE) as f:
            return f.read().strip()
    except OSError:
        return None


def set_vscode(config_dir):
    """Point VS Code's Claude Code extension at config_dir. Returns True on success."""
    try:
        with open(VSCODE_SETTINGS) as f:
            text = f.read()
    except OSError:
        return False
    new_text, n = re.subn(ENV_RE, lambda m: m.group(1) + config_dir + m.group(3), text)
    if not n:
        # No entry yet: add one, but only if the file is plain JSON (no comments).
        try:
            data = json.loads(text)
        except ValueError:
            return False
        env = data.setdefault("claudeCode.environmentVariables", [])
        env.append({"name": "CLAUDE_CONFIG_DIR", "value": config_dir})
        new_text = json.dumps(data, indent=4) + "\n"
    with open(VSCODE_SETTINGS, "w") as f:
        f.write(new_text)
    return True


def notify(msg):
    msg = msg.replace('"', "'")
    subprocess.run(["/usr/bin/osascript", "-e", f'display notification "{msg}" with title "Claude"'])


def switch(config_dir, name):
    with open(ACTIVE_FILE, "w") as f:
        f.write(config_dir + "\n")
    if set_vscode(config_dir):
        notify(f"Active account: {name}. Run 'Reload Window' in VS Code; new terminals pick it up automatically.")
    else:
        notify(f"Active account: {name} (terminal only, VS Code settings could not be updated).")


def credentials(config_dir):
    service = "Claude Code-credentials-" + hashlib.sha256(config_dir.encode()).hexdigest()[:8]
    out = subprocess.run(
        ["/usr/bin/security", "find-generic-password", "-s", service, "-w"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout).get("claudeAiOauth")
    except ValueError:
        return None


def usage(config_dir):
    cred = credentials(config_dir)
    if not cred or not cred.get("accessToken"):
        return {"error": "not logged in"}
    if cred.get("expiresAt") and cred["expiresAt"] / 1000 < time.time():
        return {"error": "token expired, open Claude once with this account"}
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": "Bearer " + cred["accessToken"],
        "anthropic-beta": "oauth-2025-04-20",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except Exception as e:  # network error, 401 etc. are shown in the menu
        return {"error": f"unavailable ({e.__class__.__name__})"}


def pct(block):
    if not block or block.get("utilization") is None:
        return None
    return round(block["utilization"])


def reset_text(block):
    if not block or not block.get("resets_at"):
        return ""
    return datetime.fromisoformat(block["resets_at"]).astimezone().strftime("%b %d %H:%M")


def color(p):
    if p is None:
        return ""
    return " color=#d9534f" if p >= 80 else (" color=#e69500" if p >= 50 else "")


def render(accounts):
    if not accounts:
        print("Claude | sfimage=sparkle")
        print("---")
        print("No accounts found in ~/.claude-*")
        print("See the README to add one | href=https://github.com/berkayvuran/claude-account-switcher")
        return

    active = active_dir()
    with ThreadPoolExecutor(len(accounts)) as ex:
        results = list(ex.map(lambda a: usage(a[1]), accounts))

    active_name, active_week = "?", None
    for (name, d), u in zip(accounts, results):
        if d == active:
            active_name, active_week = name, pct(u.get("seven_day"))
    title = active_name + (f" {active_week}%" if active_week is not None else "")
    print(f"{title} | sfimage=sparkle{color(active_week)}")
    print("---")

    for (name, d), u in zip(accounts, results):
        mark = "✓ " if d == active else "    "
        action = f"bash={SELF} param1=switch param2={d} param3={name} terminal=false refresh=true"
        if "error" in u:
            print(f"{mark}{name}  ·  {u['error']} | {action}")
            continue
        s, w = pct(u.get("five_hour")), pct(u.get("seven_day"))
        s_txt = "-" if s is None else f"{s}%"
        w_txt = "-" if w is None else f"{w}%"
        worst = max([x for x in (s, w) if x is not None], default=None)
        print(f"{mark}{name}   session {s_txt} · week {w_txt} | {action} font=Menlo{color(worst)}")
        details = []
        if reset_text(u.get("five_hour")):
            details.append("session resets " + reset_text(u.get("five_hour")))
        if reset_text(u.get("seven_day")):
            details.append("week resets " + reset_text(u.get("seven_day")))
        if details:
            print(f"      {' · '.join(details)} | size=11 color=gray")

    print("---")
    print("Refresh | refresh=true")
    print(f"Updated {datetime.now().strftime('%H:%M')} | size=11 color=gray")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "switch":
        switch(sys.argv[2], sys.argv[3])
    else:
        render(ACCOUNTS or discover())
