# test_ollamafree.py
from agents.llm_adapter import LLMAdapter
import config
from ollamafreeapi import OllamaFreeAPI
api = OllamaFreeAPI()
modelos = api.list_models()
print(modelos)

# Forzar uso de OllamaFreeAPI
config.USE_OLLAMAFREE = True
config.OLLAMAFREE_MODEL = "gpt-oss:20b" #"deepseek-r1:latest" 

print("🔌 Inicializando LLMAdapter...")
llm = LLMAdapter()

print(f"Provider: {llm.get_model_info()['provider']}")
print(f"Modelo: {llm.get_model_info()['model']}")

print("\n🧪 Probando chat completion...")
try:
    response = llm.chat_completion(
        messages=[
            {"role": "system", "content": "Responde en JSON: {\"test\": true}"},
            {"role": "user", "content": "¿Funciona la API?"}
        ],
        temperature=0.3,
        max_tokens=100
    )
    print(f"Respuesta: {response[:100]}...")
except Exception as e:
    print(f"Error: {e}")
    if llm.fallback_enabled:
        print("Fallback activado automáticamente")