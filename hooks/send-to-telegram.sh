#!/bin/bash
# Claude Code Stop hook - sends response back to Telegram
# Hybrid approach: Try transcript first (original), fall back to tmux capture
# This handles cases where transcript only contains "thinking" blocks

# Use CLAUDE_DIR if set, otherwise default to $HOME/.claude
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"

# Debug logging for troubleshooting (with rotation to prevent disk exhaustion)
DEBUG_LOG="$CLAUDE_DIR/telegram_hook_debug.log"
MAX_DEBUG_LINES=1000

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$DEBUG_LOG"
    # Simple rotation: keep last N lines
    tail -n "$MAX_DEBUG_LINES" "$DEBUG_LOG" > "${DEBUG_LOG}.tmp" 2>/dev/null && \
        mv "${DEBUG_LOG}.tmp" "$DEBUG_LOG"
}

# Cleanup on exit
cleanup() {
    rm -f "$TMPFILE" 2>/dev/null
}
trap cleanup EXIT

# Get bot token from environment, then from token file, then fallback
if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ "$TELEGRAM_BOT_TOKEN" = "YOUR_BOT_TOKEN_HERE" ]; then
    TOKEN_FILE="$CLAUDE_DIR/telegram_bot_token"
    if [ -f "$TOKEN_FILE" ]; then
        TELEGRAM_BOT_TOKEN=$(cat "$TOKEN_FILE")
    else
        TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN_HERE"
    fi
fi

INPUT=$(cat)
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path')
CHAT_ID_FILE="$CLAUDE_DIR/telegram_chat_id"
PENDING_FILE="$CLAUDE_DIR/telegram_pending"

# Only respond to Telegram-initiated messages
[ ! -f "$PENDING_FILE" ] && exit 0

log "Hook started"

PENDING_TIME=$(cat "$PENDING_FILE" 2>/dev/null)
NOW=$(date +%s)
[ -z "$PENDING_TIME" ] || [ $((NOW - PENDING_TIME)) -gt 600 ] && rm -f "$PENDING_FILE" && exit 0
[ ! -f "$CHAT_ID_FILE" ] || [ ! -f "$TRANSCRIPT_PATH" ] && rm -f "$PENDING_FILE" && exit 0

# Validate and read chat ID (must be numeric)
CHAT_ID=$(cat "$CHAT_ID_FILE")
case "$CHAT_ID" in
    ''|*[!0-9-]*)
        log "ERROR: Invalid chat ID format"
        rm -f "$PENDING_FILE"
        exit 0
        ;;
esac

LAST_USER_LINE=$(grep -n '"type":"user"' "$TRANSCRIPT_PATH" | tail -1 | cut -d: -f1)
[ -z "$LAST_USER_LINE" ] && rm -f "$PENDING_FILE" && exit 0

TMPFILE=$(mktemp)
SOURCE="unknown"

# Method 1: Try transcript (original approach)
# Extract text content from transcript
tail -n "+$LAST_USER_LINE" "$TRANSCRIPT_PATH" | \
  grep '"type":"assistant"' | \
  jq -rs '[.[].message.content[] | select(.type == "text") | .text] | join("\n\n")' > "$TMPFILE" 2>> "$DEBUG_LOG"

# Check if we got meaningful content from transcript
STRIPPED=$(sed 's/^[[:space:]]*//; s/[[:space:]]*$//' "$TMPFILE")
if [ -n "$STRIPPED" ] && [ "$STRIPPED" != "null" ]; then
    SOURCE="transcript"
    log "Response found in transcript"
