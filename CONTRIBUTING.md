# Contributing to XomFit Backend

Welcome! This guide will help you set up your development environment and understand how to contribute to the XomFit Python Lambda backend.

## Tech Stack

- **Language:** Python 3.12
- **Runtime:** AWS Lambda
- **API:** REST API via API Gateway using [api-gateway-service](https://github.com/domgiordano/api-gateway-service)
- **Database:** AWS DynamoDB
- **Authentication:** JWT Lambda Authorizer
- **Key Dependencies:** boto3, PyJWT, requests

## Project Structure

```
xomfit-backend/
├── lambdas/              # Lambda function handlers
│   ├── common/           # Shared utilities (dynamo_helpers, logger, errors)
│   ├── user_*/           # User service handlers
│   ├── workout_*/        # Workout service handlers
│   ├── feed_*/           # Feed service handlers
│   ├── friends_*/        # Friends service handlers
│   ├── prs_*/            # Personal records handlers
│   ├── exercises_*/      # Exercises handlers
│   └── authorizer/       # JWT authentication
├── requirements.txt      # Python dependencies
└── README.md             # API endpoint documentation
```

## Development Setup

### Prerequisites

- Python 3.12+
- pip and virtualenv
- Git
- AWS CLI (for local testing with AWS resources)
- GitHub CLI (`gh`) for managing issues and PRs

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Xomware/xomfit-backend.git
   cd xomfit-backend
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

### Environment Configuration

AWS credentials and DynamoDB tables are configured via:
- AWS CLI: `aws configure`
- Environment variables (for Lambda deployment)
- `.env` file (if using local testing tools)

Handlers use the common `logger` and `dynamo_helpers` modules from `lambdas/common/`.

## Running Locally

Each Lambda function in `lambdas/*/handler.py` can be tested locally:

```bash
# Test a specific handler
python -m lambdas.user_create.handler

# Or invoke directly in Python shell
from lambdas.user_create.handler import handler
response = handler({...}, None)
```

### Testing Against DynamoDB

For local DynamoDB testing, use the AWS SAM CLI or LocalStack:

```bash
# Using AWS SAM (if configured)
sam local start-api
```

## Running Tests

Currently, there is no dedicated test suite. Tests should be added following these guidelines:

```bash
# Once pytest is added to requirements.txt:
pip install pytest pytest-cov

# Run all tests
pytest

# Run with coverage
pytest --cov=lambdas tests/
```

**Guidelines for new tests:**
- Place test files in a `tests/` directory mirroring the `lambdas/` structure
- Test Lambda handlers using mock events and contexts
- Mock DynamoDB operations using `boto3.mock`
- Ensure tests for new features pass before submitting PRs

## Code Style

This project follows PEP 8. For consistency:

```bash
# Format code
pip install black
black lambdas/

# Lint code
pip install flake8
flake8 lambdas/ --max-line-length=100
```

Consider adding these to `requirements.txt` as dev dependencies in the future.

## Common Tasks

### Adding a New Lambda Handler

1. Create a new directory under `lambdas/` with your handler name
2. Create `handler.py` with your function
3. Create `__init__.py` (can be empty)
4. Use utilities from `lambdas/common/`:
   - `logger.log()` for logging
   - `dynamo_helpers.get_item()`, `put_item()`, etc. for DynamoDB
   - `errors.ErrorResponse` for standard error responses
5. Update `README.md` with the new endpoint documentation

### Example Handler Structure

```python
from lambdas.common.logger import log
from lambdas.common.dynamo_helpers import get_item
from lambdas.common.errors import ErrorResponse

def handler(event, context):
    try:
        user_id = event.get('pathParameters', {}).get('user_id')
        item = get_item('Users', {'id': user_id})
        return {
            'statusCode': 200,
            'body': item
        }
    except Exception as e:
        log(f'Error: {str(e)}', 'error')
        return ErrorResponse(500, 'Internal Server Error')
```

## Contributing Process

1. **Create a branch** from `main` for your feature or fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes:**
   - Write clear, descriptive commit messages
   - Follow the code style guidelines
   - Update `README.md` if adding or modifying endpoints

3. **Test your changes:**
   - Test Lambda handlers locally
   - Verify DynamoDB operations
   - Consider edge cases

4. **Commit and push:**
   ```bash
   git add .
   git commit -m "feat: add new endpoint" # or "fix: handle edge case"
   git push origin feature/your-feature-name
   ```

5. **Create a Pull Request:**
   ```bash
   gh pr create --title "feat: add new endpoint" --body "Description of changes"
   ```

6. **Code Review:**
   - Address feedback from reviewers
   - Ensure CI checks pass (if configured)
   - Squash commits if requested

7. **Merge:**
   Once approved, your PR will be merged into `main`.

## Commit Message Format

Use conventional commits for clarity:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `refactor:` - Code refactoring without behavior change
- `test:` - Test additions or fixes
- `chore:` - Dependency updates, config changes

Example: `feat: add workout delete endpoint`

## Reporting Issues

Found a bug or have a suggestion?

1. Check existing issues to avoid duplicates
2. Create a new issue with:
   - Clear title and description
   - Steps to reproduce (for bugs)
   - Expected vs. actual behavior
   - Environment details if relevant

## Questions?

- Check the [README.md](README.md) for API endpoint documentation
- Review existing handlers in `lambdas/` for patterns
- Open an issue with your question

Happy coding! 🚀
