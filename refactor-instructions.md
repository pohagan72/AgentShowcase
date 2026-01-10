Here is a comprehensive prompt you can copy and paste into a future chat session. It gives the AI all the context, constraints, and architectural goals needed to perform a high-level refactor without breaking your application.

***

### Copy and Paste this Prompt:

**Context:**
I have a Flask application called "AgentShowcase" deployed on Railway. It demonstrates various AI agents (Summarization, Translation, PII Redaction, Multimedia) using Google Gemini, Presidio, and OpenCV. The frontend uses HTMX for dynamic interactions. Currently, the app works, but the codebase is structured like a prototype, not an enterprise product.

**Current State:**
1.  **`app.py` is a God Object:** It handles configuration, logging, S3 initialization, and route registration via function calls (e.g., `define_translation_routes(app)`).
2.  **Configuration:** I recently moved environment variables to `.env`, but `app.py` still contains manual logic to read/validate them.
3.  **Frontend DRY Violations:** JavaScript logic (like `renderMarkdownSummary`) is repeated across multiple HTML templates.
4.  **Routes:** Feature logic is mixed with HTTP handling in `routes.py` files.

**Your Role:**
Act as a **Senior Python Architect** and **Flask Expert**. Your goal is to refactor this application into a maintainable, scalable, and professional codebase that a CTO would approve of.

**The Objective:**
We need to refactor the application architecture to follow Flask best practices (Blueprints, Application Factory Pattern, Centralized Config) without breaking existing functionality.

**Please execute the following Refactoring Plan:**

**Step 1: The Configuration Layer**
Create a `config.py` file. Move all environment variable loading, default value logic (like the Gemini token limits), and S3 settings into a strongly typed `Config` class.

**Step 2: The Application Factory**
Refactor `app.py` to use the **Application Factory Pattern** (`create_app()`). It should:
*   Load the `Config` object.
*   Initialize extensions (S3, Logging).
*   Register Blueprints (see Step 3).

**Step 3: Blueprints Implementation**
Convert the existing feature routes (currently defined as functions like `define_translation_routes(app)`) into proper **Flask Blueprints**.
*   *Example:* Convert `features/summarization/routes.py` to use `bp = Blueprint('summarization', __name__)`.

**Step 4: Frontend Asset Consolidation**
Create a single `static/js/main.js` file. Move the `renderMarkdownSummary` function and the HTMX event listeners (like sidebar toggling) into this file so we can remove the duplicate `<script>` tags from the templates.

**Constraints:**
*   **Do not break the "Zero-Click" demo functionality** (keep the sample file logic).
*   **Keep HTMX.** We are not moving to React/Vue.
*   **Keep the S3 Adapter.**
*   **Preserve Lazy Loading.** Ensure the optimizations for `presidio` and `mtcnn` remain intact.

**Output:**
Please guide me through these changes file-by-file. Start with **Step 1 (config.py)** and **Step 2 (app.py)**. Show the full code for those files first.