import json
import os
from datetime import datetime
import requests
import logging

from dotenv import load_dotenv

from utils import is_new_vacancy, process

logger = logging.getLogger(__name__)

load_dotenv()
PROG_LANGUAGE = os.getenv("PROG_LANGUAGE")
EXPERIENCE = os.getenv("EXPERIENCE")
SALARY = int(os.getenv("SALARY"))
HAS_TEST = os.getenv("HAS_TEST")
# Vacancies per Framework
VC_PR_FW = os.getenv("VC_PR_FW")
FRAMEWORKS = os.getenv("FRAMEWORKS").split(',')

url = 'https://api.hh.ru/vacancies'

params = {
    "text": PROG_LANGUAGE,
    "ored_clusters": "true",
    "experience": EXPERIENCE,
    # "enable_snippets": "true",
    "work_format": "REMOTE",
    "has_test": HAS_TEST,
    "salary": SALARY,
    "order_by": "publication_time",
    "per_page": VC_PR_FW
}


def parse_vacancies():
    vacancies = []
    for framework in FRAMEWORKS:
        current_params = params.copy()
        current_params['text'] += (' ' + framework)
        logger.info(f'Searching for vacancies ({current_params['text']})')
        r = requests.get(url=url, params=current_params)
        framework_vacancies = r.json()['items']
        vacancies += framework_vacancies
    logger.info(f'Sorting and filtering')
    # Filtering from processed vacancies
    vacancies = list(filter(is_new_vacancy, vacancies))
    # Serializing dictionaries to JSON strings to remove duplicates
    vacancies = list({json.dumps(vacancy, sort_keys=True) for vacancy in vacancies})
    # Converting the JSON strings back to dictionaries
    vacancies = [json.loads(vacancy) for vacancy in vacancies]
    # Sorting by published time
    vacancies.sort(key=lambda x: datetime.strptime(x["published_at"], "%Y-%m-%dT%H:%M:%S%z"), reverse=True)
    logger.info(f'Found {len(vacancies)} vacancies')

    for vacancy in vacancies:
        vacancy_hh_id = vacancy['id']
        logger.info(f'Preparing to process ({vacancy_hh_id})')
        vacancy_name = vacancy['name']
        employer_name = vacancy['employer']['name']
        requirements = vacancy['snippet']['requirement']
        description = dict(requests.get(vacancy['url']).json())['description']
        responsibility = vacancy['snippet']['responsibility']

        logger.info(f'Sending to LLM ({vacancy_hh_id})')
        try:
            process(vacancy_hh_id, {
                'vacancy_name': vacancy_name,
                'employer_name': employer_name,
                'requirements': requirements,
                'description': description,
                'responsibility': responsibility
            })
        except Exception as e:
            logger.error(f"Error processing vacancy {vacancy_hh_id}: {e}")
    logger.error(f"✅ Processing finished!")

if __name__ == "__main__":
    parse_vacancies()