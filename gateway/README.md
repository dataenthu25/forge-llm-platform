# Local configuration

The gateway loads configuration from a `.env` file in the project directory. Set:

- `VLLM_URL` to the vLLM base URL (for example, `http://localhost:8000`).
- `API_KEYS` to a JSON object mapping bearer tokens to team names.

For Kubernetes, set `VLLM_URL` to `http://chat-vllm-pool:8000` and provide `API_KEYS` through a Kubernetes Secret. Do not commit `.env` or real API keys.
