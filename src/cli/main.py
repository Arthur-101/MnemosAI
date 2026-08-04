#!/usr/bin/env python3
"""CLI interface for AgenticAI."""

import asyncio
import sys
import os
from pathlib import Path
from typing import Optional, List

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from src.models.provider_router import OpenRouterClient, ModelType, Message
from src.controller.model_router import ModelRouter, route_and_execute, TaskType
from src.memory.sqlite_store import SQLiteMemoryStore, SessionManager
from src.utils.config import config


console = Console()


@click.group()
def cli():
    """AgenticAI - Multi-model AI agent system."""
    pass


@cli.command()
@click.option("--message", "-m", help="Direct message to send")
@click.option("--model", "-M", type=click.Choice(["auto", "qwen", "gemini_flash", "mimo", "deepseek", "gemini_pro"]),
              default="auto", help="Force specific model")
@click.option("--stream/--no-stream", default=True, help="Stream response")
@click.option("--session", "-s", help="Session ID (default: current)")
@click.option("--system", "-S", default="You are a helpful AI assistant.", help="System prompt")
def chat(message: Optional[str], model: str, stream: bool, session: Optional[str], system: str):
    """Chat with the AI agent."""
    asyncio.run(run_chat(message, model, stream, session, system))


@cli.command()
def models():
    """List available models and their capabilities."""
    asyncio.run(list_models())


@cli.command()
@click.option("--session", "-s", help="Session ID (default: current)")
@click.option("--limit", "-l", default=10, help="Number of conversations to show")
def history(session: Optional[str], limit: int):
    """Show conversation history."""
    show_history(session, limit)


@cli.command()
def stats():
    """Show system statistics and costs."""
    show_stats()


@cli.command()
@click.option("--days", "-d", default=30, help="Days of data to keep")
def cleanup(days: int):
    """Clean up old data."""
    cleanup_data(days)


@cli.command()
def config_show():
    """Show current configuration."""
    show_config()


async def run_chat(
    message: Optional[str],
    model_str: str,
    stream: bool,
    session_id: Optional[str],
    system_prompt: str,
):
    """Run chat interaction."""
    # Initialize components
    memory_store = SQLiteMemoryStore()
    session_manager = SessionManager(memory_store)
    
    if session_id:
        session_manager.current_session_id = session_id
    
    # Get context from memory
    context = session_manager.get_session_context()
    
    try:
        # If no message provided, enter interactive mode
        if not message:
            console.print(Panel.fit(
                "[bold cyan]AgenticAI[/bold cyan] - Multi-model AI Agent\n"
                f"Session: [bold]{session_manager.current_session_id}[/bold]\n"
                f"Context: {len(context)} previous messages",
                border_style="cyan"
            ))
            
            while True:
                try:
                    user_input = Prompt.ask("\n[bold]You[/bold]")
                    
                    if user_input.lower() in ["exit", "quit", "bye"]:
                        console.print("[cyan]Goodbye![/cyan]")
                        break
                    elif user_input.lower() in ["clear", "reset"]:
                        session_manager.new_session()
                        context = []
                        console.print("[yellow]Session cleared.[/yellow]")
                        continue
                    elif user_input.lower() == "stats":
                        show_session_stats(session_manager)
                        continue
                    
                    await process_message(
                        user_input, model_str, stream, session_manager,
                        memory_store, context, system_prompt
                    )
                    
                except KeyboardInterrupt:
                    console.print("\n[yellow]Interrupted. Type 'exit' to quit.[/yellow]")
                    continue
                except EOFError:
                    console.print("\n[cyan]Goodbye![/cyan]")
                    break
        else:
            # Process single message
            await process_message(
                message, model_str, stream, session_manager,
                memory_store, context, system_prompt
            )
            
    finally:
        memory_store.close()


