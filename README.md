# URL Shortener

A simple FastAPI-based URL shortener with a dashboard UI.

## Features

- Home dashboard showing total URLs and total clicks
- Create a new short URL
- View all URLs and more details about each item
- Edit or delete existing URLs
- View analytics for clicks on each URL
- Redirect short codes to the original URLs

## Project Structure

- `run.py` — application entry point
- `myapp/main.py` — FastAPI app setup and router registration
- `myapp/routers/ui_router.py` — UI routes for dashboard and pages
- `myapp/routers/url_router.py` — API routes for URL operations and short-code redirect
- `myapp/services/url_service.py` — business logic layer
- `myapp/repos/url_repository.py` — database persistence logic
- `myapp/schemas/url_mapping.py` — Pydantic models for request and response validation
- `myapp/templates/` — Jinja2 templates for UI pages
- `myapp/static/` — static CSS assets
- `.env` — local environment variables (not committed if `.gitignore` is configured)

## Setup

1. Create and activate your virtual environment.

```bash
python -m venv .venv
.venv\Scripts\activate
```

2. Install dependencies.

```bash
python -m pip install -r requirements.txt
```

3. Create or update your `.env` file.

Example `.env`:

```env
DATABASE_URL=<your_db_url>
DEBUG=true
```

4. Start the server.

```bash
python run.py
```

5. Open the UI at:

```text
http://127.0.0.1:8000/
```

## License

This project does not include a license file by default.
