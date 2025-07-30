from rich.console import Console
from rich.text import Text
import pyfiglet

def print_banner(console: Console):
    """
    Print a gradient SAXOFLOW banner using only solid block characters (█).
    Creates clean, solid letters with cyan to white gradient left to right.
    """
    # Define gradient colors: cyan to white (left to right)
    start_rgb = (0, 255, 255)    # Cyan
    end_rgb = (255, 255, 255)    # White
    
    # Create SAXOFLOW using solid block characters
    saxoflow_art = create_solid_saxoflow()
    
    gradient_text = Text()
    
    # Find the maximum width to calculate horizontal gradient
    max_width = max(len(line) for line in saxoflow_art if line.strip())
    
    for row_idx, line in enumerate(saxoflow_art):
        for col_idx, char in enumerate(line):
            if char == ' ':
                # Just append space without any coloring
                gradient_text.append(char)
            else:
                # Calculate gradient position based on column position (left to right)
                blend = col_idx / max(1, max_width - 1)
                
                # Interpolate RGB values
                r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * blend)
                g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * blend)
                b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * blend)
                
                # Color the solid block characters
                gradient_text.append(char, style=f"bold rgb({r},{g},{b})")
        
        gradient_text.append("\n")

    console.print(gradient_text)

def create_solid_saxoflow():
    """
    Create SAXOFLOW text using only solid block characters (█).
    Returns a list of strings representing each line.
    """
    # return [
    #     " ██████    ██████  ██   ██  ██████   ██████ ██       ██████  ██     ██",
    #     "██        ██    ██  ██ ██  ██    ██ ██      ██      ██    ██ ██     ██",
    #     " ██████   ████████   ███   ██    ██ ██████  ██      ██    ██ ██  █  ██",
    #     "      ██  ██    ██  ██ ██  ██    ██ ██      ██      ██    ██ ██ ███ ██",
    #     " ██████   ██    ██ ██   ██  ██████  ██       ██████  ██████   ███ ███ ",
    #     "",
    # ]

    return [
        "███████╗ █████╗ ██╗   ██╗ ██████╗  ██████╗ ██╗      ██████╗ ██╗    ██╗",
        "██╔════╝██╔══██╗ ██║ ██╔╝██╔═══██╗██╔════╝ ██║     ██╔═══██╗██║    ██║",
        "███████╗███████║  ████╔╝ ██║   ██║██████╗  ██║     ██║   ██║██║ █╗ ██║",
        "╚════██║██╔══██║ ██╔═██╗ ██║   ██║██╔═══╝  ██║     ██║   ██║██║███╗██║",
        "███████║██║  ██║██║   ██╗╚██████╔╝██║      ███████╗╚██████╔╝╚███╔███╔╝",
        "╚══════╝╚═╝  ╚═╝╚═╝   ╚═╝ ╚═════╝ ╚═╝      ╚══════╝ ╚═════╝  ╚══╝╚══╝ ",
        ""
    ]

def print_saxoflow_banner_compact(console: Console) -> None:
    """
    Render a compact SAXOFLOW banner using a cyan‑to‑white gradient.

    The compact art uses only solid block characters (█) for crisp
    rendering on all terminals.  A horizontal gradient is applied
    across each row from light cyan to white to harmonise with the
    primary colour palette.
    """
    # Gradient colours: light cyan on the left to white on the right
    start_rgb = (64, 224, 255)   # Light cyan/blue
    end_rgb = (255, 255, 255)    # White

    compact_art = [
        "███  ███  █   █  ███  ███  █    ███  █   █",
        "█    █ █   █ █   █ █  █    █    █ █  █ █ █",
        "███  ███    █    ███  ███  █    ███  █ █ █",
        "  █  █ █   █ █   █ █  █    █    █ █  █ █ █",
        "███  █ █  █   █  █ █  █    ███  ███   █ █ ",
    ]

    gradient_text = Text()
    max_width = max(len(line) for line in compact_art)
    for line in compact_art:
        for col_idx, char in enumerate(line):
            if char == ' ':
                gradient_text.append(char)
            else:
                blend = col_idx / max(1, max_width - 1)
                r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * blend)
                g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * blend)
                b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * blend)
                gradient_text.append(char, style=f"bold rgb({r},{g},{b})")
        gradient_text.append("\n")

    console.print(gradient_text)

