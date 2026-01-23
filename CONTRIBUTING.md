# Contributing to Dynamic-KB

Thank you for your interest in contributing to Dynamic-KB! This document provides guidelines and instructions for contributing.

## Getting Started

### Prerequisites

- Python 3.11+
- [Playwright](https://playwright.dev/) (for crawl4ai)
- API keys for Gemini and ElevenLabs (for full functionality)

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/dynamic-kb.git
   cd dynamic-kb
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. **Run tests**
   ```bash
   pytest
   ```

6. **Start the development server**
   ```bash
   streamlit run app/main.py
   ```

## Code Style

This project uses [Ruff](https://github.com/astral-sh/ruff) for linting. The configuration is in `pyproject.toml`.

```bash
# Check code style
ruff check .

# Auto-fix issues
ruff check --fix .
```

### Style Guidelines

- Follow PEP 8 conventions
- Use type hints for function signatures
- Keep functions focused and small
- Write descriptive variable names

## Testing

- Write tests for new features
- Ensure existing tests pass before submitting PRs
- Place tests in the `tests/` directory
- Use pytest fixtures from `tests/conftest.py`

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest tests/test_config.py
```

## Submitting Changes

### Pull Request Process

1. **Fork the repository** and create your branch from `main`
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** with clear, focused commits

3. **Write or update tests** as needed

4. **Run the test suite** to ensure everything passes
   ```bash
   pytest
   ruff check .
   ```

5. **Push to your fork** and submit a Pull Request

### PR Guidelines

- Use a clear, descriptive title
- Reference any related issues
- Describe what changes you made and why
- Include screenshots for UI changes
- Keep PRs focused - one feature/fix per PR

### Commit Messages

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Keep the first line under 72 characters
- Reference issues when applicable

## Reporting Issues

### Bug Reports

Include:
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Error messages/logs

### Feature Requests

Include:
- Clear description of the feature
- Use case / problem it solves
- Any implementation ideas (optional)

## Project Structure

```
dynamic-kb/
├── app/
│   ├── main.py              # Streamlit entry point
│   ├── core/                # Core business logic
│   ├── models/              # Pydantic models
│   ├── ui/                  # UI components
│   └── utils/               # Utilities
├── tests/                   # Test suite
├── docs/                    # Documentation
└── config.yaml              # Configuration
```

## Questions?

Feel free to open an issue for any questions about contributing.
