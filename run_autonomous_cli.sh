#!/bin/bash
# Autonomous Coding Agent - CLI Version
# Uses Claude CLI with Pro subscription OAuth
# Run: ./run_autonomous_cli.sh

set -e

PROJECT_DIR="./app/nvmercantile"
MAX_SESSIONS=500
DELAY_SECONDS=5

cd "$(dirname "$0")"

# Function to parse reset time from Claude's error message
# Handles formats like:
#   "resets 12pm"
#   "resets 3:30pm" 
#   "resets Jan 2, 2026, 8pm (America/Los_Angeles)"
parse_reset_time() {
    local error_msg="$1"
    local now_seconds=$(date +%s)
    
    # Try to extract full date format like "Jan 2, 2026, 8pm"
    if echo "$error_msg" | grep -qoE "resets [A-Za-z]+ [0-9]+, [0-9]+, [0-9]+:?[0-9]*[ap]m"; then
        local reset_str=$(echo "$error_msg" | grep -oE "resets [A-Za-z]+ [0-9]+, [0-9]+, [0-9]+:?[0-9]*[ap]m" | sed 's/resets //')
        # Remove commas for date parsing (change "Jan 2, 2026, 8pm" to "Jan 2 2026 8pm")
        reset_str=$(echo "$reset_str" | sed 's/,//g')
        # Parse with date command
        local reset_date=$(date -d "$reset_str" +%s 2>/dev/null)
        if [ -n "$reset_date" ] && [ "$reset_date" -gt "$now_seconds" ]; then
            local wait_seconds=$((reset_date - now_seconds + 60))
            echo $wait_seconds
            return
        fi
    fi
    
    # Try simpler format like "Jan 2, 8pm" (without year)
    if echo "$error_msg" | grep -qoE "resets [A-Za-z]+ [0-9]+, [0-9]+:?[0-9]*[ap]m"; then
        local reset_str=$(echo "$error_msg" | grep -oE "resets [A-Za-z]+ [0-9]+, [0-9]+:?[0-9]*[ap]m" | sed 's/resets //')
        local reset_date=$(date -d "$reset_str" +%s 2>/dev/null)
        if [ -n "$reset_date" ] && [ "$reset_date" -gt "$now_seconds" ]; then
            local wait_seconds=$((reset_date - now_seconds + 60))
            echo $wait_seconds
            return
        fi
    fi
    
    # Try simple time format like "12pm" or "3:30pm"
    if echo "$error_msg" | grep -qoE "resets [0-9]+:?[0-9]*[ap]m"; then
        local reset_time=$(echo "$error_msg" | grep -oE "resets [0-9]+:?[0-9]*[ap]m" | sed 's/resets //')
        local reset_date=$(date -d "today $reset_time" +%s 2>/dev/null)
        if [ -n "$reset_date" ]; then
            if [ "$reset_date" -lt "$now_seconds" ]; then
                reset_date=$(date -d "tomorrow $reset_time" +%s 2>/dev/null)
            fi
            local wait_seconds=$((reset_date - now_seconds + 60))
            echo $wait_seconds
            return
        fi
    fi
    
    # Fallback: return 0 to use default wait
    echo 0
}

# Function to format seconds as human readable
format_time() {
    local seconds=$1
    if [ $seconds -lt 60 ]; then
        echo "${seconds}s"
    elif [ $seconds -lt 3600 ]; then
        echo "$((seconds / 60))m"
    elif [ $seconds -lt 86400 ]; then
        local hours=$((seconds / 3600))
        local mins=$(((seconds % 3600) / 60))
        echo "${hours}h ${mins}m"
    else
        local days=$((seconds / 86400))
        local hours=$(((seconds % 86400) / 3600))
        echo "${days}d ${hours}h"
    fi
}

# Fallback: 24 hours if parsing fails (conservative)
FALLBACK_WAIT_SECONDS=86400

echo "========================================"
echo "  AUTONOMOUS CODING AGENT (CLI Mode)"
echo "========================================"
echo "Project: $PROJECT_DIR"
echo "Rate limit: Smart wait (parses reset time, no retry limit)"
echo ""

# Check claude is available
if ! command -v claude &> /dev/null; then
    echo "Error: claude CLI not found"
    echo "Install: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

echo "Checking authentication..."
echo ""

# Check if continuing or fresh start
if [ -f "$PROJECT_DIR/feature_list.json" ]; then
    FIRST_RUN=false
    PASSING=$(grep -c '"passes": true' "$PROJECT_DIR/feature_list.json" 2>/dev/null || echo "0")
    TOTAL=$(grep -c '"passes":' "$PROJECT_DIR/feature_list.json" 2>/dev/null || echo "0")
    echo "🔄 Continuing existing project"
    echo "   Progress: $PASSING / $TOTAL features passing"
