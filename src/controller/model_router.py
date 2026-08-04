import re
import json
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
from dataclasses import dataclass
import time

from src.models.provider_router import ModelType, Message, OpenRouterClient
from src.utils.config import config


class TaskType(Enum):
    """Task types for model routing."""
    SIMPLE_CHAT = "simple_chat"
    CODING = "coding"
    COMPLEX_REASONING = "complex_reasoning"
    MULTIMODAL = "multimodal"
    UNKNOWN = "unknown"


@dataclass
class RoutingDecision:
    """Routing decision for a task."""
    model_type: ModelType
    task_type: TaskType
    confidence: float
    reasoning: str
    estimated_cost: float = 0.0
    estimated_tokens: int = 0
    complexity_score: int = 0


class TaskAnalyzer:
    """Analyzes tasks to determine their complexity and requirements."""
    
    def __init__(self):
        pass
    
    def calculate_complexity(self, user_input: str, context: Optional[List[Message]] = None) -> int:
        """Calculate complexity score (0-15+) based on input and context."""
        score = 0
        input_lower = user_input.lower()
        
        # 1. Context Pressure
        if context and len(context) > 10:
            score += 2
        if context and sum(len(m.content or "") for m in context) > 5000:
            score += 2
            
        # 2. Multimodal Complexity (Files/Images)
        if "--- file reference:" in input_lower or "--- contents of" in input_lower:
            score += 3
        if any(word in input_lower for word in ["image", "picture", "visual", "audio", "video"]):
            score += 3
            
        # 3. Coding Complexity
        coding_words = ["code", "program", "function", "class", "algorithm", "debug", "refactor", "error", "exception"]
        coding_matches = sum(1 for w in coding_words if w in input_lower)
        if coding_matches > 0:
            score += 2 + min(coding_matches, 3)
            
        # 4. Reasoning Depth
        reasoning_words = ["analyze", "reason", "explain", "understand", "theory", "logic", "compare", "critical"]
        reasoning_matches = sum(1 for w in reasoning_words if w in input_lower)
        if reasoning_matches > 0:
            score += 2 + min(reasoning_matches, 3)
            
        # 5. Planning Depth
        planning_words = ["plan", "strategy", "design", "architecture", "system", "workflow", "multi-step"]
        if any(word in input_lower for word in planning_words):
            score += 3
            
        # Short simple messages get very low score
        if len(user_input.split()) < 10 and score < 5:
            score = max(0, score - 2)
            
        return score
    
    def determine_task_type(self, input_lower: str, score: int) -> TaskType:
        if any(word in input_lower for word in ["image", "picture", "visual", "audio", "video"]):
            return TaskType.MULTIMODAL
        elif any(word in input_lower for word in ["code", "program", "function", "class", "debug", "refactor"]):
            return TaskType.CODING
        elif score >= 7:
            return TaskType.COMPLEX_REASONING
        else:
            return TaskType.SIMPLE_CHAT


class ModelRouter:
    """Routes tasks to appropriate models based on capability matching."""
    
    def __init__(self, openrouter_client: OpenRouterClient):
        self.client = openrouter_client
        self.analyzer = TaskAnalyzer()
        
    def _map_model_id_to_model_type(self, model_id: str) -> ModelType:
        # Simple heuristic to map config model string back to ModelType enum
        if "qwen" in model_id.lower():
            return ModelType.QWEN
        elif "gemini" in model_id.lower():
            return ModelType.GEMINI_FLASH
        elif "mimo" in model_id.lower():
            return ModelType.MIMO
        elif "deepseek" in model_id.lower():
            return ModelType.DEEPSEEK
        return ModelType.QWEN

    async def route_task(
        self,
        user_input: str,
        context: Optional[List[Message]] = None,
        force_model: Optional[ModelType] = None,
    ) -> RoutingDecision:
        """Route a task to the appropriate model based on complexity score."""
        start_time = time.time()
        
        # Calculate complexity
        complexity = self.analyzer.calculate_complexity(user_input, context)
        task_type = self.analyzer.determine_task_type(user_input.lower(), complexity)
        
        # Apply routing policy
        if force_model:
            selected_model = force_model
            reasoning = f"Model forced by user: {force_model.value}"
        else:
            selected_model_id = ""
            if complexity <= 3:
                selected_model_id = config.settings.complexity_routing.get("0-3")
            elif complexity <= 6:
                selected_model_id = config.settings.complexity_routing.get("4-6")
            elif complexity <= 9:
                selected_model_id = config.settings.complexity_routing.get("7-9")
            elif complexity <= 12:
                selected_model_id = config.settings.complexity_routing.get("10-12")
            else:
                selected_model_id = config.settings.complexity_routing.get("13+")
                
            # Coding override
            if task_type == TaskType.CODING and complexity >= 7:
                selected_model_id = config.settings.model_deepseek
                
            selected_model = self._map_model_id_to_model_type(selected_model_id or config.settings.model_qwen)
            reasoning = f"Routed via complexity score: {complexity}. Selected model ID: {selected_model_id}"

        # Get capabilities for cost estimation
        caps = self.client.get_model_capabilities(selected_model)
        tokens = self.client.estimate_tokens(user_input)
        estimated_cost = (tokens / 1_000_000) * caps.cost_per_token

        return RoutingDecision(
            model_type=selected_model,
            task_type=task_type,
            confidence=0.9,
            reasoning=reasoning,
            estimated_cost=estimated_cost,
            estimated_tokens=tokens,
            complexity_score=complexity
        )
    
    def learn_from_feedback(self, *args, **kwargs):
        pass
    
    def get_routing_stats(self) -> Dict[str, Any]:
        return {"status": "Using intelligent complexity routing"}
    
    async def self_improve(self):
        pass


# Helper function for quick routing
async def route_and_execute(
    router: ModelRouter,
    user_input: str,
    system_prompt: str = "You are a helpful AI assistant.",
    context: Optional[List[Message]] = None,
    stream: bool = False,
) -> Tuple[RoutingDecision, str]:
    """Route task and execute in one call."""
    from src.models.provider_router import create_messages
    
    # Route the task
    decision = await router.route_task(user_input, context)
    print(f"Routing decision: {decision.model_type.value} for {decision.task_type.value} (complexity: {decision.complexity_score})")
    print(f"Reasoning: {decision.reasoning}")
    
    # Prepare messages
    if context:
        messages = context
    else:
        messages = create_messages(system_prompt, user_input)
    
    # Execute with selected model
    client = OpenRouterClient()
    
    try:
        if stream:
            response_parts = []
            async for chunk in client.chat_completion_stream(
                messages=messages,
                model_type=decision.model_type,
            ):
                response_parts.append(chunk)
                print(chunk, end="", flush=True)
            
            response = "".join(response_parts)
            print()  # New line after streaming
        else:
            response_obj = await client.chat_completion(
                messages=messages,
                model_type=decision.model_type,
            )
            response = response_obj.choices[0]["message"]["content"]
        
        return decision, response
        
    finally:
        await client.close()