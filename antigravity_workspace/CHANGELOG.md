# Changelog


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
