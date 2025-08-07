import logging
import os
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv()
LLM_MODEL = os.getenv("LLM_MODEL")
PERSONAL_DATA = os.getenv("PERSONAL_DATA")
ADEQUACY_ROUNDS = int(os.getenv("ADEQUACY_ROUNDS"))
PUNCTUATION_ROUNDS = int(os.getenv("PUNCTUATION_ROUNDS"))
with open('prompts/data/skills.txt', 'r') as f:
    SKILLS = f.read()
OLLAMA_API_URL = "http://ollama:11434/api/generate"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def send_request(prompt: str, conversation_history: list = None) -> str:
    """
    Send a request to the LLM model via Ollama API.

    Args:
        prompt: The current user prompt/message.
        conversation_history: List of previous messages in the conversation
            (format: [{"role": "user|assistant", "content": "..."}, ...])

    Returns:
        The cleaned response from the model.

    Raises:
        RuntimeError: If the server returns a 500 error.
        ValueError: If the response format is invalid.
        ConnectionError: If the request fails.
    """
    conversation_history = conversation_history or []

    messages = conversation_history + [{"role": "user", "content": prompt}]
    formatted_prompt = (
            "".join(
                (
                    f"Пользователь: {msg['content']}\n\n"
                    if msg["role"] == "user"
                    else f"Ассистент: {msg['content']}\n\n"
                )
                for msg in messages
            )
            + "Ассистент:[SEP]"
    )

    payload = {
        "model": LLM_MODEL,
        "prompt": formatted_prompt,
        "stream": False,
        "options": {
            "num_predict": 350,
            "temperature": 0.5,  # Creativity/strictness balance
            "top_p": 0.85,
            "stop": ["\n\n\n", "Добрый день, я", "Уважаемые"],
        },
    }

    try:
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=300)

        if response.status_code == 500:
            error_detail = response.text or "No error details provided by server"
            logger.error(f"Server Error (500) - Details: {error_detail}")
            raise RuntimeError(
                f"LLM service unavailable (500). Details: {error_detail}"
            )

        response.raise_for_status()

        try:
            model_response = response.json()["response"]
            return clean_response(model_response)
        except KeyError as e:
            logger.error(
                f'Missing "response" key in JSON: {str(e)} - Full response: {response.text}'
            )
            raise ValueError(
                "Invalid response format from LLM: missing 'response' field"
            ) from e
        except ValueError as e:
            logger.error(
                f"Invalid JSON response: {str(e)} - Response text: {response.text}"
            )
            raise ValueError("Invalid JSON response from LLM") from e

    except requests.exceptions.RequestException as e:
        logger.error(
            f"Request failed: {str(e)} - URL: {OLLAMA_API_URL} - Payload: {payload}"
        )
        raise ConnectionError(f"Failed to connect to LLM service: {str(e)}") from e


def clean_response(response: str) -> str:
    """
    Clean and format the model response.

    Args:
        response: The raw response from the model.

    Returns:
        The cleaned and formatted response.
    """
    cleaned = (
        response.replace("</s>", "")
        .strip()
        .replace("\n ", "\n")  # Remove spaces after newlines
        .replace("  ", " ")  # Remove double spaces
    )

    for char in ["#", "*", "`"]:
        cleaned = cleaned.replace(char, "")

    return cleaned


def send_for_enhance(text: str, edit_wishes: str) -> str:
    """
    Send text to the model for enhancement based on specific wishes.

    Args:
        text: The text to be enhanced.
        edit_wishes: Instructions for how to enhance the text.

    Returns:
        The enhanced text.
    """
    with open('prompts/change_letter.txt', 'r') as p:
        template = p.read()

    prompt = template.format(
        edit_wishes=edit_wishes,
        text=text
    )
    return send_request(prompt)


def fix_punctuation(text: str) -> str:
    """
    Fix punctuation and formatting issues in the text.

    Args:
        text: The text to be corrected.

    Returns:
        The corrected text.
    """
    with open('prompts/fix_punctuation.txt', 'r') as p:
        prompt = p.read()

    return send_for_enhance(text, prompt)


def fix_adequacy(text: str, skills: str, requirements: str | dict) -> str:
    """
    Ensure the text accurately represents skills and meets requirements.

    Args:
        text: The text to be checked.
        skills: The candidate's actual skills.
        requirements: The job requirements.

    Returns:
        The corrected text.
    """
    with open('prompts/fix_adequacy.txt', 'r') as p:
        template = p.read()

    prompt = template.format(
        skills=skills,
        requirements=requirements
    )

    return send_for_enhance(text, prompt)


def is_require_punctuation(text: str) -> bool:
    """
    Check if the text requires punctuation corrections.

    Args:
        text: The text to be checked.

    Returns:
        True if punctuation is correct, False otherwise.
    """
    with open('prompts/is_require_punctuation.txt', 'r') as p:
        template = p.read()

    prompt = template.format(
        text=text,
    )

    response = send_request(prompt)
    return yes_no_recognizer(response)


