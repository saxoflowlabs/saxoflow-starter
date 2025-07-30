from rich.console import Console
from rich.text import Text

def interpolate_color(stops, t):
    """Interpolate between a list of RGB stops (list of 3-tuples), t in [0,1]."""
    if t <= 0: return stops[0]
    if t >= 1: return stops[-1]
    seg = 1 / (len(stops) - 1)
    idx = int(t / seg)
    local_t = (t - seg * idx) / seg
    if idx >= len(stops) - 1:
        return stops[-1]
    c1 = stops[idx]
    c2 = stops[idx + 1]
    r = int(c1[0] + (c2[0] - c1[0]) * local_t)
    g = int(c1[1] + (c2[1] - c1[1]) * local_t)
    b = int(c1[2] + (c2[2] - c1[2]) * local_t)
    return (r, g, b)

def print_banner(console: Console, compact: bool = False):
    """
    Print the SAXOFLOW banner using a blue→cyan→white gradient (very smooth).
    """
    # Much smoother gradient: Deep blue -> Blue -> Cyan -> Light Cyan -> White
    color_stops = [
        (0, 60, 180),      # Deep blue
        (0, 120, 255),     # Blue
        (0, 200, 255),     # Cyan-ish
        (0, 255, 255),     # Cyan
        (120, 255, 255),   # Light cyan
        (220, 255, 255),   # Near white
        (255, 255, 255)    # White
    ]

    if compact:
        ascii_art = [
            "███  ███  █   █  ███  ███  █    ███  █   █",
            "█    █ █   █ █   █ █  █    █    █ █  █ █ █",
            "███  ███    █    ███  ███  █    ███  █ █ █",
            "  █  █ █   █ █   █ █  █    █    █ █  █ █ █",
            "███  █ █  █   █  █ █  █    ███  ███   █ █ ",
        ]
    else:
        ascii_art = [
            "███████╗ █████╗ ██╗   ██╗ ██████╗  ██████╗ ██╗      ██████╗ ██╗    ██╗",
            "██╔════╝██╔══██╗ ██║ ██╔╝██╔═══██╗██╔════╝ ██║     ██╔═══██╗██║    ██║",
            "███████╗███████║  ████╔╝ ██║   ██║██████╗  ██║     ██║   ██║██║ █╗ ██║",
            "╚════██║██╔══██║ ██╔═██╗ ██║   ██║██╔═══╝  ██║     ██║   ██║██║███╗██║",
            "███████║██║  ██║██║   ██╗╚██████╔╝██║      ███████╗╚██████╔╝╚███╔███╔╝",
            "╚══════╝╚═╝  ╚═╝╚═╝   ╚═╝ ╚═════╝ ╚═╝      ╚══════╝ ╚═════╝  ╚══╝╚══╝ ",
            ""
        ]
    gradient_text = Text()
    max_width = max(len(line) for line in ascii_art if line.strip())
    for line in ascii_art:
        for col_idx, char in enumerate(line):
            if char == ' ':
                gradient_text.append(char)
            else:
                t = col_idx / max(1, max_width - 1)
                r, g, b = interpolate_color(color_stops, t)
                gradient_text.append(char, style=f"bold rgb({r},{g},{b})")
        gradient_text.append("\n")
    console.print(gradient_text)

# Orange shade banner (if needed)
# def print_banner(console: Console, compact: bool = False):
#     """
#     Print the SAXOFLOW banner using a smooth orange→white gradient.
#     """
#     color_stops = [
#         (255, 80, 0),   # Pure orange
#         (255, 200, 120),# Light orange
#         (255, 255, 255) # White
#     ]

#     if compact:
#         ascii_art = [
#             "███  ███  █   █  ███  ███  █    ███  █   █",
#             "█    █ █   █ █   █ █  █    █    █ █  █ █ █",
#             "███  ███    █    ███  ███  █    ███  █ █ █",
#             "  █  █ █   █ █   █ █  █    █    █ █  █ █ █",
#             "███  █ █  █   █  █ █  █    ███  ███   █ █ ",
#         ]
#     else:
#         ascii_art = [
#             "███████╗ █████╗ ██╗   ██╗ ██████╗  ██████╗ ██╗      ██████╗ ██╗    ██╗",
#             "██╔════╝██╔══██╗ ██║ ██╔╝██╔═══██╗██╔════╝ ██║     ██╔═══██╗██║    ██║",
#             "███████╗███████║  ████╔╝ ██║   ██║██████╗  ██║     ██║   ██║██║ █╗ ██║",
#             "╚════██║██╔══██║ ██╔═██╗ ██║   ██║██╔═══╝  ██║     ██║   ██║██║███╗██║",
#             "███████║██║  ██║██║   ██╗╚██████╔╝██║      ███████╗╚██████╔╝╚███╔███╔╝",
#             "╚══════╝╚═╝  ╚═╝╚═╝   ╚═╝ ╚═════╝ ╚═╝      ╚══════╝ ╚═════╝  ╚══╝╚══╝ ",
#             ""
#         ]
#     gradient_text = Text()
#     max_width = max(len(line) for line in ascii_art if line.strip())
#     for line in ascii_art:
#         for col_idx, char in enumerate(line):
#             if char == ' ':
#                 gradient_text.append(char)
#             else:
#                 t = col_idx / max(1, max_width - 1)
#                 r, g, b = interpolate_color(color_stops, t)
#                 gradient_text.append(char, style=f"bold rgb({r},{g},{b})")
#         gradient_text.append("\n")
#     console.print(gradient_text)