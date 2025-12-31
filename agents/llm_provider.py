"""
LLM Provider - Abstracción para modelos de IA locales
Soporta Ollama (recomendado) como backend principal
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from loguru import logger
import yaml
import os

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("Ollama no instalado. Instale con: pip install ollama")


@dataclass
class LLMResponse:
    """Respuesta estructurada del modelo LLM"""
    content: str
    model: str
    tokens_used: int
    success: bool
    error: Optional[str] = None


class LLMProvider:
    """
    Proveedor de LLM Local usando Ollama
    
    Uso:
        llm = LLMProvider()
        response = llm.generate("Analiza el sentimiento de esta noticia...")
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        """Inicializa el proveedor LLM con configuración"""
        self.config = self._load_config(config_path)
        self.model = self.config.get("llm", {}).get("model", "mistral")
        self.temperature = self.config.get("llm", {}).get("temperature", 0.1)  # Bajamos temperatura para más consistencia
        self.max_tokens = self.config.get("llm", {}).get("max_tokens", 1024)
        self.client = None
        
        if OLLAMA_AVAILABLE:
            self.client = ollama.Client()
            logger.info(f"LLM Provider inicializado con modelo: {self.model}")
        else:
            logger.error("Ollama no disponible. El análisis IA no funcionará.")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Carga configuración desde archivo YAML"""
        try:
            # Construir ruta absoluta desde el directorio del proyecto
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            full_path = os.path.join(base_dir, config_path)
            
            with open(full_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Archivo de config no encontrado: {config_path}")
            return {}
        except Exception as e:
            logger.error(f"Error cargando config: {e}")
            return {}
    
    def is_available(self) -> bool:
        """Verifica si el proveedor LLM está disponible"""
        if not self.client:
            return False
        
        try:
            response = self.client.list()
            # La API nueva devuelve objetos, no diccionarios
            models = response.get('models', []) if isinstance(response, dict) else getattr(response, 'models', [])
            
            for m in models:
                # Manejar tanto objetos como diccionarios
                name = m.get('name', '') if isinstance(m, dict) else getattr(m, 'model', getattr(m, 'name', ''))
                if name and name.startswith(self.model):
                    return True
            return False
        except Exception as e:
            logger.error(f"Error verificando disponibilidad: {e}")
            return False
    
    def generate(
        self, 
        prompt: str, 
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: int = 10
    ) -> LLMResponse:
        """
        Genera una respuesta del modelo LLM con un timeout
        
        Args:
            prompt: El prompt del usuario
            system_prompt: Instrucciones del sistema (opcional)
            temperature: Control de creatividad 0-1 (opcional)
            max_tokens: Límite de tokens en respuesta (opcional)
            timeout: Tiempo máximo de espera en segundos (defecto: 10s)
        
        Returns:
            LLMResponse con el contenido generado
        """
        if not self.client:
            return LLMResponse(
                content="",
                model=self.model,
                tokens_used=0,
                success=False,
                error="Ollama no disponible"
            )
        
        import concurrent.futures
        
        def _generate():
            try:
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                
                return self.client.chat(
                    model=self.model,
                    messages=messages,
                    options={
                        "temperature": temperature or self.temperature,
                        "num_predict": max_tokens or self.max_tokens
                    }
                )
            except Exception as e:
                logger.error(f"Error interno en Ollama: {e}")
                return None

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_generate)
                response = future.result(timeout=timeout)
                
            if response is None:
                raise Exception("Ollama retornó una respuesta vacía o error")
                
            content = response.get("message", {}).get("content", "")
            tokens = response.get("eval_count", 0) + response.get("prompt_eval_count", 0)
            
            logger.debug(f"LLM generó respuesta de {tokens} tokens")
            
            return LLMResponse(
                content=content,
                model=self.model,
                tokens_used=tokens,
                success=True
            )
            
        except concurrent.futures.TimeoutError:
            logger.warning(f"Timeout de {timeout}s alcanzado esperando al LLM")
            return LLMResponse(
                content="",
                model=self.model,
                tokens_used=0,
                success=False,
                error=f"Timeout superado ({timeout}s)"
            )
        except Exception as e:
            logger.error(f"Error generando respuesta LLM: {e}")
            return LLMResponse(
                content="",
                model=self.model,
                tokens_used=0,
                success=False,
                error=str(e)
            )
    
    def analyze_sentiment(self, text: str, context: str = "forex") -> Dict[str, Any]:
        """
        Analiza el sentimiento de un texto para trading
        
        Args:
            text: Texto a analizar (noticia, tweet, etc.)
            context: Contexto del análisis (forex, crypto, stocks)
        
        Returns:
            Dict con sentiment (bullish/bearish/neutral), score (-1 a 1), y razón
        """
        system_prompt = """Eres un analista financiero experto en {context}. 