async def process_message(
    user_input: str,
    model_str: str,
    stream: bool,
    session_manager: SessionManager,
    memory_store: SQLiteMemoryStore,
    context: List[Message],
    system_prompt: str,
):
    """Process a single message."""
    # Determine model
    if model_str == "auto":
        force_model = None
    else:
        model_map = {
            "qwen": ModelType.QWEN,
            "gemini_flash": ModelType.GEMINI_FLASH,
            "mimo": ModelType.MIMO,
            "deepseek": ModelType.DEEPSEEK,
        }
        force_model = model_map.get(model_str)
    
    # Initialize router and client
    client = OpenRouterClient()
    router = ModelRouter(client)
    
    try:
        # Show thinking spinner
        with Live(Spinner("dots", text="Analyzing task..."), refresh_per_second=10) as live:
            # Route and execute
            decision, response = await route_and_execute(
                router=router,
                user_input=user_input,
                system_prompt=system_prompt,
                context=context,
                stream=False,  # We'll handle streaming manually if needed
            )
        
        # Save conversation to memory
        model_id = client.model_ids[decision.model_type]
        conversation_id = session_manager.save_conversation(
            model_id=model_id,
            user_message=user_input,
            assistant_message=response,
            tokens_used=decision.estimated_tokens * 2,  # Rough estimate
            cost=decision.estimated_cost,
            metadata={
                "task_type": decision.task_type.value,
                "confidence": decision.confidence,
                "routing_reasoning": decision.reasoning,
            }
        )
        
        # Show response
        console.print(f"\n[bold green]Assistant[/bold green] ([cyan]{decision.model_type.value}[/cyan]):")
        console.print(Panel(response, border_style="green"))
        
        # Show routing info
        routing_table = Table(show_header=False, box=None)
        routing_table.add_row("Task type:", f"[yellow]{decision.task_type.value}[/yellow]")
        routing_table.add_row("Confidence:", f"[yellow]{decision.confidence:.2f}[/yellow]")
        routing_table.add_row("Estimated cost:", f"[yellow]${decision.estimated_cost:.4f}[/yellow]")
        routing_table.add_row("Estimated tokens:", f"[yellow]{decision.estimated_tokens}[/yellow]")
        
        console.print(Panel(routing_table, title="[bold]Routing Info[/bold]", border_style="cyan"))
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
    finally:
        await client.close()


async def list_models():
    """List available models."""
    client = OpenRouterClient()
    
    try:
        models = client.get_available_models()
        
        table = Table(title="Available Models", show_lines=True)
        table.add_column("Type", style="cyan")
        table.add_column("Model ID", style="magenta")
        table.add_column("Max Tokens", style="green")
        table.add_column("Capabilities", style="yellow")
        table.add_column("Speed", style="blue")
        table.add_column("Cost/1M", style="red")
        
        for model_info in models:
            caps = model_info["capabilities"]
            capabilities = []
            if caps["supports_tools"]:
                capabilities.append("tools")
            if caps["supports_vision"]:
                capabilities.append("vision")
            
            table.add_row(
                model_info["type"],
                model_info["id"][:40] + "..." if len(model_info["id"]) > 40 else model_info["id"],
                str(caps["max_tokens"]),
                ", ".join(capabilities) if capabilities else "text",
                f"{caps['speed']:.1f}",
                f"${caps['cost_per_token']:.2f}",
            )
        
        console.print(table)
        
        # Show current cost summary
        cost_summary = config.get_cost_summary()
        console.print(f"\n[bold]Current Cost:[/bold] ${cost_summary['total_cost']:.4f}")
        
    finally:
        await client.close()


def show_history(session_id: Optional[str], limit: int):
    """Show conversation history."""
    memory_store = SQLiteMemoryStore()
    session_manager = SessionManager(memory_store)
    
    if session_id:
        session_manager.current_session_id = session_id
    
    conversations = memory_store.get_conversation_history(
        session_manager.current_session_id,
        limit=limit,
    )
    
    if not conversations:
        console.print("[yellow]No conversation history found.[/yellow]")
        return
    
    table = Table(title=f"Conversation History - Session: {session_manager.current_session_id[:8]}...")
    table.add_column("Time", style="cyan")
    table.add_column("Model", style="magenta")
    table.add_column("User", style="green")
    table.add_column("Assistant", style="yellow")
    table.add_column("Cost", style="red")
    
    for conv in conversations:
        table.add_row(
            conv["created_at"][:19],
            conv["model_id"].split("/")[-1][:15],
            conv["user_message"][:50] + "..." if len(conv["user_message"]) > 50 else conv["user_message"],
            conv["assistant_message"][:50] + "..." if len(conv["assistant_message"]) > 50 else conv["assistant_message"],
            f"${conv['cost']:.4f}" if conv["cost"] else "-",
        )
    
    console.print(table)
    memory_store.close()


