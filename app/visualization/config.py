# Background layers
BG_BASE       = "#0D1117" 
BG_SURFACE    = "#161B22"
BG_ELEVATED   = "#1C2330"
BG_BORDER     = "#2D3748"

# ASUS accent
ASUS_BLUE     = "#1A7FD4"
ASUS_BLUE_DIM = "#0F3D6B"

# Status
ACCENT_RED     = "#F05252"
ACCENT_RED_DIM = "#3B1A1A"
ACCENT_PURPLE  = "#818CF8"
ACCENT_PINK    = "#F472B6"
ACCENT_PINK_DIM= "#3B1A2E"

# Typography
TEXT_PRIMARY   = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"
TEXT_MUTED     = "#484F58"

EMOTION_COLOR_SCALE = [
    "#1A7FD4",
    "#4A8FD4",
    "#818CF8",
    "#B794F4",
    "#F472B6",
]

SENTIMENT_COLORS = {
    "Positif": ASUS_BLUE,
    "Negatif": ACCENT_RED,
}

MODEL_TASK_LABELS = {
    "sentiment": "F1 Sentimen",
    "emotion":   "F1 Emosi",
}

MODEL_TASK_COLORS = {
    "sentiment": ASUS_BLUE,
    "emotion":   ACCENT_PINK,
}

ALERT_TYPE_LABELS = {
    "rating_drop":        "Penurunan Rating",
    "sentiment_negative": "Sentimen Negatif",
}

RATING_THRESHOLD = 4.0
PAGE_SIZE        = 5