---
trigger: always_on
---

## 1. Core Principles

- Code like Robert C. Martin : Clean Code, Clean Architecture, SOLID Principles
- Single Responsibility: every service/file has one clear concern.
- Separation of Concerns: Routers = HTTP only, Services = business logic, Managers = YAML data loading, Agents/Tools = LLM orchestration, Storage = persistence.
- Type Safety Everywhere: Python with full type hints + Pydantic models.
- English Only: code, comments, docs, data.

## 2. Backend Code Standards

- Pydantic V2 models with validators and explicit error messages.
- Docstrings (Google style) for every public function/method. MUST include:
  - **Purpose**: Why the method exists in 3 sentences minimum
  - **Args**: All arguments with types and descriptions.
  - **Returns**: Return value type and description.
  - **Language**: English only.
- Services: no file or network I/O (delegate to persistence/storage classes).
- Avoid circular dependencies—prefer dependency injection passing services explicitly.
- Logging: use JSON logger (`back/utils/logger.py`); never `print()`.
- Exceptions: raise custom ones from `utils/exceptions.py`.
- Async: use `async` for I/O (file, network, CPU-bound stays sync unless justified).

**Type Hints**: **MANDATORY**. All functions, methods, variables, class properties, and parameters must have explicit type hints. This includes:

- All function parameters and return types
- All class properties (declared at class level)
- All local variables (inline type annotations)
- All loop variables
- All comprehension variables where ambiguous
  **Example:**

  ```python
  class MyService:
      property_name: str  # Class property type hint
      count: int
      
      def __init__(self, name: str) -> None:
          self.property_name = name
          local_var: int = 42  # Local variable type hint
  ```

- **Pydantic Models**: Use for all data structures. Use V2 features like `field_validator`.
- **Async**: Use `async/await` for all I/O operations.
- **Docstrings**: Document all public methods (description, args, returns).
- **FastAPI Route Documentation**: For all FastAPI router endpoints, provide comprehensive docstrings with detailed descriptions, parameter explanations, request/response JSON examples, and error conditions. This ensures complete OpenAPI documentation for API consumers. Include full JSON schemas for requests and responses to facilitate automatic API documentation generation.
- **Error Handling**: Use custom exceptions from `utils/exceptions.py`.
- **File Naming**:
  - Services: `{domain}_service.py`
  - Managers: `{resource}_manager.py`
  - Tools: `{category}_tools.py`

## 3. Testing

```bash
# Backend tests
cd back && pytest tests/ -v
```

- Mirror source structure: add tests under matching folder (e.g. `tests/routers/`).
- New service or model == new test module.
- Avoid mocking managers unless necessary; prefer real YAML fixtures.
- Keep tests deterministic (no real LLM calls—mock or isolate tool logic).
