# Danny Ocean — Things to Catch

> A field-sourced catalogue of real issues observed in Fanatics Casino production and lower environments, compiled from #icasino-content-operations, #icasino-experiences-hub, and #icasino-support Slack channels (May 2025 – May 2026). Use this as Danny's prompt layer for what to watch for during gameplay, app navigation, and general app usage.

---

## 1. Game Launch & Loading Failures

These are among the highest-impact issues — a player taps a game and gets nothing.

| What to catch | Real example | Severity |
|---|---|---|
| **Game loads to blank white screen** | Triple Cash Eruption showed blank white on launch day in prod (Dec 2025) | CRITICAL |
| **Game error after FanCash Spins deep-link** | Player won free spins in FC Spins, tapped the eligible game popup, game wouldn't load and threw an error message (Mar 2026) | HIGH |
| **Free spin deep-link fails but organic launch works** | Cash Eruption deep-link from promo produced an error; game worked fine when accessed through the lobby (Jan 2026) | HIGH |
| **"Players Hub" error blocking free spins** | Users awarded 500 FS sign-up offer to Cash Eruption — spins said "awarded" but couldn't be used due to a "players hub" error in-game (Jan 2026) | HIGH |
| **403 errors on game assets in CERT/lower envs** | Web CERT PA returning 403 from OGS translation JSON and CloudFront gameconfig.json (Apr 2026) | MEDIUM |
| **Game launch broken by new build** | New dev build broke game launch entirely in dev environment (Apr 2026) | HIGH |
| **Games failing to load detected via Launch-to-Wager analytics** | Multiple games identified with abnormally low Launch-to-Wager rates — players launching but unable to actually play. Caught through data analytics, not manual QA (Oct 2025) | HIGH |
| **Deep-link "Something went wrong" error on promo banners** | Promotional banner deep-links landing on a "Something went wrong" error screen instead of the target game or page (Sep 2025) | HIGH |
| **Slow game loads from specific provider (Aristocrat)** | Aristocrat/Pariplay games exhibiting noticeably slow load times compared to other providers (Jul 2025) | MEDIUM |

**Danny prompt**: After every game launch, verify the game renders fully (not blank/white), the spin/bet button is interactable, and no error modal is blocking gameplay. On deep-link launches (from FC Spins, promos), verify the free spins are actually usable in the game. Track launch-to-first-wager time — if a game loads but no wager can be placed, that's a silent launch failure.

---

## 2. Game Freezes, Crashes & Visual Glitches During Play

| What to catch | Real example | Severity |
|---|---|---|
| **Game freeze → flash white/black → unresponsive buttons** | Triple Cash Eruption on Android tablet: game freezes mid-play, spazzes out, flashes white/black, buttons go unresponsive, requires force-close. Outcome settles in background. Happened across both Combo and STAC builds (Mar 2026) | CRITICAL |
| **Portrait/landscape rotation breaks game UI** | Road to Gold (WHG game): switching back from landscape to portrait mode broke the display — buttons hidden, only side panel visible (Apr 2026) | HIGH |
| **Casino Game Header resizing / jackpot component jitter** | Header buttons jump and slide outward, games get stretched/re-sized, clipping occurs — related to Jackpot component loading (May 2026) | MEDIUM |
| **iOS app crash from CMS tray widget** | A CMS-configured Casino S-M Tray caused iOS to crash entirely; Android was fine (Mar 2026) | CRITICAL |
| **iOS crash from TileMediumBadgeRow** | TileMediumNormalView badge row crashing iOS on MI Test environment, needed hotfix (Mar 2026) | CRITICAL |
| **Game crash during bonus round with significant funds** | Player experienced game crash mid-bonus round with substantial wager in play — led to regulatory complaint. Outcome unclear to player (Jan 2026) | CRITICAL |
| **"Active Game Round" dialog persisting after round completion** | Dialog warning about an active game round kept appearing even after the round had settled, blocking normal gameplay flow (Aug 2025) | HIGH |
| **Instant Blackjack overlay displaying on all pages** | Instant Blackjack game overlay incorrectly rendering on top of non-game pages, blocking interaction across the app (Oct 2025) | HIGH |
| **In-game toast showing wrong casino credit info** | Toast notification inside the game displaying incorrect casino credit balance or bonus info, misleading the player (Oct 2025) | MEDIUM |
| **Constant cyclic re-render causing scroll jitter** | App lobby entering a cyclic re-render loop causing scrolling jitter, delayed content display, and missing content. Affected both STAC and SBM (Oct 2025) | HIGH |

