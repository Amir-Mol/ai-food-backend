# AI Food Backend

This repository contains the backend service for the **NutriRecom Mobile Application**. It is responsible for handling user authentication, managing user data, and powering the AI-driven recipe recommendation engine.

## Related Repositories

* **Frontend (UI):** [ai-food-frontend](https://github.com/Amir-Mol/ai-food-frontend)

---

## ✨ Key Features

* **User Authentication:** Secure user sign-up, login, password reset, and email verification.
* **AI Recommendation Engine:** Provides personalized recipe recommendations based on user preferences and history.
* **Full CRUD API:** Endpoints for managing users, recipes, profiles, and interaction history.
* **Type-Safe Database:** Uses [Prisma Client Python](https://prisma-client-py.readthedocs.io/en/stable/) for database ORM.
* **Containerized:** Fully containerized with Docker.

---

## 🛠️ Tech Stack

* **Language:** **Python 3.11+**
* **Framework:** **FastAPI**
* **Database ORM:** **Prisma Client Python**
* **Database:** (e.g., PostgreSQL, MySQL - *please specify your database*)
* **Deployment:** **Docker**
* **Key Libraries:**
    * `uvicorn` as the ASGI server.
    * `pydantic` for data validation.
    * `passlib[bcrypt]` for password hashing.
    * `python-jose[cryptography]` for JWT tokens.

---

## ⚙️ Setup and Installation

You can run this project using Docker.

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/Amir-Mol/ai-food-backend.git](https://github.com/Amir-Mol/ai-food-backend.git)
    cd ai-food-backend
    ```

2.  **Create an environment file:**
    Create a `.env` file in the root of the project. You will need to add your database connection string and a secret key for JWTs.

    ```env
    # Example for PostgreSQL
    DATABASE_URL="postgresql://user:password@db:5432/mydb"
    
    # Secret key for signing JWTs (generate a strong random string)
    SECRET_KEY="your-super-secret-key"

    # Add any other keys needed (e.g., for email service)
    EMAIL_HOST="smtp.example.com"
    EMAIL_PORT=587
    EMAIL_USER="your-email@example.com"
    EMAIL_PASSWORD="your-email-password"
    ```

3.  **Build and Run with Docker Compose:**
    *(Note: This assumes you have a `docker-compose.yml` file to run the app and a database. If not, you can build and run the Dockerfile directly.)*

    **To run with Docker Compose (if you have a file):**
    ```bash
    docker-compose up --build
    ```

    **To run with Dockerfile only (no separate database):**
    ```bash
    # Build the image
    docker build -t ai-food-backend .
    
    # Run the container, passing the .env file
    docker run --env-file .env -p 8000:8000 ai-food-backend
    ```
---

## 📄 License

This project is licensed under the MIT License. See the `LICENSE` file for details.