def show_stats():
    """Show system statistics."""
    memory_store = SQLiteMemoryStore()
    
    # Database stats
    db_stats = memory_store.get_database_stats()
    
    table = Table(title="System Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Conversations", str(db_stats.get("conversations_count", 0)))
    table.add_row("Tool Executions", str(db_stats.get("tool_executions_count", 0)))
    table.add_row("Documents", str(db_stats.get("documents_count", 0)))
    table.add_row("Database Size", f"{db_stats.get('database_size_bytes', 0) / 1024:.1f} KB")
    
    if "most_used_model" in db_stats:
        table.add_row("Most Used Model", f"{db_stats['most_used_model']} ({db_stats['most_used_model_count']} times)")
    
    # Check Redis status
    try:
        from src.memory.redis_store import redis_store
        redis_status = "Connected" if redis_store.is_connected() else "Disconnected"
    except ImportError:
        redis_status = "Not Installed"
        
    table.add_row("Redis Status", redis_status)
    
    console.print(table)
    
    # Cost stats
    cost_summary = config.get_cost_summary()
    cost_table = Table(title="Cost Summary")
    cost_table.add_column("Model", style="cyan")
    cost_table.add_column("Cost", style="red")
    cost_table.add_column("Input Tokens", style="green")
    cost_table.add_column("Output Tokens", style="yellow")
    
    for model, usage in cost_summary.get("model_usage", {}).items():
        cost_table.add_row(
            model.split("/")[-1][:20],
            f"${usage.get('cost', 0):.4f}",
            str(usage.get("input_tokens", 0)),
            str(usage.get("output_tokens", 0)),
        )
    
    cost_table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]${cost_summary.get('total_cost', 0):.4f}[/bold]",
        str(cost_summary.get("total_input_tokens", 0)),
        str(cost_summary.get("total_output_tokens", 0)),
    )
    
    console.print(cost_table)
    
    # Warning if near limit
    total_cost = cost_summary.get("total_cost", 0)
    if total_cost >= config.settings.cost_limit:
        console.print(f"[bold red]⚠️  COST LIMIT EXCEEDED: ${total_cost:.2f}[/bold red]")
    elif total_cost >= config.settings.cost_warning_threshold:
        console.print(f"[bold yellow]⚠️  Cost warning: ${total_cost:.2f}[/bold yellow]")
    
    memory_store.close()


def cleanup_data(days: int):
    """Clean up old data."""
    memory_store = SQLiteMemoryStore()
    
    if Confirm.ask(f"Delete data older than {days} days?", default=False):
        deleted = memory_store.cleanup_old_data(days)
        console.print(f"[green]Deleted {deleted} rows of old data.[/green]")
    else:
        console.print("[yellow]Cleanup cancelled.[/yellow]")
    
    memory_store.close()


def show_config():
    """Show current configuration."""
    settings = config.settings
    
    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    
    # API settings
    table.add_row("OpenRouter Base URL", settings.openrouter_base_url)
    table.add_row("API Key", "[red](hidden)[/red]" if settings.openrouter_api_key else "[yellow]Not set[/yellow]")
    
    # Model settings
    table.add_row("Qwen Model", settings.model_qwen)
    table.add_row("Gemini Flash", settings.model_gemini_flash)
    table.add_row("Mimo Model", settings.model_mimo)
    table.add_row("DeepSeek Model", settings.model_deepseek_flash)
    
    # Cost settings
    table.add_row("Cost Limit", f"${settings.cost_limit}")
    table.add_row("Cost Warning", f"${settings.cost_warning_threshold}")
    
    # Performance settings
    table.add_row("Max Tokens", str(settings.max_tokens_per_request))
    table.add_row("Temperature", str(settings.temperature))
    table.add_row("Request Timeout", f"{settings.request_timeout}s")
    
    # Security settings
    table.add_row("Allowed File Types", ", ".join(settings.allowed_file_types))
    table.add_row("Max File Size", f"{settings.max_file_size_mb}MB")
    table.add_row("Require Permission", "Yes" if settings.require_permission_prompt else "No")
    
    console.print(table)


def show_session_stats(session_manager: SessionManager):
    """Show session statistics."""
    stats = session_manager.get_session_stats()
    
    table = Table(title=f"Session Statistics - {stats['session_id'][:8]}...")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Start Time", stats["start_time"])
    table.add_row("Conversations", str(stats["conversation_count"]))
    table.add_row("Total Tokens", str(stats["total_tokens"]))
    table.add_row("Total Cost", f"${stats['total_cost']:.4f}")
    
    # Model usage
    for model, count in stats["model_usage"].items():
        table.add_row(f"→ {model.split('/')[-1][:15]}", str(count))
    
    console.print(table)


if __name__ == "__main__":
    cli()