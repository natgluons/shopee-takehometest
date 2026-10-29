# Receipt AI

This repository is the submission for the Shopee take home test. It is a receipt intelligence
platform that uploads food receipts, extracts the merchant, date, items, and total with local OCR,
stores them in SQLite, and answers natural-language questions about spending.

A video demo and a sample receipt image are in the demo/ folder.

## How to run

Start the app with Docker:

    docker compose up --build

Then open http://localhost:8000.

To run without Docker, install the dependencies and start the server:

    pip install -e .
    uvicorn receipt_ai.api.main:app --reload

Run the tests with:

    pytest
