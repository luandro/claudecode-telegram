#!/bin/bash
# Claude Code Stop hook - sends response back to Telegram
# Combines transcript parsing with tmux capture fallback

DEBUG_LOG="${CLAUDE_DIR:-$HOME/.claude}/telegram_hook_debug.log"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$DEBUG_LOG"
}

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

PENDING_TIME=$(cat "$PENDING_FILE" 2>/dev/null)
NOW=$(date +%s)
[ -z "$PENDING_TIME" ] || [ $((NOW - PENDING_TIME)) -gt 600 ] && rm -f "$PENDING_FILE" && exit 0
[ ! -f "$CHAT_ID_FILE" ] && rm -f "$PENDING_FILE" && exit 0

CHAT_ID=$(cat "$CHAT_ID_FILE")
log "Hook started"

# Find tmux session and socket
TMUX_SESSION="${TMUX_SESSION:-claude}"
TMUX_SOCKET_PATH="${TMUX_SOCKET_PATH:-}"

tmux_cmd() {
    if [ -n "$TMUX_SOCKET_PATH" ] && [ -S "$TMUX_SOCKET_PATH" ]; then
        tmux -S "$TMUX_SOCKET_PATH" "$@" 2>/dev/null
    else
        tmux "$@" 2>/dev/null
    fi
}

# Function to extract response from tmux (fallback method)
extract_from_tmux() {
    # Capture visible pane content
    local RAW_OUTPUT
    RAW_OUTPUT=$(tmux_cmd capture-pane -t "$TMUX_SESSION" -p -S -100 2>/dev/null)
    [ -z "$RAW_OUTPUT" ] && return 1

    local LINE_COUNT=$(echo "$RAW_OUTPUT" | wc -l)
    log "Tmux capture: $LINE_COUNT lines captured"

    # Extract the response: everything after the last user prompt until the next prompt or end
    # Claude's response appears after ">" prompt lines and before next ">" or tool output
    local RESPONSE
    RESPONSE=$(echo "$RAW_OUTPUT" | awk '
        BEGIN { in_response = 0; response = ""; last_prompt_line = 0 }
        # Track prompt lines (user input starts with >)
        /^> / || /^❯ / || /^\$ / {
            if (in_response && response != "") {
                # We hit a new prompt while collecting response, stop here
                exit
            }
            last_prompt_line = NR
            in_response = 0
            next
        }
        # Skip tool/status lines
        /^[[:space:]]*[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]/ { next }
        /^[[:space:]]*├/ { next }
        /^[[:space:]]*│.*Tool/ { next }
        /^[[:space:]]*│.*Read/ { next }
        /^[[:space:]]*│.*Write/ { next }
        /^[[:space:]]*│.*Edit/ { next }
        /^[[:space:]]*│.*Bash/ { next }
        /^[[:space:]]*│.*running/ { next }
        /^[[:space:]]*│.*completed/ { next }
        /^[[:space:]]*└/ { next }
        # Skip empty lines at start
        NR == last_prompt_line + 1 && /^[[:space:]]*$/ { next }
        # Start capturing after prompt
        NR > last_prompt_line && last_prompt_line > 0 {
            in_response = 1
            if (response != "") response = response "\n"
            response = response $0
        }
        END { print response }
    ')

    # Clean up: remove leading/trailing whitespace and ANSI codes
    RESPONSE=$(echo "$RESPONSE" | sed 's/\x1b\[[0-9;]*m//g' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

    local EXTRACTED_LINES=$(echo "$RESPONSE" | wc -l)
    log "After extraction: $EXTRACTED_LINES lines"

    [ -z "$RESPONSE" ] && return 1
    echo "$RESPONSE"
}

# Function to extract response from transcript
extract_from_transcript() {
    [ ! -f "$TRANSCRIPT_PATH" ] && return 1

    local LAST_USER_LINE
    LAST_USER_LINE=$(grep -n '"type":"user"' "$TRANSCRIPT_PATH" | tail -1 | cut -d: -f1)
    [ -z "$LAST_USER_LINE" ] && return 1

    local MAX_WAIT=15
    local WAIT_COUNT=0
    local RESPONSE=""

    while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
        RESPONSE=$(tail -n "+$LAST_USER_LINE" "$TRANSCRIPT_PATH" 2>/dev/null | \
            grep '"type":"assistant"' | \
            jq -rs '[.[].message.content[] | select(.type == "text") | .text] | join("\n\n")' 2>/dev/null)

        # Check if we got meaningful content (not empty, not null, not just whitespace)
        if [ -n "$RESPONSE" ] && [ "$RESPONSE" != "null" ] && [ -n "$(echo "$RESPONSE" | tr -d '[:space:]')" ]; then
            echo "$RESPONSE"
            return 0
        fi

        WAIT_COUNT=$((WAIT_COUNT + 1))
        sleep 0.5
    done

    return 1
}

TMPFILE=$(mktemp)
RESPONSE_SOURCE=""

# Try transcript first
if CONTENT=$(extract_from_transcript); then
    echo "$CONTENT" > "$TMPFILE"
    RESPONSE_SOURCE="transcript"
    log "Response extracted from transcript"
else
    log "No text in transcript, trying tmux capture"
    # Fallback to tmux capture
    if CONTENT=$(extract_from_tmux); then
        echo "$CONTENT" > "$TMPFILE"
        RESPONSE_SOURCE="tmux"
        log "Response captured from tmux"
    fi
fi

# Check if we got any content
if [ ! -s "$TMPFILE" ]; then
    log "INFO: No response found in transcript or tmux"
    rm -f "$TMPFILE" "$PENDING_FILE"
    exit 0
fi

CONTENT_SIZE=$(wc -c < "$TMPFILE")
log "Sending response ($CONTENT_SIZE bytes, source: $RESPONSE_SOURCE)"

python3 - "$TMPFILE" "$CHAT_ID" "$TELEGRAM_BOT_TOKEN" "$DEBUG_LOG" << 'PYEOF'
import sys, re, json, urllib.request

tmpfile, chat_id, token, debug_log = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

def log(msg):
    with open(debug_log, 'a') as f:
        f.write(f"DEBUG: {msg}\n")

with open(tmpfile) as f:
    text = f.read().strip()

if not text or text == "null":
    sys.exit(0)

# Truncate if too long
if len(text) > 4000:
    text = text[:4000] + "\n..."

def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

# Process markdown formatting
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
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return result.get("ok")
    except Exception as e:
        log(f"Send error: {e}")
        return False

html_ok = send(text, "HTML")
log(f"Message sent successfully (HTML: {html_ok})")

if not html_ok:
    # Fallback to plain text
    with open(tmpfile) as f:
        plain_ok = send(f.read()[:4096])
        if plain_ok:
            log("Fallback to plain text succeeded")
        else:
            log("Both HTML and plain text sends failed")
PYEOF

log "Response sent successfully to $CHAT_ID"
rm -f "$TMPFILE" "$PENDING_FILE"
exit 0
