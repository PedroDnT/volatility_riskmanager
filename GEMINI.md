# Project Context: Advanced Crypto Position Risk Management System

This document provides an overview of the `market_analysis` project, designed to serve as instructional context for the Gemini CLI.

## Project Overview

This is a comprehensive cryptocurrency trading risk management system. Its primary purpose is to provide sophisticated risk management for crypto trading by combining real-time position monitoring with advanced volatility analysis (using GARCH and HAR-RV models) and portfolio correlation analysis. It calculates optimal stop-loss/take-profit levels, recommends position sizes, and assesses overall portfolio risk.

**Key Technologies:**
*   **Python:** The core programming language.
*   **Bybit API:** For fetching real-time position data.
*   **GARCH(1,1) and HAR-RV Models:** For advanced volatility forecasting.
*   **ATR (Average True Range):** For basic volatility assessment.
*   **TOML:** For configuration management (`settings.toml`).
*   **Docker:** For containerized deployment.
*   **Pytest:** For unit testing.

## Building and Running

The application can be run either locally via `pip` or using Docker.

### Local Installation & Execution

1.  **Clone the repository and navigate into the directory.**
2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate # On Windows: venv\Scripts\activate
    ```
3.  **Install the package in editable mode:**
    ```bash
    pip install -e .
    ```
4.  **Configuration:**
    *   Copy `settings.example.toml` to `settings.toml`.
    *   Add your Bybit API credentials to `settings.toml`.
    *   Create a `.env` file in the root directory with your API credentials:
        ```
        BYBIT_API_KEY=your_api_key_here
        BYBIT_API_SECRET=your_api_secret_here
        ```
5.  **Run the application:**
    ```bash
    risk-manager
    ```

### Docker Execution

1.  **Build the Docker image from the project root:**
    ```bash
    docker build -t risk-manager-app .
    ```
2.  **Run the container (mounting `.env` and `settings.toml`):**
    ```bash
    docker run --rm -v "$(pwd)/.env":/app/.env -v "$(pwd)/settings.toml":/app/settings.toml risk-manager-app
    ```

### Running Tests

1.  **Install test dependencies:**
    ```bash
    pip install -e .[test]
    ```
2.  **Run the test suite:**
    ```bash
    pytest -v
    ```

## Development Conventions

*   **Code Structure:** The main logic resides in `position_risk_manager.py`, with volatility models in `garch_vol_triggers.py` and position fetching in `get_position.py`.
*   **Configuration:** Uses `settings.toml` (from `settings.example.toml`) for dynamic settings.
*   **Environment Variables:** API credentials are loaded from a `.env` file.
*   **Testing:** Unit tests are located in the `tests/` directory and executed using `pytest`.
*   **Contribution:** Follows a standard fork-branch-pull request workflow.
*   **Risk Management Logic:** Employs a multi-layered approach including confidence scoring, dynamic risk target adjustment, and dynamic stop-loss/take-profit multipliers based on market conditions, leverage, and trade confidence.
*   **Volatility Blending:** Combines GARCH, HAR-RV, and ATR models with specific weights (30% GARCH, 40% HAR-RV, 30% ATR) for robust volatility estimates.
*   **Correlation Analysis:** Identifies correlated positions and applies cluster risk caps to manage overall portfolio risk.