**Danny prompt**: During gameplay, watch for: sudden white/black screen flashes, unresponsive spin/bet buttons, UI elements disappearing after device rotation, the game header resizing or clipping, unexpected overlays from other games appearing on-screen, and "Active Game Round" dialogs that won't dismiss. If any of these occur, capture a screenshot and record the game name, device orientation, and build version. Pay special attention during bonus rounds — crashes mid-bonus are the highest-severity incidents due to regulatory exposure.

---

## 3. Lobby & Navigation Issues

| What to catch | Real example | Severity |
|---|---|---|
| **Trays appearing out of order vs CMS config** | Trays showing in wrong position on STAC prod debug — Video Poker appeared where it shouldn't, tray replaced by wrong widget after CMS save (Mar 2026) | HIGH |
| **Jackpots route completely empty** | Bottom nav "Jackpots" tab led to an empty page in prod MI — both STAC and SBM affected (Feb 2026) | HIGH |
| **Bottom nav item unexpectedly reverting** | "Jackpots" tab reverted to "Slots" in prod-debug without anyone making the change (Feb 2026) | MEDIUM |
| **Laggy scroll on lobby / OneLounge** | Incredibly laggy scrolling on OneLounge in prod, user gets stuck at top of page (Mar 2026) | HIGH |
| **iOS jerky scroll behavior (P1 incident)** | GIFs in MI prod lobby caused jerky scrolling severe enough for a P1 incident; mitigated by removing GIFs (Jan 2026) | CRITICAL |
| **Category nav (CatNav) dropdown issues** | Opening tray sometimes doesn't allow scroll down; scrolling sometimes closes the tray instead (Mar 2026) | MEDIUM |
| **Inconsistent scrolling in ModalBottomSheet** | Known Jetpack Compose issue affecting bottom sheet scroll behavior — launch blocker (Mar 2026) | HIGH |
| **Recommended games tray buried too deep** | Recommended games tray positioned far down the lobby beneath Live Dealer, away from optimal placement (Jan 2026) | LOW |
| **Invite text cut off in bottom nav** | "Invite $$" / "Earn $XX" text getting truncated in bottom nav label (Jan 2026) | MEDIUM |
| **Promotions carousel missing** | Entire promotions carousel not showing for anyone in prod debug apps (Sports + Casino), only xs content cards appearing (Apr 2026) | CRITICAL |
| **FCS Bottom Nav button blocking interaction (P1)** | FanCash Spins button in bottom nav overlapping and blocking other interactive elements on Android — escalated as P1 incident (Dec 2025) | CRITICAL |
| **Category content disappearing / blank category page** | Selecting a game category (e.g. Slots, Table Games) loaded a blank page with no game tiles — content disappeared entirely (Sep 2025) | HIGH |
| **iOS categories ghosting when one is selected** | On iOS, selecting one category caused other category labels/tabs to visually ghost or disappear, confusing navigation (Oct 2025) | MEDIUM |
| **Extra search bar appearing on casino pages** | A sports search bar incorrectly rendering on the casino Jackpots page and other casino-specific screens (Sep 2025). Broader duplicate/extra search bar bug caused major issues across the app (Oct 2025) | HIGH |
| **Promo cards showing blank screens** | Tapping promotional content cards led to blank screens instead of the promo details or target page (Nov 2025) | HIGH |

