What Is It?
Spin to Win is a free-to-play (F2P) daily game built by Fanatics Game Studios (FGS) for the Fanatics Casino app. Users spin a virtual wheel once per day for a chance to win prizes — primarily FanCash, but also casino credits, free spins, and discount codes. It's designed as a retention and habituation driver, encouraging users to return to the app every day. It launched in August 2024 and saw massive engagement — 97% user engagement rate, ~75K unique users, and over $1.3M in bonus prizes awarded in its first month alone. 
Fanatics Game Studio - August 2024

The game also serves as a differentiator for Fanatics Casino, targeting users who may not be interested in sports-based games. 
Spin to Win

Core Features
Daily Free Spin — Every user gets one free spin per day. After spinning, a countdown timer appears until midnight ET when the next spin unlocks. 
FanCash Spins MASTER Runbook

SuperCharged Spins — Users who wager $10+ in cash the previous day unlock an upgraded "SuperCharged" spin with better prize odds. This incentivizes real-money wagering among lower-value segments. 
Spin to Win Knowledge Share - Upcoming FEATs

SuperCharged Streaks — Rewards for maintaining consecutive days of SuperCharged spins (4-day and 7-day streak milestones), driving daily bet days and share of wallet.

FanCash Multipliers — Multiplier prizes (2x–10x FanCash on all games for the rest of the day) are being added to replace "better luck next time" outcomes entirely.

Bonus Rounds — A "surprise and delight" feature where some users are randomly selected to enter a card-picking bonus game after their spin, extending the experience beyond the ~7-second base spin and increasing engagement. FEAT-6297: [S2W] - Spin To Win Bonus Rounds
Abandoned

Themeable Experience — The game supports custom seasonal themes (e.g., Holiday 2024, NFL/Super Bowl themes, a "gold-plated" wheel for high-value users). 
FGS - MBR - October 2024

Choose Your Bonus Spins (upcoming) — Players will be able to pick which game to use free spin rewards on from a curated catalogue, rather than being locked to a pre-assigned game. 
Choose Your Bonus Spins — PRD

Rules & Mechanics
One spin per day, resetting at midnight ET

All prizes are FanCash only (V1), with a max prize of $500 FanCash (to stay under the $600 taxable threshold)

Prize amounts, odds, and tiers are configurable per state/jurisdiction and per user segment (Ace, Jack, King, Queen, etc.) via backend prize tables

The game contains no cash prizes — currency references are limited to FanCash

SuperCharged eligibility is determined by a $10 cash wager threshold the previous day

Prize pools may be capped daily (e.g., $5,000 FanCash daily cap discussed for compliance)

The game can be feature-flagged on/off and phased-rolled out via LaunchDarkly

An emergency brake exists in PlayMaker to deactivate the game across all states instantly

Tech Spec - Spin To Win

UI & Design Style
Native mobile app — built natively (not HTML5), resulting in sub-1-second load times (~0.98s avg vs. 23s industry average for HTML5 games)

Wheel-based interface — a visually prominent spinning wheel is the core interaction

Themed component library — every visual element is themeable via a structured component system including:

Container with gradient borders and backgrounds behind the wheel

Countdown timer (HR:MIN:SEC) with customizable text styles

Dialog screens for settings, onboarding (FTUE), deposit prompts

GameLogo with Lottie animations

Win celebration animations and Lottie-based motion graphics

Theme-able Components Library

Key UI states (especially for the bottom nav):

Spin available — Free Spin

Spin available — SuperCharged Spin

Spin used — Tomorrow's spin is Free

Spin used — Tomorrow's spin is SuperCharged

Settings accessible during countdown — a key UX improvement moved away from locking users out of the game during countdown; users can still access the scoreboard, sound/haptics toggles, prize table, and T&C. 
[F2P] Improved Countdown and UI Experience

Widget integration — the game appears as a tile widget in both the Casino lobby and the Sportsbook Discover feed, with dynamic visibility based on spin state. 
[F2P] Spin to Win Widget

Sound effects and haptic feedback are included with per-user toggle controls