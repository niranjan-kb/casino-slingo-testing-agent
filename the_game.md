Slingo® Cash Eruption
Game Title: Slingo® Cash Eruption

Content Provider / Studio: Gaming Realms

RTP (Return to Player): ~95.73% - 95.79%

Max Win: 10,000x Base Stake

1. Core Game Architecture & UI Layout
The agent must map the screen into three primary interaction zones:

The Slingo Grid: A 5x5 matrix of 25 random numbers.

The Slot Reel: A 1x5 horizontal row located directly beneath the grid columns.

The Control Panel: Located at the bottom, housing the Stake Adjuster, the main Spin button, and the End Game/Collect button.

2. Standard Gameplay Loop & Mechanics
Unlike traditional Slingo games that award 10 spins, Slingo Cash Eruption operates on a 5-spin base cycle. 1.  Initialization: The agent selects a stake ($0.20 minimum) and clicks "Spin."
2.  The Spin Phase: The 1x5 reel spins and lands on numbers or special symbols.
3.  Auto-Daubing: Any numbers on the reel that perfectly match numbers in the column directly above them on the 5x5 grid are automatically marked off (daubed) and replaced by a golden Aztec coin.
4.  Creating Slingos: A "Slingo" is achieved when a horizontal, vertical, or diagonal line of 5 numbers is fully daubed. There are 12 possible paylines.
5.  Prize Ladder: Each completed Slingo moves the player up the left-hand prize ladder. The goal is to reach tier 4 (1x multiplier) or higher to trigger the game's bonus features.

3. Special Symbol Logic & Agent Interaction
This is where your AI agent must pause standard execution and perform OCR (Optical Character Recognition) or image matching to make a decision.

Wild (Incan Princess): * Visual cue: Lands on the bottom reel. The game pauses.

Agent Action: The agent must identify which column (1-5) the Wild landed in. It must then click any unmarked number within that specific column on the grid above.

Optimization: Program the agent to prioritize numbers that are one daub away from completing a Slingo.

Super Wild (Princess with Headdress): * Visual cue: Lands on the bottom reel. The game pauses.

Agent Action: The agent can select any unmarked number on the entire 5x5 grid.

Optimization: Prioritize the center square (Row 3, Column 3) as it intersects with the most paylines (horizontal, vertical, and two diagonals).

Free Spin (+1 Symbol): Adds an extra base spin to the counter. The agent simply logs this; no interaction is required.

Fireball (Scatter): These accumulate. If the agent logs 6 or more Fireballs in a single base game, it automatically triggers the Cash Eruption Bonus.

4. Critical Automation Boundary: Extra Spins Phase
This is the most common point of failure for testing agents. After the base 5 spins (and any awarded Free Spins) are exhausted, the game enters the "Extra Spins" phase.

State Detection: The main spin button will display a cash value (e.g., "Spin for $0.50") instead of the standard spin icon.

QA Directive: Extra spins dynamically increase in cost based on how close the grid is to a Full House. If your agent is running a standard base-game loop to test stability, it MUST be programmed to locate and click the "END GAME" / "COLLECT" button during this phase. If it blindly clicks the center button, it will drain the test account balance rapidly on overpriced extra spins.

5. Bonus Features State Management
If the agent achieves 5+ Slingos, it will enter a bonus state that requires different interaction protocols:

Hot Picks (5, 6, or 7 Slingos): The grid changes to a 2x3, 3x3, or 4x3 layout of mystery fireballs. The agent must randomly click these fireballs to reveal multipliers or trigger the main bonus.

Cash Eruption Bonus (8-12 Slingos or 6+ Scatters): This is a "Hold & Win" feature. The agent starts with 3 respins. The reels spin automatically. Any multipliers or jackpot symbols that land become sticky, and the spin counter resets to 3. The agent must wait for the "Game Over" or "Collect" modal to appear to log the final payout (Mini, Minor, Major, or Grand Jackpots) before returning to the base game loop.

## Game characterstics
Color Palette & Thematic Styling
Theme: Mesoamerican / Aztec Temple with a volcanic, fiery motif.

Primary Background: Ancient stone temple columns and steps, bathed in warm ambient light with animated burning torches on the lower left and right edges.

Dominant Colors: * Warm Tones: Deep reds, vibrant oranges, and glowing yellows dominate the title, the main 5x5 grid, and the fire-based animations.

Cool Contrasts: Dark teal and cyan are used heavily for the 1x5 slot reel, actionable buttons (like [PLAY] and [END GAME]), and the backgrounds of certain special symbols to make them pop against the fiery grid.

Accents: Gold is used extensively for borders, frames, and the "marked off" coin symbols to represent Aztec treasure.

2. Character & Symbol Identification
Your agent will need to recognize several distinct symbols that appear on the 1x5 bottom reel:

Standard Numbers: Bright yellow or light green text on a dark teal background.

The Wild (Incan Princess): A female character portrait set against a teal background. She wears a turquoise/green feathered headdress. The word "WILD" is written in gold across the bottom of the symbol.

The Super Wild (High Priestess): The same female character, but set against a glowing orange/red background. She wears a much larger, fiery golden headdress. The words "SUPER WILD" are written in gold across the bottom.

Multipliers (Fireballs): Glowing, animated balls of fire containing text like x2 or x4 in dark red/black text.

Blocker / Dud Symbol: A simple, bold yellow X on the standard teal reel background. It does nothing and acts as a dead space.

