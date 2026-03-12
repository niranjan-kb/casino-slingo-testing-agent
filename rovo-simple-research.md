Below is what I can pull together from Confluence/Jira for the Fanatics Casino / STAC app. For a few items (like exact bundle IDs, some endpoints, full test device matrices) there isn’t a single authoritative doc in the search results, so I’ll call that out as “not found / needs follow‑up” rather than guessing.

Where I reference a page or ticket, I include the direct URL.

---

## 0. Anchor: P0 User Journeys (what your AI QA agent must own)

You’re already looking at this, but it’s the best single source of “what matters most” for Casino:

- **iCasino P0 User Journeys – Managed by ogx‑bot**  
  https://betfanatics.atlassian.net/wiki/spaces/~6414c91c5534b0bf7440ceac/pages/2718498826/iCasino+P0+User+Journeys+-+Managed+by+ogx-bot  

This defines all P0 flows that, if broken, are release‑blocking (launch, lobby load, game launch, gameplay, deposit/withdrawal, RG enforcement, promos, jackots, etc.). Your AI agent’s coverage should be mapped directly to the table in this doc.

---

## 1. APP ARCHITECTURE

### 1.1 Product flavors / apps

There are two “product variants” at the **app level**:

1. **Fanatics Sportsbook & Casino (combined app)**  
   - Android app identified as “Fanatics Sportsbook & Casino” in Play Store telemetry (see GitHub ratings script bug):  
     https://betfanatics.atlassian.net/browse/SMA-191  
   - This is built from the `fbg-sportsbook-kmp` repo with an `androidApp` module that also contains iCasino:
     - “All client code (CAT, FanX, iCasino, etc.) is in the `androidApp` module. The iCasino code is all within the package `com/betfanatics/shared/broker/sportsbook/casino`.”  
       Source: **White-label Casino App Decision – Android Architecture**  
       https://betfanatics.atlassian.net/wiki/spaces/~632dabc49b32cfef932590ca/pages/306839553/White-label+Casino+App+Decision+-+Android+Architecture  

2. **Fanatics Casino – Standalone (STAC)**  
   - A separate, casino‑only app, but architected as a clone of the combined app:
   - Strategy doc: **Fanatics Casino app Strategy**  
     https://betfanatics.atlassian.net/wiki/spaces/CAS/pages/1102479685/Fanatics+Casino+app+Strategy  
   - Integration / certification status: **Integration Status: Stand Alon Casino App (STAC)**  
     https://betfanatics.atlassian.net/wiki/spaces/TE/pages/1254130082/Integration+Status+Stand+Alon+Casino+App+STAC  

   From that doc:
   - NJ GLI submission build:  
     - iOS: `Fanatics Casino Cert - 5.8.2 (2501291824)`  
     - Android: `Fanatics Casino - 5.8.2-cert-release (201291820)`

**Bundle IDs / package names**

No document in the search explicitly lists the Android applicationId or iOS bundle identifier for Sportsbook vs STAC. The Android architecture doc only gives the **package path** for casino feature code:

- `com/betfanatics/shared/broker/sportsbook/casino`  
  https://betfanatics.atlassian.net/wiki/spaces/~632dabc49b32cfef932590ca/pages/306839553/White-label+Casino+App+Decision+-+Android+Architecture  

To get exact IDs (e.g. `com.betfanatics.sportsbook` vs `com.betfanatics.casino`), you’ll need to look directly in the `androidApp` Gradle config and the Xcode project for the Casino target.

### 1.2 Environments & build matrix

On the **mobile side**, there are four main runtime environments, and both Sportsbook and Casino have all four:

From **Bitrise CI/CD Quick Start & User Guide**  
https://betfanatics.atlassian.net/wiki/spaces/Atlas/pages/1373863983/Bitrise+CI+CD+Quick+Start+User+Guide  

For iOS workflows:

- `ios-cd-casino-dev`
- `ios-cd-casino-test`
- `ios-cd-casino-cert`
- `ios-cd-casino-prod-debug`
- `ios-cd-casino-prod`

Similarly for `ios-cd-sportsbook-*`.

For Android, the release pipelines show:

- `cut-mobile-release` (creates Test/Cert/Prod‑Debug builds for Casino & Sportsbook)  
- `mobile-release-production-builds` (creates `prod` and `prod-debug` for both apps)

So for your purposes:

- **Environments:**
  - `dev` – developer validation, internal QA
  - `test` – formal QA / regression environment
  - `cert` – certification / pre‑prod for regulators and GLI
  - `prod` – production (with an additional `prod-debug` flavor for internal debugging)

The CI environment matrix is described at:  
https://betfanatics.atlassian.net/wiki/spaces/FAN/pages/2194341937/Project+Onboarding+Checklist+CI+CD+Platforms  

(See “Key Environment Identifiers”: `dev`, `test`, `prod` plus an `inf-dev` and hub CI account.)

**Base URLs / API endpoints**

Search results don’t give a single canonical table of mobile base URLs. You do see:

- **Casino Web – Log in endpoints** (fan ID endpoints with proxy through FBG web):  
  https://betfanatics.atlassian.net/wiki/spaces/~712020fbc79b4fbc2041059f20fc961f46e23d/pages/1847328802/Casino+Web+-+Log+in+endpoints  

  This explains the login HTTP flow for Casino web, but it references Fan ID endpoints and Nginx proxy, not explicit hostnames in the snippet.

- **Trading API Endpoints** describes a large set of REST endpoints used by NATS/Trading for casino bonuses and wagers (e.g. `/ats-trader/api/bets/casino/w2g/detail/search`, `/ats-trader/api/bonus/bulkAwards/casinoCredit/award`):  
  https://betfanatics.atlassian.net/wiki/spaces/SB/pages/1372323869/Trading+API+Endpoints  

