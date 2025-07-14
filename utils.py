import logging
import os
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv()
LLM_MODEL = os.getenv("LLM_MODEL")
SKILLS = os.getenv("SKILLS")
PERSONAL_DATA = os.getenv("PERSONAL_DATA")

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
            "num_predict": 350,  # Optimal for 2 paragraphs
            "temperature": 0.6,  # Creativity/strictness balance
            "top_p": 0.85,  # Better selectivity
            "stop": ["\n\n\n", "Добрый день, я", "Уважаемые"],  # Clear boundaries
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
    prompt = f"""
    СОПРОВОДИТЕЛЬНОЕ ПИСЬМО НУЖНО ИЗМЕНИТЬ С УЧЁТОМ ПОЖЕЛАНИЙ.
    ПОЖЕЛАНИЯ:
    {edit_wishes}
    В ТВОЁМ ОТВЕТЕ ДОЛЖНО БЫТЬ ТОЛЬКО ИЗМЕНЕННОЕ ПИСЬМО И НИЧЕГО БОЛЬШЕ
    ПИСЬМО:
    {text}"""
    return send_request(prompt)


def fix_punctuation(text: str) -> str:
    """
    Fix punctuation and formatting issues in the text.

    Args:
        text: The text to be corrected.

    Returns:
        The corrected text.
    """
    prompt = "В письме что-то не так с пунктуацией или есть плейсхолдеры. Нужно привести письмо в презентабельный вид, что бы его можно было отправить с откликом."
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
    prompt = f"""В письме что-то есть несоответствия с навыками кандидата или требованиями. 
    Нужно сделать так, что бы письмо не врало по поводу навыков и соответствовало требованиям.
    Навыки кандидата:
    {skills}
    Требования к вакансии:
    {requirements}"""
    return send_for_enhance(text, prompt)


def is_require_punctuation(text: str) -> bool:
    """
    Check if the text requires punctuation corrections.

    Args:
        text: The text to be checked.

    Returns:
        True if punctuation is correct, False otherwise.
    """
    prompt = f"""
    Ответь на вопрос соответствует ли письмо правильной пунктуации, нет ли лишних символов или плейсхолдеров. Можно ли его прямо сейчас отправить с откликом.
    ОТВЕТ ЛИБО ДА ЛИБО НЕТ
    ПИСЬМО:
    {text}"""
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
    prompt = f"""
    Ответь на вопрос соответствует ли письмо навыкам кандидата и требованиям вакансии. Нет ли наглого вранья, что кандидат знает какой-то фреймворк или технологию, которой не указано в навыках.
    Навыки кандидата:
    {skills}
    Требования к вакансии:
    {requirements}
    Письмо:
    {text}
    ОТВЕТ ЛИБО ДА ЛИБО НЕТ:"""
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
    prompt = f"""
    ТВОИ ЖЕСТКИЕ ПРАВИЛА:
    1. Формат: 3 АБЗАЦА (4-6 предложений) + КОНТАКТЫ ОТДЕЛЬНО
    2. ТОЛЬКО КОНКРЕТИКА из данных ниже
    3. НИКАКИХ шаблонных фраз типа "идеально подхожу"
    4. Акцент на: ЧТО СДЕЛАЛ → КАКОЙ РЕЗУЛЬТАТ → КАК ЭТО РЕЛЕВАНТНО вакансии

    ДАННЫЕ КАНДИДАТА (НЕ ИЗМЕНЯТЬ):
    {PERSONAL_DATA}
    {SKILLS}

    ВАКАНСИЯ:
    {context}

    СГЕНЕРИРУЙ ТОЧНО ПО СТРУКТУРЕ:
    [Приветствие]

    [1 абзац] Конкретно какие 2-3 навыка из вакансии закрываю + факты
    [2 абзац] Как именно мой опыт решит ваши задачи (на примере проектов)
    [3 мини-абзац] Почему вакансия интересна, пару примеров из требований/описания

    [отдельно] Контакты одной строкой

    ПРИМЕР:
    Здравствуйте, меня зовут [Имя].

    У меня есть опыт работы с [Основной навык 1] и [Основной навык 2], что соответствует ключевым требованиям вакансии. В частности, я работал с [Технология/Инструмент], который активно используется в вашем проекте. Это позволяет мне быстро включиться в рабочий процесс.

    В моем предыдущем проекте по [Область применения] я занимался [Конкретная задача]. Этот опыт напрямую соотносится с [Требование из вакансии]. Также участвовал в [Другой релевантный проект], где применял [Соответствующий навык].

    Ваша вакансия привлекла меня потому, что [Причина 1] и [Причина 2]. Особенно интересен аспект [Конкретный пункт из описания вакансии], который соответствует моему профессиональному опыту.

    Контакты для связи: [Телефон], [Email]
    """

    logger.info(f"Generating letter for vacancy {vacancy_id}")
    letter = send_request(prompt)

    logger.info(f"Validating adequacy for vacancy {vacancy_id}")
    for round in range(1, 4):
        if is_require_adequacy(letter, SKILLS, context):
            break
        logger.info(f"Adequacy check round {round} for vacancy {vacancy_id}")
        letter = fix_adequacy(letter, SKILLS, context)
    else:
        save_to_txt(letter, f"{vacancy_id}-defective")
        raise Exception(
            f"Failed to generate adequate letter for vacancy {vacancy_id} after 3 attempts"
        )

    logger.info(f"Validating punctuation for vacancy {vacancy_id}")
    for round in range(1, 4):
        if is_require_punctuation(letter):
            break
        logger.info(f"Punctuation check round {round} for vacancy {vacancy_id}")
        letter = fix_punctuation(letter)
    else:
        save_to_txt(letter, f"{vacancy_id}-defective")
        raise Exception(
            f"Failed to fix punctuation for vacancy {vacancy_id} after 3 attempts"
        )

    logger.info(f"Letter for vacancy {vacancy_id} meets all requirements")
    save_to_txt(letter, vacancy_id)


def save_to_txt(content: str, filename: str) -> None:
    """
    Save content to a text file in the letters directory.

    Args:
        content: The text content to save.
        filename: The base filename (without extension).
    """
    os.makedirs("letters/", exist_ok=True)
    filepath = f"letters/{filename}-{date.today()}.txt"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"Saved letter to {filepath}")