Daubed / Marked Grid Symbol: When a grid number is matched, it is replaced by a shiny gold Aztec calendar coin featuring a bright teal gemstone in the center.

3. UI Structure & Placement (Top to Bottom)
Top Header (Jackpots & Trackers)

Jackpot Displays: Four distinct black rectangular boxes with gold borders. The text colors are distinct for OCR sorting: Grand (Red text), Major (Purple text), Minor (Green text), and Mini (Blue text).

Hot Picks Tracker (Left): A dark red horizontal bar tracking > > > x1 and "1 HOT PICK, 2 HOT PICKS, 3 HOT PICKS".

Fireball Tracker (Right): A row of four circular slots with ornate golden borders, used to collect scatter symbols.

The Main Play Area

5x5 Grid: Framed by thick gold pillars. The background of the grid is a dark reddish-brown. The grid lines are thin and gold.

Highlight State: When the agent must make a choice via a standard Wild, the selectable numbers in the specific column are highlighted with a glowing bright green/cyan box.

Match State: When a number auto-matches, it pulses with a bright white/yellow glow before turning into the gold coin.

1x5 Slot Reel: Directly below the 5x5 grid, separated by a horizontal gold border. The background of this reel is a solid dark teal, making the colorful symbols highly visible.

The Footer Controls

Left UI Widget: A circular stone button with a "stack of coins" icon. Used to open the stake adjustment menu.

Center Spin Button: A large circular button resembling an Aztec calendar stone.

Base State: Displays a looping arrow.

Extra Spin State: The center fills with a flaming orb, and text appears detailing the cost (e.g., "Spin for $0.30").

Right UI Widget: A circular stone button with a "gear" icon for game settings.

Spin Counter (Far Right): A small floating element shaped like a torch/vase. It displays a large number indicating remaining spins, with the text "SPINS LEFT" below it.

Bottom Text Bar: Pure black background. Displays "Stake: $X.XX" on the far left and "Balance: $XX.XX" on the far right.

4. Modal Overlays
END GAME Prompt: During the Extra Spins phase, a massive, rectangular dark teal button with a thick gold border and the words END GAME in pale yellow appears directly above the center spin button.

GAME OVER Screen: A large, dark teal square modal with a thick gold border appears over the center of the screen, displaying "GAME OVER" in bold, pale yellow text.

## mapping idea - only for referrence
Slingo® Cash Eruption, calculated for a standard 1080x1920 (FHD) portrait viewport (common for Android emulators like Pixel 5 or standard iOS devices).

Note for your automation framework (e.g., Appium): These coordinates represent the center anchor points of each UI element. You will likely need to apply a scaling multiplier depending on the specific DPI or device screen size your testing agent is using, but the proportional logic remains identical.

1. The Main 5x5 Grid (Click/Daub Targets)
The grid is horizontally centered. Assuming the grid width is ~800px (leaving 140px margins on the left and right), each cell is roughly 160x160 pixels.

X-Axis (Columns 1-5 Centers):

Col 1: X = 220

Col 2: X = 380

Col 3: X = 540 (Center of screen)

Col 4: X = 700

Col 5: X = 860

Y-Axis (Rows 1-5 Centers):
Assuming the grid starts around Y = 650 (below the header and jackpots).

Row 1 (Top): Y = 730

Row 2: Y = 890

Row 3: Y = 1050 (True Center)

Row 4: Y = 1210

Row 5 (Bottom): Y = 1370

Grid Coordinate Matrix [Row][Column]:
Use this 2D array mapping for your agent to target specific squares when a Wild/Super Wild lands:

Plaintext
[730, 220]  [730, 380]  [730, 540]  [730, 700]  [730, 860]
[890, 220]  [890, 380]  [890, 540]  [890, 700]  [890, 860]
[1050, 220] [1050, 380] [1050, 540] [1050, 700] [1050, 860]
[1210, 220] [1210, 380] [1210, 540] [1210, 700] [1210, 860]
[1370, 220] [1370, 380] [1370, 540] [1370, 700] [1370, 860]
2. The 1x5 Slot Reel (OCR / Image Reading Zones)
The bottom reel slots perfectly align horizontally with the grid columns above them. These coordinates are for setting up bounding boxes for your OCR or image-matching scripts to read the results of a spin.

Reel Slot 1: X = 220, Y = 1550

Reel Slot 2: X = 380, Y = 1550

Reel Slot 3: X = 540, Y = 1550

Reel Slot 4: X = 700, Y = 1550

Reel Slot 5: X = 860, Y = 1550

(Bounding Box Tip: Create a box roughly 120x140 pixels around these center points to isolate the number/symbol without catching the borders).

3. Core Action Buttons (Click Targets)
These are the critical path buttons for driving the game loop.

Main Spin Button: X = 540, Y = 1780

Note: This is the large circular button at the bottom center.

End Game / Collect Button: X = 540, Y = 1620

Note: This rectangular button appears directly above the main spin button during the Extra Spins phase (visible in Image 5).

Stake / Bet Adjuster: X = 220, Y = 1780

Note: The coin stack icon in the bottom left.

Settings Menu: X = 860, Y = 1780

Note: The gear icon in the bottom right.

Close / Acknowledge "GAME OVER" Modal: X = 540, Y = 1050

Note: Tapping the dead center of the screen usually dismisses large end-of-round modals.