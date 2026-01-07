# Copilot Instructions

This file defines the coding rules and behavior for this project. Please follow them strictly.

## Global Rules

1.  **Communication Language**: You must always communicate with the user in **English**.
2.  **Code Language**: All code, comments, variable/function/class names, and tests must be written in **English**.
3.  **Context**: Forget any prior context regarding "Java Graph RAG API" or "indexer". This project is a modern web application (Python/FastAPI + Vue.js/Tailwind).

## PYTHON GUIDELINES

### Style and Formatting
-   Strictly adhere to **PEP 8**.
-   Use line breaks to keep code airy and readable.

### Typing
-   **Strict**: Type hints are **MANDATORY** for all function arguments, return values, and class attributes.
-   **Modern**: Use modern Python 3.10+ type syntax (e.g., `list[str]` instead of `List[str]`, `dict[str, Any]` instead of `Dict[str, Any]`, `str | None` instead of `Optional[str]`).
-   Never use `Any` unless absolutely necessary and justified.

### Documentation
-   **Docstrings**: Every public module, class, and function MUST have an explanatory docstring.
-   **Format**: Use Google or NumPy style for docstrings.

### Asynchrony
-   Always prefer `async`/`await` for I/O-bound operations (databases, HTTP requests).

### Architecture and Validation
-   Use **Pydantic** for data validation and schema definitions (models).

## VUE.JS GUIDELINES

### Tech Stack
-   **Framework**: Vue.js 3.
-   **Language**: TypeScript (strict).
-   **Build**: Vite.

### Code Style
-   **Composition API**: Exclusively use the **Composition API** with `<script setup lang="ts">` syntax.
-   **Naming**: Component filenames and imports must be in **PascalCase** (e.g., `AppButton.vue`, `UserProfile.vue`).

### CSS and Design
-   **CSS Framework**: Use **Tailwind CSS** for styling.
-   **No Scoped CSS**: Avoid `<style scoped>` blocks unless absolutely necessary for specific styles that cannot be handled via Tailwind. Prefer utility classes.
-   **Design**: The interface must be modern, clean, and responsive.

### State Management
-   Use **Pinia** for global application state management. Do not use Vuex.
