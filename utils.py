import logging
import os
from datetime import date
import requests
from dotenv import load_dotenv

load_dotenv()
LLM_MODEL = os.getenv("LLM_MODEL")
SKILLS = os.getenv("SKILLS")
PERSONAL_DATA = os.getenv("PERSONAL_DATA")

url = "http://ollama:11434/api/generate"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def send_request(prompt, conversation_history=None):
    """
    Отправляет запрос к YandexGPT-5-Lite-8B-instruct через Ollama API

    :param prompt: Текущий запрос пользователя
    :param conversation_history: История диалога в формате [{"role": "user", "content": "..."}, ...]
    :return: Ответ модели
    """
    if conversation_history is None:
        conversation_history = []

    # Формируем полный контекст согласно шаблону модели
    messages = conversation_history + [{"role": "user", "content": prompt}]
    formatted_prompt = "".join(
        f"Пользователь: {msg['content']}\n\n" if msg["role"] == "user"
        else f"Ассистент: {msg['content']}\n\n"
        for msg in messages
    ) + "Ассистент:[SEP]"  # Критически важный маркер генерации

    data = {
        "model": LLM_MODEL,  # "yandexgpt-5-lite-8b-instruct"
        "prompt": formatted_prompt,
        "stream": False,
        "options": {
            "num_predict": 350,  # Оптимально для 2 абзацев
            "temperature": 0.6,  # Баланс креативности/строгости
            "top_p": 0.85,  # Лучшая селективность
            "stop": ["\n\n\n", "Добрый день, я", "Уважаемые"]  # Четкие границы
        }
    }

    try:
        r = requests.post(url, json=data, timeout=300)
        # logging.info(f'Request to {url} - Status: {r.status_code}')

        if r.status_code == 500:
            error_detail = r.text if r.text else 'No error details provided by server'
            logging.error(f'Server Error (500) - Details: {error_detail}')
            raise RuntimeError(f"LLM service unavailable (500). Details: {error_detail}")

        r.raise_for_status()

        try:
            response = r.json()['response']
            # Улучшенная очистка ответа
            cleaned_response = (
                response.replace("</s>", "")
                .strip()  # Удаляем пробелы в начале/конце
                .replace("\n ", "\n")  # Удаляем пробелы после переносов
                .replace("  ", " ")  # Удаляем двойные пробелы
            )
            # Дополнительная очистка форматирования
            for char in ['#', '*', '`']:
                cleaned_response = cleaned_response.replace(char, '')
            return cleaned_response
        except KeyError as e:
            logging.error(f'Missing "response" key in JSON: {str(e)} - Full response: {r.text}')
            raise ValueError("Invalid response format from LLM: missing 'response' field") from e
        except ValueError as e:
            logging.error(f'Invalid JSON response: {str(e)} - Response text: {r.text}')
            raise ValueError("Invalid JSON response from LLM") from e

    except requests.exceptions.RequestException as e:
        logging.error(f'Request failed: {str(e)} - URL: {url} - Payload: {data}')
        raise ConnectionError(f"Failed to connect to LLM service: {str(e)}") from e


def send_for_enhance(text, edit_wishes):
    prompt = f"""
    СОПРОВОДИТЕЛЬНОЕ ПИСЬМО НУЖНО ИЗМЕНИТЬ С УЧЁТОМ ПОЖЕЛАНИЙ.
    ПОЖЕЛАНИЯ:
    {edit_wishes}
    В ТВОЁМ ОТВЕТЕ ДОЛЖНО БЫТЬ ТОЛЬКО ИЗМЕНЕННОЕ ПИСЬМО И НИЧЕГО БОЛЬШЕ
    ПИСЬМО:
    {text}"""
    response = send_request(prompt)
    return response


def fix_punctuation(text):
    prompt = "В письме что-то не так с пунктуацией или есть плейсхолдеры. Нужно привести письмо в презентабельный вид, что бы его можно было отправить с откликом."
    return send_for_enhance(text, prompt)


def fix_adequacy(text, skills, requirements):
    prompt = (f"""В письме что-то есть несоответствия с навыками кандидата или требованиями. 
        Нужно сделать так, что бы письмо не врало по поводу навыков и соответствовало требованиям.
        Навыки кандидата:
        {skills}
        Требования к вакансии:
        {requirements}
         """)
    return send_for_enhance(text, prompt)


def is_require_punctuation(text):
    prompt = f"""
    Ответь на вопрос соответствует ли письмо правильной пунктуации, нет ли лишних символов или плейсхолдеров. Можно ли его прямо сейчас отправить с откликом.
    ОТВЕТ ЛИБО ДА ЛИБО НЕТ
    ПИСЬМО:
    {text}"""
    response = send_request(prompt)
    return yes_no_recognizer(response)


def is_require_adequacy(text, skills, requirements):
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


def yes_no_recognizer(string: str) -> bool:
    """Recognizes yes or no in string"""
    if not isinstance(string, str):
        raise Exception('Type should be string')
    if len(string) > 5:
        raise Exception('Lenght should be <= 5')
    string = string.lower()
    if 'да' in string and 'нет' not in string:
        return True
    elif 'нет' in string and 'да' not in string:
        return False
    else:
        raise ValueError('Incorrect Value')


_old_vacancies_cache = None


def is_new_vacancy(vacancy):
    global _old_vacancies_cache

    # Инициализация кеша при первом вызове
    if _old_vacancies_cache is None:
        _old_vacancies_cache = set()
        for root, _, files in os.walk('letters/'):
            for file_name in files:
                try:
                    vacancy_id = file_name.split('-')[0]
                    _old_vacancies_cache.add(vacancy_id)
                except IndexError:
                    continue

    # Извлекаем ID в зависимости от типа входных данных
    if isinstance(vacancy, (str, int, float)):
        vacancy_id = str(vacancy)  # на случай, если передали число
    elif isinstance(vacancy, dict) and 'id' in vacancy:
        vacancy_id = str(vacancy['id'])
    else:
        raise ValueError(
            f"Unsupported data type for vacancy: {type(vacancy)}. "
            "Expected string/number (ID) or dictionary with key 'id'"
        )

    return vacancy_id not in _old_vacancies_cache


def process(vacancy_hh_id, context: dict):
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
    requirements = context  # Hope there's enough context.
    logging.info(f'Writing letter for vacancy ({vacancy_hh_id})')
    letter = send_request(prompt)
    logging.info(f'Checking letter for adequacy ({vacancy_hh_id})')
    try:
        round = 1
        while not is_require_adequacy(letter, SKILLS, requirements):
            if round > 3:
                save_to_txt(letter, vacancy_hh_id + "-defective")
                raise Exception("Can't write a letter")
            logging.info(f'Round {round} ({vacancy_hh_id})')
            letter = fix_adequacy(letter, SKILLS, requirements)
            round += 1
        logging.info(f'Checking letter for punctuation ({vacancy_hh_id})')
        round = 1
        while not is_require_punctuation(letter):
            logging.info(f'Round {round} ({vacancy_hh_id})')
            letter = fix_punctuation(letter)
            round += 1
    except Exception as e:
        logging.error(f"Can't write a letter ({vacancy_hh_id})")
        pass
    else:
        logging.info(f'Letter meets the requirements ({vacancy_hh_id})')
        save_to_txt(letter, vacancy_hh_id)



def save_to_txt(letter, vacancy_hh_id):
    with open(f'letters/{vacancy_hh_id}-{date.today()}.txt', 'w') as f:
        f.write(letter)
