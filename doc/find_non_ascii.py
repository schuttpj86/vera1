import os


def find_non_ascii_in_folder(folder_path: str, extensions=None):
    """
    Recursively search for non-ASCII characters in files under a folder,
    optionally filtering by file extension.

    Args:
        folder_path (str): Root folder to scan.
        extensions (list[str], optional): List of allowed extensions (e.g. ['.md', '.py']).
                                          If None, all files are checked.

    Returns:
        list[tuple]: (file_path, line_number, column_number, char, line)
    """
    non_ascii_occurrences = []
    if extensions:
        extensions = [ext.lower() for ext in extensions]

    for root, _, files in os.walk(folder_path):
        for filename in files:
            if extensions and not any(filename.lower().endswith(ext) for ext in extensions):
                continue  # skip non-matching extensions

            file_path = os.path.join(root, filename)
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, start=1):
                        for j, ch in enumerate(line, start=1):
                            if ord(ch) > 127:
                                non_ascii_occurrences.append(
                                    (file_path, i, j, repr(ch), line.strip())
                                )
            except Exception as e:
                print(f"⚠️ Could not read file {file_path}: {e}")

    if non_ascii_occurrences:
        print("Found non-ASCII characters:\n")
        for file_path, line_num, col, ch, line in non_ascii_occurrences:
            print(f"{file_path}:{line_num}:{col}  {ch}  ->  {line}")
    else:
        print("✅ No non-ASCII characters found.")

    return non_ascii_occurrences


if __name__ == '__main__':
    find_non_ascii_in_folder("md_source", extensions=[".md"])
