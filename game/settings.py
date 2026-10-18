"""Design system: virtual resolution, layout grid, colours and type sizes."""

TITLE = "Packet Panic - The Network Survival Game"

# Everything is drawn on a fixed 1280x720 virtual canvas, then scaled to
# fit the window (letterboxed), so the layout works on any laptop screen.
WIDTH, HEIGHT = 1280, 720
FPS = 60
SIM_DT = 1.0 / 60.0          # fixed simulation time step

# Layout -------------------------------------------------------------------
TOPBAR_H = 60
MARGIN = 16
SIDE_W = 340
CONTENT_Y = TOPBAR_H + MARGIN
CONTENT_H = HEIGHT - CONTENT_Y - MARGIN
WORK_RECT = (MARGIN, CONTENT_Y, WIDTH - SIDE_W - 3 * MARGIN, CONTENT_H)
SIDE_RECT = (WIDTH - SIDE_W - MARGIN, CONTENT_Y, SIDE_W, CONTENT_H)

# Colours ------------------------------------------------------------------
BG = (9, 14, 26)
BG_GRID = (16, 24, 40)
PANEL = (15, 23, 38)
PANEL_ALT = (20, 30, 48)
PANEL_HI = (27, 39, 61)
BORDER = (36, 50, 74)
BORDER_HI = (58, 78, 110)

TEXT = (230, 237, 247)
TEXT_DIM = (148, 163, 188)
TEXT_MUTED = (98, 113, 140)

ACCENT = (45, 212, 191)        # teal - primary accent
ACCENT_DIM = (20, 110, 104)
ACCENT_SOFT = (18, 52, 58)
CYAN = (56, 189, 248)
GREEN = (52, 211, 153)
AMBER = (245, 158, 11)
RED = (244, 63, 94)
VIOLET = (167, 139, 250)

GREEN_SOFT = (16, 50, 44)
AMBER_SOFT = (58, 42, 14)
RED_SOFT = (62, 20, 34)

# Colour per protocol layer (used consistently in every screen)
LAYER_COLORS = {
    "data": (226, 232, 240),
    "transport": ACCENT,
    "l4": ACCENT,
    "network": CYAN,
    "ip": CYAN,
    "datalink": VIOLET,
    "eth": VIOLET,
    "fcs": VIOLET,
    "physical": AMBER,
}

LEVEL_COLORS = {"info": CYAN, "ok": GREEN, "warn": AMBER, "error": RED}

# Type scale ----------------------------------------------------------------
FS_XS = 13
FS_SM = 15
FS_MD = 17
FS_LG = 21
FS_XL = 28
FS_HERO = 64

STAGES = ["Compose", "Encapsulate", "Gateway", "Route", "Deliver"]