else
    FIRST_RUN=true
    echo "📋 First run - will use initializer prompt"
fi
echo ""

# Main loop - NO RETRY LIMIT, runs forever until done or stopped
for ((session=1; session<=MAX_SESSIONS; session++)); do
    echo ""
    echo "========================================"
    echo "  SESSION $session"
    echo "========================================"
    
    # Determine prompt and model - MAX PLAN: Use Opus for everything
    if [ "$FIRST_RUN" = true ] && [ $session -eq 1 ]; then
        PROMPT_FILE="prompts/initializer_prompt.md"
        MODEL="opus"
        echo "📋 Using Opus for initialization"
    else
        PROMPT_FILE="prompts/coding_prompt.md"
        MODEL="opus"
        echo "🚀 Using Opus (Max plan)"
    fi
    
    if [ ! -f "$PROMPT_FILE" ]; then
        echo "Error: Prompt file not found: $PROMPT_FILE"
        exit 1
    fi
    PROMPT=$(cat "$PROMPT_FILE")
    
    echo "Running Claude CLI..."
    
    # Run claude from project directory
    pushd "$PROJECT_DIR" > /dev/null
    
    CLAUDE_CMD="claude -p --dangerously-skip-permissions --model $MODEL"
    [ $session -gt 1 ] && CLAUDE_CMD="$CLAUDE_CMD --continue"
    
    # Capture output to parse for rate limit reset time
    OUTPUT_FILE=$(mktemp)
    
    set +e
    $CLAUDE_CMD "$PROMPT" 2>&1 | tee "$OUTPUT_FILE" "claude-progress.txt"
    EXIT_CODE=${PIPESTATUS[0]}
    set -e
    
    OUTPUT=$(cat "$OUTPUT_FILE")
    rm -f "$OUTPUT_FILE"
    
    popd > /dev/null
    
    # Check for rate limit
    if echo "$OUTPUT" | grep -qiE "limit|quota|resets"; then
        # Try to parse reset time from error message
        wait_time=$(parse_reset_time "$OUTPUT")
        
        if [ "$wait_time" -gt 0 ]; then
            # Use parsed reset time
            reset_time_str=$(date -d "+${wait_time} seconds" "+%Y-%m-%d %I:%M %p")
            echo ""
            echo "========================================"
            echo "  ⏳ RATE LIMITED"
            echo "========================================"
            echo "Reset at: $reset_time_str"
            echo "Waiting $(format_time $wait_time)..."
        else
            # Fallback: wait 24 hours
            wait_time=$FALLBACK_WAIT_SECONDS
            echo ""
            echo "========================================"
            echo "  ⏳ RATE LIMITED (24h fallback)"
            echo "========================================"
            echo "Could not parse reset time."
            echo "Waiting 24 hours to be safe..."
        fi
        
        echo "(Will auto-resume - NO RETRY LIMIT)"
        echo ""
        
        # Countdown with periodic updates
        remaining=$wait_time
        while [ $remaining -gt 0 ]; do
            # Sleep in chunks, update every 10 min or remaining time
            if [ $remaining -gt 600 ]; then
                sleep_chunk=600
            else
                sleep_chunk=$remaining
            fi
            sleep $sleep_chunk
            remaining=$((remaining - sleep_chunk))
            if [ $remaining -gt 0 ]; then
                echo "   ... $(format_time $remaining) remaining"
            fi
        done
        
        echo "✓ Wait complete. Resuming..."
        session=$((session - 1))  # Retry same session
        continue
        
    elif [ $EXIT_CODE -eq 0 ]; then
        echo "✓ Session completed"
    else
        echo "⚠️  Exit code $EXIT_CODE - waiting 1 min before retry..."
        sleep 60
    fi
    
    # Show progress
    if [ -f "$PROJECT_DIR/feature_list.json" ]; then
        PASSING=$(grep -c '"passes": true' "$PROJECT_DIR/feature_list.json" 2>/dev/null || echo "0")
        TOTAL=$(grep -c '"passes":' "$PROJECT_DIR/feature_list.json" 2>/dev/null || echo "0")
        echo "📊 Progress: $PASSING / $TOTAL features passing"
        
        if [ "$PASSING" -eq "$TOTAL" ] && [ "$TOTAL" -gt 0 ]; then
            echo ""
            echo "🎉 ALL FEATURES COMPLETE!"
            break
        fi
    fi
    
    echo "Auto-continuing in ${DELAY_SECONDS}s... (Ctrl+C to stop)"
    sleep $DELAY_SECONDS
done

echo ""
echo "========================================"
echo "  COMPLETE"
echo "========================================"
echo "To run: cd $PROJECT_DIR && npm run dev"
