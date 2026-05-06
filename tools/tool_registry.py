from typing import Dict, List

from models.tool_definitions import ToolArgument, ToolDefinition

# ----- Slingo QA tools -----
slingo_wait_seconds_tool = ToolDefinition(
    name="WaitSeconds",
    description="Pause execution for a number of seconds. Use after taps that trigger animations or screen transitions.",
    arguments=[
        ToolArgument(name="seconds", type="number", description="How many seconds to wait (max 30)"),
    ],
)

slingo_tap_coordinate_tool = ToolDefinition(
    name="TapCoordinate",
    description="Tap at specific pixel coordinates on the device screen. Use for WebView/game elements that appium_find_element cannot see. For native elements, prefer appium_find_element + appium_click instead.",
    arguments=[
        ToolArgument(name="x", type="number", description="X coordinate in physical pixels"),
        ToolArgument(name="y", type="number", description="Y coordinate in physical pixels"),
    ],
)

slingo_detect_screen_tool = ToolDefinition(
    name="DetectScreen",
    description="Detect which screen the app is currently showing by analyzing visible elements. Returns the screen name, confidence score, and matched signatures.",
    arguments=[
        ToolArgument(name="app_context", type="string", description="'platform' for native app screens, or game name like 'slingo_cash_eruption' for game screens"),
    ],
)

slingo_lookup_coords_tool = ToolDefinition(
    name="LookupCoords",
    description="Look up stored coordinates for a UI element from the screen map database. Returns x, y, confidence, and whether verification is needed.",
    arguments=[
        ToolArgument(name="app_context", type="string", description="'platform' or game name (e.g. 'slingo_cash_eruption')"),
        ToolArgument(name="screen_name", type="string", description="Screen name (e.g. 'home', 'main_game', 'login')"),
        ToolArgument(name="element_name", type="string", description="Element name (e.g. 'spin_button', 'search_bar', 'close_button')"),
    ],
)

slingo_verify_tap_tool = ToolDefinition(
    name="VerifyTap",
    description="Verify that a tap produced the expected screen transition. Updates confidence scores in the coordinate database. Call this after tapping to confirm the tap worked.",
    arguments=[
        ToolArgument(name="app_context", type="string", description="'platform' or game name"),
        ToolArgument(name="screen_name", type="string", description="Screen you were on BEFORE the tap"),
        ToolArgument(name="element_name", type="string", description="Element you tapped"),
        ToolArgument(name="tapped_x", type="number", description="X coordinate that was tapped"),
        ToolArgument(name="tapped_y", type="number", description="Y coordinate that was tapped"),
        ToolArgument(name="expected_screen", type="string", description="Screen you expect to be on AFTER the tap (optional)"),
    ],
)

slingo_find_element_with_fallback_tool = ToolDefinition(
    name="FindElementWithFallback",
    description=(
        "Find a native UI element by trying multiple (strategy, selector) candidates in order. "
        "Returns the first match's elementUUID — which plugs straight into appium_click, "
        "appium_set_value, or appium_get_text. Use this INSTEAD of calling appium_find_element "
        "multiple times yourself: it collapses 3-6 LLM round-trips into one. "
        "Each candidate is a dict with 'strategy' (e.g. 'xpath', 'id', 'accessibility id', "
        "'-android uiautomator', 'class name') and 'selector'. Tried in order, first hit wins."
    ),
    arguments=[
        ToolArgument(
            name="candidates",
            type="array",
            description=(
                "Ordered list of {strategy, selector} dicts. Example: "
                "[{\"strategy\": \"xpath\", \"selector\": \"//*[@text='Continue']\"}, "
                "{\"strategy\": \"accessibility id\", \"selector\": \"next button\"}, "
                "{\"strategy\": \"id\", \"selector\": \"continue_button\"}]"
            ),
        ),
    ],
)

slingo_smart_tap_tool = ToolDefinition(
    name="SmartTap",
    description="All-in-one tap tool: looks up coordinates from the DB, taps, waits for transition, verifies the result, and updates confidence — guaranteeing the learning loop runs every time. Use this instead of separate LookupCoords → TapCoordinate → WaitSeconds → VerifyTap calls.",
    arguments=[
        ToolArgument(name="app_context", type="string", description="'platform' or game name (e.g. 'slingo_cash_eruption')"),
        ToolArgument(name="screen_name", type="string", description="Current screen name (e.g. 'home', 'main_game', 'login')"),
        ToolArgument(name="element_name", type="string", description="Element to tap (e.g. 'spin_button', 'search_bar', 'close_button')"),
        ToolArgument(name="expected_screen", type="string", description="Screen expected after the tap (optional — if omitted, success = screen changed)"),
        ToolArgument(name="wait_seconds", type="number", description="Seconds to wait after tap for UI transition (default 2, max 30)"),
    ],
)

