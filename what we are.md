What QA Actually Means for FBG
You're not testing the game engine — Gaming Realms owns that. You're testing your app as the platform. The concerns are completely different:

What FBG QA actually cares about:

Category	What You're Testing	Example
App launch & stability	Does the app open, not crash, render correctly	Cold start, background/foreground, kill & reopen
Game discovery	Search, browse, categories, filters work	Search "Slingo" → correct results appear
Game loading	Game launches inside the app shell correctly	Tap game tile → game loads → no white screen / infinite spinner
Balance integration	Your wallet talks to the game provider correctly	Balance before play = balance after play ± bet/win. No discrepancies.
Deposit / Withdrawal	Payment flows work end to end	Add $50 via card → balance updates → play → withdraw $30
Promotions & Bonuses	Promo codes apply, bonus cash credited, wagering requirements enforced	Apply "WELCOME100" → $100 bonus → can only withdraw after 10x wagering
Responsible Gaming	Deposit limits, loss limits, session timers, self-exclusion all enforced	Set $100 daily deposit limit → try to deposit $150 → blocked
Geolocation / Compliance	App correctly blocks/allows based on state	VPN to restricted state → app blocks play
Cross-device	Same account, different devices, same state	Play on Pixel 7 → switch to Samsung S24 → balance and history consistent
Feature flags	LaunchDarkly flags correctly show/hide features, games, promos	Flag slingo_cash_eruption_enabled=false → game not visible in catalog
Network resilience	App handles poor connectivity gracefully	Kill network mid-spin → app recovers, balance correct
New build regression	Every release, all of the above still works	CI triggers full test suite on every build
Multi-game coverage	Not just Slingo — every game in the catalog	100+ games all launch, play one round, settle correctly
The game itself (RTP, symbol distribution, animation) is Gaming Realms' problem. Your problem is: does our app correctly wrap, launch, settle, and account for it.

The Real Product: Fanatics Casino App QA Agent
Slingo is just the first game. The architecture should be:


┌─────────────────────────────────────────────────────────┐
│ Fanatics Casino QA Agent                                 │
│                                                          │
│ PLATFORM WORKFLOWS (app-level, game-agnostic)            │
│  ├── LoginWorkflow                                       │
│  ├── DepositWorkflow                                     │
│  ├── WithdrawWorkflow                                    │
│  ├── SearchGameWorkflow                                  │
│  ├── NavigateToGameWorkflow(game_name)                   │
│  ├── CheckBalanceWorkflow                                │
│  ├── ApplyPromoWorkflow(promo_code)                      │
│  ├── ResponsibleGamingWorkflow(limit_type, amount)       │
│  └── GeolocationCheckWorkflow(spoofed_state)             │
│                                                          │
│ GAME WORKFLOWS (per-game, uses platform workflows)       │
│  ├── SlingoCashEruptionRoundWorkflow                     │
│  ├── BlackjackRoundWorkflow                              │
│  ├── RouletteRoundWorkflow                               │
│  ├── SlotsGenericRoundWorkflow(game_name)                │
│  └── ...one per game type                                │
│                                                          │
│ TEST SUITE WORKFLOWS (compose platform + game)           │
│  ├── SmokeTestWorkflow                                   │
│  │    login → check balance → play 1 round of 5 games   │
│  │    → verify balance → logout                          │
│  ├── RegressionTestWorkflow                              │
│  │    full platform + all games + edge cases             │
│  ├── NewBuildTestWorkflow                                │
│  │    install APK → smoke test → report                  │
│  └── PromotionTestWorkflow(promo_details)                │
│       apply promo → play required games → verify terms   │
│                                                          │
│ INFRASTRUCTURE                                           │
│  ├── screen_maps/ (per resolution)                       │
│  ├── mobile-mcp (device interaction)                     │
│  ├── proxyman-mcp (network validation)                   │
│  ├── launchdarkly-mcp (feature flags)                    │
│  └── Temporal (durability, retries, orchestration)        │
└─────────────────────────────────────────────────────────┘
Why This Works at Scale
Platform workflows are written once. Login, deposit, balance check, search — these are the same regardless of which game you're testing. Write them once, reuse everywhere.

Game workflows are thin. For most games (slots especially), the workflow is: tap spin, wait, tap spin, wait, collect. The game-specific logic is minimal — mostly just "how many spins" and "what decisions exist." Slingo is actually one of the more complex ones because of wilds.

Test suites compose freely. Want a smoke test? Chain login + 5 games + balance check. Want a full regression? Run all platform workflows + all game workflows + edge cases. Want to test a specific promo? Compose promo workflow + the games it applies to.

Screen map has two layers now:


{
  "platform": {
    "1080x1920": {
      "login_screen": { "email_field": {}, "password_field": {}, "login_button": {} },
      "home_screen": { "search_icon": {}, "balance_display": {}, "profile_icon": {} },
      "search_screen": { "search_input": {}, "first_result": {} }
    }
  },
  "games": {
    "slingo_cash_eruption": {
      "1080x1920": {
        "spin_button": {}, "end_game_button": {}, "balance_region": {}
      }
    },
    "blackjack_classic": {
      "1080x1920": {
        "deal_button": {}, "hit_button": {}, "stand_button": {}
      }
    }
  }
}
Platform coords are shared across all tests. Game coords are per-game. New resolution? Only the platform layer needs re-mapping (games render inside a webview that may scale independently).

The Honest Assessment
Can this become a complete QA solution for Fanatics Casino? Yes, for functional/integration testing. It covers everything a human QA engineer does with a phone in their hand.

What it won't replace:

Server-side API tests (you should still have those)
Performance/load testing (different tool entirely)
Security/penetration testing (different discipline)
What it will replace:

Manual device testing before releases
Manual regression cycles
Manual promotion verification
Manual multi-device testing
The "someone needs to check this on 8 devices" problem
The multiplier: Once this works on one emulator, it works on N emulators in parallel. AWS Device Farm gives you real devices. Same workflows, same screen maps (per resolution), run the full suite across Pixel 7, Samsung S24, iPhone 15 simultaneously.

