import curses
import sys
import signal


def is_end_of_line(y, x, lines):
    return x >= len(lines[y])


PAIR_CHARS = {('"', '"'), ("'", "'"), ("(", ")"), ("[", "]"), ("<", ">"), ("{", "}")}


def find_pair_boundaries(y, x, lines):
    """
    Find the boundaries of pairs like "", '', {}, [], and ().
    Returns ((start_y, start_x), (end_y, end_x)) if a pair is found, otherwise None.
    """
    for start_char, end_char in PAIR_CHARS:
        start_pos, end_pos = None, None

        # Search backward for the start character
        cur_x = x
        while cur_x >= 0:
            if lines[y][cur_x] == start_char:
                start_pos = (y, cur_x)
                break
            cur_x -= 1

        # Search forward for the end character
        cur_x = x
        while cur_x < len(lines[y]):
            if lines[y][cur_x] == end_char:
                end_pos = (y, cur_x + 1)  # Include the end character in the selection
                break
            cur_x += 1

        if start_pos and end_pos:
            return start_pos, end_pos

    return None


def alt_n_logic(y, x, lines, selection_stage):
    """
    Logic for alt-n key press. Cycles through selection stages.
    """
    if selection_stage == 0:  # Word selection
        start, end, _ = find_word_boundaries(y, x, lines, None)
        return start, end, 1  # Move to next stage
    elif selection_stage == 1:  # Pair selection
        pair_boundaries = find_pair_boundaries(y, x, lines)
        if pair_boundaries:
            return pair_boundaries[0], pair_boundaries[1], 2
        else:
            # If no pair is found, skip directly to line selection
            return (y, 0), (y, len(lines[y])), 3
    elif selection_stage == 2:  # Line selection
        return (y, 0), (y, len(lines[y])), 3
    else:  # Reset selection
        return (y, x), (y, x), 0


def alt_p_logic(y, x, lines, selection_stage):
    """
    Logic for alt-p key press. Reverse cycles through selection stages.
    """
    if selection_stage <= 0:  # No selection
        return (y, x), (y, x), 0
    elif selection_stage == 1:  # Word selection
        return (y, x), (y, x), 0
    elif selection_stage == 2:  # Pair selection
        start, end, _ = find_word_boundaries(y, x, lines, None)
        return start, end, 1
    elif selection_stage == 3:  # Line selection
        pair_boundaries = find_pair_boundaries(y, x, lines)
        if pair_boundaries:
            return pair_boundaries[0], pair_boundaries[1], 2
        return (y, 0), (y, len(lines[y])), 2


def find_word_boundaries(y, x, lines, current_selection):
    if not lines or not lines[y] or not lines[y][x].isalnum():
        return (y, x), (y, x), False  # No word at the cursor

    start_x, end_x = x, x

    # Find the start of the word
    while start_x > 0 and lines[y][start_x - 1].isalnum():
        start_x -= 1

    # Find the end of the word
    while end_x < len(lines[y]) and lines[y][end_x].isalnum():
        end_x += 1

    entire_word_selected = current_selection == ((y, start_x), (y, end_x))
    return (y, start_x), (y, end_x), entire_word_selected


def modify_selected_text(lines, selection_start, selection_end, modify_function):
    if not selection_start or not selection_end:
        return lines, (0, 0)  # Return default cursor position if no selection

    # Determine the start and end points correctly
    start_y, start_x = min(selection_start, selection_end)
    end_y, end_x = max(selection_start, selection_end)

    # Extract the selected text
    selected_text = extract_selected_text((start_y, start_x), (end_y, end_x), lines)

    # Apply modification function to the selected text
    modified_text = modify_function(selected_text)
    modified_lines = modified_text.split("\n")

    # Merge the modified text back into the lines
    if start_y == end_y:
        # Modification within a single line
        lines[start_y] = lines[start_y][:start_x] + modified_text + lines[end_y][end_x:]
    else:
        # Modification spans multiple lines
        lines[start_y] = lines[start_y][:start_x] + modified_lines[0]

        # Handle multiple modified lines
        if len(modified_lines) > 1:
            lines[end_y] = modified_lines[-1] + lines[end_y][end_x:]
            lines[start_y + 1 : end_y] = modified_lines[1:-1]
        else:
            # Concatenate parts of the start and end line if modified_text is empty
            lines[start_y] = lines[start_y][:start_x] + lines[end_y][end_x:]
            del lines[start_y + 1 : end_y + 1]

    # Remove any empty lines that may have been introduced
    lines = [line for line in lines if line.strip() != ""]

    # Calculate the new cursor position
    new_y, new_x = start_y, start_x
    if new_y >= len(lines):  # Ensure new_y is within the range of lines
        new_y = max(0, len(lines) - 1)
    if lines:  # Ensure lines list is not empty
        new_x = min(new_x, len(lines[new_y]))
    else:  # If lines list is empty, reset cursor to (0, 0)
        new_y, new_x = 0, 0

    return lines, (new_y, new_x)


