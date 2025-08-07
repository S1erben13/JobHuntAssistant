import json
import logging
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from datetime import datetime, date
from math import ceil
from multiprocessing import Process
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from utils import VacancyCache

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

load_dotenv()


class VacancyProcessor(ABC):
    """Abstract base class for vacancy processing."""

    @abstractmethod
    def process_vacancy(self, vacancy_id: str, vacancy_details: Dict[str, Any]) -> None:
        """Process a single vacancy."""
        pass


class VacancyFetcher:
    """Handles fetching vacancies from the API."""

    def __init__(self, api_url: str, default_params: Dict[str, Any]):
        self.api_url = api_url
        self.default_params = default_params

    def fetch_vacancies_for_framework(
        self, framework: str, experience: List[str], per_params: int
    ) -> List[Dict[str, Any]]:
        """
        Fetch vacancies for a specific programming framework.

        Args:
            framework: The framework to search for
            experience: List of experience levels to filter by
            per_params: Number of vacancies to fetch per experience level

        Returns:
            List of fetched vacancy dictionaries
        """
        vacancies = []
        for page in range(1, ceil(per_params / 100) + 1):
            for period in experience:
                search_query = f"{self.default_params['text']} {framework}"
                params = self.default_params.copy()
                params["text"] = search_query
                params["page"] = page
                params["per_page"] = min(per_params, 100)
                params["experience"] = period

                logger.info(
                    f"Searching for vacancies: {search_query} (page №{page}) (experience {period})"
                )
                response = requests.get(url=self.api_url, params=params)
                response.raise_for_status()
                vacancies += response.json().get("items", [])
        return vacancies


class VacancyHandler:
    """Handles processing and managing vacancies."""

    def __init__(
        self,
        fetcher: VacancyFetcher,
        processor: VacancyProcessor,
        cache: VacancyCache,
        include: List[str],
    ):
        self.fetcher = fetcher
        self.processor = processor
        self.cache = cache
        self.include = include

    def remove_duplicates(self, vacancies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Remove duplicate vacancies.
        """
        unique_vacancies = {json.dumps(v, sort_keys=True) for v in vacancies}
        return [json.loads(v) for v in unique_vacancies]

    def filter_by_excluded(self, vacancies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filtering vacancies by excluded words
        """
        exclude_words = os.getenv("EXCLUDE").split(",")
        filtered_vacancies = [
            v for v in vacancies
            if not any(word.lower() in v["name"].lower() for word in exclude_words)
        ]
        return filtered_vacancies

    def sort_by_date(self, vacancies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sort vacancies by publication date.

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

    def get_vacancy_details(self, vacancy: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract detailed information about a vacancy.

        Args:
            vacancy: Raw vacancy dictionary

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

    def parse_vacancies(self, experience: List[str], per_params: int) -> None:
        """
        Main method to fetch and process vacancies.

        Args:
            experience: List of experience levels to filter by
            per_params: Number of vacancies to fetch per experience level
        """
        all_vacancies = []
        for query in self.include:
            try:
                all_vacancies.extend(
                    self.fetcher.fetch_vacancies_for_framework(query, experience, per_params)
                )
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch vacancies for {query}: {e}")
                continue

        unique_vacancies = self.remove_duplicates(all_vacancies)
        new_vacancies = [v for v in unique_vacancies if self.cache.is_new_vacancy(v)]
        filtered_vacancies = self.filter_by_excluded(new_vacancies)
        sorted_vacancies = self.sort_by_date(filtered_vacancies)

        logger.info(f"Found {len(sorted_vacancies)} new vacancies to process")
        os.makedirs("logs", exist_ok=True)

        counter = 1
        for vacancy in sorted_vacancies:
            vacancy_id = vacancy["id"]
            logger.info(f"Processing vacancy {counter}/{len(sorted_vacancies)}: {vacancy_id}")
            counter +=1
            with open(f"logs/processed-vacancies-{date.today()}.txt", "a", encoding="utf-8") as log_file:
                try:
                    vacancy_details = self.get_vacancy_details(vacancy)
                    self.processor.process_vacancy(vacancy_id, vacancy_details)
                    log_file.write(f"{vacancy_id} - {vacancy_details['vacancy_name']} - {vacancy_details['employer_name']}\n")
                except Exception as e:
                    log_file.write(f"Error - {vacancy_id} - {vacancy_details['vacancy_name']} - {vacancy_details['employer_name']}\n")
                    logger.error(f"Error processing vacancy {vacancy_id}: {str(e)}")
                    continue

        logger.info("✅ Vacancy processing completed successfully")


# class LetterSender:
#     """Handles sending cover letters."""
#
#     @staticmethod
#     def run_send_letters() -> None:
#         """Run the send_letters.py script as a separate process."""
#         subprocess.run([sys.executable, "send_letters.py"])


class DefaultVacancyProcessor(VacancyProcessor):
    """Default implementation of VacancyProcessor."""

    def process_vacancy(self, vacancy_id: str, vacancy_details: Dict[str, Any]) -> None:
        """Process a vacancy by writing a cover letter."""
        from utils import process
        process(vacancy_id, vacancy_details)


def main() -> None:
    """Main execution function."""
    default_params = {
        "text": os.getenv("MAIN_QUERY"),
        "ored_clusters": "true",
        "work_format": "REMOTE",
        "has_test": os.getenv("HAS_TEST"),
        "salary": int(os.getenv("SALARY")),
        "order_by": "publication_time",
    }

    fetcher = VacancyFetcher(
        api_url="https://api.hh.ru/vacancies",
        default_params=default_params,
    )

    processor = DefaultVacancyProcessor()
    cache = VacancyCache()

    handler = VacancyHandler(
        fetcher=fetcher,
        processor=processor,
        cache=cache,
        include=os.getenv("INCLUDE").split(","),
    )

    handler.parse_vacancies(
        experience=os.getenv("EXPERIENCE").split(","),
        per_params=int(os.getenv("PER_PARAMS")),
    )


if __name__ == "__main__":
    main()