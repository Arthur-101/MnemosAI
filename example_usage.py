#!/usr/bin/env python3
"""Example usage of AgenticAI system."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.models.provider_router import OpenRouterClient, ModelType, create_messages
from src.controller.model_router import ModelRouter, route_and_execute
from src.memory.sqlite_store import SQLiteMemoryStore, SessionManager
from src.tools.basic_tools import ToolManager
from src.utils.config import config


async def example_basic_chat():
    """Example: Basic chat with model routing."""
    print("=" * 60)
    print("Example 1: Basic Chat with Model Routing")
    print("=" * 60)
    
    memory_store = SQLiteMemoryStore()
    session_manager = SessionManager(memory_store)
    client = OpenRouterClient()
    router = ModelRouter(client)
    
    try:
        # Simple chat
        user_input = "Write a Python function to calculate factorial"
        
        print(f"User: {user_input}")
        
        decision, response = await route_and_execute(
            router=router,
            user_input=user_input,
            system_prompt="You are a helpful coding assistant.",
            context=None,
            stream=False,
        )
        
        print(f"\nModel selected: {decision.model_type.value}")
        print(f"Task type: {decision.task_type.value}")
        print(f"Confidence: {decision.confidence:.2f}")
        print(f"\nResponse:\n{response}")
        
        # Save to memory
        session_manager.save_conversation(
            model_id=client.model_ids[decision.model_type],
            user_message=user_input,
            assistant_message=response,
            tokens_used=decision.estimated_tokens * 2,
            cost=decision.estimated_cost,
        )
        
        print(f"\n✓ Conversation saved to session: {session_manager.current_session_id}")
        
    finally:
        await client.close()
        memory_store.close()


async def example_tool_usage():
    """Example: Using tools with the AI."""
    print("\n" + "=" * 60)
    print("Example 2: Tool Usage")
    print("=" * 60)
    
    tool_manager = ToolManager()
    
    # Example 1: Get system info
    print("\n1. Getting system information:")
    result = tool_manager.execute_tool("get_system_info", {})
    if result["success"]:
        info = result["result"]
        print(f"   System: {info['system']} {info['release']}")
        print(f"   Python: {info['python_version']}")
        print(f"   Directory: {info['current_directory']}")
    
    # Example 2: List files
    print("\n2. Listing files in current directory:")
    result = tool_manager.execute_tool("list_files", {"directory": "."})
    if result["success"]:
        files = result["result"]
        print(f"   Found {len(files)} items:")
        for file in files[:5]:  # Show first 5
            print(f"   - {file['name']} ({file['type']})")
        if len(files) > 5:
            print(f"   ... and {len(files) - 5} more")
    
    # Example 3: Calculate
    print("\n3. Calculating expression:")
    result = tool_manager.execute_tool("calculate", {"expression": "15 * (3 + 7)"})
    if result["success"]:
        print(f"   15 * (3 + 7) = {result['result']}")
    
    # List all available tools
    print("\n4. Available tools:")
    tools = tool_manager.list_tools()
    if tools["success"]:
        for tool_name, tool_info in tools["result"].items():
            print(f"   - {tool_name}: {tool_info['description']}")


async def example_memory_persistence():
    """Example: Memory persistence across sessions."""
    print("\n" + "=" * 60)
    print("Example 3: Memory Persistence")
    print("=" * 60)
    
    memory_store = SQLiteMemoryStore()
    session_manager = SessionManager(memory_store)
    
    # Create some conversation history
    session_id = session_manager.current_session_id
    
    # Save some conversations
    conversations = [
        ("What is Python?", "Python is a high-level programming language..."),
        ("Explain lists in Python", "Lists are ordered collections in Python..."),
        ("How to sort a list?", "You can use the sort() method or sorted() function..."),
    ]
    
    for user_msg, assistant_msg in conversations:
        session_manager.save_conversation(
            model_id="test-model",
            user_message=user_msg,
            assistant_message=assistant_msg,
            tokens_used=100,
            cost=0.001,
        )
    
    print(f"Saved {len(conversations)} conversations to session: {session_id[:8]}...")
    
    # Get session context
    context = session_manager.get_session_context(max_messages=5)
    print(f"\nSession context has {len(context)} messages")
    
    # Show session stats
    stats = session_manager.get_session_stats()
    print(f"\nSession statistics:")
    print(f"  Conversations: {stats['conversation_count']}")
    print(f"  Total tokens: {stats['total_tokens']}")
    print(f"  Total cost: ${stats['total_cost']:.4f}")
    
    # Show database stats
    db_stats = memory_store.get_database_stats()
    print(f"\nDatabase statistics:")
    print(f"  Total conversations: {db_stats.get('conversations_count', 0)}")
    print(f"  Database size: {db_stats.get('database_size_bytes', 0) / 1024:.1f} KB")
    
    memory_store.close()


async def example_cost_tracking():
    """Example: Cost tracking and management."""
    print("\n" + "=" * 60)
    print("Example 4: Cost Tracking")
    print("=" * 60)
    
    # Simulate some cost tracking
    models = ["qwen/qwen-2.5-32b-instruct", "google/gemini-2.5-flash-lite", "deepseek/deepseek-v3.2"]
    
    for model in models:
        # Track some usage
        input_tokens = 500
        output_tokens = 300
        config.track_cost(model, input_tokens, output_tokens)
    
    # Get cost summary
    cost_summary = config.get_cost_summary()
    
    print("Current cost summary:")
    print(f"  Total cost: ${cost_summary['total_cost']:.4f}")
    print(f"  Total input tokens: {cost_summary['total_input_tokens']}")
    print(f"  Total output tokens: {cost_summary['total_output_tokens']}")
    
    print("\nCost by model:")
    for model, usage in cost_summary.get('model_usage', {}).items():
        print(f"  {model.split('/')[-1][:20]:20} ${usage.get('cost', 0):.4f}")
    
    # Check warnings
    total_cost = cost_summary['total_cost']
    if total_cost >= config.settings.cost_limit:
        print(f"\n⚠️  COST LIMIT EXCEEDED: ${total_cost:.2f}")
    elif total_cost >= config.settings.cost_warning_threshold:
        print(f"\n⚠️  Cost warning: ${total_cost:.2f}")


async def example_full_integration():
    """Example: Full integration of all components."""
    print("\n" + "=" * 60)
    print("Example 5: Full System Integration")
    print("=" * 60)
    
    # Initialize all components
    memory_store = SQLiteMemoryStore()
    session_manager = SessionManager(memory_store)
    tool_manager = ToolManager()
    client = OpenRouterClient()
    router = ModelRouter(client)
    
    try:
        print("\nSystem initialized with:")
        print(f"  - Session: {session_manager.current_session_id[:8]}...")
        print(f"  - Available tools: {len(tool_manager.tool_registry)}")
        print(f"  - Available models: {len(client.model_ids)}")
        
        # Interactive loop
        print("\nInteractive mode (type 'exit' to quit):")
        
        while True:
            try:
                user_input = input("\nYou: ").strip()
                
                if user_input.lower() in ["exit", "quit"]:
                    print("Goodbye!")
                    break
                
                if user_input.lower() == "tools":
                    # Show available tools
                    tools = tool_manager.list_tools()
                    if tools["success"]:
                        print("\nAvailable tools:")
                        for tool_name, tool_info in tools["result"].items():
                            print(f"  - {tool_name}: {tool_info['description']}")
                    continue
                
                if user_input.lower() == "stats":
                    # Show session stats
                    stats = session_manager.get_session_stats()
                    print(f"\nSession stats:")
                    print(f"  Conversations: {stats['conversation_count']}")
                    print(f"  Cost: ${stats['total_cost']:.4f}")
                    continue
                
                if user_input.lower().startswith("tool "):
                    # Execute tool directly
                    tool_command = user_input[5:].strip()
                    # Simple tool parsing (in real system, AI would handle this)
                    if "calculate" in tool_command:
                        expr = tool_command.replace("calculate", "").strip()
                        result = tool_manager.execute_tool("calculate", {"expression": expr})
                        if result["success"]:
                            print(f"Result: {result['result']}")
                        else:
                            print(f"Error: {result['message']}")
                    continue
                
                # Route and execute with AI
                print("Thinking...", end="", flush=True)
                
                decision, response = await route_and_execute(
                    router=router,
                    user_input=user_input,
                    system_prompt="You are a helpful AI assistant with access to tools.",
                    context=None,
                    stream=False,
                )
                
                print(f"\nAssistant ({decision.model_type.value}): {response}")
                
                # Save to memory
                session_manager.save_conversation(
                    model_id=client.model_ids[decision.model_type],
                    user_message=user_input,
                    assistant_message=response,
                    tokens_used=decision.estimated_tokens * 2,
                    cost=decision.estimated_cost,
                )
                
            except KeyboardInterrupt:
                print("\n\nInterrupted. Type 'exit' to quit.")
                continue
            except Exception as e:
                print(f"\nError: {e}")
                continue
                
    finally:
        await client.close()
        memory_store.close()


async def main():
    """Run all examples."""
    print("AgenticAI - Example Usage")
    print("=" * 60)
    
    examples = [
        ("Basic Chat", example_basic_chat),
        ("Tool Usage", example_tool_usage),
        ("Memory Persistence", example_memory_persistence),
        ("Cost Tracking", example_cost_tracking),
        ("Full Integration", example_full_integration),
    ]
    
    for i, (name, example_func) in enumerate(examples, 1):
        print(f"\n[{i}/{len(examples)}] Running: {name}")
        try:
            await example_func()
        except Exception as e:
            print(f"Error in example '{name}': {e}")
        
        if i < len(examples):
            input("\nPress Enter to continue to next example...")
    
    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())