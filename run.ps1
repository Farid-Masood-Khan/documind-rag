# DocuMind PowerShell Automation Script
param(
    [Parameter(Position=0)]
    [string]$Command = "help"
)

$VenvPython = if (Test-Path ".venv/Scripts/python.exe") { ".venv/Scripts/python.exe" } else { "python" }

switch ($Command.ToLower()) {
    "setup" {
        Write-Host "Setting up virtual environment for DocuMind..." -ForegroundColor Cyan
        if (-not (Test-Path ".venv")) {
            python -m venv .venv
        }
        & $VenvPython -m pip install --upgrade pip
        & $VenvPython -m pip install -r requirements.txt
    }
    "lint" {
        Write-Host "Running ruff linter..." -ForegroundColor Cyan
        & $VenvPython -m ruff check app tests eval
    }
    "format" {
        Write-Host "Checking formatting with ruff..." -ForegroundColor Cyan
        & $VenvPython -m ruff format --check app tests eval
    }
    "typecheck" {
        Write-Host "Running mypy type checks..." -ForegroundColor Cyan
        & $VenvPython -m mypy app
    }
    "test" {
        Write-Host "Running pytest test suite..." -ForegroundColor Cyan
        & $VenvPython -m pytest tests
    }
    "serve" {
        Write-Host "Starting DocuMind FastAPI server on port 8000..." -ForegroundColor Cyan
        & $VenvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
    }
    "ui" {
        Write-Host "Starting DocuMind Streamlit UI on port 8501..." -ForegroundColor Cyan
        & $VenvPython -m streamlit run app/ui/streamlit_app.py
    }
    "eval" {
        Write-Host "Executing RAG benchmark evaluation harness..." -ForegroundColor Cyan
        & $VenvPython -m eval.run_eval
    }
    "ci" {
        Write-Host "Running full CI verification..." -ForegroundColor Green
        & $VenvPython -m ruff check app tests eval
        & $VenvPython -m ruff format --check app tests eval
        & $VenvPython -m mypy app
        & $VenvPython -m pytest tests
    }
    default {
        Write-Host "DocuMind Command Runner" -ForegroundColor Yellow
        Write-Host "Usage: .\run.ps1 [setup|lint|format|typecheck|test|serve|ui|eval|ci]"
    }
}