**Danny prompt**: After navigating to any lobby screen, verify: all trays render in the expected order, trays are not empty when they should have content, the bottom nav shows all expected tabs (Home, Jackpots, etc.) without overlapping/blocking other elements, scrolling is smooth with no jitter or cyclic re-render loops, CatNav dropdown opens/closes properly, selecting a category loads its game tiles (not a blank page), and no duplicate/extra search bars appear. Tap every promo card and verify it loads content (not a blank screen).

---

## 4. Game Tiles, Images & Search

| What to catch | Real example | Severity |
|---|---|---|
| **Game tile showing no image (blank tile)** | Top Live Dealer game in PA showing no tile image at all (Mar 2026) | HIGH |
| **Hero tile wrong size / stretched / squished** | Crazy Time Live Dealer hero tile was old small format, then appeared stretched after initial fix (Mar 2026). Blackjack hero tile also wrong size (Feb 2026) | MEDIUM |
| **Incorrect image loaded on tile** | Wrong image displayed on a game tile (Apr 2026) | MEDIUM |
| **Tile metadata clipping** | New game tile showing metadata that overlaps or clips the tile display (Apr 2026) | LOW |
| **Image sizing issues in FanCash Spins** | Smash Hammer Gold image too big after winning free spins in FanCash Spins (Mar 2026) | MEDIUM |
| **Web tile not showing at all** | Marble Races tile not rendering on web platform while working on mobile (Feb 2026) | MEDIUM |
| **Game not appearing in search** | New game (Super Cash Boost: Hold & Win) was LIVE in Playmaker but didn't appear in search, and "New" tagline wasn't displaying (Feb 2026). Ongoing issue with newly released games (Feb 2026) | HIGH |
| **Clipping on Android** | Visual clipping observed on Android game display (May 2026) | MEDIUM |

**Danny prompt**: For every game tile visible in the lobby, verify: image renders (not blank), image is not stretched/squished, tile metadata doesn't clip, and "New" badge appears on recently launched games. Try searching for the current game by name — verify it returns results.

---

## 5. FanCash Spins & Bonus Issues

| What to catch | Real example | Severity |
|---|---|---|
| **Free spins awarded but not usable in game** | Users won bonus in FC Spins, bonus visible in Nats, but not shown in-app account area or in the game itself — game charged $2 real money for the spin instead (Mar 2026) | CRITICAL |
| **Free spins not awarded at all** | PA users not receiving FS for Hyperova Megaways PA after promo fulfillment — setup appeared correct (Jan 2026) | CRITICAL |
| **WHG outage causing missed spin awards** | Provider outage meant customers who were supposed to get spins did not receive them (Mar 2026) | HIGH |
| **Unexpected free spins appearing in account** | Bunch of free spins appearing in account that the user didn't win — potentially from a test (Jan 2026) | MEDIUM |
| **"Spin Now" CTA not clickable** | FanCash Spins popup "Spin Now" button was not clickable — only the X close button worked (Apr 2026) | HIGH |
| **Geolocation notice after FanCash Spins win** | Player in NJ (with past CO geolocation) won spins and was immediately hit with Colorado Player Prop legislation notice (Mar 2026) | MEDIUM |
| **Free Spins stuck in "Pending Activation" for 30-60+ minutes** | Awarded free spins remained in "Pending Activation" status for extended periods (30–60+ minutes) before becoming usable — players thought they weren't awarded (Jun 2025) | HIGH |
| **Free Spins "Insufficient Funds" error charging real money** | Player awarded free spins saw an "Insufficient Funds" error when trying to use them — system attempted to charge real money instead of applying the free spin credit (May 2025). Pattern repeated in Mar 2026 with a different game | CRITICAL |

