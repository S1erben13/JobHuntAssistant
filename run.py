import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from math import ceil
from multiprocessing import Process
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

from utils import VacancyCache, process

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()
MAIN_QUERY = os.getenv("MAIN_QUERY")
EXCLUDE = os.getenv("EXCLUDE")
EXPERIENCE = os.getenv("EXPERIENCE")
SALARY = int(os.getenv("SALARY"))
HAS_TEST = os.getenv("HAS_TEST")
PER_PARAMS = int(os.getenv("PER_PARAMS"))
INCLUDE = os.getenv("INCLUDE").split(",")

vacancy_cache = VacancyCache()

HH_API_URL = "https://api.hh.ru/vacancies"

DEFAULT_PARAMS = {
    "text": MAIN_QUERY,
    "excluded_text": EXCLUDE,
    "ored_clusters": "true",
    "work_format": "REMOTE",
    "has_test": HAS_TEST,
    "salary": SALARY,
    "order_by": "publication_time",
}


def fetch_vacancies_for_framework(framework: str) -> List[Dict[str, Any]]:
    """
    Fetch vacancies for a specific programming framework from HeadHunter API.

    Args:
        framework: The framework to search for (e.g., 'Django', 'Flask')

    Returns:
        List of vacancy dictionaries from the API response.
    """
    vacancies = []
    experience = EXPERIENCE.split(',')
    for page in range(1, ceil(PER_PARAMS/100)+1):
        for period in experience:
            search_query = f"{MAIN_QUERY} {framework}"
            params = DEFAULT_PARAMS.copy()
            params["text"] = search_query
            params["page"] = page
            params["per_page"] = min(PER_PARAMS, 100)

            logger.info(f"Searching for vacancies: {search_query} (page №{page}) (experience {period})")
            response = requests.get(url=HH_API_URL, params=params)
            response.raise_for_status()
            vacancies += response.json().get("items", [])
    return vacancies


def remove_duplicate_vacancies(vacancies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate vacancies by converting to JSON strings and back.

    Args:
        vacancies: List of vacancy dictionaries

    Returns:
        List of unique vacancies
    """
    unique_vacancies = {json.dumps(v, sort_keys=True) for v in vacancies}
    return [json.loads(v) for v in unique_vacancies]


def sort_vacancies_by_date(vacancies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort vacancies by publication date (newest first).

    Args:
        vacancies: List of vacancy dictionaries

    Returns:
        Sorted list of vacancies
    """
    return sorted(
        vacancies,
        key=lambda x: datetime.strptime(x["published_at"], "%Y-%m-%dT%H:%M:%S%z"),
        reverse=True,
    )


def get_vacancy_details(vacancy: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract and enrich vacancy details.

    Args:
        vacancy: Raw vacancy dictionary from API

    Returns:
        Dictionary with enriched vacancy details
    """
    vacancy_id = vacancy["id"]
    logger.info(f"Fetching details for vacancy: {vacancy_id}")

    response = requests.get(vacancy["url"])
    response.raise_for_status()
    full_details = response.json()

    return {
        "vacancy_name": vacancy["name"],
        "employer_name": vacancy["employer"]["name"],
        "requirements": vacancy["snippet"]["requirement"],
        "description": full_details.get("description", ""),
        "responsibility": vacancy["snippet"]["responsibility"],
    }


def parse_vacancies() -> None:
    """
    Main function to fetch, process, and handle vacancies from HeadHunter API.
    Filters new vacancies, processes them through LLM, and handles errors.
    """
    all_vacancies = []
    for query in INCLUDE:
        try:
            all_vacancies.extend(fetch_vacancies_for_framework(query))
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch vacancies for {query}: {e}")
            continue

    unique_vacancies = remove_duplicate_vacancies(all_vacancies)
    new_vacancies = [v for v in unique_vacancies if vacancy_cache.is_new_vacancy(v)]
    sorted_vacancies = sort_vacancies_by_date(new_vacancies)

    logger.info(f"Found {len(sorted_vacancies)} new vacancies to process")

    for vacancy in sorted_vacancies:
        vacancy_id = vacancy["id"]
        logger.info(f"Processing vacancy: {vacancy_id}")

        try:
            vacancy_details = get_vacancy_details(vacancy)
            process(vacancy_id, vacancy_details)
        except Exception as e:
            logger.error(f"Error processing vacancy {vacancy_id}: {str(e)}")
            continue
    logger.info("✅ Vacancy processing completed successfully")

def run_send_letters():
    """Run send_letters.py as separate process"""
    subprocess.run([sys.executable, "send_letters.py"])

if __name__ == "__main__":
    parse_vacancies()

    # p = Process(target=run_send_letters)
    # p.start()