For your AI QA agent, you’ll likely need to introspect the running app (or decompile) to confirm base URLs per flavor/environment for:

- Fan ID API (auth)
- FBG gateway / sportsbook-casino API
- Casino search API (`/search/v1?domain=casino&jurisdictionCode=XX`):  
  https://betfanatics.atlassian.net/wiki/spaces/Helios/pages/407537564/Casino+x+Search+Query+API  

### 1.3 Game loading architecture (WebView vs iframe vs native)

Evidence from multiple tickets and epics:

- **[Android] Load L&W Games in an iFrame**  
  https://betfanatics.atlassian.net/browse/ICG-94  

  > Previously when we integrated with IGT we embedded the launch url for games right into the WebView. However with L&W, the use of their `gcmLib.js` library requires that games run inside of an iFrame in the WebView.  
  >  
  > An optional `loadUrl` parameter will be added to Browser so that the GameHandler can override the default implementation and call `loadDataWithBaseURL` with HTML that includes an iFrame with the original game URL as the `src`.

- **Client Game Provider Support: DGC**  
  https://betfanatics.atlassian.net/browse/OGX-1819  

  This is clearly using an iframe message bus:

  ```js
  // sent from operator (FBG) to game iframe:
  gameflexIframeWindow.postMessage({
    method: 'operator.ready',
    data: { origin: '<origin>' }
  }, gameflexOrigin);

  // closing game:
  gameflexIframeWindow.postMessage({
    method: 'operator.game.session.end'
  }, gameflexOrigin);
  ```

  And game events received via:

  ```js
  gameflexIframeWindow.addEventListener("message", function(message) {
    if (message.data && message.data.method === "gel.ready") {
      console.log("Provider integration ready");
    }
  });
  ```

- **Client Game Provider Support: WHG (White Hat Studios)**  
  https://betfanatics.atlassian.net/browse/ICG-950  

  Notes that game events only work correctly when the game is **running inside an iframe**; game uses `parent.parent` window for postMessage. Example:

  ```js
  window.addEventListener("message", (msg) => { 
    if (msg.data.type === 'gameReady') {
      // game finished loading
    }
  });

  document.getElementById('gameFrame')
    .contentWindow.postMessage({ type: 'requestBalanceUpdate' }, '*');
  ```

So for your agent:

- **Game container model:**
  - **Mobile client**: WebView that loads **HTML shell** containing an iframe, where the game loads via provider URL.
  - **Integration pattern**: HTML+JS message bus over `postMessage` between WebView parent and provider iframe.

- **RGS / RGI integration pattern (backend)**

  - See **Casino Provider Integrations – RGS, RGI, aggregator explanation.pdf**:  
    https://betfanatics.atlassian.net/wiki/pages/viewpageattachments.action?pageId=131498495&preview=%2F131498495%2F177012989%2FCasino+Provider+Integrations+-+RGS%2C+RGI%2C+aggregator+explanation.pdf  

  - FBG uses a **Remote Gaming Interface (RGI)** that proxies to multiple **Remote Gaming Systems (RGS)**:
    - RGS (Evolution, NetEnt, IGT, L&W, etc.) handle bet outcome, settlement, wallet updates.
    - RGI is the connector between game providers and the FBG wallet.
    - There is an option for using **aggregators** (e.g., Light & Wonder OGS) vs direct RGS integration; FBG leans away from single‑aggregator because it becomes a single point of failure.

  - **Responsible Gaming – Game Provider Adapters Support**  
    https://betfanatics.atlassian.net/wiki/spaces/CAS/pages/2429386895/Responsible+Gaming+-+Game+Provider+Adapters+Support  

    Points out adapters like `icp-igt-adapter`, `icp-ogs-adapter`, `icp-boom-adapter`:

    > Adapters map FBG/GameSession/Wallet requests → RGS APIs and **proxy/normalize responses** back to FBG.  
    > They rely on upstream services for RG enforcement (limits, exclusions).

### 1.4 Game providers & catalog size

**Provider list / integration type / jurisdiction coverage**

- **Casino RGS Game Provider Integration Matrix**  
  https://betfanatics.atlassian.net/wiki/spaces/CAS/pages/2644344964/Casino+RGS+Game+Provider+Integration+Matrix  

This is a detailed matrix. Partial sample (MI / NJ / PA / WV):

- Direct:
  - Boom Gaming
  - Evolution
  - Games Global
  - IGT
  - Light & Wonder (direct and OGS)
  - Pariplay
  - Playtech
  - White Hat Studios
- Via Light & Wonder (OGS):
  - 1X2 Network, 4ThePlayer, AGS, Ainsworth, Bragg, Crucible, DWG, Elk Studios, Everi, Gamecode, Gaming Realms, Greentube, Hacksaw, High 5 Games, Inspired, Konami, Light & Wonder Spark, Octoplay, Red Rake, ReelPlay, Relax Gaming, Wazdan, etc.
- Via Evolution:
  - Big Time Gaming, NetEnt, No Limit City, Red Tiger, Ezugi
- Via Pariplay:
  - Aristocrat, Spinomenal, Wazdan (also via L&W)
- Others:
  - Oddsworks (through L&W) in planning.

**Total game count**

No doc in the search returns a canonical “we currently have N games per state”. Closest is:

- **Steps to Onboard an RGS Provider** (North star):  
  https://betfanatics.atlassian.net/wiki/spaces/CAS/pages/358386059/Steps+to+Onboard+an+RGS+Provider  

  > “support 10+ providers directly integrated … in 4+ states, covering **100–200 games / state**, with tens of games launched every month.”

So design target: **100–200 games per state**, but you should query the catalog API (search or games manager service) to get a live count for your agent.

---

## 2. CURRENT QA PROCESS

### 2.1 Manual QA process before release

From **Casino Standalone QE Status**:  
https://betfanatics.atlassian.net/wiki/spaces/QE/pages/1216479233/Casino+Standalone+QE+Status  

