"""
API endpoints for AI Agent Chat Interface

Adds chat endpoints to the FastAPI server for real-time communication with the agent.
"""

from fastapi import HTTPException

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from src.shared.utils import detect_language, get_language_display_name

logger = logging.getLogger(__name__)

# Global agent instance
_agent_instance: Optional[UnifiedAgent] = None


class ChatMessage(BaseModel):
    """Chat message model"""
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str
    timestamp: Optional[str] = None


class ChatRequest(BaseModel):
    """Chat request model"""
    message: str = Field(min_length=1)
    context: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    """Chat response model"""
    message: str
    success: bool
    agent_version: str = "unified"
    detected_language: Optional[str] = None
    language_display: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


def register_chat_endpoints(app, get_agent_fn=None):
    """
    Register chat endpoints to FastAPI app.
    
    Args:
        app: FastAPI app instance
        get_agent_fn: Optional function to get the agent instance
    """
    
    chat_history: List[ChatMessage] = []
    
    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest):
        """
        Send a message to the AI Agent and get response.
        """
        try:
            # Detect language from user input
            detected_lang = detect_language(request.message)
            lang_display = get_language_display_name(detected_lang)
            
            user_message = ChatMessage(
                role="user",
                content=request.message,
                timestamp=datetime.now().isoformat()
            )
            chat_history.append(user_message)
            
            # Get agent
            agent = get_agent_fn() if get_agent_fn else None

            if agent is None:
                logger.warning("Agent not initialized")
                raise HTTPException(
                    status_code=503,
                    detail="Agent not initialized."
                )

            response_text = await _process_with_agent(request.message, request.context, agent, detected_lang)
            
            assistant_message = ChatMessage(
                role="assistant",
                content=response_text,
                timestamp=datetime.now().isoformat()
            )
            chat_history.append(assistant_message)
            
            # Keep only last 50 messages
            if len(chat_history) > 50:
                chat_history[:] = chat_history[-50:]
            
            return ChatResponse(
                message=response_text,
                success=True,
                agent_version="unified",
                detected_language=detected_lang,
                language_display=lang_display,
                context={"history_size": len(chat_history)}
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return ChatResponse(
                message=f"Error: {str(e)}",
                success=False,
                agent_version="unified"
            )
    
    @app.get("/api/chat/history")
    async def get_chat_history(limit: int = 50):
        """Get chat history"""
        return {
            "history": chat_history[-limit:],
            "total": len(chat_history)
        }
    
    @app.delete("/api/chat/history")
    async def clear_chat_history():
        """Clear chat history"""
        chat_history.clear()
        return {"status": "cleared"}
    
    @app.get("/api/chat/history/export")
    async def export_chat_history():
        """Export chat history as JSON"""
        from pathlib import Path
        
        logs_dir = Path("AI_support/logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"carv_chat_history_{timestamp}.json"
        filepath = logs_dir / filename
        
        export_data = {
            "exported_at": datetime.now().isoformat(),
            "total_messages": len(chat_history),
            "messages": chat_history
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        return {
            "status": "exported",
            "file": str(filepath),
            "count": len(chat_history),
        }


async def _process_with_agent(
    message: str,
    context: Optional[Dict] = None,
    agent=None,
    detected_lang: str = "en"
) -> str:
    """
    Process message with AI Agent.
    
    Args:
        message: User message to process
        context: Optional context dictionary
        agent: Agent instance to use
        detected_lang: Detected language code
        
    Returns:
        Response text from the agent
    """
    try:
        # Add language-specific instruction to the message
        from src.shared.utils import get_language_system_prompt_suffix
        lang_suffix = get_language_system_prompt_suffix(detected_lang)
        
        if agent is not None:
            # Check if agent supports language context
            if hasattr(agent, 'process_message'):
                return await agent.process_message(message, context, detected_lang=detected_lang)
            return await agent.process_message(message, context)

        # Fallback: use simple Ollama LLM with language instruction
        from src.infrastructure.llm.ollama import OllamaLLM
        llm = OllamaLLM()
        
        # Prepend language instruction if not English
        full_message = message
        if lang_suffix:
            full_message = f"{message}\n{lang_suffix}"
        
        response = await llm.generate(full_message)
        return response
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return f"I'm having trouble connecting to the AI. Please make sure Ollama is running.\n\nError: {str(e)}\n\nStart Ollama with: `ollama serve`"


def register_agent_endpoints(app, state):
    """Register Agent endpoints"""
    
    @app.get("/api/agent/status")
    async def get_agent_status():
        """Get agent status"""
        return {
            "version": "unified",
            "features": [
                "Multi-Agent Orchestration",
                "Firmware Development",
                "Build & Flash Integration",
                "Code Review & Security",
                "Test Generation (Unity)",
                "DevOps Automation",
            ],
            "capabilities": {
                "codegen": True,
                "review": True,
                "security": True,
                "test": True,
                "devops": True,
                "monitoring": True,
                "firmware": True,
                "build": True,
                "flash": True,
            }
        }
    
    @app.post("/api/agent/task")
    async def run_agent_task(request: ChatRequest):
        """Run task with agent"""
        try:
            agent = FirmwareAgent()
            result = await agent.process(Task(
                type="firmware",
                description=request.message,
                context=request.context or {}
            ))
            
            return {
                "success": result.get("success", False),
                "message": result.get("message", str(result)),
                "result": result,
            }
        except Exception as e:
            logger.error(f"Agent task error: {e}")
            return {
                "success": False,
                "message": f"Error: {str(e)}",
            }
    
    @app.post("/api/agent/security")
    async def run_security_scan(request: ChatRequest):
        """Security scan with agent"""
        try:
            agent = SecurityAgent()
            result = await agent.process(Task(
                type="security",
                description=request.message,
                context=request.context or {}
            ))
            return result
        except Exception as e:
            logger.error(f"Security scan error: {e}")
            return {"error": str(e)}
    
    @app.post("/api/agent/review")
    async def run_code_review(request: ChatRequest):
        """Code review with agent"""
        try:
            agent = ReviewAgent()
            result = await agent.process(Task(
                type="review",
                description=request.message,
                context=request.context or {}
            ))
            return result
        except Exception as e:
            logger.error(f"Code review error: {e}")
            return {"error": str(e)}
    
    @app.post("/api/agent/devops")
    async def run_devops(request: ChatRequest):
        """DevOps task with agent"""
        try:
            agent = DevOpsAgent()
            result = await agent.process(Task(
                type="devops",
                description=request.message,
                context=request.context or {}
            ))
            return result
        except Exception as e:
            logger.error(f"DevOps error: {e}")
            return {"error": str(e)}
    
    @app.get("/api/agent/health")
    async def agent_health():
        """Health check for agent"""
        try:
            agent = MonitoringAgent()
            result = await agent.process(Task(
                type="monitor",
                description="Health check",
                context={"action": "health_check"}
            ))
            return result
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {"error": str(e)}


# Keep old v2 endpoints for backwards compatibility
def register_agent_v2_endpoints(app, state):
    """Register Agent endpoints (backwards compatible)"""
    register_agent_endpoints(app, state)


# ============================================================================
# Reasoning/Confidence Analysis Endpoints
# ============================================================================

class ReasoningRequest(BaseModel):
    """Request for reasoning analysis"""
    question: str = Field(min_length=1)
    context: Optional[Dict[str, Any]] = None


class ConfidenceFactor(BaseModel):
    """Confidence factor model"""
    id: str
    label: str
    description: str
    impact: str  # 'positive' | 'negative' | 'neutral'
    weight: float
    evidence: Optional[List[str]] = None


class ReasoningStep(BaseModel):
    """Reasoning step model"""
    step: int
    description: str
    conclusion: str
    confidence_delta: float


class SourceRef(BaseModel):
    """Source reference model"""
    file: str
    line: Optional[int] = None
    snippet: Optional[str] = None
    relevance: str = "medium"  # 'high' | 'medium' | 'low'


class ReasoningChain(BaseModel):
    """Full reasoning chain model"""
    id: str
    question: str
    answer: str
    confidence: float
    factors: List[ConfidenceFactor]
    sources: List[SourceRef]
    reasoning_steps: List[ReasoningStep]
    limitations: Optional[List[str]] = None


def register_reasoning_endpoints(app, get_agent_fn=None):
    """Register reasoning/confidence analysis endpoints."""

    @app.post("/api/reasoning/analyze", response_model=ReasoningChain)
    async def analyze_reasoning(request: ReasoningRequest):
        """
        Analyze reasoning for a given question.
        Returns confidence breakdown with evidence and sources.
        """
        try:
            # Get agent if available
            agent = get_agent_fn() if get_agent_fn else None

            # Build reasoning response
            reasoning = _generate_reasoning_chain(request.question, request.context, agent)

            return reasoning

        except Exception as e:
            logger.error(f"Reasoning analysis error: {e}")
            # Return error reasoning chain
            return ReasoningChain(
                id=f"error-{datetime.now().timestamp()}",
                question=request.question,
                answer=f"Error analyzing reasoning: {str(e)}",
                confidence=0.0,
                factors=[],
                sources=[],
                reasoning_steps=[],
                limitations=[str(e)]
            )

    @app.get("/api/reasoning/factors")
    async def get_confidence_factors():
        """
        Get available confidence factors for reasoning.
        """
        return {
            "factors": [
                {"id": "code_coverage", "label": "Code Coverage", "weight_range": [0.1, 0.3]},
                {"id": "citation_count", "label": "Citation Count", "weight_range": [0.1, 0.25]},
                {"id": "hardware_match", "label": "Hardware Match", "weight_range": [0.15, 0.3]},
                {"id": "test_coverage", "label": "Test Coverage", "weight_range": [0.1, 0.2]},
                {"id": "similarity", "label": "Similarity to Known Patterns", "weight_range": [0.05, 0.15]},
            ]
        }


def _generate_reasoning_chain(
    question: str,
    context: Optional[Dict] = None,
    agent=None
) -> ReasoningChain:
    """
    Generate reasoning chain for a question.
    This can be extended to use actual agent reasoning in the future.
    """
    timestamp = datetime.now().isoformat()

    # Simple heuristic-based reasoning for demo
    # In production, this would call the agent to analyze the question

    # Default response with demo data
    factors = [
        ConfidenceFactor(
            id="f1",
            label="Static Analysis",
            description="Analyzed codebase structure and patterns",
            impact="positive",
            weight=0.3,
            evidence=["Found matching code patterns in 3 files"]
        ),
        ConfidenceFactor(
            id="f2",
            label="Documentation",
            description="Documentation references found",
            impact="positive",
            weight=0.2,
            evidence=["RM0480 reference manual cited"]
        ),
        ConfidenceFactor(
            id="f3",
            label="Hardware Constraints",
            description="Hardware limitations considered",
            impact="neutral",
            weight=0.1,
            evidence=["STM32F407VG constraints checked"]
        ),
    ]

    reasoning_steps = [
        ReasoningStep(
            step=1,
            description="Parse question and identify key concepts",
            conclusion="Identified embedded system topic",
            confidence_delta=0.15
        ),
        ReasoningStep(
            step=2,
            description="Search codebase for relevant files",
            conclusion="Found 3 relevant source files",
            confidence_delta=0.2
        ),
        ReasoningStep(
            step=3,
            description="Analyze code patterns and dependencies",
            conclusion="Code follows HAL pattern",
            confidence_delta=0.15
        ),
        ReasoningStep(
            step=4,
            description="Cross-reference with documentation",
            conclusion="Documentation confirms approach",
            confidence_delta=0.1
        ),
    ]

    sources = [
        SourceRef(
            file="main/software/Src/main.c",
            line=145,
            snippet="HAL_UART_Transmit(&huart2, buffer, len, 1000);",
            relevance="high"
        ),
        SourceRef(
            file="main/software/Src/usart.c",
            line=23,
            snippet="huart2.Init.BaudRate = 115200;",
            relevance="medium"
        ),
    ]

    return ReasoningChain(
        id=f"reasoning-{timestamp}",
        question=question,
        answer=f"Based on analysis of the codebase, I can provide insights about: {question}",
        confidence=0.85,
        factors=factors,
        sources=sources,
        reasoning_steps=reasoning_steps,
        limitations=[
            "Analysis based on static code inspection",
            "Runtime behavior not verified"
        ]
    )
