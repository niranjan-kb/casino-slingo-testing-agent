# App Structure (Fanatics Casino — Android)

Your mental map of the app. The lobby is **CMS-driven** (Playmaker / NATS): widget composition, category ordering, and bottom-nav items can change per state/jurisdiction and over time. Treat the layout below as the *current shape*, not a guarantee. When in doubt, read live page-source.

---

## Splash → Home

After the splash screen, the agent lands on the **Home screen** (also called the **casino lobby**). Login state determines what shows in the header.

## Home / Casino Lobby

### Header (top of the screen)

| Area | Pre-auth | Post-auth | Notes |
|---|---|---|---|
| **Top-left** | Fanatics logo / flag | Same | Debug builds only: **tap = opens the debug menu** (device-id info, UI component library, geo-location override, etc.). On non-debug builds: NEVER tap. On debug builds: do NOT enter during normal navigation — but it's an **available capability** if the SessionIntent explicitly asks for it (e.g. cross-jurisdiction testing via geo override). Only enter when invoked deliberately. |
| **Top-right** | "Login" button | Account/Profile icon + Quick Deposit button | Profile → opens the Profile screen. Quick Deposit → opens a bottom sheet. **NEVER confirm anything inside the Quick Deposit sheet** — it's a real-money flow. |

### Cat Nav (Casino Category Navigation)

A redesigned top navigation bar that replaces the old flat pill-tab system with a hierarchical, CMS-configurable category browser. Sits directly below the header. **This is the same surface listed below as the "Category Navigation" widget — one component, two names.**

- **Pinned main categories** display in a top navbar — e.g. **Slots**, **Table & Card**, **Live Dealer**. Order + pinning configurable in the CMS via checkbox.
- **Subcategories** are nested under each main category (e.g. *Live Dealer → Roulette*). Tapping a main category reveals its subcategories.
- **"All" button** → opens a bottom-sheet drawer showing every category and subcategory at once for fast browsing. Useful when the target's main category isn't pinned.
- Smooth animations when switching between categories.

### Casino lobby body (CMS-driven widget stack)

Below the Cat Nav, the lobby is a vertical stack of widgets. **Composition changes** — what's there today may not be there tomorrow, and may differ per state. The widget types you can encounter:

| Widget | What it is |
|---|---|
| **Hero** | Top-of-page banner. Single game or multi-game carousel. Has background image, icon, title, description, CTA button, hex color. Title field is internal only (not user-visible). |
| **Casino Search** | Search + filtering input for games. **Interaction model:** tapping the search input opens a search surface that initially shows **trending searches / suggestion pills** (labels like `casino1`, `casino2`, recent terms). These pills are pre-typing hints, NOT search failure — do not bail or cancel. Type the literal query, then real game results render (e.g. multiple blackjack tiles for `blackjack`). Tap the first matching result tile. |
| **Category Navigation** | Same as the top **Cat Nav** above — listed here too because CMS treats it as a placeable widget. Don't double-count it. |
| **Tray** | The most flexible widget. Configurable size (S / M / L / XL), metadata (None / Title / Min-Max / RTP), and content source (**Manually Curated**, **Recently Played**, or **Query Driven**). Has a max-tile limit and image/title overrides. Personalized rows like *"Continue Playing for &lt;user&gt;"*, *"Because You Played &lt;Game&gt;"*, *"Top 10"* are Trays with Query-Driven sources. |
| **Theme Tray** | Like a Tray but with a prominent title, optional icon, background image. Sizes S or M. For themed collections. |
| **Grid** | Two styles: Standard (2×2) or Multi-Column Scrollable. Manually curated. |
| **List** | Multiple styles: Standard, Background, Arcade, KeyArt. Supports title + Min-Max + RTP metadata. |
| **Tabs** | Tab group that loads separate page routes (e.g. Featured, New, Trending). **Must be the last widget on the page** — nothing can sit beneath it. |
| **Promotion Widget** | Promo/bonus display. View types: Image+Text+CTA or Text+CTA. Has title, description, link, promo/bonus ID. |
| **Album Scroll** | Spotify-style horizontally scrollable carousel with infinite loop and haptic feedback on the centered item. Two tile sizes: Small-Medium and XL. |