Pre‑launch testing activities (this is a concrete checklist):

- Test plan and test case review meetings.
- Iterative testing of new functionality.
- Regression test passes for completed functionality.
- Scheduled DEV → TEST deployment.
- Full regression test pass.
- Scheduled TEST → CERT deployment.
- Code freeze / final regression pass.
- Bug bash in CERT.
- Latency competitive analysis testing in PROD.
- Prod readiness and launch plan review.
- Border crossing testing in PROD.
- Identify final P0 test cases for regression testing.
- Scheduled CERT → PROD deployment.
- Bug bash session in PROD.
- Launch.

So your AI QA agent fits best as an executor of:

- Regression passes (in TEST and CERT).
- Targeted P0 checks pre‑deploy / post‑deploy.
- Long‑running stateful scenarios (latency measures, RG enforcement, credit settlement).

### 2.2 Existing test cases / plans for casino

- P0 journeys we already saw:  
  https://betfanatics.atlassian.net/wiki/spaces/~6414c91c5534b0bf7440ceac/pages/2718498826/iCasino+P0+User+Journeys+-+Managed+by+ogx-bot  

- geo & RG coverage for Casino:  
  **iCasino GeoComply**  
  https://betfanatics.atlassian.net/wiki/spaces/QE/pages/370835462/iCasino+GeoComply  

  Focuses on:
  - GeoComply token lifecycle.
  - Bet success/failure based on token and state.
  - Casino session behavior when token invalid/expired.

- Many casino‑specific test cases are referenced by Jira IDs in release blockers, for example:
  - `QE-T5428` – relates to [WEB-888]: session logout after 15+ mins of gameplay.  
    https://betfanatics.atlassian.net/browse/WEB-888  
  - `QE-T4601` – free spins promo re‑use bug:  
    https://betfanatics.atlassian.net/browse/SHOCK-2421  
  - `QE-T5436`, `QE-T6117`, `QE-T5306` – casino credits reflection and wallet issues in games:  
    https://betfanatics.atlassian.net/browse/OLY-885  
    https://betfanatics.atlassian.net/browse/VLAD-443  

Your agent should ingest those references plus the Zephyr project(s) attached to Casino epics. The iCasino P0 Journeys doc is the canonical high‑level list.

### 2.3 Devices / OS versions

- **TestPlan: Fanatics Five: Daily and Jackpot Test Cases** explicitly lists:  
  https://betfanatics.atlassian.net/wiki/spaces/FAN/pages/492996784/TestPlan+Fanatics+Five+Daily+and+Jackpot+Test+Cases  

  > “We will cover the latest versions of iOS and Android on iPhone 14 and Samsung Galaxy S22.”

- **Casino Onboarding – Geo task force** and various blockers show test devices:
  - Windows 10 Pro, Mac Safari/Chrome for web.
  - iPhone 14, iPhone 15/16 Pro Max, Samsung S22/S23+/S24+, Galaxy A15, Galaxy A15, etc. (various Jira tickets like OLY‑885, SHOCK‑2421, VLAD‑443, VLAD‑593, QE‑13452).

- **Casino UI Automation Assessment – Appium Readiness & Environment Feasibility**  
  https://betfanatics.atlassian.net/wiki/spaces/QE/pages/2418835963/Casino+UI+Automation+Assessment+Appium+Readiness+Environment+Feasibility  

  Notes:

  > Device / OS Coverage: 5 – “Browserstack providers a wide range of OS and devices”.

So there is a **standard device list** but the specific document URL wasn’t in the snippets. Your AI agent should assume:

- At minimum:
  - iOS: latest iOS on iPhone 14/15/16.
  - Android: latest Android on Galaxy S22/S23/S24/A‑series.
- Additional devices via BrowserStack matrix.

### 2.4 Existing automation

- **Casino UI Automation Assessment – Appium Readiness & Environment Feasibility**  
  https://betfanatics.atlassian.net/wiki/spaces/QE/pages/2418835963/Casino+UI+Automation+Assessment+Appium+Readiness+Environment+Feasibility  

  Explicitly about **Appium** for Casino:

  - Requirements list includes:
    - “App Build Availability – Stable APK/IPA available per environment”.
    - “Device Strategy – Utilizing BrowserStack for regression and exploratory test.”
    - “App Identifiers – Android identifiers complete, iOS and image recognition in progress.”
  - Environment scores:
    - CERT: **Automate Immediately** (Automation Value 47/55).
    - PROD‑DEBUG: **Automate with Mitigations** (45/55).

- **Case: Casino FAST Automation** (backend/functional suite)  
  https://betfanatics.atlassian.net/wiki/spaces/~632dabbe140ba0bf651a3543/pages/1703248195/Case+Casino+FAST+Automation  

  This doc is about backend “FAST” automation and how it missed certain release blockers because tests were only run in lower environments. This is relevant for your agent because those same endpoints (Games Manager v1/v2) are core to game lobby content.

- **RAF automation docs** mention multiple frameworks:  
  https://betfanatics.atlassian.net/wiki/spaces/QE/pages/1673691137/FEAT-5354+RAF+-+Short-term+Support+for+Casino+RAF+Test+Plan  

  - ETDGE (internal tool), FAST automation, SKTI automation.

Nothing in search shows Espresso/XCTest/Detox as primary; **Appium + internal frameworks (FAST, SKTI, ETDGE)** are the key automation systems.

### 2.5 Biggest QA pain points / recurring bugs

From recent release blockers and Casino bugs:

