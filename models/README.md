# Modelos de IA Locales

Este directorio contiene los modelos de IA descargados localmente.

## Instrucciones

Para este proyecto usamos **Ollama** como gestor de modelos.
Los modelos se descargan automáticamente en la carpeta de datos de Ollama.

### Modelo recomendado: Mistral 7B

```powershell
# Instalar Ollama (si no está instalado)
winget install Ollama.Ollama

# Descargar Mistral 7B
ollama pull mistral
```

### Modelos alternativos

```powershell
# LLaMA 2 (más pesado pero capaz)
ollama pull llama2

# Phi-2 (más ligero, ideal para pruebas)
ollama pull phi

# Neural Chat (optimizado para conversación)
ollama pull neural-chat
```

## Verificar modelos instalados

```powershell
ollama list
```
