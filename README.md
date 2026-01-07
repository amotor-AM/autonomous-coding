# Autonomous Coding Agent Template

A flexible framework for building long-running autonomous coding agents using the Claude Agent SDK. This template implements a two-agent pattern (initializer + coding agent) that can build complete applications over multiple sessions.

## Features

- **Two-Agent Pattern**: Initializer plans the project, coding agent implements iteratively
- **Session Persistence**: Progress is saved via `feature_list.json` and git commits
- **Auto-Continue**: Automatically resumes after each session with fresh context
- **Rate Limit Handling**: Gracefully handles API rate limits with auto-retry
- **Security Sandbox**: OS-level isolation with bash command allowlist
- **Hybrid Mode**: Use Opus for planning, Sonnet for implementation

## Quick Start

### 1. Install Dependencies

```bash
# Install Claude Code CLI
npm install -g @anthropic-ai/claude-code

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Set Up Authentication

**Option A: API Key (recommended for automation)**
```bash
# Copy the example and add your key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

# Obtaining your API Key
########################
# Claude code uses an API key to authenticate with the Anthropic API.
# You can get an API key from the Anthropic Console: https://console.anthropic.com/
# BUT you will be charged per token used. This can easily add up to $100 - $200 per day.
# 
# Option B: Claude OAuth. This repo has been "hacked" to use OAuth natively instead of an API Key. Once you have installed claude code sign in with:
claude  # Opens browser for OAuth login

# Once signed in you can obtain your OAuth token by typing the following:
claude setup-token

# Simply copy and paste the token into the .env file with the following line:
export ANTHROPIC_API_KEY='your-api-key-here'


### 3. Customize Your Project

Edit `prompts/app_spec.txt` to define your application:
- Project name and description
- Technology stack
- Core features
- Database schema
- UI layout
- Success criteria

### 4. Run the Agent

```bash
# Start a new project
python autonomous_agent_demo.py

# Use hybrid mode (Opus planning + Sonnet coding)
python autonomous_agent_demo.py --hybrid

# Limit iterations for testing
python autonomous_agent_demo.py --max-iterations 5
```

## How It Works

### Two-Agent Pattern

1. **Initializer Agent (Session 1)**
   - Reads `app_spec.txt`
   - Creates `feature_list.json` with testable features
   - Sets up project structure
   - Initializes git repository

2. **Coding Agent (Sessions 2+)**
   - Picks up where the previous session left off
   - Implements features one by one
   - Marks completed features in `feature_list.json`
   - Commits each feature to git

### Session Management

- Each session runs with a fresh context window
- Progress persists via `feature_list.json` and git commits
- Agent auto-continues between sessions (3 second delay)
- Press `Ctrl+C` to pause; run the same command to resume

## Configuration

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--project-dir` | Directory for the project | `./generations/app` |
| `--max-iterations` | Max agent iterations | Unlimited |
| `--model` | Claude model to use | `claude-sonnet-4-5-20250929` |
| `--hybrid` | Use Opus for planning, Sonnet for coding | Off |
| `--spec-file` | Custom spec file name | `app_spec.txt` |
| `--list-specs` | List available spec files | - |

### Customizing Prompts

| File | Purpose |
|------|---------|
| `prompts/app_spec.txt` | Define your application requirements |
| `prompts/initializer_prompt.md` | How the initializer agent plans the project |
| `prompts/coding_prompt.md` | How the coding agent implements features |

### Adjusting Feature Count

Edit `prompts/initializer_prompt.md` to change the target feature count:
- **Quick demos**: 20-30 features
- **Full applications**: 50-100 features
- **Comprehensive builds**: 100-200 features

### Modifying Security

Edit `security.py` to add or remove commands from `ALLOWED_COMMANDS`.

## Security Model

This template uses defense-in-depth security:

1. **OS-level Sandbox**: Bash commands run in an isolated environment
2. **Filesystem Restrictions**: File operations restricted to project directory
3. **Bash Allowlist**: Only permitted commands can execute:
   - File inspection: `ls`, `cat`, `head`, `tail`, `wc`, `grep`
   - File operations: `cp`, `mkdir`
   - Node.js: `npm`, `node`
   - Version control: `git`
   - Process management: `ps`, `lsof`, `sleep`, `pkill` (dev processes only)

## Project Structure

```
autonomous-coding/
├── autonomous_agent_demo.py  # Main entry point
├── agent.py                  # Agent session logic
├── client.py                 # Claude SDK client configuration
├── security.py               # Bash command allowlist and validation
├── progress.py               # Progress tracking utilities
├── prompts.py                # Prompt loading utilities
├── prompts/
│   ├── app_spec.txt          # Your application specification
│   ├── initializer_prompt.md # First session prompt
│   └── coding_prompt.md      # Continuation session prompt
├── .env.example              # Environment variable template
└── requirements.txt          # Python dependencies
```

## Generated Project Structure

After running, your project directory will contain:

```
generations/app/
├── feature_list.json         # Test cases (source of truth)
├── app_spec.txt              # Copied specification
├── init.sh                   # Environment setup script
├── claude-progress.txt       # Session progress notes
├── .claude_settings.json     # Security settings
└── [application files]       # Generated application code
```

## Running the Generated Application

```bash
cd generations/app

# Run the setup script created by the agent
./init.sh

# Or manually (typical for Node.js apps)
npm install
npm run dev
```

## Timing Expectations

> **Note: Autonomous coding takes time!**

- **First session (initialization)**: 5-15 minutes to generate the feature list
- **Subsequent sessions**: 5-15 minutes each, depending on feature complexity
- **Full application**: Many hours across multiple sessions

The agent may appear to hang during complex operations—watch for `[Tool: ...]` output to confirm it's working.

## Troubleshooting

**"Appears to hang on first run"**
This is normal. The initializer agent is generating detailed test cases. Watch for `[Tool: ...]` output. This usually takes like 30 minutes at first.

**"Command blocked by security hook"**
The agent tried to run a command not in the allowlist. Add it to `ALLOWED_COMMANDS` in `security.py` if needed.

**"No authentication found"**
Either export `ANTHROPIC_API_KEY` or run `claude` to authenticate via OAuth.

**"Rate limited"**
The agent will automatically wait and retry. This is normal with Pro subscriptions.

## License

MIT License - Use this template for any project.