1. **Casino credits not reflected in games or wallet UIs**

   - [OLY‑885] (CERT, Dec 2025):  
     https://betfanatics.atlassian.net/browse/OLY-885  

     > “Casino credits are not reflected on the game page; only the cash balance is displayed.”  
     > Affects TEST environment, Android 8.1.0 / iOS 8.1.0, WV/MI.

   - [VLAD‑443] (TEST, Jan 2026):  
     https://betfanatics.atlassian.net/browse/VLAD-443  

     > Same defect but in newer build 8.3.0. Test case `QE-T5306`.

   - [QE‑13452] – casino credits not shown in Account page after promo:  
     https://betfanatics.atlassian.net/browse/QE-13452  

   - [ICG‑2761] – cosmic crash in‑game balance missing casino credits:  
     https://betfanatics.atlassian.net/browse/ICG-2761  

   Your agent should heavily focus on wallet, casino credit display, and provider‑level balances.

2. **Free spin promo logic**

   - [SHOCK‑2421] – user can use free spins promo a second time:  
     https://betfanatics.atlassian.net/browse/SHOCK-2421  

   This ties into P0 journeys around **Free Spins Lifecycle** and **Daily Spin – Free Spins Reward** in the P0 doc.

3. **Session / authentication behavior during/after gameplay**

   - [WEB‑888] – user is logged out after 15+ minutes gameplay then refresh home page:  
     https://betfanatics.atlassian.net/browse/WEB-888  

4. **FanCash conversion to Casino Credit and in‑game redemption**

   - [OGX‑3288] – Launch blocker: game not recognizing newly converted casino credits until restart:  
     https://betfanatics.atlassian.net/browse/OGX-3288  

   - Various wallet & tier point integration issues (WHEEL‑904):  
     https://betfanatics.atlassian.net/browse/WHEEL-904  

5. **UI / content glitches related to Casino tiles**

   - [ICG‑2601], [ICG‑2637] – casino tile spacing issues after Cosmic Crash tile injection.  
     https://betfanatics.atlassian.net/browse/ICG-2601  
     https://betfanatics.atlassian.net/browse/ICG-2637  

The Jira agent query for casino bugs is here for extending your own analysis:  
https://betfanatics.atlassian.net/issues/?jql=project%20%3D%20ICG%20AND%20issuetype%20%3D%20Bug%20AND%20summary%20~%20%22casino%22%20AND%20created%20%3E%3D%20-24w%20ORDER%20BY%20created%20DESC  

### 2.6 Regression cycle length

No doc snippet gives a specific “full regression = X days”. From the **Casino Standalone QE Status** page you can infer:

- There is **Iterative testing**, a **Full regression pass**, then **Code freeze / Final regression**, plus bug bashes in CERT and PROD.
- Your AI agent should be designed assuming at least **multi‑day** regression cycles in TEST and CERT.

---

## 3. AUTH & USER FLOWS

### 3.1 Login flow

All FBG apps (Casino and Sportsbook) are unified under **Fanatics ONE/ID (Fan ID)**:

- **PRD – Fanatics ID**  
  https://betfanatics.atlassian.net/wiki/spaces/FAN/pages/1048051967/PRD+-+Fanatics+ID  

- **Fanatics Identity Login flow events**  
  https://betfanatics.atlassian.net/wiki/spaces/FAN/pages/1813217810/Fanatics+Identity+Login+flow+events  

Login flow mechanics:

- **Credentials**: Email + password (plus OTP flows for MFA and password reset).
- **Events**:
  - `SIGNIN_FACTOR_START.ACCOUNT` — starting login factor (email/password, OTP).
  - `SIGNIN_FACTOR_COMPLETED.ACCOUNT` — factor completed.
  - `SIGNIN.ACCOUNT` — successful login.
  - `PASSWORD_RESET_REQUESTED.ACCOUNT` / `PASSWORD_RESET_SUCCESSFUL.ACCOUNT`.
  - `REGISTER.ACCOUNT` / `REGISTER_ERROR.ACCOUNT`.

Front‑end events for Casino web login:

- `VIEW.PAGE "/login"` – login page open.
- `SELECT.BUTTON` `{"bctx":"submit","bid":"username"}` – username submit.
- `SELECT.BUTTON` `{"bctx":"submit","bid":"pwd"}` – password submit.
- `VIEW.PAGE "/account/create"` – account creation page.
- `SELECT.LINK {"lid":"forgot_password"}` – forgot password.

Doc:  
https://betfanatics.atlassian.net/wiki/spaces/FAN/pages/1813217810/Fanatics+Identity+Login+flow+events  

MFA:

- Fanatics Live States cheat‑sheet shows 14‑day MFA requirements for some states, but that’s more sports; still, your agent should expect **MFA prompts** after X days or new device.

### 3.2 Account creation

Registration is also via Fan ID:

- `create-account` endpoints from Fan ID UI and FBG API gateway:
  - `fanidui create-account` or `fanapigateway native/create-account`.
- After registration:
  - Event `REGISTER.ACCOUNT` then `SIGNIN.ACCOUNT`.

Doc:  
https://betfanatics.atlassian.net/wiki/spaces/FAN/pages/1813217810/Fanatics+Identity+Login+flow+events  

Also see registration flows for Exchange (reuses FBG KYC patterns):  
https://betfanatics.atlassian.net/wiki/spaces/FanExchang/pages/1693024541/Feature+Registration+KYC+Login  

And Canada Casino account creation:  
https://betfanatics.atlassian.net/wiki/spaces/CL2/pages/2354053213/CAN+Casino+Account+Creation+Onboarding  

Key points your agent should model:

- Registration collects:
  - Email, password initially.
  - Then KYC data (name, DOB, address, SSN, etc.) in a later step.

### 3.3 KYC & Responsible Gaming integration

From **Casino Standalone QE Status** KYC section:  
https://betfanatics.atlassian.net/wiki/spaces/QE/pages/1216479233/Casino+Standalone+QE+Status  

Already‑tested flows:

