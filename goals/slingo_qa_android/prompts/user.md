# User — Test Flow & Game Knowledge

## Environment Context (live values for this run)

- `BUILD_ENV` = `{{BUILD_ENV}}`
- `DEFAULT_OTP` = `{{DEFAULT_OTP}}` (used only in dev/test)
- OTP policy → **{{OTP_POLICY}}**

## Standalone Commands

The user may invoke a single phase rather than the full test. Match intent loosely.

| User says (examples) | Run |
|----------------------|-----|
| "log in", "login", "sign in", "authenticate" | **Login Workflow** (Phases 0 → 1 → 2). Stop after login succeeds and report. |
| "launch the app", "open casino" | Phases 0 → 1. Report current screen. |
| "run the full slingo qa test", "play a round" | Full QA Test Flow (all phases) |
| "exit the game" | Phase 6 |

For any standalone command, still run Phase 0 (device select) and any prerequisite phases — do not skip setup.

## Full QA Test Flow

When the user says "Run the full Slingo QA test" (or similar), execute these phases in order.
Stop immediately if any phase fails — do NOT continue to the next.

### Phase 0: Device Setup
1. `select_device` for serial `{{ANDROID_SERIAL}}`
2. Confirm device is connected

### Phase 1: Launch App
1. `appium_app` with `action="activate"`, `id`=`{{APP_PACKAGE}}`
2. `WaitSeconds(seconds=3)` for splash
3. `appium_screenshot` to see the current screen
4. **Always dump the tree first** so classification is grounded in real UI:
   - Call `appium_get_page_source` (no args). Read the XML.
5. **Classify** by inspecting the tree (do NOT rely on a single guess):
   - **Permission/onboarding modal** → text contains any of: `Precise location`, `Location permission`, `Allow`, `Continue`, `Got it`, `Got it!`, `Skip`, `Allow notifications`, `Set up biometrics`, `Welcome to Fanatics`, `Age verification`. **Dismiss action**: click the primary button (`Continue` / `Allow` / `Got it` / `Allow while using app` / `OK`). After dismissing, sleep 2s, screenshot, page source again, and re-classify (max **5** modal dismissals — if you exceed this, STOP and `SaveEvidence(label="modal_loop")`).
   - **System permission dialog** → resource-id contains `com.android.permissioncontroller:id/permission_allow_button` or text `Allow` / `While using the app`. Tap it; same loop.
   - **Login screen** → tree has an EditText with `password="true"` OR text contains any of: `Sign In`, `Log In`, `Sign in to Fanatics`, `Email`, `Username`, `Email or Mobile`, `Continue with email`.
   - **OTP screen** → text contains: `Enter Code`, `Verification`, `Verify your`, `6-digit`, `One-time`, `OTP`, `Enter the code we sent`.
   - **Home screen** → text contains: `Featured`, `Casino`, `Slingo`, `Search`, `My Account`, OR resource-id contains `bottom_nav` / `search_input` / `casino_lobby`.
   - **Unknown** → if none of the above match after one re-screenshot, call `SaveEvidence(label="phase1_unknown")` and STOP. Do NOT loop blindly.
6. **Branch**:
   - Home detected → already logged in. Skip Phase 2.
   - Login detected → proceed to Phase 2.
   - OTP detected → jump to Phase 2d.
   - Modal detected → dismiss (see above) and re-loop.

### Phase 2: Login (Bulletproof)

This phase MUST be idempotent and re-runnable. Never assume — always observe between steps.

**Step 2a: Locate & fill email**

Try these element strategies in order; stop at the first hit:
1. `appium_find_element` `strategy="-android uiautomator"` selector=`new UiSelector().resourceIdMatches(".*(email|username|user_name|login_id).*")`
2. `appium_find_element` `strategy="-android uiautomator"` selector=`new UiSelector().className("android.widget.EditText").instance(0)`
3. `appium_find_element` `strategy="xpath"` selector=`(//android.widget.EditText)[1]`

Then:
1. `appium_get_text` on the elementId — if it already equals `{{TEST_EMAIL}}` → skip to 2b.
2. `appium_click` elementId=... to focus the field.
3. If pre-existing text exists and is wrong: clear it (`appium_set_value` value="" or long-press → select all → delete via `appium_mobile_press_key` key="67" repeatedly).
4. `appium_set_value` value=`{{TEST_EMAIL}}`
5. `appium_screenshot` and verify the email is visible. If characters dropped, clear and retry once.

**Step 2b: Submit email → password screen (Fanatics ONE 2-step flow)**

Fanatics ONE is a **2-step login**: email page → Continue → password page. The password field is NOT on the email screen.

After typing email:
1. Tap the **Continue** button (resource-id is `next button`, text is `Continue`):
   - `appium_find_element` `strategy="xpath"` selector=`//*[@text="Continue"]`
   - Or `strategy="accessibility id"` selector=`next button`
   - Then `appium_click` elementUUID=...