else
    # Method 2: Fall back to tmux capture
    log "No text in transcript, trying tmux capture"

    # Wait for tmux to update (increased wait time)
    sleep 1

    # Use TMUX_SESSION from environment if set, default to "claude"
    TMUX_SESSION="${TMUX_SESSION:-claude}"
    TMUX_OUTPUT=$(tmux capture-pane -t "$TMUX_SESSION" -S - -p 2>/dev/null || echo "")

    log "Tmux capture: $(echo "$TMUX_OUTPUT" | wc -l) lines captured"

    if [ -n "$TMUX_OUTPUT" ]; then
        # Extract only the LAST complete response from tmux
        # Filter UI noise: lines with UI symbols, timing info, tool invocations, or separator blocks
        echo "$TMUX_OUTPUT" | grep -vE '^[[:space:]]*(✽|✻|✢|⏵|↓|↑|·|✶)[[:space:]]|(✽|✻|✢|⏵|✶)· [0-9]+m [0-9]+s|(running stop hooks|Computing|Cooked|Crunched|thought for|thinking|tokens?)|^[[:space:]]*─+[[:space:]]*$' | awk '
        BEGIN {
            count = 0
        }
        {
            lines[++count] = $0
        }
        END {
            # Find both prompts first, then extract content between them
            final_prompt = 0
            prev_prompt = 0

            # Find final prompt (going backwards from end)
            for (i = count; i >= 1; i--) {
                if (lines[i] ~ /^[[:space:]]*❯/) {
                    final_prompt = i
                    break
                }
            }

            # Find previous prompt (before the final one)
            for (i = final_prompt - 1; i >= 1; i--) {
                if (lines[i] ~ /^[[:space:]]*❯/) {
                    prev_prompt = i
                    break
                }
            }

            # Find first response marker AFTER the previous prompt
            first_marker = 0
            for (i = prev_prompt + 1; i < final_prompt; i++) {
                if (lines[i] ~ /^[[:space:]]*●[[:space:]]/) {
                    first_marker = i
                    break
                }
            }

            if (first_marker == 0) {
                exit
            }

            # Extract from first_marker to final_prompt-1 (in forward order)
            response = ""
            for (i = first_marker; i < final_prompt; i++) {
                line = lines[i]
                # Strip markers and leading spaces
                gsub(/^[[:space:]]*●[[:space:]]*/, "", line)
                gsub(/^[[:space:]]*❯.*/, "", line)
                gsub(/^[[:space:]]*/, "", line)

                # Skip empty lines, separators, and additional noise patterns
                if (length(line) == 0) {
                    continue
                }
                # Skip separator blocks
                if (line ~ /^[─░▒▓█━═│┌┐└┘├┤┬┴┼▌▐]+$/) {
                    continue
                }
                # Skip tool invocation headers (Bash(...), Read(...), etc.)
                if (line ~ /^(Bash|Read|Write|Edit|Grep|Glob|Task|TodoWrite|AskUserQuestion|Skill|EnterPlanMode|ExitPlanMode|WebSearch|mcp__|NotebookEdit)\(/) {
                    continue
                }
                # Skip path indicators (⎿ /path)
                if (line ~ /^⎿\//) {
                    continue
                }
                # Skip git hash lines (format: "5d29c08 [main]")
                if (line ~ /^[a-f0-9]{7,8}\s*\[.*\]$/) {
                    continue
                }
                # Skip collapse indicators (… +N lines (ctrl+o to expand))
                if (line ~ /^… \+[0-9]+ lines.*\(ctrl\+o to expand\)/) {
                    continue
                }
                # Skip lines with UI state keywords
                if (line ~ /(Symbioting|Photosynthesizing|Tomfoolering|working stop hooks|Computing|Cooked|Crunched|thinking)\.\.\./) {
                    continue
                }

                # Keep this line
                if (length(response) > 0) {
                    response = response "\n" line
                } else {
                    response = line
                }
            }

            if (length(response) > 0) {
                print response
            }
        }
        ' > "$TMPFILE"

        log "After extraction: $(wc -l < "$TMPFILE") lines"

        STRIPPED=$(sed 's/^[[:space:]]*//; s/[[:space:]]*$//' "$TMPFILE")
        if [ -n "$STRIPPED" ]; then
            SOURCE="tmux"
            log "Response captured from tmux"
        fi
    fi
fi

# If still no content, exit gracefully
if [ -z "$STRIPPED" ]; then
    log "INFO: No response found in transcript or tmux"
    rm -f "$PENDING_FILE"
    exit 0
fi

SIZE=$(wc -c < "$TMPFILE")
log "Sending response (${SIZE} bytes, source: $SOURCE)"

# Capture stderr for debugging
python3 - "$TMPFILE" "$CHAT_ID" "$TELEGRAM_BOT_TOKEN" 2>> "$DEBUG_LOG" << 'PYEOF'
import sys, re, json, urllib.request

tmpfile, chat_id, token = sys.argv[1], sys.argv[2], sys.argv[3]
with open(tmpfile) as f:
    text = f.read().strip()

# Exit gracefully if no content
if not text or text == "null":
    print("DEBUG: No content to send", file=sys.stderr)
    sys.exit(0)

# Truncate if too long
if len(text) > 4000:
    text = text[:4000] + "\n..."

def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

# Apply formatting
blocks, inlines = [], []
text = re.sub(r'```(\w*)\n?(.*?)```', lambda m: (blocks.append((m.group(1) or '', m.group(2))), f"\x00B{len(blocks)-1}\x00")[1], text, flags=re.DOTALL)
text = re.sub(r'`([^`\n]+)`', lambda m: (inlines.append(m.group(1)), f"\x00I{len(inlines)-1}\x00")[1], text)
text = esc(text)
text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', text)

for i, (lang, code) in enumerate(blocks):
    text = text.replace(f"\x00B{i}\x00", f'<pre><code class="language-{lang}">{esc(code.strip())}</code></pre>' if lang else f'<pre>{esc(code.strip())}</pre>')
for i, code in enumerate(inlines):
    text = text.replace(f"\x00I{i}\x00", f'<code>{esc(code)}</code>')

def send(txt, mode=None):
    data = {"chat_id": chat_id, "text": txt}
    if mode:
        data["parse_mode"] = mode
    try:
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", json.dumps(data).encode(), {"Content-Type": "application/json"})
        response = json.loads(urllib.request.urlopen(req, timeout=10).read())
        if response.get("ok"):
            print(f"DEBUG: Message sent successfully (HTML: {bool(mode)})", file=sys.stderr)
            return True
        else:
            print(f"DEBUG: Telegram API error: {response}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"DEBUG: Send failed with exception: {e}", file=sys.stderr)
        return False

# Try HTML first, fallback to plain text
success = send(text, "HTML")
if not success:
    print("DEBUG: HTML send failed, trying plain text", file=sys.stderr)
    with open(tmpfile) as f:
        plain_text = f.read()[:4096]
        success = send(plain_text, None)

# Exit with error if both attempts failed
sys.exit(0 if success else 1)
PYEOF

# Check if Python script succeeded
PYTHON_EXIT=$?
if [ $PYTHON_EXIT -eq 0 ]; then
    log "Response sent successfully to $CHAT_ID"
    # Only delete pending file on success (allows potential retry if failed)
    rm -f "$PENDING_FILE"
else
    log "ERROR: Failed to send response to Telegram (see stderr above for details)"
    # Keep pending file (though no retry mechanism exists yet)
fi

# Always exit 0 - don't fail the Stop hook
exit 0