- KYC success, doc verification, manual review, rejection.
- State exclusion & duplicate account checks.
- MFA after KYC (e.g., `[WV] MFA screen is displayed after KYC`).
- Different states step‑up vs non step‑up.
- Session expiry during DocV and re‑login.

### 3.4 Test accounts

Multiple Jira issues list test account patterns:

- Emails like `dlong+fbgprimary_cert@applausemail.com`, `awilley+test_...@applausemail.com`, `Renuka.vaskuri.xc+testdec151@betfanatics.com`, etc.

QE has dedicated QE_P0_Test segments and test users (see QE‑13452). There is also emphasis on **account stability** and strategies for top‑up and 2FA recovery in the Appium assessment doc.

Your AI agent will need:

- A pool of stable test accounts per environment (TEST, CERT, PROD‑DEBUG).
- Some flagged as Spinner/Roller/VIP segments once the segmentation library is implemented (see automation assessment action items).

### 3.5 Deposit flows

- High‑level wallet flows are referenced in many docs; for a concrete flow see **Bally’s Casino – Cash at Fanatics Venue – Overview & FAQs**:  
  https://betfanatics.atlassian.net/wiki/spaces/SB/pages/670564489/Bally+s+Casino+-+Cash+at+Fanatics+Venue+-+Overview+FAQs  

  It describes:

  - **Deposit**:
    - Customer deposits cash at **retail venue**; mobile app wallet updated.
    - Deposit limits: `$50.00 – $100,000.00`.
    - Responsible gaming deposit limits can block deposit (error messaging defined).
  - **Withdrawal**:
    - Customer requests withdrawal to a retail venue; multi‑step approval process; 48‑hour review SLA.
    - Withdrawal limits: `$50.00 – $100,000.00`.

- Standard online deposit flows (cards, bank, Interac in Canada, etc.) are referenced here:  
  - **CAN: Casino Account Creation & Onboarding – Deposit Readiness**  
    https://betfanatics.atlassian.net/wiki/spaces/CL2/pages/2354053213/CAN+Casino+Account+Creation+Onboarding  

    > “Interac supported at launch… Deposit screen accessible only after successful KYC… Payment method saved for future deposits/withdrawals…”

Your AI QA agent should treat deposit flows as P0 (see P0 doc: “Deposit Flows – Standard, in-game, quick, card error handling”).

### 3.6 Withdrawal flows

From Bally’s doc again:

- Withdrawals can be made via **Cash at Fanatics Venue** with strict state/location constraints.
- Errors include:
  - Transaction not approved / wrong location / account status not Active.

Doc:  
https://betfanatics.atlassian.net/wiki/spaces/SB/pages/670564489/Bally+s+Casino+-+Cash+at+Fanatics+Venue+-+Overview+FAQs  

Additionally, the P0 doc has **“Withdrawal Flow – Completion, failure messaging, balance updates”** as Critical.

---

## 4. FEATURE FLAGS & CONFIGURATION

### 4.1 LaunchDarkly usage for Casino

- **Casino Launch Darkly Flags/Configs**  
  https://betfanatics.atlassian.net/wiki/spaces/CAS/pages/351109540/Casino+Launch+Darkly+Flags+Configs  

  Key flags:

  - **Casino Feature** (bool):
    - Used to determine if the entire **Casino section / bottom nav** is enabled.
    - Targeted by **state**.
  - **Casino Config** (JSON):
    - Large JSON blob controlling various Casino‑specific feature settings and enablement.
    - Current payload referenced from: [casino-config JSON link in that page].

- **LaunchDarkly Feature Flags Used to Manage Content (CMS)**  
  https://betfanatics.atlassian.net/wiki/spaces/CAS/pages/1966506000/LaunchDarkly+Feature+Flags+Used+to+Manage+Content+CMS  

  Lists many **Casino‑specific client flags**, e.g.:

  - `client-casino-stac-nav-bar-config`: controls bottom nav config for standalone casino; Variation 9 includes `"wheelSpinTitle": "Daily Spin"`.
  - `client-casino-fancash-jackpots-config`: configures jackpot names & metadata.
  - `client-casino-fancash-jackpots-notifications-config`: text for FanCash Jackpots notifications.
  - `client-casino-fancash-jackpots-standalone-widget-config`: widget text.

- **Casino – LaunchDarkly Banner**  
  https://betfanatics.atlassian.net/wiki/spaces/FSM/pages/1683423326/Casino+-+LaunchDarkly+Banner  

  Uses a **Manual Notification Banner** flag with JSON like:

  ```json
  {
    "enabled": true,
    "notificationData": {
      "body": "Select casino games will be temporarily unavailable due to planned maintenance by our third party provider...",
      "targetScreens": ["CASINO"],
      "title": "Select Casino Games temporarily unavailable"
    }
  }
  ```

  Targeting by `region_code.key` for specific states.

### 4.2 LaunchDarkly projects / keys

- FBG uses a shared LD project **“Fanatics Betting & Gaming”** for all platforms (Sportsbook, Casino, shared services).  
  See **Guide: Using LaunchDarkly**:  
  https://betfanatics.atlassian.net/wiki/spaces/FanExchang/pages/1779729399/Guide+Using+LaunchDarkly  

  For FMX they re‑use FBG project; same idea applies to STAC.

The page doesn’t expose the raw project key string, but implies:

- Project: **Fanatics Betting & Gaming**.
- Environments: `DEV`, `TEST`, `CERT`, `PRODUCTION` (similar to app envs).

Your AI agent will need environment‑specific LD SDK keys (backed by `fbg-feature-util`).

### 4.3 Other remote configs

Besides LaunchDarkly, Casino content is also driven by:

- **CMS (Playmaker / Contentful)** for:
  - Game metadata and tiles (via Games Manager, see FAST Automation doc).
  - FanCash → Casino Credit conversion rate management:  
    https://betfanatics.atlassian.net/wiki/spaces/CAS/pages/1529905166/FanCash+to+Casino+Credit+Conversion+Rate+Architecture  

