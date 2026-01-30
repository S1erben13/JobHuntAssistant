# JobHuntAssistant 🤖

**Automated Job Search and Application Management System powered by Local LLM.**

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Docker](https://img.shields.io/badge/Docker-Enabled-blue.svg)
![LLM](https://img.shields.io/badge/AI-Ollama-orange.svg)
![Status](https://img.shields.io/badge/Status-Active-green.svg)

## 📖 Overview

JobHuntAssistant is a modular Python automation tool designed to streamline the job search process on HeadHunter (hh.ru). Unlike simple parsers, this system acts as an intelligent agent:

1.  **Fetches & Filters:** Aggregates vacancies based on complex criteria, filtering out irrelevant listings using negative keywords.
2.  **Analyzes:** Uses a Local LLM (via Ollama) to analyze the relevance of a vacancy against the candidate's profile.
3.  **Generates:** Writes hyper-personalized cover letters based on the specific job description and the candidate's skills.
4.  **Validates:** Implements a multi-stage **Self-Correction Loop** where the AI reviews its own output for adequacy and punctuation before saving.

## 🚀 Key Features

* **OOP Architecture:** Built with extensibility in mind using Abstract Base Classes (`VacancyProcessor`) to easily swap processing logic (e.g., switching from generating letters to auto-applying).
* **Intelligent Caching:** Prevents processing the same vacancy twice using a persistent cache mechanism.
* **AI Quality Control:** The system doesn't just generate text; it critiques it.
    * *Adequacy Check:* Ensures the letter actually addresses the job requirements.
    * *Grammar Check:* Auto-corrects punctuation and styling.
* **Dockerized Environment:** Ready for deployment with `docker-compose`.
* **Customizable Pipelines:** Easily configurable search queries, experience levels, and negative filters via environment variables.

## 🛠 Tech Stack

* **Core:** Python 3.11
* **Architecture:** OOP, Modular Design
* **AI Integration:** Ollama (Llama 3 / Mistral / Gemma), REST API
* **Data Handling:** JSON, File-based Logging
* **Network:** Requests (Synchronous), Multiprocessing (ready for scaling)
* **Containerization:** Docker & Docker Compose

## 🏗 System Architecture

The project follows a clean separation of concerns:

- **`VacancyFetcher`**: Handles API interactions and pagination with the job board.
- **`VacancyHandler`**: Orchestrates the data flow (fetching -> filtering -> sorting -> processing).
- **`VacancyProcessor` (Interface)**: Defines the contract for processing vacancies.
- **`utils.py`**: Contains the LLM interaction layer with retry logic and prompt management.

## ⚙️ Installation & Setup

### Prerequisites
- Python 3.10+
- [Ollama](https://ollama.com/) installed and running locally
- Docker (optional)

### Local Run

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/S1erben13/JobHuntAssistant.git](https://github.com/S1erben13/JobHuntAssistant.git)
   cd JobHuntAssistant
