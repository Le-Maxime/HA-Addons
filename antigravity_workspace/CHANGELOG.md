# Changelog



## 1.5.3

- Added each subagent's model next to its name in the subagent rows above the prompt and in `/agents` (hidden on narrow terminals), with the full model and effort in a subagent's detail view, and a `model` field on each `subagents` entry in the status line JSON; `/agents` now shows a single `Tip: Press enter on a subagent to view details.` line instead of repeating `[view details]` on every row.
- Added the `PLUGIN_ROOT` and `PLUGIN_DATA` environment variables to hook commands that come from a plugin, pointing to the plugin's folder and its persistent data folder, so plugin hooks can use files bundled with the plugin and keep state between runs; `agy plugin validate` no longer warns that these variables are not set for hooks.
- Changed the error shown when Vertex AI reports that the selected model does not exist or that your Google Cloud project cannot use it, which now reads `The requested model was not found, or your project does not have access to it.` instead of the raw API error.
- Improved the plugin sign-in screen in `/plugin`, which now indents the sign-in link like the surrounding text and sets it apart with a blank line, no longer underlines trailing blank space in wrapped links, and uses the plugin's display name from `plugin.json`, such as `Canva` instead of `canva`.
- Improved `agy plugin validate` so the `category` field in `plugin.json` is accepted instead of reported as an unknown field, with a warning only when it is not a non-empty string.
- Improved auto-generated conversation titles, which now keep abbreviations and acronyms from your request as written instead of guessing what they stand for.
- Fixed `agy plugin uninstall`, `agy plugin enable`, `agy plugin disable`, and uninstalling from `/plugin` failing for plugins installed as symbolic links, such as plugins installed from Antigravity, or for plugins whose names contain spaces or symbols such as `c++-tools`, and `agy plugin list` shows symlinked plugins again.
- Fixed agent turns failing with `http2: timeout awaiting response headers` when the model took more than 60 seconds to start responding, which are now retried.
- Fixed every model request failing with a 404 error when an enterprise model gateway URL ended in `/v1beta`, even though the model list loaded; a trailing `/v1beta` in the gateway URL is now ignored.
- Fixed the agent's requests to sign in to a plugin being dropped from the conversation, so when a plugin needs a sign-in the CLI now shows a line such as `⚠ The <plugin> plugin needs you to sign in. Open /plugin to sign in.`
- Fixed the agent's file tools mishandling text that is not UTF-8, mostly on Windows: reading a UTF-16 or legacy code-page file now returns its text instead of treating it as binary, edits keep a file's UTF-8 byte order mark or UTF-16 encoding, and PowerShell scripts (`.ps1`, `.psm1`, `.psd1`) with non-ASCII text are written with a UTF-8 byte order mark so Windows PowerShell 5.1 reads them correctly.
- Fixed a message sent during a turn with the `Send Immediately` queued-messages mode briefly disappearing from the conversation and reappearing when it arrived just as the turn ended.
- Fixed hooks receiving a placeholder or empty model name when the session uses a custom model, so hooks now get the name of the model actually in use.
- Fixed files larger than the remote read limit being silently cut off in `--remote-agent` sessions, which now load in full up to 20 MiB and report an error above that instead of showing partial content.
- Fixed `agy acp` sessions exiting before the agent backend finished shutting down when the client closed the connection, which could interrupt saving conversation data.
- Fixed a security issue where a command run in the terminal sandbox could change environment state later loaded by persistent terminal commands run outside the sandbox, and hardened persistent terminal IDs against path traversal.
- Fixed garbled characters in tool-call summaries when the CLI shortens file paths that contain non-ASCII characters.
- Fixed paths that share a prefix with your home directory, such as `/home/alice` when your home is `/home/al`, showing with a mangled `~` prefix in the `/context` file list and the keybindings reset hint.

## 1.5.2

- Added skills from the cloud plugins you connected with `/plugin` to `--remote-agent` sessions, so they now appear in the `/` menu and can be typed at the start of a message, `/skills` lists them grouped by plugin under `Remote agent skills`, and `/skills reload` lists them again.
- Changed the default for macOS Option-key shortcuts such as `alt+m`, which now work out of the box without setting Option to act as Alt in your terminal, where previously pressing them did nothing or typed a character such as `µ`; set `AGY_CLI_MAC_OPTION_AS_ALT=0` to go back to the old behavior.
- Changed `--dangerously-skip-permissions` so commands on the built-in list of protected commands are no longer approved automatically and go through the usual checks, while every other command still runs without asking.
- Changed `--dangerously-skip-permissions` and plugin agents set to auto-allow so they no longer approve terminal commands or file access outside the workspace when your Gemini Enterprise administrator requires those to be reviewed, and headless runs now deny such requests instead.
- Changed the prompt shown when the agent asks for access to a file outside the workspace, which now reads `Allow access to this file?` and offers to always allow or deny that one path for the conversation or in `settings.json`, instead of turning on access to everything outside the workspace.
- Improved `agy -p` runs so they no longer make a background model request to generate a conversation title that print mode never shows.
- Improved Remote Control connections, which now retry a brief network or server error while setting up a new connection instead of dropping it.
- Improved `agy plugin validate` so an unknown field under `extensions["com.google.antigravity"]` in `plugin.json` is reported as a warning that the field is ignored instead of an error, and the plugin's other extension settings are still checked.
- Improved protection against malicious plugins: `agy plugin` import, install, uninstall, enable, and disable now reject plugin names that are not safe file names with `invalid plugin name`, and refuse to write outside the plugins folder or through symbolic links, so an imported plugin can no longer overwrite other configuration files such as `mcp_config.json`.
- Improved protection against untrusted repositories: plugins and skills listed in a workspace's `.agents/plugins.json` or `.agents/skills.json` now load only from inside the workspace or its repository root, and entries that point elsewhere through absolute paths, `../`, or symbolic links are skipped.
- Fixed subagents stalling for about 60 seconds on file permissions under `--dangerously-skip-permissions`, so reads and writes outside the workspace now go through without a prompt, and headless `-p` runs with the flag no longer wait on any remaining interaction, while your explicit deny rules still apply.
- Fixed signing in to an MCP server that uses OAuth failing with `Invalid PKCE code_verifier` when the server reconnected during sign-in, such as when `/mcp` reloaded servers or a new turn started, so the sign-in link you already opened keeps working.
- Fixed MCP tools that declare their own `explanation`, `toolSummary`, `toolAction`, or `waitForPreviousTools` parameter receiving calls without that argument, so the value the model sends now reaches the tool.
- Fixed the agent re-running a failed turn in a rapid loop when messages were queued at the moment it hit an error, so queued messages now wait for your next message.
- Fixed the `/` menu listing the commands and skills of a default agent instead of those of the agent the session actually runs, so in `agy acp` sessions it now shows that session's agent, including a custom agent's commands.
- Fixed adding PDFs, other binary files, or files larger than about 8 MB to a remote project from `/projects` in `--remote-agent` sessions, which failed and now upload successfully.
- Fixed voice dictation in Chinese and Japanese showing a space between every character in the live draft before the final transcript arrived, and fullwidth Latin words losing the spaces between them.

## 1.0.0
- Начальный релиз Antigravity Agent Workspace.
- Интеграция с Google Antigravity CLI (`agy`).
- Web-терминал Ingress на базе `ttyd` и постоянной сессии `tmux`.
- Готовое виртуальное окружение Python 3 с Telethon, Pyrogram, tgcrypto, Pandas, Aiohttp.
- Персистентное хранилище в `/data` для сессий Telegram и истории агента.
- Поддержка архитектур `amd64` и `aarch64`.