- Some LD flags are misused as **copy CMS**; that’s being remediated per the CMS flags doc.

---

## 5. RESPONSIBLE GAMING & COMPLIANCE

### 5.1 RG features in app

From **iCasino P0 User Journeys** and **Casino Standalone QE Status** RG section:

- Responsible Gaming P0s:
  - **Responsible Gaming Enforcement** – session limits, bet limits, deposit limits, reality checks.
  - **State & Compliance Gating** – geo‑based gating, regulatory messaging, state approval enforcement.

Confirmed test coverage:

- Set/update/cancel:
  - **Wager limits**
  - **Deposit limits**
  - **Session limits**
- Validate:
  - Deposit limits across payment methods.
  - Session limit persists across state changes and app restarts.
  - Auto‑spin until session limit met.
  - Reality check banners on STAC per RG settings.

Doc:  
https://betfanatics.atlassian.net/wiki/spaces/QE/pages/1216479233/Casino+Standalone+QE+Status  

### 5.2 Geolocation provider

- **GeoComply & Eligibility**  
  https://betfanatics.atlassian.net/wiki/spaces/CAT/pages/128516222/GeoComply+Eligibility  

- **iCasino GeoComply**  
  https://betfanatics.atlassian.net/wiki/spaces/QE/pages/370835462/iCasino+GeoComply  

Explicit: FBG integrates **GeoComply** for Casino and Sportsbook:

- GeoComply generates “geolocation tokens” with TTL.
- Tokens cached in Redis via Kafka pipelines.
- iCasino launch uses tokens from cache; **expired/invalid tokens do NOT prevent game launch but block bet placement**.

### 5.3 US casino states where FBG operates & differences

From **Casino Onboarding – Part 1: Introduction to Casino & Online Gaming**  
https://betfanatics.atlassian.net/wiki/spaces/CAS/pages/2360737855/Casino+Onboarding+Part+1+Introduction+to+Casino+Online+Gaming  

> “FBG is live with Casino in:
> * New Jersey  
> * Pennsylvania  
> * Michigan  
> * West Virginia (RNG only)”

State‑specific differences:

- **West Virginia**:
  - RNG only; **no live dealer**.
- **PA / NJ / MI**:
  - support both **RNG slots/table games** and **live dealer** where licensed.
- Various state‑specific RG and UX requirements captured in:
  - **Fanatics Live‑States Cheat Sheet**  
    https://betfanatics.atlassian.net/wiki/spaces/TE/pages/684294194/Fanatics+Live-States+Cheat+Sheet  

  This doc lists:

  - Where Casino is legal vs Sportsbook only.
  - State‑specific RG prompts, logos, session displays, 14‑day MFA, payment method caps, etc.

Your AI agent should parameterize flows by **jurisdiction code** (e.g., `MI`, `NJ`, `PA`, `WV`).

---

## 6. PROMOTIONS & BONUSES

### 6.1 Promotion types

From **PRD – New Entitlement Options for Casino Credit Bonuses via XP [m20]** and the QE doc:  
PRD: https://betfanatics.atlassian.net/wiki/spaces/CAS/pages/949944355/PRD+-+New+Entitlement+Options+for+Casino+Credit+Bonuses+via+XP+m20  
QE doc: https://betfanatics.atlassian.net/wiki/spaces/QE/pages/1029767244/Promos+New+Entitlement+Options+for+Casino+Credit+Bonuses  

Casino promotion features include:

- **Casino Credits**:
  - Earned via:
    - Casino wagering entitlements (game or category specific).
    - Sportsbook wagering entitlements (bet sports to earn casino credits).
  - Redeemed in any casino game (subject to rules).

- **Free Spins**:
  - Daily Spin free spins.
  - Promo‑specific free spins (e.g. “Play 5 spins at $1 on Cleopatra”).

- **FanCash incentives**:
  - FanCash Jackpots.
  - Deposit bonuses denominated in FanCash.

- **RAF (Refer‑a‑Friend) Casino Wagering promos**:
  - RAF test plans confirm integration with **casino wagering** as reward trigger:
    https://betfanatics.atlassian.net/wiki/spaces/QE/pages/1673691137/FEAT-5354+RAF+-+Short-term+Support+for+Casino+RAF+Test+Plan  

Welcome bonuses, cashback, referrals, etc. are typically orchestrated via the **XP (XtremePush)** bonus engine & NATS trading APIs.

### 6.2 Wagering requirements

Detailed spec: **Fanatics Casino – Wagering Requirements/Playthrough**  
https://betfanatics.atlassian.net/wiki/spaces/~63cafead1d7734b550c29b9a/pages/2547384627/Fanatics+Casino-+Wagering+Requirements+Playthrough  

Key points:

- Historically, Fanatics favors **1x playthrough** for simplicity.
- This doc outlines potential support for:

  - **Game‑level playthrough multipliers** (slots vs table games).
  - **Contribution rates** (e.g. table games contribute 20% to playthrough).
  - **Deposit match playthrough**: wagering on deposit + bonus.
  - **Order of funds** (cash vs bonus).
  - **Casino credit drop** as non‑withdrawable promo funds until requirements met.
  - **FIFO bonus processing** if multiple bonuses active.
  - **Reg‑driven progression tracking UI** (especially PA).

At present, this is WIP; your AI agent should:

- Understand that **1x playthrough** is baseline.
- Be able to simulate extended playthrough scenarios once implemented.

### 6.3 Promo configuration surface

Promos are primarily configured in:

- **XP (XtremePush)** for entitlements and casino credit bonuses.  
  (See PRD & QE docs above.)
- **NATS Backoffice** via Trading API endpoints:
  - `/ats-trader/api/bonus/add`, `/bonus/list`, `/ats-trader/api/bonus/bulkAwards/casinoCredit/award`, etc.  
    https://betfanatics.atlassian.net/wiki/spaces/SB/pages/1372323869/Trading+API+Endpoints  

