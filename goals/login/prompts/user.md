# goal_login — Authenticate the casino app

Your job: launch the app, dismiss any pre-login modals, complete the Fanatics ONE 2-step login (email → password → OTP), and confirm a logged-in home/lobby screen. Then stop. Do not navigate further.

## Phases (run in order, stop on the first failure that exhausts recovery)

### Phase 0 — Device + session

1. `select_device` for the configured platform / serial.
2. `create_session` with the platform.

### Phase 1 — Launch + classify

1. `appium_app` action=`activate` id=`{{APP_PACKAGE}}`
2. `WaitSeconds` 3 — splash.
3. `appium_screenshot` — record the first frame.
4. `appium_get_page_source` — read the tree.
5. **Classify** by inspecting the tree. Branch on the first match:
   - **App permission/onboarding modal** (e.g. "Precise location required", "Get rewarded — Fanatically", "Welcome to Fanatics"): use `FindElementWithFallback` with these `candidates`:
     ```json
     [{"strategy": "xpath", "selector": "//*[@text='Continue']"},
      {"strategy": "xpath", "selector": "//*[@text='Got it']"},
      {"strategy": "xpath", "selector": "//*[@text='Got it!']"},
      {"strategy": "xpath", "selector": "//*[@text='Start Playing']"},
      {"strategy": "accessibility id", "selector": "next button"}]
     ```
     Then `appium_click` with the returned `elementUUID`.
   - **System permission dialog** (`com.android.permissioncontroller` / `com.google.android.permissioncontroller`): use `FindElementWithFallback` with:
     ```json
     [{"strategy": "id", "selector": "com.android.permissioncontroller:id/permission_allow_foreground_only_button"},
      {"strategy": "id", "selector": "com.android.permissioncontroller:id/permission_allow_button"},
      {"strategy": "xpath", "selector": "//*[@text='While using the app']"},
      {"strategy": "xpath", "selector": "//*[@text='Allow']"}]
     ```
     Never tap `Don't allow` if avoidable.
   - **Login screen** (Fanatics ONE): text contains `Log in or sign up` OR EditText `resource-id="email address text"`. → Phase 2.
   - **Password screen**: text contains `Enter your password` OR EditText `resource-id="password text"` with `password="true"`. → Phase 2 step 2c.
   - **OTP screen**: text contains `One time passcode` OR EditText `resource-id="mfa code text"`. → Phase 2 step 2d.
   - **Logged-in home/lobby**: balance text visible (e.g. `$NN,NNN.NN`), header logo (`Hollywood Casino`, `Fanatics Casino`), or bottom-nav. → DONE, run Phase 3 (success report).
   - **Unknown** after one re-screenshot+page-source → `SaveEvidence(label="login_phase1_unknown")` and STOP.
6. After dismissing a modal, **always re-classify** (loop back to step 3). Cap modal dismissals at 6 total — beyond that, save evidence and stop.

### Phase 2 — Fanatics ONE 2-step login

#### 2a — Email

1. `FindElementWithFallback` candidates:
   ```json
   [{"strategy": "xpath", "selector": "//android.widget.EditText[@resource-id='email address text']"},
    {"strategy": "class name", "selector": "android.widget.EditText"},
    {"strategy": "xpath", "selector": "(//android.widget.EditText)[1]"}]
   ```
2. `appium_click` elementUUID=(returned)
3. `appium_set_value` elementUUID=(same) text=`{{TEST_EMAIL}}`
4. `appium_screenshot` — verify the email is visible. If it dropped chars, clear and retry once.

#### 2b — Continue → password screen

1. `FindElementWithFallback` candidates:
   ```json
   [{"strategy": "xpath", "selector": "//*[@text='Continue']"},
    {"strategy": "accessibility id", "selector": "next button"}]
   ```
2. `appium_click` elementUUID=(returned)
3. `WaitSeconds` 3 — server checks the email.
4. `appium_screenshot` + `appium_get_page_source` — confirm password input is now visible.

#### 2c — Password

1. `FindElementWithFallback` candidates:
   ```json
   [{"strategy": "xpath", "selector": "//android.widget.EditText[@resource-id='password text']"},
    {"strategy": "class name", "selector": "android.widget.EditText"},
    {"strategy": "xpath", "selector": "(//android.widget.EditText)[1]"}]
   ```
2. `appium_click` elementUUID=(returned)
3. `appium_set_value` elementUUID=(same) text=`{{TEST_PASSWORD}}`  ← inject EXACT, never log it.
4. `appium_screenshot` — confirm dots/asterisks appeared. If field is empty, retry once.

#### 2d — Submit → OTP

1. `FindElementWithFallback` candidates:
   ```json
   [{"strategy": "xpath", "selector": "//*[@text='Log in']"},
    {"strategy": "xpath", "selector": "//*[@text='Sign In']"},
    {"strategy": "xpath", "selector": "//*[@text='Continue']"}]
   ```
2. `appium_click` elementUUID=(returned)
3. `WaitSeconds` 3 — credential check.
4. `appium_screenshot` + `appium_get_page_source` — classify (OTP screen | error | home).
5. If still on password screen with an error visible (text matches `(?i)(invalid|incorrect|try again|wrong|unable to)`): `SaveEvidence(label="login_failed")`, report the error text, STOP.

#### 2e — OTP

1. Detect: text contains `One time passcode` or EditText `resource-id="mfa code text"`.
2. **OTP source — follow the OTP policy from Identity**: `AUTO-OTP` → use `{{DEFAULT_OTP}}` directly. `ASK-USER-OTP` → `next='question'` with prompt: "Please enter the OTP sent via SMS."
3. `FindElementWithFallback` candidates:
   ```json
   [{"strategy": "xpath", "selector": "//android.widget.EditText[@resource-id='mfa code text']"},
    {"strategy": "class name", "selector": "android.widget.EditText"},
    {"strategy": "xpath", "selector": "(//android.widget.EditText)[1]"}]
   ```
4. `appium_click` elementUUID=(returned)
5. `appium_set_value` elementUUID=(same) text=`{{DEFAULT_OTP}}` (always quoted as a STRING).
6. `FindElementWithFallback` for the submit button:
   ```json
   [{"strategy": "xpath", "selector": "//*[@text='Done']"},
    {"strategy": "xpath", "selector": "//*[@text='Verify']"},
    {"strategy": "xpath", "selector": "//*[@text='Submit']"},
    {"strategy": "xpath", "selector": "//*[@text='Confirm']"},
    {"strategy": "xpath", "selector": "//*[@text='Continue']"}]
   ```
   If auto-submits on the 6th digit, this step may already be off-screen — that's fine, skip the click.
7. `appium_click` elementUUID=(returned, if any)
8. `WaitSeconds` 4 — auth round-trip.

### Phase 3 — Confirm + report

1. `appium_screenshot` + `appium_get_page_source`.
2. Verify a logged-in indicator: balance text (e.g. `$NN,NNN.NN`), header logo, bottom-nav, or any anchor that doesn't appear pre-login.
3. If confirmed → respond `next='done'` with a short success report:
   - `LOGIN PASS — email=<email> | balance=<balance> | platform=<platform> | build=<build_env> | resolution=<W x H>`
4. If NOT confirmed within 8s of submit → `SaveEvidence(label="login_unverified")` and STOP.