def move_to_next_word(y, x, lines, backward=False):
    if backward:
        return move_to_previous_word(y, x, lines)

    if y >= len(lines) - 1 and x >= len(lines[y]) - 1:
        # If at the last word of the last line, do nothing
        return y, x

    # Check if we're currently in the middle of a word
    in_word = x < len(lines[y]) and lines[y][x].isalnum()

    # If we're not in a word, move to the start of the next word
    if not in_word:
        while y < len(lines) and x < len(lines[y]) and not lines[y][x].isalnum():
            x += 1
            if x >= len(lines[y]):
                y += 1
                x = 0
                if y >= len(lines):
                    return len(lines) - 1, len(lines[-1]) - 1

    # Move to the end of the current or next word
    while y < len(lines) and x < len(lines[y]) and lines[y][x].isalnum():
        x += 1

    return y, x


def move_to_previous_word(y, x, lines, backward=False):
    if backward:
        return move_to_next_word(y, x, lines)

    if y == 0 and x == 0:
        # If at the first word of the first line, do nothing
        return y, x

    # Move left from the current position
    if x > 0:
        x -= 1

    # If we are at the beginning of a line, move up to the end of the previous line
    if x == 0 and y > 0:
        y -= 1
        x = len(lines[y]) - 1

    # Move to the beginning of the current or previous word
    while y >= 0 and x >= 0 and not lines[y][x].isalnum():
        x -= 1
        if x < 0 and y > 0:
            y -= 1
            x = len(lines[y]) - 1

    while y >= 0 and x > 0 and lines[y][x - 1].isalnum():
        x -= 1

    return y, x


def extract_selected_text(start, end, lines):
    if not start or not end:
        return ""

    selected_text = ""
    start_y, start_x = start
    end_y, end_x = end

    if start_y == end_y:
        selected_text = lines[start_y][start_x:end_x]
    else:
        selected_text += lines[start_y][start_x:] + "\n"
        for line_num in range(start_y + 1, end_y):
            selected_text += lines[line_num] + "\n"
        selected_text += lines[end_y][:end_x]

    return selected_text


def insert_character_at_cursor(lines, y, x, char):
    if not lines:  # If lines is empty, add a new line
        lines.append("")
        y, x = 0, 0

    # Insert the character at the cursor location
    lines[y] = lines[y][:x] + char + lines[y][x:]
    return lines


def load_file(file_path):
    try:
        with open(file_path, "r") as file:
            lines = file.read().splitlines()
        if not lines:  # If the file is empty, add an empty line
            lines.append("")
        return lines
    except FileNotFoundError:
        # If the file does not exist, create it with an empty content
        with open(file_path, "w") as file:
            pass
        return [""]  # Return a list with one empty line


def save_file(file_path, lines):
    with open(file_path, "w") as file:
        trimmed_lines = [line.rstrip() for line in lines]
        file.write("\n".join(trimmed_lines))