- **Playmaker** for FanCash → Casino Credit conversion rate management.  
  https://betfanatics.atlassian.net/wiki/spaces/CAS/pages/1529905166/FanCash+to+Casino+Credit+Conversion+Rate+Architecture  

Your AI agent doesn’t need write access, but it should read promo IDs and rules from API responses, and align them with UI expectations.

---

## 7. CI/CD & BUILD PIPELINE

### 7.1 CI/CD system

From **Bitrise CI/CD Quick Start & User Guide**:  
https://betfanatics.atlassian.net/wiki/spaces/Atlas/pages/1373863983/Bitrise+CI+CD+Quick+Start+User+Guide  

FBG is migrating mobile CI/CD from GitHub Actions to **Bitrise**:

- Mobile release pipelines in Bitrise for:

  - **Cut Mobile Release** (from release branch):
    - Creates 12 builds:
      - iOS: Sportsbook (test, cert, prod‑debug), Casino (test, cert, prod‑debug).
      - Android: Sportsbook and Casino same.
  - **Mobile Release Production Builds**:
    - Creates **8 builds**:
      - iOS:
        - Sportsbook prod + prod‑debug.
        - Casino prod + prod‑debug.
      - Android: same.

- For ad‑hoc builds, there are individual workflows:
  - `ios-cd-casino-dev`, `ios-cd-casino-test`, `ios-cd-casino-cert`, `ios-cd-casino-prod-debug`, `ios-cd-casino-prod`, etc.

### 7.2 Distribution & artifact storage

- **[Spike] Investigate Pulling Builds from Bitrise Instead of GitHub Actions**  
  https://betfanatics.atlassian.net/browse/QE-11498  

Explains how to:

- Use Bitrise APIs with workspace / personal access tokens.
- Retrieve builds by workflow (`ios-cd-casino-cert`, `android-cd-casino-test`, etc.).
- Enumerate artifacts and download APK/IPA via `expiring_download_url`.

Distribution to QA:

- For CERT/PROD builds, distribution is via **TestFlight (iOS)** and Android equivalent (internal testers). From STAC integration doc:
  - CERT builds for STAC are distributed via TestFlight / App Tester for GLI and state testers:
    https://betfanatics.atlassian.net/wiki/spaces/TE/pages/1254130082/Integration+Status+Stand+Alon+Casino+App+STAC  

Where APKs/IPAs live:

- **Primary source of truth** is Bitrise artifacts fetched via API (per QE‑11498).
- For internal testers, they’re surfaced via TestFlight / Google internal testing tracks.

### 7.3 Release cadence

No doc explicitly states “weekly” or “bi‑weekly”, but:

- Presence of **cut‑release** and **mobile-release-production-builds** pipelines, plus frequent release blockers, suggests at least **bi‑weekly** (often weekly/hotfix) cadence.
- 2025 Gaming Engineering OKRs emphasize high delivery cadence and 80%+ milestone delivery for iCasino:  
  https://betfanatics.atlassian.net/wiki/spaces/Transforme/pages/882835529/2025+Gaming+Engineering+OKRs  

Your QA agent should be designed for **continuous** regression (nightly against TEST/CERT, smoke on PROD‑DEBUG).

---

## 8. NETWORK & API LAYER

### 8.1 API style

- Internal services are overwhelmingly **REST**:
  - Trading API endpoints under `/ats-trader/api/...`.
  - Reward API (`/reward/v2/fancashConversion`), etc.
  - Manager Multiplier API uses REST:  
    https://betfanatics.atlassian.net/wiki/spaces/CAT/pages/1624014850/FEAT-5517+API+Contracts+-+REST-+Manager+Multiplier  

- GraphQL is used in other domains (Odds API) but not obviously for Casino game flows; DSEA doc shows GraphQL vs REST but not Casino‑specific:  
  https://betfanatics.atlassian.net/wiki/spaces/DATA/pages/341280615/GraphQL+vs+REST+API  

Game search uses REST:

- `/search/v1?q=...&domain=casino&jurisdictionCode=MI` etc.  
  https://betfanatics.atlassian.net/wiki/spaces/Helios/pages/407537564/Casino+x+Search+Query+API  

### 8.2 Key endpoints for balance, bets, sessions, deposits, withdrawals

While there’s no one consolidated “casino API spec” in the snippets, relevant pieces:

- **Bonuses & Casino credit** (Trading API):  
  https://betfanatics.atlassian.net/wiki/spaces/SB/pages/1372323869/Trading+API+Endpoints  

  - `/ats-trader/api/bonus/bulkAwards/casinoCredit/award`
  - `/backoffice/rest/customerdata/void/bonus/casinocredit`

- **FanCash → Casino Credit conversion**:
  - Reward API bug:  
    https://betfanatics.atlassian.net/browse/WHEEL-43  

    Endpoint: `/reward/v2/fancashConversion` with `bonusType` `"casino_credit"` or `"bonus_bet"`.

- **Casino play / W2G detail search**:
  - `/ats-trader/api/bets/casino/w2g/detail/search`

- **Casino search**:
  - `/search/v1` with `domain=casino-game` and `jurisdictionCode`.

- **Geolocation** (GeoComply for Casino):
  - iCasino GeoComply doc references **geocomply write/read endpoints** and Redis cache, though not explicit URIs in snippet:
    https://betfanatics.atlassian.net/wiki/spaces/QE/pages/370835462/iCasino+GeoComply  

Your AI agent should:

- Use mobile proxy (e.g., Charles/Proxyman) to auto‑discover live endpoints for:
  - Balance (wallet REST endpoint).
  - Game launch (game session token endpoint).
  - Bet placement (RGS→RGI).
  - Deposit/withdrawal (payments API).