2. `WaitSeconds(seconds=3)` — server checks the email and shows the password screen.
3. `appium_screenshot` + `appium_get_page_source` — confirm a password input is now visible.
4. Locate the password field. Try in order:
   - `strategy="class name"` selector=`android.widget.EditText` (only EditText on password screen)
   - `strategy="-android uiautomator"` selector=`new UiSelector().resourceIdMatches(".*(password|pass_word|pwd).*")`
   - `strategy="xpath"` selector=`//android.widget.EditText[1]`
5. `appium_click` elementUUID=... to focus.
6. `appium_set_value` elementUUID=... text=`{{TEST_PASSWORD}}` (type EXACTLY this value — do NOT make up a password, do NOT echo it back in your `response` field).
7. `appium_screenshot` to confirm dots/asterisks appeared. Do NOT log or echo the password.

**Step 2c: Submit login**

Try these element strategies in order:
1. `appium_find_element` `strategy="-android uiautomator"` selector=`new UiSelector().textMatches("(?i)(sign in|log in|continue|submit)")`
2. `appium_find_element` `strategy="xpath"` selector=`//*[@text="Sign In" or @text="Log In" or @text="Continue"]`
3. `appium_find_element` `strategy="-android uiautomator"` selector=`new UiSelector().resourceIdMatches(".*(sign_in|login|submit|continue).*")`

Then:
1. `appium_click` elementId=...
2. `WaitSeconds(seconds=4)` for network round-trip.
3. `appium_screenshot` and reclassify (login | otp | home | error).
4. **If login screen still showing**: look for an inline error message (text matching `(?i)(invalid|incorrect|try again|wrong|unable to)`). If present → screenshot via `SaveEvidence(label="login_failed")`, report the error text to the user, then **STOP** (do not retry blindly — credentials may be wrong).

**Step 2d: OTP**

Detect OTP screen via `appium_find_element` text match `(?i)(enter code|verification|verify|6.?digit|one.?time)`.

If detected:
1. **OTP source — follow the OTP policy injected at top of this file**:
   - `AUTO-OTP` mode → use the value `{{DEFAULT_OTP}}` directly. **DO NOT ask the user.**
   - `ASK-USER-OTP` mode → set `next='question'` with prompt: "Please enter the OTP sent to your phone via SMS." Wait for the user's reply.
2. Locate the OTP input. Try in order:
   - `appium_find_element` `strategy="-android uiautomator"` selector=`new UiSelector().className("android.widget.EditText").instance(0)`
   - `appium_find_element` `strategy="xpath"` selector=`(//android.widget.EditText)[1]`
3. `appium_click` elementId=...
4. `appium_set_value` value=(the OTP — either DEFAULT_OTP or what the user provided)
5. `appium_screenshot` to verify all 6 digits entered.
6. Find and tap the submit button (text matches `(?i)(verify|submit|continue|confirm|next)`). Some forms auto-submit on the 6th digit — if so, skip the tap.
7. `WaitSeconds(seconds=4)`
8. `appium_screenshot` — should now be on home. If still on OTP and an error is visible, screenshot via `SaveEvidence(label="otp_failed")` and STOP.

If no OTP screen is detected after login submit → continue to Phase 3.

**Step 2e: Confirm login success**

Before leaving Phase 2:
1. `appium_screenshot`
2. `appium_find_element` for home anchor (search bar, bottom nav, or a balance label).
3. If home not confirmed within 8s of submit → `SaveEvidence(label="login_unverified")` and STOP.

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
2. `LookupElementCoords(app_context="slingo_cash_eruption", screen_name="main_game", element_name="spin_button")` → get coordinates
3. `TapCoordinate(x=..., y=...)` to tap spin button
4. `WaitSeconds(seconds=4)` for animation
5. `appium_screenshot` to check result
6. Handle special symbols if detected (see Game Knowledge below)
7. If spins > 0: continue to next spin
8. If spins = 0: **STOP** — do NOT tap the spin button (it now costs money)

### Phase 6: Exit Game Safely

**CRITICAL: NEVER tap the in-game END GAME button. It overlaps with the paid SPIN FOR button.**

Reliable exit sequence:
1. `LookupElementCoords(app_context="platform", screen_name="game_header", element_name="close_button")` → get coords
2. `TapCoordinate(x=..., y=...)` to tap the native close button (OUTSIDE the WebView)
3. `WaitSeconds(seconds=2)`
4. `DetectScreen(app_context="platform")` to confirm "Keep Playing?" modal appeared
5. `LookupElementCoords(screen_name="keep_playing_modal", element_name="no_thanks_exit")` → tap it
6. `TapCoordinate(x=..., y=...)`
7. `WaitSeconds(seconds=2)`
8. `appium_screenshot` to verify you're back in the app

### Phase 7: Read Ending Balance & Report
1. `appium_find_element` for balance on home/search screen
2. Record as `ending_balance`
3. `GenerateReport(starting_balance=..., ending_balance=..., spins_played=5, wilds=..., super_wilds=..., extra_spins_purchased=0, anomalies=...)`

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
