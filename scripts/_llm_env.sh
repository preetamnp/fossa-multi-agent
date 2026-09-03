# Shared LLM env for Neuro SAN server, Studio, and POC client.
# Source after .env so DEEPSEEK_API_KEY takes precedence over MISTRAL_API_KEY.

if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
  export OPENAI_API_KEY="${DEEPSEEK_API_KEY}"
elif [[ -z "${OPENAI_API_KEY:-}" && -n "${MISTRAL_API_KEY:-}" ]]; then
  export OPENAI_API_KEY="${MISTRAL_API_KEY}"
fi

if [[ -z "${OPENAI_API_BASE:-}" ]]; then
  if [[ -n "${DEEPSEEK_API_KEY:-}" ]]; then
    export OPENAI_API_BASE="https://api.deepseek.com"
  else
    export OPENAI_API_BASE="https://api.mistral.ai/v1"
  fi
fi