slingo_save_evidence_tool = ToolDefinition(
    name="SaveEvidence",
    description="Save a screenshot as labeled test evidence for the QA report. Use after key moments: balance reads, spin results, wild encounters, exit confirmation.",
    arguments=[
        ToolArgument(name="screenshot_path", type="string", description="Path to the screenshot file (from appium_screenshot result)"),
        ToolArgument(name="label", type="string", description="Descriptive label (e.g. 'pre_game_balance', 'spin_3_wild', 'post_exit')"),
        ToolArgument(name="run_id", type="string", description="Test run ID (optional, auto-generated if omitted)"),
    ],
)

slingo_generate_report_tool = ToolDefinition(
    name="GenerateReport",
    description="Generate a structured QA test report with pass/fail determination. Call this at the end of a test run with all collected data.",
    arguments=[
        ToolArgument(name="starting_balance", type="string", description="Balance before game (e.g. '$50.00')"),
        ToolArgument(name="ending_balance", type="string", description="Balance after game (e.g. '$49.80')"),
        ToolArgument(name="spins_played", type="number", description="Number of spins completed"),
        ToolArgument(name="total_spins", type="number", description="Expected spins (default 5)"),
        ToolArgument(name="wilds", type="number", description="Number of wilds encountered"),
        ToolArgument(name="super_wilds", type="number", description="Number of super wilds encountered"),
        ToolArgument(name="extra_spins_purchased", type="number", description="Must be 0 for PASS"),
        ToolArgument(name="anomalies", type="string", description="Comma-separated list of anomaly descriptions"),
        ToolArgument(name="run_id", type="string", description="Test run ID (optional)"),
    ],
)

# ----- System tools -----
list_agents_tool = ToolDefinition(
    name="ListAgents",
    description="List available agents to interact with, pulled from goal_registry. ",
    arguments=[],
)

change_goal_tool = ToolDefinition(
    name="ChangeGoal",
    description="Change the goal of the active agent. ",
    arguments=[
        ToolArgument(
            name="goalID",
            type="string",
            description="Which goal to change to",
        ),
    ],
)

give_hint_tool = ToolDefinition(
    name="GiveHint",
    description="Give a hint to the user regarding the location of the pirate treasure. Use previous conversation to determine the hint_total, it should initially be 0 ",
    arguments=[
        ToolArgument(
            name="hint_total",
            type="number",
            description="How many hints have been given",
        ),
    ],
)

guess_location_tool = ToolDefinition(
    name="GuessLocation",
    description="Allow the user to guess the location (in the form of an address) of the pirate treasure. ",
    arguments=[
        ToolArgument(
            name="address",
            type="string",
            description="Address at which the user is guessing the treasure is located",
        ),
        ToolArgument(
            name="city",
            type="string",
            description="City at which the user is guessing the treasure is located",
        ),
        ToolArgument(
            name="state",
            type="string",
            description="State at which the user is guessing the treasure is located",
        ),
    ],
)

# ----- Travel use cases tools -----
search_flights_tool = ToolDefinition(
    name="SearchFlights",
    description="Search for return flights from an origin to a destination within a date range (dateDepart, dateReturn). "
    "You are allowed to suggest dates from the conversation history, but ALWAYS ask the user if ok.",
    arguments=[
        ToolArgument(
            name="origin",
            type="string",
            description="Airport or city (infer airport code from city and store)",
        ),
        ToolArgument(
            name="destination",
            type="string",
            description="Airport or city code for arrival (infer airport code from city and store)",
        ),
        ToolArgument(
            name="dateDepart",
            type="ISO8601",
            description="Start of date range in human readable format, when you want to depart",
        ),
        ToolArgument(
            name="dateReturn",
            type="ISO8601",
            description="End of date range in human readable format, when you want to return",
        ),
        ToolArgument(
            name="userConfirmation",
            type="string",
            description="Indication of the user's desire to search flights, and to confirm the details "
            + "before moving on to the next step",
        ),
    ],
)

search_trains_tool = ToolDefinition(
    name="SearchTrains",
    description="Search for trains between two English cities. Returns a list of train information for the user to choose from. Present the list to the user.",
    arguments=[
        ToolArgument(
            name="origin",
            type="string",
            description="The city or place to depart from",
        ),
        ToolArgument(
            name="destination",
            type="string",
            description="The city or place to arrive at",
        ),
        ToolArgument(
            name="outbound_time",
            type="ISO8601",
            description="The date and time to search for outbound trains. If time of day isn't asked for, assume a decent time of day/evening for the outbound journey",
        ),
        ToolArgument(
            name="return_time",
            type="ISO8601",
            description="The date and time to search for return trains. If time of day isn't asked for, assume a decent time of day/evening for the inbound journey",
        ),
    ],
)