Analiza el sentimiento del siguiente texto y responde SOLO en formato JSON:
{{
    "sentiment": "bullish|bearish|neutral",
    "score": <número entre -1 y 1>,
    "impact": "high|medium|low",
    "reason": "<breve explicación>"
}}
Solo responde con el JSON, sin texto adicional, sin preámbulos y sin markdown.
Si no puedes determinar el sentimiento, responde neutral con score 0.""".format(context=context)
        
        response = self.generate(text, system_prompt=system_prompt)
        
        if not response.success:
            return {
                "sentiment": "neutral",
                "score": 0.0,
                "impact": "low",
                "reason": "Error en análisis",
                "error": response.error
            }
        
        # Intentar parsear JSON
        try:
            import json
            # Limpiar respuesta de posibles caracteres extra
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            result = json.loads(content)
            
            # Validar campos mínimos
            required = ["sentiment", "score", "impact"]
            if all(k in result for k in required):
                return result
            else:
                logger.warning(f"JSON incompleto de LLM: {result}")
                raise ValueError("JSON incompleto")
                
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Error parseando JSON de LLM: {e}. Contenido: {response.content[:100]}...")
            # Fallback robusto: buscar campos con regex si el JSON está mal formado o truncado
            try:
                import re
                sentiment_match = re.search(r'"sentiment":\s*"([^"]+)"', response.content)
                score_match = re.search(r'"score":\s*([-+]?\d*\.?\d+)', response.content)
                impact_match = re.search(r'"impact":\s*"([^"]+)"', response.content)
                
                if sentiment_match and score_match:
                    return {
                        "sentiment": sentiment_match.group(1),
                        "score": float(score_match.group(1)),
                        "impact": impact_match.group(1) if impact_match else "medium",
                        "reason": "Parsed via regex (JSON failed)"
                    }
            except:
                pass
                
            # Fallback final
            lower_content = response.content.lower()
            if "bullish" in lower_content:
                return {"sentiment": "bullish", "score": 0.5, "impact": "medium", "reason": response.content[:100]}
            elif "bearish" in lower_content:
                return {"sentiment": "bearish", "score": -0.5, "impact": "medium", "reason": response.content[:100]}
            else:
                return {"sentiment": "neutral", "score": 0.0, "impact": "low", "reason": response.content[:100]}
    
    def extract_events(self, text: str) -> list:
        """
        Extrae eventos económicos relevantes de un texto
        
        Args:
            text: Texto con información económica
        
        Returns:
            Lista de eventos extraídos
        """
        system_prompt = """Eres un analista económico. Extrae eventos económicos del texto.
Responde SOLO en formato JSON array:
[
    {{"event": "nombre", "currency": "USD/EUR/etc", "impact": "high|medium|low", "date": "fecha si disponible"}}
]
Solo responde con el JSON array, sin texto adicional."""
        
        response = self.generate(text, system_prompt=system_prompt)
        
        if not response.success:
            return []
        
        try:
            import json
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)
        except:
            return []
    
    def list_models(self) -> list:
        """Lista los modelos disponibles en Ollama"""
        if not self.client:
            return []
        
        try:
            response = self.client.list()
            # La API nueva devuelve objetos, no diccionarios
            models = response.get('models', []) if isinstance(response, dict) else getattr(response, 'models', [])
            
            result = []
            for m in models:
                # Manejar tanto objetos como diccionarios
                name = m.get('name', '') if isinstance(m, dict) else getattr(m, 'model', getattr(m, 'name', ''))
                if name:
                    result.append(name)
            return result
        except Exception as e:
            logger.error(f"Error listando modelos: {e}")
            return []


# Singleton para uso global
_llm_instance: Optional[LLMProvider] = None


def get_llm() -> LLMProvider:
    """Obtiene instancia singleton del LLM Provider"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMProvider()
    return _llm_instance


if __name__ == "__main__":
    # Test básico
    print("=" * 50)
    print("Test de LLM Provider")
    print("=" * 50)
    
    llm = get_llm()
    
    print(f"\nModelos disponibles: {llm.list_models()}")
    print(f"Proveedor disponible: {llm.is_available()}")
    
    if llm.is_available():
        # Test de generación
        print("\n--- Test de generación ---")
        response = llm.generate("¿Cuál es la capital de España?")
        print(f"Respuesta: {response.content}")
        print(f"Tokens: {response.tokens_used}")
        
        # Test de análisis de sentimiento
        print("\n--- Test de análisis de sentimiento ---")
        noticia = "El BCE sube tipos de interés 25 puntos básicos, superando expectativas del mercado"
        sentiment = llm.analyze_sentiment(noticia)
        print(f"Noticia: {noticia}")
        print(f"Análisis: {sentiment}")
    else:
        print("\n⚠️ El modelo no está disponible. Ejecuta: ollama pull mistral")