def fill_letter_interiors(lines):
    """
    Fill the interior spaces of ASCII art letters.
    Converts hollow letters to solid filled letters.
    """
    if not lines:
        return lines
    
    # Convert lines to a 2D grid for easier manipulation
    max_width = max(len(line) for line in lines)
    grid = []
    for line in lines:
        # Pad line to max width and convert to list for mutability
        padded_line = line.ljust(max_width)
        grid.append(list(padded_line))
    
    height = len(grid)
    width = max_width
    
    # For each row, fill spaces that are enclosed between non-space characters
    for row in range(height):
        # Find segments between non-space characters and fill them
        in_letter = False
        start_fill = -1
        
        for col in range(width):
            char = grid[row][col]
            
            if char != ' ':  # Found a letter character
                if not in_letter:
                    # Starting a new letter segment
                    in_letter = True
                    start_fill = col
                else:
                    # We're continuing in a letter or found the end
                    # Fill the gap between start_fill and current position
                    if start_fill != -1 and col > start_fill + 1:
                        for fill_col in range(start_fill + 1, col):
                            if grid[row][fill_col] == ' ':
                                grid[row][fill_col] = '█'  # Use a solid block character
                    start_fill = col
            # If we hit a space, we might be in a gap or outside the letter
            # We'll continue and let the next non-space character handle filling
    
    # Also fill vertical gaps within letters
    for col in range(width):
        in_letter = False
        start_fill = -1
        
        for row in range(height):
            char = grid[row][col]
            
            if char != ' ':  # Found a letter character
                if not in_letter:
                    in_letter = True
                    start_fill = row
                else:
                    # Fill vertical gap
                    if start_fill != -1 and row > start_fill + 1:
                        for fill_row in range(start_fill + 1, row):
                            if grid[fill_row][col] == ' ':
                                # Only fill if there are non-spaces on both sides horizontally too
                                left_has_char = col > 0 and grid[fill_row][col-1] != ' '
                                right_has_char = col < width-1 and grid[fill_row][col+1] != ' '
                                if left_has_char or right_has_char:
                                    grid[fill_row][col] = '█'
                    start_fill = row
    
    # Convert back to strings
    filled_lines = [''.join(row).rstrip() for row in grid]
    return filled_lines

def print_saxoflow_banner_alt_colors(console: Console) -> None:
    """
    Alternative banner with a cyan‑to‑purple gradient.

    This variation transitions from deep cyan to a soft purple across
    each line, offering a striking yet harmonious contrast to the
    primary cyan–white palette.  Only solid block characters are used
    to ensure crisp rendering on all displays.
    """
    # Gradient: deep cyan to soft purple
    start_rgb = (0, 191, 255)   # Deep sky blue
    end_rgb = (160, 32, 240)    # Purple

    saxoflow_art = create_solid_saxoflow()
    gradient_text = Text()
    max_width = max(len(line) for line in saxoflow_art if line.strip())
    for line in saxoflow_art:
        for col_idx, char in enumerate(line):
            if char == ' ':
                gradient_text.append(char)
            else:
                blend = col_idx / max(1, max_width - 1)
                r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * blend)
                g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * blend)
                b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * blend)
                gradient_text.append(char, style=f"bold rgb({r},{g},{b})")
        gradient_text.append("\n")

    console.print(gradient_text)

def print_saxoflow_banner_compact(console: Console):
    """
    Compact version of SAXOFLOW banner for smaller spaces.
    Uses only solid block characters (█) with horizontal gradient.
    """
    # Define gradient colors
    start_rgb = (64, 224, 255)   # Light cyan/blue
    end_rgb = (144, 238, 144)    # Light green
    
    # Smaller version of SAXOFLOW using only █
    compact_art = [
        "███  ███  █   █  ███  ███  █    ███  █   █",
        "█    █ █   █ █   █ █  █    █    █ █  █ █ █",
        "███  ███    █    ███  ███  █    ███  █ █ █",
        "  █  █ █   █ █   █ █  █    █    █ █  █ █ █",
        "███  █ █  █   █  █ █  █    ███  ███   █ █ ",
    ]
    
    gradient_text = Text()
    
    # Find maximum width for horizontal gradient
    max_width = max(len(line) for line in compact_art)
    
    for line in compact_art:
        for col_idx, char in enumerate(line):
            if char == ' ':
                gradient_text.append(char)
            else:
                # Calculate horizontal gradient (left to right)
                blend = col_idx / max(1, max_width - 1)
                r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * blend)
                g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * blend)
                b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * blend)
                
                gradient_text.append(char, style=f"bold rgb({r},{g},{b})")
        
        gradient_text.append("\n")

    console.print(gradient_text)