book_trains_tool = ToolDefinition(
    name="BookTrains",
    description="Books train tickets. Returns a booking reference.",
    arguments=[
        ToolArgument(
            name="train_ids",
            type="string",
            description="The IDs of the trains to book, comma separated",
        ),
        ToolArgument(
            name="userConfirmation",
            type="string",
            description="Indication of user's desire to book train tickets",
        ),
    ],
)

create_invoice_tool = ToolDefinition(
    name="CreateInvoice",
    description="Generate an invoice for the items described for the total inferred by the conversation history so far. Returns URL to invoice.",
    arguments=[
        ToolArgument(
            name="amount",
            type="float",
            description="The total cost to be invoiced. Infer this from the conversation history.",
        ),
        ToolArgument(
            name="tripDetails",
            type="string",
            description="A description of the item details to be invoiced, inferred from the conversation history.",
        ),
        ToolArgument(
            name="userConfirmation",
            type="string",
            description="Indication of user's desire to create an invoice",
        ),
    ],
)

search_fixtures_tool = ToolDefinition(
    name="SearchFixtures",
    description="Search for upcoming fixtures for a given team within a date range inferred from the user's description. Ignore valid premier league dates. Valid teams this season are Arsenal FC, Aston Villa FC, AFC Bournemouth, Brentford FC, Brighton & Hove Albion FC, Chelsea FC, Crystal Palace FC, Everton FC, Fulham FC, Ipswich Town FC, Leicester City FC, Liverpool FC, Manchester City FC, Manchester United FC, Newcastle United FC, Nottingham Forest FC, Southampton FC, Tottenham Hotspur FC, West Ham United FC, Wolverhampton Wanderers FC",
    arguments=[
        ToolArgument(
            name="team",
            type="string",
            description="The full name of the team to search for.",
        ),
        ToolArgument(
            name="date_from",
            type="string",
            description="The start date in format (YYYY-MM-DD) for the fixture search inferred from the user's request (e.g. mid-March).",
        ),
        ToolArgument(
            name="date_to",
            type="string",
            description="The end date in format (YYYY-MM-DD) for the fixture search (e.g. 'the last week of May').",
        ),
    ],
)

find_events_tool = ToolDefinition(
    name="FindEvents",
    description="Find upcoming events to travel to a given city (e.g., 'Melbourne') and a month. "
    "It knows about events in Oceania only (e.g. major Australian and New Zealand cities). "
    "Returns events that overlap with the specified month. ",
    arguments=[
        ToolArgument(
            name="city",
            type="string",
            description="Which city to search for events",
        ),
        ToolArgument(
            name="month",
            type="string",
            description="The month to search for events (e.g., 'April')",
        ),
    ],
)

# ----- HR use cases tools -----
current_pto_tool = ToolDefinition(
    name="CurrentPTO",
    description="Find how much PTO a user currently has accrued. "
    "Returns the number of hours and (calculated) number of days of PTO. ",
    arguments=[
        ToolArgument(
            name="email",
            type="string",
            description="email address of user",
        ),
    ],
)

future_pto_calc_tool = ToolDefinition(
    name="FuturePTOCalc",
    description="Calculate if the user will have enough PTO as of their proposed date to accommodate the request. The proposed start and end dates should be in the future. "
    "Returns a boolean enough_pto and how many hours of PTO they will have remaining if they take the proposed dates. ",
    arguments=[
        ToolArgument(
            name="start_date",
            type="string",
            description="Start date of proposed PTO, sent in the form yyyy-mm-dd",
        ),
        ToolArgument(
            name="end_date",
            type="string",
            description="End date of proposed PTO, sent in the form yyyy-mm-dd",
        ),
        ToolArgument(
            name="email",
            type="string",
            description="email address of user",
        ),
    ],
)

book_pto_tool = ToolDefinition(
    name="BookPTO",
    description="Book PTO start and end date. Either 1) makes calendar item, or 2) sends calendar invite to self and boss? "
    "Returns a success indicator. ",
    arguments=[
        ToolArgument(
            name="start_date",
            type="string",
            description="Start date of proposed PTO, sent in the form yyyy-mm-dd",
        ),
        ToolArgument(
            name="end_date",
            type="string",
            description="End date of proposed PTO, sent in the form yyyy-mm-dd",
        ),
        ToolArgument(
            name="email",
            type="string",
            description="Email address of user, used to look up current PTO",
        ),
        ToolArgument(
            name="userConfirmation",
            type="string",
            description="Indication of user's desire to book PTO",
        ),
    ],
)

paycheck_bank_integration_status_check = ToolDefinition(
    name="CheckPayBankStatus",
    description="Check status of Bank Integration for Paychecks. "
    "Returns the status of the bank integration, connected or disconnected. ",
    arguments=[
        ToolArgument(
            name="email",
            type="string",
            description="email address of user",
        ),
    ],
)

