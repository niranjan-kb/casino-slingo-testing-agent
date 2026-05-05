# Contract: Screen Map JSON Schema

**Type**: Data file contract
**Producer**: Manual calibration / screen mapping tool
**Consumer**: `goals/slingo_qa.py` (inlined into goal description at code-write time)

## Contract

Screen map JSON files follow the constitution's schema, stored in `screen_maps/`:

```
screen_maps/
├── platform/
│   └── <resolution>.json       # Native app screens (login, search, modals)
└── games/
    └── <game_id>/
        └── <resolution>.json   # Game-specific screens (grid, controls, reel)
```

### Platform Screen Map (`screen_maps/platform/<resolution>.json`)

```json
{
  "app": "fanatics_casino",
  "resolution": "1080x1920",
  "screens": {
    "<screen_name>": {
      "visual_anchors": ["<description>"],
      "elements": {
        "<element_name>": {
          "x": 540,
          "y": 1780,
          "intent": "<action description>",
          "type": "button|input|region|text",
          "notes": "<optional>"
        }
      },
      "last_verified": "2026-03-12",
      "device_verified": "Pixel_5_API_34"
    }
  }
}
```

### Game Screen Map (`screen_maps/games/<game_id>/<resolution>.json`)

```json
{
  "game": "<game_id>",
  "provider": "<provider_name>",
  "resolution": "1080x1920",
  "webview_bounds": { "x_min": 0, "x_max": 1080, "y_min": 300, "y_max": 1850 },
  "screens": {
    "main_game": {
      "grid": {
        "columns": { "1": 220, "2": 380, "3": 540, "4": 700, "5": 860 },
        "rows": { "1": 730, "2": 890, "3": 1050, "4": 1210, "5": 1370 }
      },
      "reel": { "y": 1550, "slots": [220, 380, 540, 700, 860] },
      "controls": { "<element_name>": { "x": 540, "y": 1780, "intent": "..." } }
    }
  }
}
```

## Constraints

- Resolution is the primary key (not build version)
- Coordinates are integer pixel values (center of element)
- `last_verified` must be updated when coordinates are re-calibrated
- Screen maps are append-only in production (per constitution)
