BG_BASE       = "#F4F6F9"
BG_SURFACE    = "#FFFFFF"
BG_ELEVATED   = "#EBEEF2"
BG_BORDER     = "#D0D5DD"

ASUS_BLUE     = "#1A7FD4"
ASUS_BLUE_DIM = "#D6E8FB"

ACCENT_RED     = "#F05252"
ACCENT_RED_DIM = "#FDE2E2"
ACCENT_PURPLE  = "#818CF8"
ACCENT_PURPLE_DIM = "#E0DFFE"
ACCENT_PINK    = "#F472B6"
ACCENT_PINK_DIM= "#FCE4EC"

TEXT_PRIMARY   = "#1A1D24"
TEXT_SECONDARY = "#5A6573"
TEXT_MUTED     = "#9CA3AF"

EMOTION_COLORS = {
    "Happy":   "#1A7FD4",
    "Love":    "#2EA043",
    "Fear":    "#F472B6",
    "Sadness": "#B794F4",
    "Anger":   "#F05252",
}

SENTIMENT_COLORS = {
    "Positive": ASUS_BLUE,
    "Negative": ACCENT_RED,
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