def main(stdscr, file_path):
    # Initialize curses
    curses.curs_set(1)
    stdscr.clear()
    curses.start_color()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Selection color

    # Load the text from the file
    lines = load_file(file_path)

    y, x = 0, 0
    alt_pressed = False
    selection_start = None
    selection_end = None
    is_selecting = False
    extend_selection_forward = True  # Flag to extend the selection forward or backward
    is_navigation_command = False
    selection_stage = 0  # Initialize the selection stage

    while True:
        try:
            stdscr.clear()
            # Display the text buffer with optional selection highlighting
            for i, line in enumerate(lines):
                if (
                    is_selecting
                    and selection_start is not None
                    and selection_end is not None
                ):
                    # Determine the start and end of selection for highlighting
                    sel_start_y, sel_start_x = min(selection_start, selection_end)
                    sel_end_y, sel_end_x = max(selection_start, selection_end)

                    if sel_start_y <= i <= sel_end_y:
                        start_x = sel_start_x if i == sel_start_y else 0
                        end_x = sel_end_x if i == sel_end_y else len(line)
                        stdscr.addstr(i, 0, line[:start_x])
                        stdscr.addstr(
                            i, start_x, line[start_x:end_x], curses.color_pair(1)
                        )
                        stdscr.addstr(i, end_x, line[end_x:])
                    else:
                        stdscr.addstr(i, 0, line)
                else:
                    stdscr.addstr(i, 0, line)
            stdscr.move(y, x)
            key = stdscr.getch()
            if key == 27:  # Escape character for Alt key combinations
                alt_pressed = True
                continue

            # Handle Alt key press
            if alt_pressed:
                if key == ord("f"):  # Alt-f
                    y, x = move_to_next_word(y, x, lines)
                    if is_selecting:
                        selection_end = (y, x)
                elif key == ord("b"):  # Alt-b
                    y, x = move_to_previous_word(y, x, lines)
                    if is_selecting:
                        selection_end = (y, x)
                elif key == ord("n") and alt_pressed:  # Alt-n
                    selection_start, selection_end, selection_stage = alt_n_logic(
                        y, x, lines, selection_stage
                    )
                    is_selecting = True
                elif key == ord("p") and alt_pressed:  # Alt-p
                    selection_start, selection_end, selection_stage = alt_p_logic(
                        y, x, lines, selection_stage
                    )
                    is_selecting = selection_stage != 0
                elif key == ord("m") and alt_pressed:  # Alt-m
                    modify_function = (
                        lambda text: text.upper()
                    )  # Example: Convert to uppercase
                    lines, (y, x) = modify_selected_text(
                        lines, selection_start, selection_end, modify_function
                    )
                    selection_start = None
                    selection_end = None
                    is_selecting = False
                    # Validate cursor position
                    y = min(y, len(lines) - 1)
                    x = min(x, len(lines[y]) if lines else 0)
                elif key == ord("u") and alt_pressed:  # Alt-u
                    modify_function = lambda text: ""  # Delete
                    lines, (y, x) = modify_selected_text(
                        lines, selection_start, selection_end, modify_function
                    )
                    selection_start = None
                    selection_end = None
                    is_selecting = False
                elif key == ord("s"):
                    save_file(file_path, lines)
                elif key == ord(" "):  # Alt-Space
                    if selection_start and selection_end:
                        selected_text = extract_selected_text(
                            selection_start, selection_end, lines
                        )
                        # Handle the extracted text as needed
                alt_pressed = False
                continue

            # Handle other key presses
            if key == curses.KEY_RIGHT or key == ord("\x06"):  # Ctrl-f
                if extend_selection_forward:
                    x = min(x + 1, len(lines[y]))
                else:
                    x = max(x - 1, 0)
                if is_selecting:
                    selection_end = (y, x)
                is_navigation_command = True
            elif key == curses.KEY_LEFT or key == ord("\x02"):  # Ctrl-b
                if extend_selection_forward:
                    x = max(x - 1, 0)
                else:
                    x = min(x + 1, len(lines[y]))
                if is_selecting:
                    selection_end = (y, x)
                is_navigation_command = True
            elif key == curses.KEY_DOWN or key == ord("\x0e"):  # Ctrl-n
                if y >= len(lines) - 1:
                    # If on the last line, add a new empty line
                    lines.append("")
                y = min(y + 1, len(lines) - 1)
                x = min(x, len(lines[y]))
                if is_selecting:
                    selection_end = (y, x)
                is_navigation_command = True
            elif key == curses.KEY_UP or key == ord("\x10"):  # Ctrl-p
                if y == 0:
                    # If on the first line, insert a new empty line at the beginning
                    lines.insert(0, "")
                    # No need to change y, as we want the cursor to move to the new line above
                else:
                    y = max(y - 1, 0)
                x = min(x, len(lines[y]))
                if is_selecting:
                    selection_end = (y, x)
                is_navigation_command = True

            elif key == ord("\x01"):  # Ctrl-a
                x = 0
                if is_selecting:
                    selection_end = (y, x)
                is_navigation_command = True
            elif key == ord("\x05"):  # Ctrl-e
                x = len(lines[y])
                if is_selecting:
                    selection_end = (y, x)
                is_navigation_command = True
            elif key == 0:  # Ctrl-Space
                if not is_selecting:
                    selection_start = (y, x)
                    selection_end = (y, x)
                    is_selecting = True
                else:
                    is_selecting = False
            elif is_selecting:
                selection_end = (y, x)
            elif key == ord(" "):  # Space
                if not is_selecting:
                    lines = insert_character_at_cursor(lines, y, x, " ")  # Insert space
                    x += 1  # Move cursor right
                    is_navigation_command = True
                elif is_navigation_command:
                    extend_selection_forward = not extend_selection_forward
                else:
                    selection_start = None
                    selection_end = None
                    is_selecting = False
                is_navigation_command = False
            elif key == curses.KEY_ENTER or key == ord("\n"):  # Handle Enter key
                # Split the current line at the cursor position
                lines.insert(
                    y + 1, lines[y][x:]
                )  # Move the rest of the line to the next line
                lines[y] = lines[y][
                    :x
                ]  # Keep only the part of the line before the cursor
                y = min(y + 1, len(lines) - 1)
                x = 0  # Reset cursor position to the start of the line

            elif key == ord("\t"):  # Handle Tab key
                tab_spaces = "    "  # Represent a tab as 4 spaces (or use "\t" for a tab character)
                lines[y] = lines[y][:x] + tab_spaces + lines[y][x:]
                x += len(tab_spaces)
            elif key == curses.KEY_DC or key == ord("\x7f"):  # Delete or Backspace
                if not lines:  # If lines list is empty, reset cursor
                    y, x = 0, 0

                if (
                    x == 0 and y > 0
                ):  # If at the beginning of a line, merge with the previous line
                    lines[y - 1] = (
                        lines[y - 1].rstrip() + lines[y].lstrip()
                    )  # Merge lines without extra spaces
                    del lines[y]  # Remove the current line
                    y -= 1
                    x = len(
                        lines[y]
                    )  # Position the cursor at the end of the merged line
                elif x > 0:
                    lines[y] = (
                        lines[y][: x - 1] + lines[y][x:]
                    )  # Remove the character before the cursor
                    x -= 1  # Move cursor left

                if not lines:  # If all lines are deleted
                    lines.append("")  # Add an empty line
                    y, x = 0, 0  # Reset cursor position

                # Validate cursor position
                y = min(y, len(lines) - 1)
                x = min(x, len(lines[y]) if lines else 0)
            elif key >= 32 and key <= 126:  # Insert printable character
                if not is_selecting:
                    char = chr(key)
                    lines = insert_character_at_cursor(lines, y, x, char)
                    x += 1  # Move cursor right
                    # Validate cursor position
                    y = min(y, len(lines) - 1)
                    x = min(x, len(lines[y]) if lines else 0)
                    is_navigation_command = True
                else:
                    selection_start = None
                    selection_end = None
                    is_selecting = False
                is_navigation_command = False
            elif is_selecting:
                selection_end = (y, x)

            # Validate cursor position
            y = min(y, len(lines) - 1)
            x = min(x, len(lines[y]) if lines else 0)

            # Refresh the screen
            stdscr.refresh()
        except KeyboardInterrupt:
            sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python editor.py <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]
    # Register a signal handler for Ctrl-C (SIGINT)
    signal.signal(signal.SIGINT, lambda signum, frame: sys.exit(0))
    curses.wrapper(main, file_path)
