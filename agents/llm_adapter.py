"""
agents/llm_adapter.py - Adaptador unificado para LLM local y OllamaFreeAPI
"""
import time
from loguru import logger
import config

try:
    from ollamafreeapi import OllamaFreeAPI
    OLLAMAFREE_AVAILABLE = True
except ImportError:
    OLLAMAFREE_AVAILABLE = False
    logger.warning("OllamaFreeAPI no instalado. pip install ollamafreeapi")

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.error("OpenAI package no instalado. pip install openai")


class LLMAdapter:
    """Adaptador que unifica acceso a LLM local y OllamaFreeAPI"""
    
    def __init__(self, model_name: str = None, use_ollamafree: bool = None):
        self.use_ollamafree = use_ollamafree if use_ollamafree is not None else config.USE_OLLAMAFREE
        self.fallback_enabled = config.OLLAMAFREE_FALLBACK
        self.timeout = config.OLLAMAFREE_TIMEOUT
        
        if self.use_ollamafree:
            self.model_name = config.OLLAMAFREE_MODEL
            logger.info(f"Usando OllamaFreeAPI con modelo: {self.model_name}")
        else:
            self.model_name = model_name or config.LLM_MODEL
            logger.info(f"Usando servidor local con modelo: {self.model_name}")
        
        self.client = None
        self._init_client()
        
        logger.info(f"LLMAdapter: {'OllamaFreeAPI' if self.use_ollamafree else 'Local'} | Modelo: {self.model_name}")
    
    def _init_client(self):
        """Inicializa el cliente según configuración"""
        if self.use_ollamafree and OLLAMAFREE_AVAILABLE:
            try:
                self.client = OllamaFreeAPI()
                logger.info("Conectado a OllamaFreeAPI")
            except Exception as e:
                logger.error(f"Error conectando a OllamaFreeAPI: {e}")
                if self.fallback_enabled and OPENAI_AVAILABLE:
                    logger.info("Fallback a cliente local...")
                    self._init_local_client()
                else:
                    raise
        else:
            self._init_local_client()
    
    def _init_local_client(self):
        """Inicializa cliente OpenAI-compatible local"""
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI package required for local LLM")
        
        self.client = OpenAI(
            base_url=config.LLM_BASE_URL,
            api_key=config.LLM_API_KEY,
            timeout=self.timeout
        )
        logger.info(f"Conectado a servidor local: {config.LLM_BASE_URL}")
    
    def chat_completion(self, messages: list, temperature: float = 0.3, max_tokens: int = 4000, **kwargs):
        """
        Ejecuta chat completion con interfaz unificada
        Retorna: str con el contenido de la respuesta
        """
        start_time = time.time()
        
        try:
            if self.use_ollamafree and isinstance(self.client, OllamaFreeAPI):
                #prompt = "\n".join([m["content"] for m in messages if m["role"] == "user"])
                system_content = ""
                user_content = ""                
                for m in messages:
                    if m["role"] == "system":
                        system_content = m["content"] + "\n\n"
                    elif m["role"] == "user":
                        user_content = m["content"]
                prompt = system_content + user_content
            
                response = self.client.chat(
                    model=self.model_name,
                    prompt=prompt,
                    temperature=temperature,
                    stream=False
                )
                elapsed = time.time() - start_time
                logger.debug(f"OllamaFreeAPI response in {elapsed:.2f}s")
                return response
            else:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs
                )
                elapsed = time.time() - start_time
                logger.debug(f"Local/OpenAI response in {elapsed:.2f}s")
                return response.choices[0].message.content
                
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"LLM error after {elapsed:.2f}s: {e}")
            
            if self.fallback_enabled and self.use_ollamafree:
                logger.info("Intentando fallback a cliente local...")
                self.use_ollamafree = False
                self._init_client()
                return self.chat_completion(messages, temperature, max_tokens, **kwargs)
            
            raise
    
    def get_model_info(self) -> dict:
        """Retorna información del modelo activo"""
        return {
            "provider": "ollamafree" if self.use_ollamafree else "local",
            "model": self.model_name,
            "fallback_enabled": self.fallback_enabled,
            "timeout": self.timeout
        }
    
    def switch_provider(self, use_ollamafree: bool):
        """Cambia dinámicamente entre providers"""
        if use_ollamafree != self.use_ollamafree:
            self.use_ollamafree = use_ollamafree
            self._init_client()
            logger.info(f"Provider cambiado a: {'OllamaFreeAPI' if use_ollamafree else 'Local'}")