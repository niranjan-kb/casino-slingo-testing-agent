# User — Test Flow & Game Knowledge

## Full QA Test Flow

When the user says "Run the full Slingo QA test" (or similar), execute these phases in order.
Stop immediately if any phase fails — do NOT continue to the next.

### Phase 0: Device Setup
1. `select_device` for serial `{{ANDROID_SERIAL}}`
2. Confirm device is connected

### Phase 1: Launch App
1. `appium_activate_app` with appId=`{{APP_PACKAGE}}`
2. Wait 3 seconds
3. `appium_screenshot` to see the current screen
4. `appium_find_element` to detect which screen: login? home? other?

### Phase 2: Login (if needed)
If the app shows a login screen (detected by "Sign In", "Log In", or email/password fields):

**Step 2a: Email**
1. `appium_find_element` to find email input field (look for EditText or "Email")
2. If the email field already has text, check if it matches `{{TEST_EMAIL}}`
   - If it matches → skip to password
   - If different → clear and re-enter
3. Tap the email field coordinates
4. `appium_set_value` value=`{{TEST_EMAIL}}`
5. `appium_screenshot` to verify email entered correctly

**Step 2b: Password**
1. `appium_find_element` to find password field
2. Tap the password field
3. `appium_set_value` value=(password from env)
4. `appium_screenshot` to verify

**Step 2c: Submit Login**
1. `appium_find_element` to find the Sign In / Log In button
2. Tap the button
3. Wait 3-5 seconds

**Step 2d: OTP**
1. `appium_screenshot` to check if OTP screen appeared
2. `appium_find_element` — look for "Enter Code", "Verification", or "OTP"
3. If OTP screen detected:
   - **ASK THE USER**: "I need the OTP code sent to your phone via SMS. Please enter it here."
   - Set `next='question'` in your response and wait for the user's reply
   - When the user provides the OTP code:
     a. `appium_find_element` to find the OTP input field
     b. Tap the OTP field
     c. `appium_set_value` with the OTP code
     d. Find and tap the submit/verify button
     e. Wait 3-5 seconds
     f. `appium_screenshot` to verify login succeeded
4. If no OTP screen → login may have succeeded, continue to Phase 3

### Phase 3: Read Starting Balance
1. You should now be on the home screen
2. `appium_find_element` to find balance text in the header/nav area
3. Record the value as `starting_balance`
4. If balance can't be read, flag as `balance_uncertain` but continue

### Phase 4: Navigate to Game
1. `appium_find_element` to find the search bar/icon
2. Tap the search bar (use coordinates from element detection or screen map)
3. `appium_set_value` value='Slingo Cash Eruption'
4. `appium_screenshot` to verify search results
5. Tap the matching game tile (usually the first result)
6. Handle prompts that may appear:
   - **FanCash prompt**: Find and tap "Start Playing" or dismiss button
   - **Location prompt**: Tap "Allow" or dismiss
   - **Any other modal**: Screenshot, detect, and dismiss
7. Wait 5-8 seconds for game to load
8. `appium_screenshot` to confirm game loaded (you should see the 5x5 grid)

### Phase 5: Play One Round (5 Base Spins)

For each of the 5 base spins:
1. `appium_screenshot` to read game state (spins remaining visible in UI)
2. Tap spin button using coordinates from screen map
3. Wait 3-4 seconds for animation
4. `appium_screenshot` to check result
5. Handle special symbols if detected (see Game Knowledge below)
6. If spins > 0: continue to next spin
7. If spins = 0: **STOP** — do NOT tap the spin button (it now costs money)

### Phase 6: Exit Game Safely

**CRITICAL: NEVER tap the in-game END GAME button. It overlaps with the paid SPIN FOR button.**

Reliable exit sequence:
1. Tap the **native header close button** (top-left X, OUTSIDE the WebView)
   - Use coordinates from screen map for `game_header.close_button`
2. Wait 2 seconds
3. `appium_find_element` to confirm "Keep Playing?" modal appeared
4. Tap "No thanks, exit" (use element coordinates or screen map)
5. Wait 2 seconds
6. `appium_screenshot` to verify you're back in the app

### Phase 7: Read Ending Balance & Report
1. `appium_find_element` for balance on home/search screen
2. Record as `ending_balance`
3. Produce the test report (format below)

---

## Slingo Cash Eruption — Game Knowledge

### Basic Rules
- **Base spins**: 5 (exactly 5, NOT 10)
- **Default stake**: $0.20
- **Grid**: 5x5 matrix of random numbers
- **Reel**: 1x5 horizontal row below the grid
- **Auto-daubing**: Matching numbers are marked automatically
- **Slingos**: Complete line of 5 = payline hit
- **RTP**: ~95.73-95.79%

### Special Symbols

**WILD (Incan Princess)**
- Visual cue: Game pauses. One column highlighted with "SELECT ANY HIGHLIGHTED NUMBER". Numbers glow green/cyan.
- Action: Identify which column (1-5) the wild is in. Tap ANY unmarked number in that column.
- Column x-values from screen map: grid columns 1-5

**SUPER WILD (Princess with golden headdress)**
- Visual cue: Game pauses. ALL unmarked numbers are selectable.
- Action: Tap any unmarked number. Prefer center of grid for maximum payline coverage.

**FREE SPIN (+1)**
- Adds one extra base spin. No action needed.

**FIREBALL / BLOCKER**
- No action needed.

### Game Over / Cash Eruption Bonus
- If Cash Eruption Bonus triggers, wait for it to complete automatically
- When "Game Over" modal appears, tap center to dismiss
- Then proceed with exit sequence

---

## Test Report Format

```
=== SLINGO QA TEST REPORT (ANDROID) ===
Device: {{ANDROID_SERIAL}} ({{DEVICE_RESOLUTION}})
Starting Balance: $XX.XX
Ending Balance: $XX.XX
Balance Delta: -$X.XX
Spins Played: X/5
Wilds Encountered: X
Super Wilds Encountered: X
Extra Spins Purchased: 0 (must always be 0)
Anomalies: [list any unexpected behavior]
Status: PASS/FAIL
```

**PASS criteria**: All 5 base spins completed, exited without extra spins, balance obtained, no crashes.
**FAIL criteria**: Crash, extra spins purchased, round incomplete, balance unreadable.

---

## Edge Cases

- **Device not reachable**: Report to user. Suggest checking ADB / emulator.
- **App crash mid-game**: Screenshot the crash state. Report as FAIL. Do not continue.
- **Game load timeout**: Wait 10s, screenshot. Wait 5 more. If still loading → FAIL.
- **Reality Check popup**: Find and tap dismiss/continue, then continue test.
- **Unexpected modal/prompt**: Screenshot, use `appium_find_element` to identify, dismiss if safe.
- **Uncertain balance**: Flag as `balance_uncertain` in report.
