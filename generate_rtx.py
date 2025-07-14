import logging
import os
import shutil
from datetime import datetime


def rtf_escape(text):
    """Escape text for RTF with full Unicode (Cyrillic) support."""
    escaped = (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", "\\par\n")
    )
    return "".join(c if ord(c) < 128 else f"\\u{ord(c)}?" for c in escaped)


def create_rtf_with_cover_letters():
    """Generate RTF file with cover letters and archive processed files."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    letters_dir = "letters"
    today = datetime.now().strftime("%d-%m-%y")
    archive_dir = os.path.join(letters_dir, today)
    output_rtf = "cover_letters.rtf"

    os.makedirs(archive_dir, exist_ok=True)

    with open(output_rtf, "w", encoding="utf-8") as rtf_file:
        rtf_file.write(
            r"{\rtf1\ansi\ansicpg1251\deff0" + "\n"
            r"{\fonttbl{\f0\fnil\fcharset204 Calibri;}}" + "\n"
            r"{\*\generator Python RTF Generator}" + "\n"
            r"\viewkind4\uc1\pard\f0\fs24" + "\n"
        )

        for file_name in os.listdir(letters_dir):
            file_path = os.path.join(letters_dir, file_name)

            if (
                not os.path.isfile(file_path)
                or file_name == "cover_letters.rtf"
                or "defective" in file_name.lower()
            ):
                continue

            try:
                vacancy_id = file_name.split("-")[0]
                hh_link = f"https://hh.ru/vacancy/{vacancy_id}"

                with open(file_path, "r", encoding="utf-8") as f:
                    cover_text = f.read().strip()

                rtf_file.write(
                    f"{rtf_escape('Вакансия:')} \\b0 {hh_link}\\par\n"
                    f"{rtf_escape('Текст письма:')} \\b0\\par\n"
                    f"{rtf_escape(cover_text)}\\par\n"
                    "\\line\\par\\par\n"
                )

                shutil.move(file_path, os.path.join(archive_dir, file_name))
                logging.info(f"Processed: {file_name}")

            except Exception as e:
                logging.error(f"Error processing {file_name}: {e}")
                continue

        rtf_file.write("}")

    logging.info(f"\nDone! RTF file: {os.path.abspath(output_rtf)}")
    logging.info(f"Letters archive: {os.path.abspath(archive_dir)}")


if __name__ == "__main__":
    create_rtf_with_cover_letters()