# ----- Financial use cases tools -----
financial_check_account_is_valid = ToolDefinition(
    name="FinCheckAccountIsValid",
    description="Check if an account is valid by email address or account ID. "
    "Returns the account status, valid or invalid. ",
    arguments=[
        ToolArgument(
            name="email",
            type="string",
            description="email address of user",
        ),
        ToolArgument(
            name="account_id",
            type="string",
            description="account ID of user",
        ),
    ],
)

financial_get_account_balances = ToolDefinition(
    name="FinCheckAccountBalance",
    description="Get account balance for your accounts. "
    "Returns the account balances of your accounts. ",
    arguments=[
        ToolArgument(
            name="email_address_or_account_ID",
            type="string",
            description="email address or account ID of user",
        ),
    ],
)

financial_move_money = ToolDefinition(
    name="FinMoveMoney",
    description="Send money from one account to another under the same acount ID (e.g. checking to savings). "
    "Returns the status of the order and the new balances in each account. ",
    arguments=[
        ToolArgument(
            name="email_address_or_account_ID",
            type="string",
            description="email address or account ID of user (you will need both to find the account)",
        ),
        ToolArgument(
            name="accounttype",
            type="string",
            description="account type, such as checking or savings",
        ),
        ToolArgument(
            name="amount",
            type="string",
            description="amount to move in the order (e.g. checking or savings)",
        ),
        ToolArgument(
            name="destinationaccount",
            type="string",
            description="account to move the money to (e.g. checking or savings)",
        ),
        ToolArgument(
            name="userConfirmation",
            type="string",
            description="Indication of user's desire to move money",
        ),
    ],
)

financial_submit_loan_approval = ToolDefinition(
    name="FinCheckAccountSubmitLoanApproval",
    description="Submit a loan application. " "Returns the loan status. ",
    arguments=[
        ToolArgument(
            name="email_address_or_account_ID",
            type="string",
            description="email address or account ID of user",
        ),
        ToolArgument(
            name="amount",
            type="string",
            description="amount requested for the loan",
        ),
    ],
)

# ----- ECommerce Use Case Tools -----
ecomm_list_orders = ToolDefinition(
    name="ListOrders",
    description="Get all orders for a certain email address.",
    arguments=[
        ToolArgument(
            name="email_address",
            type="string",
            description="Email address of user by which to find orders",
        ),
    ],
)

ecomm_get_order = ToolDefinition(
    name="GetOrder",
    description="Get infromation about an order by order ID.",
    arguments=[
        ToolArgument(
            name="order_id",
            type="string",
            description="ID of order to determine status of",
        ),
    ],
)

ecomm_track_package = ToolDefinition(
    name="TrackPackage",
    description="Get tracking information for a package by shipping provider and tracking ID",
    arguments=[
        ToolArgument(
            name="tracking_id",
            type="string",
            description="ID of package to track",
        ),
        ToolArgument(
            name="userConfirmation",
            type="string",
            description="Indication of user's desire to get package tracking information",
        ),
    ],
)


# ----- Food Ordering Use Case Tools -----
food_add_to_cart_tool = ToolDefinition(
    name="AddToCart",
    description="Add a menu item to the customer's cart using item details from Stripe.",
    arguments=[
        ToolArgument(
            name="customer_email",
            type="string",
            description="Email address of the customer",
        ),
        ToolArgument(
            name="item_name",
            type="string",
            description="Name of the menu item (e.g., 'Margherita Pizza', 'Caesar Salad')",
        ),
        ToolArgument(
            name="item_price",
            type="number",
            description="Price of the item in dollars (e.g., 14.99)",
        ),
        ToolArgument(
            name="quantity",
            type="number",
            description="Quantity of the item to add (defaults to 1)",
        ),
        ToolArgument(
            name="stripe_product_id",
            type="string",
            description="Stripe product ID for reference (optional)",
        ),
    ],
)

# MCP Integration Functions


def create_mcp_tool_definitions(
    mcp_tools_info: Dict[str, Dict],
) -> List[ToolDefinition]:
    """Convert MCP tool info to ToolDefinition objects"""
    tool_definitions = []

    for tool_name, tool_info in mcp_tools_info.items():
        # Extract input schema properties
        input_schema = tool_info.get("inputSchema", {})
        properties = (
            input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
        )

        # Convert properties to ToolArgument objects
        arguments = []
        for param_name, param_info in properties.items():
            if isinstance(param_info, dict):
                arguments.append(
                    ToolArgument(
                        name=param_name,
                        type=param_info.get("type", "string"),
                        description=param_info.get("description", ""),
                    )
                )

        # Create ToolDefinition
        tool_def = ToolDefinition(
            name=tool_info["name"],
            description=tool_info.get("description", ""),
            arguments=arguments,
        )
        tool_definitions.append(tool_def)

    return tool_definitions