- Then overlay them with the REST docs above.

### 8.3 Proxyman / Charles usage

Search snippets don’t explicitly mention Proxyman/Charles configs, but many QE investigations require network debugging. Given standard practice at FBG, it’s safe to assume:

- QE uses Charles/Proxyman + Prod‑Debug/CERT builds with proxy support.
- For your agent, you’d capture traffic via the OS proxy or add instrumentation at the KMM networking layer.

---

## 9. KNOWN ISSUES & EDGE CASES

Summarizing top recurring bug categories from the Jira samples:

1. **Wallet & Casino Credit Display / Integration**
   - OLY‑885, VLAD‑443, QE‑13452, ICG‑2761.

2. **Promo Abuses / Logic Bugs**
   - Free spins re‑use: SHOCK‑2421.
   - Casino credit progression not reflected or miscounted.

3. **Session & Authentication Edge Cases**
   - WEB‑888 – logout after long gameplay + refresh.
   - Various Fan ID login / welcome UX issues (MAGU‑5656).

4. **FanCash & Loyalty Integration**
   - WHEEL‑904 – tier points not updating while FanCash is earned.

5. **In‑Game Balance Sync After Funding**
   - OGX‑3288 – user must restart game after converting FanCash to Casino Credit.

6. **RG / State Cross‑border Behavior**
   - Verified via Geo task force doc; cross‑state sessions & bet placement edge cases:
     https://betfanatics.atlassian.net/wiki/spaces/AOBG/pages/1463616318/Geo+task+force+Live+states+Geo+Drive+testing  

7. **UI/UX Layout Issues**
   - ICG‑2601 / ICG‑2637 – casino tile spacing, dynamic tile injection quirks.

8. **Content / Copy Configuration via LaunchDarkly**
   - TRAIL‑217 – bonus text displayed incorrectly on FanCash → Casino Credit conversion page.  
     https://betfanatics.atlassian.net/browse/TRAIL-217  

9. **Game provider‑specific bugs**
   - OGX‑3288 lists provider coverage and notes behavior differences (e.g., some providers need multiple spin attempts after deposit).

10. **Accounting / Transaction Record Issues**
    - VLAD‑593 – casino session transaction incorrectly shows casino credits redeemed $0.0.  
      https://betfanatics.atlassian.net/browse/VLAD-593  

Your AI agent should be particularly robust on:

- Cross‑component flows (promo → wallet → provider balance).
- Long‑running sessions (session tokens, RG timers, GeoComply TTL).
- Cross‑state transitions while games are active.

---

## 10. TEAM & PROCESS

### 10.1 Who owns Casino QA

From various docs:

- **Casino Standalone QE Status** is owned by **Leshon Alexander (Casino QAE)**.  
  https://betfanatics.atlassian.net/wiki/spaces/QE/pages/1216479233/Casino+Standalone+QE+Status  

- **Casino FAST Automation** doc is authored by the same QE contact and references cross‑team dependencies for Games Manager, Polly, etc.  
  https://betfanatics.atlassian.net/wiki/spaces/~632dabbe140ba0bf651a3543/pages/1703248195/Case+Casino+FAST+Automation  

- Presence QA strategy doc lists domain squads and external QA vendor for Sportsbook/CAT/FanX; Casino now has its own dedicated QE but uses similar processes:  
  https://betfanatics.atlassian.net/wiki/spaces/TE/pages/34374035/Presence+QA+Strategy+Fanatics+Sportsbook+CAT+FanX  

### 10.2 Dev → QA handoff

Implicit from process docs:

- Dev writes feature stories & PRDs; QE defines test plans.
- QE attends squad ceremonies, then:

  1. Feature built in DEV.
  2. QE performs **iterative testing**.
  3. Merges/releases to TEST; QE runs regression.
  4. CERT deployment; QE runs final regression and bug bash.
  5. PROD deployment with post‑launch validation & prod bug bash.

The **P0 Journeys** doc declares **Definition of Done for P0 Automation**, which is essentially your agent’s acceptance criteria:

- Happy path covered.
- At least one failure state validated.
- State gating validated (geo/compliance).
- Segmentation validated (logged out, logged in, VIP).
- Performance signals captured where relevant.
- Reward settlement validated.

### 10.3 Reporting / dashboards

While no explicit dashboard link surfaced in search, we have:

- Weekly QE status reports referenced in multiple test plans:
  - e.g., Fanatics Five test plan:  
    https://betfanatics.atlassian.net/wiki/spaces/FAN/pages/492996784/TestPlan+Fanatics+Five+Daily+and+Jackpot+Test+Cases  

- Data & reconciliation dashboards for game provider reconciliation:  
  https://betfanatics.atlassian.net/wiki/spaces/DATA/pages/656474734/ICasino+Game+Provider+Reconciliation+Runbook  
  https://betfanatics.atlassian.net/wiki/spaces/DATA/pages/892797174/Reconciliation+Game+Provider+Integration  

Your AI QA agent could hook into:

- Jira (for automatic P0 bug creation).
- Datadog metrics (for performance thresholds).
- Existing QE status reports as read‑only outputs.

---

## How this maps to your AI QA agent

Given all of the above, a practical next step is:

- Define **agent test suites** directly from the P0 table:  
  https://betfanatics.atlassian.net/wiki/spaces/~6414c91c5534b0bf7440ceac/pages/2718498826/iCasino+P0+User+Journeys+-+Managed+by+ogx-bot  

- For each P0 journey, bind:
  - Environment(s) (`test`, `cert`, `prod-debug`).
  - Jurisdictions (MI/NJ/PA/WV).
  - Required feature flags (from the Casino LD pages).
  - Dependent providers (from the RGS matrix).
  - Existing manual test cases (QE‑Tx IDs).
  - Known bug patterns (from the Jira links above).


