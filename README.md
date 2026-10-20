# Claude Account Switcher

A small macOS menu bar plugin for people who use more than one Claude Code account. It shows each account's plan usage and lets you switch the active account with one click.

```
✦ work 18%                                      <- menu bar: active account, weekly usage
──────────────────────────────────────────
✓ work       session 35% · week 18%
      session resets Oct 20 12:39 · week resets Oct 23 02:59
  personal   session 0%  · week 22%
      week resets Oct 25 05:59
  team       token expired, open Claude once with this account
──────────────────────────────────────────
  Refresh
```

- Session (5-hour) and weekly usage for every account, refreshed every 5 minutes
- Orange above 50%, red above 80%
- Click an account to make it active for VS Code and for new terminals

It is a single Python script for [SwiftBar](https://github.com/swiftbar/SwiftBar). It uses only the Python standard library.

## How it works

Claude Code keeps everything for an account (login, history, settings, memory) in one config directory, chosen with the `CLAUDE_CONFIG_DIR` environment variable. One directory per account gives you separate accounts that can even run at the same time.

The plugin:

1. **Finds accounts** by looking for `~/.claude-*` directories that contain a logged-in `.claude.json`. The menu name is the part of the email before the `@`.
2. **Reads each account's token** from the macOS Keychain entry `Claude Code-credentials-<sha256(dir)[:8]>`, which is where Claude Code stores it.
3. **Fetches usage** from `https://api.anthropic.com/api/oauth/usage`, the endpoint behind the `/usage` command.
4. **Switches accounts** by writing the chosen directory to:
   - the `CLAUDE_CONFIG_DIR` entry in VS Code's `claudeCode.environmentVariables` setting
   - `~/.claude-active`, which your shell reads when it starts

Tokens never leave your machine except in requests to `api.anthropic.com`.

## Requirements

- macOS
- Python 3 at `/usr/bin/python3`. It comes with the Xcode Command Line Tools: `xcode-select --install`
- [SwiftBar](https://github.com/swiftbar/SwiftBar)

## Setup

### 1. Give each account its own config directory

Log in once per account, each with its own directory. The directory name must start with `~/.claude-`:

```sh
CLAUDE_CONFIG_DIR=~/.claude-work claude      # then /login with your work account
CLAUDE_CONFIG_DIR=~/.claude-personal claude  # then /login with your personal account
```

The default `~/.claude` directory is not picked up. Give that account its own `~/.claude-*` directory too.

### 2. Install SwiftBar and the plugin

```sh
brew install --cask swiftbar
mkdir -p ~/.config/swiftbar/plugins
curl -fsSL https://raw.githubusercontent.com/berkayvuran/claude-account-switcher/main/claude-accounts.5m.py \
  -o ~/.config/swiftbar/plugins/claude-accounts.5m.py
chmod +x ~/.config/swiftbar/plugins/claude-accounts.5m.py
defaults write com.ameba.SwiftBar PluginDirectory "$HOME/.config/swiftbar/plugins"
open -a SwiftBar
```

The `5m` in the file name is the refresh interval. Rename the file to `claude-accounts.1m.py` to refresh every minute.

### 3. Let your shell follow the active account

Add this line to `~/.zshrc` (or `~/.bashrc`), using your own default directory:

```sh
export CLAUDE_CONFIG_DIR="$(cat ~/.claude-active 2>/dev/null || echo ~/.claude-work)"
```

Terminals opened after a switch start with the new account. Terminals that are already open keep the account they started with.

### 4. VS Code

You don't need to set anything up. On the first switch the plugin adds the setting below, or updates it if it already exists:

```json
"claudeCode.environmentVariables": [
    { "name": "CLAUDE_CONFIG_DIR", "value": "/Users/you/.claude-work" }
]
```

After a switch, run **Developer: Reload Window** in VS Code to restart the extension with the new account.

If your `settings.json` has comments and no entry yet, the plugin cannot add one safely. In that case only the terminal is switched and a notification tells you so. Add the entry once by hand and later switches will work.

## Configuration

At the top of `claude-accounts.5m.py`:

| Setting | Default | Purpose |
|---|---|---|
| `ACCOUNTS` | `[]` (auto-discover) | Set fixed names and order, e.g. `[("work", f"{HOME}/.claude-work")]` |
| `VSCODE_SETTINGS` | VS Code user settings | Point it at another editor's `settings.json`, e.g. Cursor's |
| `ACTIVE_FILE` | `~/.claude-active` | File the shell reads |

## Limitations

- **The usage endpoint is undocumented.** It is the one Claude Code's `/usage` command uses, and it may change without notice. If the percentages disappear after a Claude Code update, that is the likely cause.
- **Expired tokens are not refreshed.** Claude Code refreshes a token when you use that account. Until then the menu shows `token expired`.
- **VS Code needs a manual Reload Window** after each switch.
- **macOS only**, because tokens are read from the Keychain.

## License

MIT