def is_require_adequacy(text: str, skills: str, requirements: str | dict) -> bool:
    """
    Check if the text accurately represents skills and requirements.

    Args:
        text: The text to be checked.
        skills: The candidate's actual skills.
        requirements: The job requirements.

    Returns:
        True if the text is accurate, False otherwise.
    """
    with open('prompts/is_require_adequacy.txt', 'r') as p:
        template = p.read()

    prompt = template.format(
        skills=skills,
        text=text,
        requirements=requirements
    )

    response = send_request(prompt)
    return yes_no_recognizer(response)


def yes_no_recognizer(text: str) -> bool:
    """
    Recognize a yes/no answer in Russian text.

    Args:
        text: The text to analyze (should contain "да" or "нет").

    Returns:
        True if "да" is found, False if "нет" is found.

    Raises:
        ValueError: If the input doesn't contain a clear yes/no answer.
        Exception: If input is not a string or is too long.
    """
    if not isinstance(text, str):
        raise Exception("Input should be a string")
    if len(text) > 5:
        raise Exception("Input length should be <= 5 characters")

    text = text.lower()
    if "да" in text and "нет" not in text:
        return True
    elif "нет" in text and "да" not in text:
        return False
    else:
        raise ValueError("Input does not contain a clear yes/no answer")


class VacancyCache:
    """Cache for tracking processed vacancies."""

    def __init__(self):
        self.cache = set()
        self.initialize_cache()

    def initialize_cache(self):
        """Initialize the cache by scanning existing letter files."""
        if not os.path.exists("letters/"):
            os.makedirs("letters/", exist_ok=True)
            return

        for root, _, files in os.walk("letters/"):
            for file_name in files:
                try:
                    vacancy_id = file_name.split("-")[0]
                    self.cache.add(vacancy_id)
                except IndexError:
                    continue

    def is_new_vacancy(self, vacancy) -> bool:
        """
        Check if a vacancy is new (not in cache).

        Args:
            vacancy: Can be a string/number (ID) or dict with 'id' key.

        Returns:
            True if the vacancy is new, False if already processed.

        Raises:
            ValueError: If the input type is not supported.
        """
        if isinstance(vacancy, (str, int, float)):
            vacancy_id = str(vacancy)
        elif isinstance(vacancy, dict) and "id" in vacancy:
            vacancy_id = str(vacancy["id"])
        else:
            raise ValueError(
                f"Unsupported data type for vacancy: {type(vacancy)}. "
                "Expected string/number (ID) or dictionary with key 'id'"
            )

        return vacancy_id not in self.cache


def process(vacancy_id: str, context: dict) -> None:
    """
    Generate and validate a cover letter for a job vacancy.

    Args:
        vacancy_id: The ID of the vacancy.
        context: Dictionary containing vacancy details.

    Raises:
        Exception: If unable to generate a valid letter after multiple attempts.
    """
    with open('prompts/generate_letter.txt', 'r') as p:
        template = p.read()

    prompt = template.format(
        PERSONAL_DATA=PERSONAL_DATA,
        SKILLS=SKILLS,
        context=context
    )

    logger.info(f"Generating letter for vacancy {vacancy_id}")
    letter = send_request(prompt)

    logger.info(f"Validating adequacy for vacancy {vacancy_id}")
    for round in range(1, ADEQUACY_ROUNDS + 1):
        if is_require_adequacy(letter, SKILLS, context):
            break
        logger.info(f"Adequacy check round {round} for vacancy {vacancy_id}")
        letter = fix_adequacy(letter, SKILLS, context)
    else:
        save_to_txt(letter, f"{vacancy_id}", defective=True)
        raise Exception(
            f"Failed to generate adequate letter for vacancy {vacancy_id} after {ADEQUACY_ROUNDS} attempts"
        )

    logger.info(f"Validating punctuation for vacancy {vacancy_id}")
    for round in range(1, PUNCTUATION_ROUNDS + 1):
        if is_require_punctuation(letter):
            break
        logger.info(f"Punctuation check round {round} for vacancy {vacancy_id}")
        letter = fix_punctuation(letter)
    else:
        save_to_txt(letter, f"{vacancy_id}", defective=True)
        raise Exception(
            f"Failed to fix punctuation for vacancy {vacancy_id} after {PUNCTUATION_ROUNDS} attempts"
        )

    logger.info(f"Letter for vacancy {vacancy_id} meets all requirements")
    save_to_txt(letter, vacancy_id)


def save_to_txt(content: str, filename: str, defective: bool = False) -> None:
    """
    Save content to a text file in the letters directory.

    Args:
        content: The text content to save.
        filename: The base filename (without extension).
    """
    name_format = f"{filename}-{date.today()}"
    os.makedirs("letters/defective/", exist_ok=True)
    if not defective:
        filepath = f"letters/{name_format}.txt"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        filepath = f"letters/defective/{name_format}.txt"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    logger.info(f"Saved letter to {filepath}")