Category pills also appear inline near the top of the lobby (Rewards, Featured, New, Slots, Table & Card, …).

All widgets are configured via the CMS Page Builder (Playmaker/NATS), segmentable by state/jurisdiction, stackable, reorderable, and schedulable.

### Game tile sushi menu (action menu)

Many — not all — game tiles expose a **sushi menu** (also called the **action menu**) revealing title, minimum bet, maximum bet, RTP, etc. A real casino player doesn't open it pre-emptively — most of this info is already on the tile itself. You only open it **on demand**: when you need to size a bet inside `intent_play_game` and the visible min/max isn't enough. **Do NOT open the sushi menu during navigation**; it adds turns and isn't player-natural.

### Bottom navigation

Bottom-nav items are CMS-configurable, **with one slot always reserved for Fanatics Spin to Win** (the FanCash Spins game — see [`fancash_spins.md`](../../fancash_spins.md)). FanCash Spins is a daily-bonus feature, **not a regular game tile**. Other bottom-nav slots can be jackpots, promos, rewards, slots, etc.

**FanCash Spins slot position is fixed per platform:**
- **Android**: center of the bottom nav
- **iOS**: side of the bottom nav

Use this when path-planning to FanCash Spins — position-based lookup is reliable as a fallback if text matching misses.

---

## Profile screen (tap Account/Profile in the header)

Holds the user's financial + activity history. Read-only for the agent.

- **Deposits & withdrawals** — amount, transaction status, previous balance, balance after, payment method, state, timestamp, transaction ID.
- **Casino game play summaries** — per-session wager records.
- **Casino Credits Redeemed** — value of casino credits used in a game session.
- **Offline transactions** — deposits/withdrawals via customer service or *Cash at Fanatics Venue* (cage deposits).
- **Casino credit earnings** — credits earned from promos or FanCash conversions.

---

## Lobby tile recognition (DB-driven)

Game tiles use Fanatics' generic resource-ids: `casino_game_component_tile`, `small_game_component`, `game_component`, `casino_game` — seeded in the `lobby_tile_patterns` DB table. Because the rid is shared across every tile, the slug is derived from the tile's display name inside `extract_game_tiles`.

---

## Universal modals (can appear on any screen)

Dismissal defaults — not exhaustive. If you hit a modal not listed, dump page-source and reason from the buttons.

| Trigger | Default action |
|---|---|
| Geo / location prompt | Tap "Continue" / "Allow" |
| Responsible-gaming reminder | Tap "Continue" / dismiss |
| "Are you still there?" timeout | Tap "Yes, keep playing" |
| FanCash conversion offer | Tap "Not now" / X. **NEVER tap "Convert"** |
| Update-required banner | `SaveEvidence` and terminate the intent |
| Quick Deposit bottom sheet | Back-dismiss; never confirm / submit |

## Navigation safety rules (shared by both navigate intents)

1. **Back-to-home anchor.** Lost or after a failed sub-strategy: tap the Home item in the bottom-nav, or `appium_mobile_press_key key="BACK"` (cap 5).
2. **Loop detector.** ≥5 visits to one screen signature within 20 actions → trip. `SaveEvidence`, BACK out, terminate.
3. **≥1 verified attempt before `next=done`.** Zero tool calls on a navigation control = `SaveEvidence(label=nav_no_attempts)`, never a hallucinated success.

## Deposit / destructive-action avoidance

**NEVER** tap any of: Deposit, Add Funds, Withdraw, Convert FanCash, KYC Submit, Cancel Withdrawal, the Fanatics logo on non-debug builds, or any Confirm/Submit inside the Quick Deposit bottom sheet. Inside `intent_play_game`, only the SmartTap+VerifyTap pair for `spin_button` / `place_bet` (HIGH-risk tier — always verified) is allowed. If a flow appears to require any other financial action, `SaveEvidence` and terminate.

## Jurisdictional guard

If `RuntimeFacts.jurisdiction == "WV"`: do **not** attempt any `live_*` kind. EVONET is unavailable in WV. Mark `target.unresolved=true reason=evonet_unavailable_in_wv`, `SaveEvidence`, emit done.