**Danny prompt**: When interacting with FanCash Spins: verify the spin animation completes, verify any won spins appear in account (check they're not stuck in "Pending Activation" — re-check after 2 minutes), verify deep-link to the eligible game works, verify free spins are loaded in the game (not charged real money — watch for "Insufficient Funds" errors on free spin games), and verify no unexpected geolocation popups appear.

---

## 6. Jackpot Display Issues

| What to catch | Real example | Severity |
|---|---|---|
| **Jackpot ticker values not showing** | Backend Jackpot ID strings updated, frontend jackpot values stopped coming through on both web and mobile in prod (Mar 2026) — 62-reply thread | HIGH |
| **Jackpot tickers stopped on EVO/Red Tiger games** | Jackpot tickers stopped working specifically on Evolution (Red Tiger) content (Apr 2026) | HIGH |
| **Jackpot ticker Playmaker issue (recurring)** | Known recurring issue with Jackpot Ticker in Prod Playmaker (Jan 2026) | MEDIUM |
| **FanCash Jackpots in-game header not displaying** | In-game jackpot header not showing for some OGS games on iOS — root cause was wrong event mapping (gameLoaded vs gameReady) (Apr 2026) | HIGH |

**Danny prompt**: On any jackpot-themed game or jackpot tray, verify: ticker values are populated (not $0.00 or blank), tickers are actively updating, and the in-game jackpot header displays correctly.

---

## 7. Game Data & Configuration Mismatches

| What to catch | Real example | Severity |
|---|---|---|
| **Min/max bet display doesn't match game rules** | Blackjack X-Change game info showed $1-$250 but game rules stated $2500 max — incorrect since March 2024 (Mar 2026). Customer dispute over accepted wager exceeding displayed max | HIGH |
| **Game name mismatch between tile and info menu** | Game name on the tile differed from the name in the info/details menu (Jan 2026) | MEDIUM |
| **"DONOTUSE" prefix appearing in player history** | Disabled game versions renamed with "DONOTUSE-" prefix appeared in customers' Account Activity page as "DONOTUSE-Cash Eruption" (Feb 2026) | HIGH |
| **VIP game showing in non-VIP context** | Fortune Coin Fever Spins (VIP) appearing in non-VIP query-driven widgets due to game name/ID mismatch between systems (Feb 2026) | MEDIUM |
| **Provider miscategorization** | Lion Link Horse and Dancing Drums Link Fortune randomly changed from OGS_Rgs to PLAYZIDO without anyone making the change (Feb 2026) | MEDIUM |
| **Game IDs different between environments** | Prod game IDs differ from lower environment (CERT) IDs, complicating test automation (Feb 2026) | LOW |
| **Duplicate content trays** | "Because You Played" trays duplicated on the Homepage (Jan 2026) | MEDIUM |
| **Same games in consecutive containers (List then Grid)** | Arcade > Originals category showing identical games as List and then immediately as Grid in prod MI (May 2026) | MEDIUM |
| **Non-progressive game in progressive category** | Bonanza Christmas appearing at the front of the Daily Drop Progressive category despite not being a progressive game (Dec 2025) | MEDIUM |

**Danny prompt**: On game info screens, cross-check: displayed min/max bet matches in-game limits, game name is consistent between tile and info menu, no "DONOTUSE" prefix in game titles, and VIP-only games don't appear in standard trays.

---

## 8. CMS & Content Issues

| What to catch | Real example | Severity |
|---|---|---|
| **Empty CMS trays visible to users** | Query-driven trays ("Because You Played", "Our Top Picks For You", "Try Something New", "Your Preferred Games") returning empty for some users — trays should auto-hide but worth flagging (May 2026) | MEDIUM |
| **"From the Creators of" tray not returning games** | Red Tiger games not returning results for the "From the Creators of" content source tray (Feb 2026) | MEDIUM |
| **Hero images missing on web** | Web hero images showing badly or missing entirely because no web-specific hero assets were uploaded (Mar 2026) | MEDIUM |
| **Content card images wrong size** | Content card images bigger than others causing layout issues in promotions area (Feb 2026) | LOW |
| **Providers page created but empty** | A Providers page existed in CERT with no content built out (Dec 2025) | LOW |
| **RAF bottom nav showing wrong dollar amount** | "Earn $80" in bottom nav leading to a page with a lower-than-advertised RAF offer after promo values changed (Feb 2026) | HIGH |
| **CERT environments showing no content outside FanCash widget** | CERT test environment rendering only the FanCash Spins widget — all other lobby content (trays, heroes, games) completely absent (Nov 2025) | MEDIUM |
| **Endless client parse error logs for CasinoSocketUpdate** | Client continuously logging parse errors for CasinoSocketUpdate messages, cluttering logs and potentially impacting performance (Aug 2025) | MEDIUM |

**Danny prompt**: On lobby screens, check for: empty trays that should have content, trays with missing game recommendations, hero images that look stretched/missing, and any promotional CTAs that don't match their destination content.

---

## 9. Performance & Latency

| What to catch | Real example | Severity |
|---|---|---|
| **Casino page latency spike** | Latency increase on /page/casino-promos possibly from accumulated old promos not being cleaned out (Jan 2026) | HIGH |
| **Promos page latency** | Spike in casino promos page latency noticed by on-call (Mar 2026) | MEDIUM |
| **iOS 10-second unnecessary wait on OGS games** | Wrong event mapping (gameLoaded instead of gameReady) caused iOS users to always wait 10 seconds on some OGS games even if they loaded faster (Apr 2026) | HIGH |
| **Circuit breaker trips in Casino Experience** | Downstream 500s silently swallowed as warnings, causing circuit breaker trips — ERROR_NO_RECOMMENDATIONS and ERROR_REFERENCE_GAME_MISSING_STUDIO responses (Feb 2026) | HIGH |
| **Game load times degraded (specific title)** | Huff and Lots of Puff showing long load times in PA with CS complaints (Jan 2026) | MEDIUM |
| **Light-to-moderate service impact** | Cross-board service impact lasting ~14 minutes in early morning (May 2026) | MEDIUM |
| **Cyclic re-render causing lobby performance degradation** | Constant cyclic re-rendering in the lobby caused scrolling delay, jitter, and content failing to display. Affected multiple app entry points (Oct 2025) | HIGH |
| **Provider-specific slow loads (Aristocrat/Pariplay)** | Games from the Aristocrat/Pariplay provider consistently loading slower than other providers, generating CS complaints (Jul 2025) | MEDIUM |

**Danny prompt**: Time every game launch and lobby load. Flag any game that takes >10 seconds to load or any lobby screen that takes >5 seconds to render. Note if the app feels sluggish during scroll.

---

## 10. Provider Maintenance & Outages

These are not things Danny can "catch" by playing, but Danny should be **aware** of them as context for failures.

| Pattern | Example |
|---|---|
| **Scheduled OGS maintenance (frequent)** | Multiple states, usually 1:30 AM – 6:00 AM EST, gameplay unavailable during window |
| **IGT maintenance** | RGS upgrades, services unavailable during window |
| **Games Global maintenance** | Platform temporarily unavailable for up to 3 hours |
| **White Hat Studios maintenance** | Brief disruptions, 30-60 minute windows |
| **BOOM maintenance** | Services unavailable for 2-hour windows |
| **Provider pulling a game** | IGT requested Icy Wilds be taken down across all jurisdictions while investigating an issue (Feb 2026) |
| **Maintenance banner management** | On-call responsible for enabling/disabling LD maintenance banners per provider calendar |

**Danny prompt**: If a game fails to load or returns an error, check whether the game's provider is currently in a scheduled maintenance window before escalating as a bug.

---

## 11. Platform-Specific Issues

| Platform | What to catch | Real example |
|---|---|---|
| **iOS** | Crashes from CMS tray widgets, badge row rendering, wrong event mapping | Multiple iOS-only crashes (Mar 2026) |
| **iOS** | GIF-induced jerky scrolling (P1) | Lobby GIFs caused severe scroll jitter (Jan 2026) |
| **Android** | Visual clipping, game display issues | Clipping reported on Android (May 2026) |
| **Android tablet** | Game freeze + flash white/black | Triple Cash Eruption on Galaxy Tab S7+ (Mar 2026) |
| **Web** | Missing game tiles, hero images | Marble Races tile not showing on web (Feb 2026) |
| **STAC vs SBM** | Testing through different app entry points matters | Question raised about Casino testing via Sportsbook app vs STAC (Apr 2026) |

**Danny prompt**: For each issue found, note: app (STAC/SBM/Combo), platform (iOS/Android/Web), OS version, device model, and build number. Issues often reproduce on one platform but not the other.

---

## 12. Account & Balance Issues

| What to catch | Real example | Severity |
|---|---|---|
| **FanCash balance disappearing** | VIP customer UID 1082353 had ~$4k in FanCash vanish when converting to Casino Credits (Apr 2026) | CRITICAL |
| **Wager amount changing dramatically** | Player wagering $0.10 suddenly had 3 wagers for $20, $8, and $0.40 in rapid succession (5-second intervals) on game "One Coin" — regulatory complaint (Jan 2026) | CRITICAL |
| **Stuck rounds** | WWE Multi-Hand Blackjack stuck round where FBG returned HTTP 500 on wager acknowledgement (Mar 2026) | HIGH |
| **Session limit behavior unclear** | What counts toward session time limits — logged in? Playing? Game open but idle? (Feb 2026) | MEDIUM |
| **Account page navigation broken after game** | CERT web: clicking account icon after finishing a game redirects to home page instead of account page — missing quit-game confirmation dialog (Apr 2026) | MEDIUM |
| **Player with sufficient balance unable to place wagers** | Player had sufficient funds in their account but the game refused to accept wagers — no error message shown, just failed silently (May 2025) | CRITICAL |

**Danny prompt**: Before and after every gameplay session, check: balance is consistent (pre-play balance minus wagers plus winnings = post-play balance), no unexpected wagers appear in history, and navigating to Account shows correct info.

---

## Summary: Danny's Top-Priority Watchlist

1. **Game launches to blank/white/error screen** — especially after deep-links or free spin awards. Watch for silent launch failures (game loads but wager can't be placed)
2. **Game freezes mid-play** — flash white/black, buttons unresponsive, force-close required. Bonus round crashes are the highest-severity variant (regulatory exposure)
3. **Free spins awarded but not usable** — game charges real money instead ("Insufficient Funds" on a free-spin game). Also watch for spins stuck in "Pending Activation" for extended periods
4. **Jackpot tickers blank or $0** — values not populating on jackpot-themed content
5. **iOS crashes** — from CMS tray widgets, badge rendering, GIF scroll jitter, or category ghosting
6. **Lobby trays out of order or missing** — empty trays, wrong positions, promotions carousel gone, promo cards leading to blank screens
7. **Bottom nav blocking / overlapping** — FCS button overlapping other elements (P1 pattern), duplicate search bars appearing on wrong pages
8. **Game tiles missing images** — blank tiles, stretched heroes, missing web assets
9. **Balance discrepancies** — FanCash disappearing, unexpected wagers, stuck rounds, player unable to wager despite sufficient funds
10. **Min/max bet display doesn't match actual limits** — regulatory risk
11. **Performance degradation** — >10s game loads, laggy scroll, cyclic re-render loops, provider-specific slowness (Aristocrat)
12. **Game overlay / dialog leaks** — Instant Blackjack overlay on non-game pages, "Active Game Round" dialog persisting after settlement

---

*Compiled: 2026-05-20 from Slack channels #icasino-content-operations, #icasino-experiences-hub, #icasino-support — covering May 2025 through May 2026 (full year)*
