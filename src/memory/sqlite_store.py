import sqlite3
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.config import config
from src.memory.redis_store import redis_store

class SQLiteMemoryStore:
    """SQLite-based memory storage for conversations, tools, and documents."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Create the SQLite connection.

        * If ``db_path`` is the sentinel ``":memory:"`` we open an
          in‑memory database (useful for tests).
        * Otherwise we treat ``db_path`` as a filesystem path, ensure the
          parent directory exists, and open the file‑based database.
        """
        raw_path = db_path or config.settings.sqlite_db_path
        # Detect the explicit in‑memory sentinel (allow surrounding whitespace)
        if isinstance(raw_path, str) and raw_path.strip() == ":memory:":
            self.connection = sqlite3.connect(":memory:")
            self.db_path = Path(":memory:")
        else:
            self.db_path = Path(raw_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self._initialize_database()

    # -----------------------------------------------------------------
    # Helper that always commits after a write operation (reduces boiler‑plate)
    # -----------------------------------------------------------------
    def _execute(self, sql: str, params: tuple = ()):  # pragma: no cover – simple helper
        cur = self.connection.cursor()
        cur.execute(sql, params)
        self.connection.commit()
        return cur

    
    
    def _initialize_database(self):
        """Initialize database with required tables."""
        cursor = self.connection.cursor()
        
        # Create conversations table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            model_id TEXT,
            user_message TEXT,
            assistant_message TEXT,
            tokens_used INTEGER,
            cost REAL,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create tool_executions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tool_executions (
            id TEXT PRIMARY KEY,
            conversation_id TEXT,
            tool_name TEXT,
            parameters TEXT,
            result TEXT,
            success INTEGER,
            execution_time REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations (id)
        )
        """)
        
        # Create documents table (for RAG)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            content TEXT,
            source TEXT,
            embedding_id TEXT,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create cost_tracking table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cost_tracking (
            id TEXT PRIMARY KEY,
            model_id TEXT,
            operation_type TEXT,
            tokens_input INTEGER,
            tokens_output INTEGER,
            cost REAL,
            latency REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create messages table for chat with summaries and tags
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            role TEXT NOT NULL,
            content_raw TEXT NOT NULL,
            content_summary TEXT,
            tags_json TEXT,
            model_id TEXT,
            tokens_used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES conversations (id) ON DELETE CASCADE
        )
        """)
        
        # Create user_memories table for factual knowledge
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_memories (
            id TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            tags_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create api_keys table for storing multi-provider API keys
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL UNIQUE,
            label TEXT,
            key_value TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Create role_assignments table for model role configuration
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS role_assignments (
            role TEXT PRIMARY KEY,
            provider TEXT NOT NULL DEFAULT 'openrouter',
            model_id TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Create model_notes table for favorite models and user notes
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS model_notes (
            model_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL DEFAULT 'openrouter',
            is_favorite INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Migration for existing database
        try:
            cursor.execute("ALTER TABLE role_assignments ADD COLUMN provider TEXT DEFAULT 'openrouter'")
        except Exception:
            pass  # Column already exists
            
        try:
            cursor.execute("ALTER TABLE model_notes ADD COLUMN provider TEXT DEFAULT 'openrouter'")
        except Exception:
            pass
        
        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversations_created ON conversations(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tools_conversation ON tool_executions(conversation_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cost_model ON cost_tracking(model_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_provider ON api_keys(provider)")
        
        # Pre-populate default role assignments
        cursor.execute("SELECT COUNT(*) as cnt FROM role_assignments")
        row = cursor.fetchone()
        # Handle dict-like row or tuple-like row
        cnt = row["cnt"] if isinstance(row, dict) else row[0]
        if cnt == 0:
            default_roles = [
                ("orchestrator", "amd-cloud", "amd-cloud/llama-3-8b-instruct"),
                ("coding", "amd-cloud", "amd-cloud/qwen-2.5-7b-instruct"),
                ("reasoning", "amd-cloud", "amd-cloud/llama-3-8b-instruct"),
                ("summarizer", "amd-cloud", "amd-cloud/qwen-2.5-7b-instruct"),
                ("synthesizer", "amd-cloud", "amd-cloud/llama-3-8b-instruct"),
            ]
            cursor.executemany(
                "INSERT INTO role_assignments (role, provider, model_id) VALUES (?, ?, ?)",
                default_roles
            )

        self.connection.commit()
    
    def save_conversation(
        self,
        session_id: str,
        model_id: str,
        user_message: str,
        assistant_message: str,
        tokens_used: int = 0,
        cost: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Save a conversation to memory."""
        conversation_id = str(uuid.uuid4())
        self._execute(
            """
            INSERT INTO conversations 
            (id, session_id, model_id, user_message, assistant_message, tokens_used, cost, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                session_id,
                model_id,
                user_message,
                assistant_message,
                tokens_used,
                cost,
                json.dumps(metadata or {}),
            ),
        )
        return conversation_id
    
    def get_conversation_history(
        self,
        session_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get conversation history for a session."""
        cursor = self.connection.cursor()
        cursor.execute("""
        SELECT id, model_id, user_message, assistant_message, tokens_used, cost, metadata, created_at
        FROM conversations
        WHERE session_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """, (session_id, limit, offset))
        
        rows = cursor.fetchall()
        conversations = []
        
        for row in rows:
            conversations.append({
                "id": row["id"],
                "model_id": row["model_id"],
                "user_message": row["user_message"],
                "assistant_message": row["assistant_message"],
                "tokens_used": row["tokens_used"],
                "cost": row["cost"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "created_at": row["created_at"],
            })
        
        return conversations
    
    def save_tool_execution(
        self,
        conversation_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        result: str,
        success: bool = True,
        execution_time: float = 0.0,
    ) -> str:
        """Save tool execution record."""
        tool_id = str(uuid.uuid4())
        self._execute(
            """
            INSERT INTO tool_executions
            (id, conversation_id, tool_name, parameters, result, success, execution_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tool_id,
                conversation_id,
                tool_name,
                json.dumps(parameters),
                result,
                1 if success else 0,
                execution_time,
            ),
        )
        return tool_id
    
    def get_tool_executions(
        self,
        conversation_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get tool executions for a conversation."""
        cursor = self.connection.cursor()
        cursor.execute("""
        SELECT id, tool_name, parameters, result, success, execution_time, created_at
        FROM tool_executions
        WHERE conversation_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """, (conversation_id, limit))
        
        rows = cursor.fetchall()
        executions = []
        
        for row in rows:
            executions.append({
                "id": row["id"],
                "tool_name": row["tool_name"],
                "parameters": json.loads(row["parameters"]) if row["parameters"] else {},
                "result": row["result"],
                "success": bool(row["success"]),
                "execution_time": row["execution_time"],
                "created_at": row["created_at"],
            })
        
        return executions
    
    def save_document(
        self,
        content: str,
        source: str,
        embedding_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Save a document for RAG."""
        document_id = str(uuid.uuid4())
        self._execute(
            """
            INSERT INTO documents
            (id, content, source, embedding_id, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                document_id,
                content,
                source,
                embedding_id,
                json.dumps(metadata or {}),
            ),
        )
        return document_id
    
    def search_documents(
        self,
        query: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Search documents by content or source."""
        cursor = self.connection.cursor()
        
        if query:
            # Simple text search (can be enhanced with FTS)
            cursor.execute("""
            SELECT id, content, source, embedding_id, metadata, created_at
            FROM documents
            WHERE content LIKE ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """, (f"%{query}%", limit, offset))
        elif source:
            cursor.execute("""
            SELECT id, content, source, embedding_id, metadata, created_at
            FROM documents
            WHERE source = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """, (source, limit, offset))
        else:
            cursor.execute("""
            SELECT id, content, source, embedding_id, metadata, created_at
            FROM documents
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """, (limit, offset))
        
        rows = cursor.fetchall()
        documents = []
        
        for row in rows:
            documents.append({
                "id": row["id"],
                "content": row["content"],
                "source": row["source"],
                "embedding_id": row["embedding_id"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "created_at": row["created_at"],
            })
        
        return documents
    
    def track_cost(
        self,
        model_id: str,
        operation_type: str,
        tokens_input: int,
        tokens_output: int,
        cost: float,
        latency: float,
    ) -> str:
        """Track cost usage."""
        cost_id = str(uuid.uuid4())
        self._execute(
            """
            INSERT INTO cost_tracking
            (id, model_id, operation_type, tokens_input, tokens_output, cost, latency)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cost_id,
                model_id,
                operation_type,
                tokens_input,
                tokens_output,
                cost,
                latency,
            ),
        )
        return cost_id
    
    def get_cost_summary(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get cost summary for time period."""
        cursor = self.connection.cursor()
        
        query = "SELECT model_id, SUM(tokens_input) as total_input, SUM(tokens_output) as total_output, SUM(cost) as total_cost FROM cost_tracking"
        conditions = []
        params = []
        
        if start_date:
            conditions.append("created_at >= ?")
            params.append(start_date)
        
        if end_date:
            conditions.append("created_at <= ?")
            params.append(end_date)
        
        if model_id:
            conditions.append("model_id = ?")
            params.append(model_id)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " GROUP BY model_id"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        summary = {
            "total_cost": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "by_model": {},
        }
        
        for row in rows:
            model = row["model_id"]
            summary["by_model"][model] = {
                "cost": row["total_cost"] or 0.0,
                "input_tokens": row["total_input"] or 0,
                "output_tokens": row["total_output"] or 0,
            }
            summary["total_cost"] += row["total_cost"] or 0.0
            summary["total_input_tokens"] += row["total_input"] or 0
            summary["total_output_tokens"] += row["total_output"] or 0
        
        return summary
    
    def get_recent_conversations(
        self,
        days: int = 7,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get recent conversations across all sessions."""
        cursor = self.connection.cursor()
        cursor.execute("""
        SELECT session_id, model_id, user_message, assistant_message, tokens_used, cost, created_at
        FROM conversations
        WHERE created_at >= datetime('now', ?)
        ORDER BY created_at DESC
        LIMIT ?
        """, (f"-{days} days", limit))
        
        rows = cursor.fetchall()
        conversations = []
        
        for row in rows:
            conversations.append({
                "session_id": row["session_id"],
                "model_id": row["model_id"],
                "user_message": row["user_message"][:100] + "..." if len(row["user_message"]) > 100 else row["user_message"],
                "assistant_message": row["assistant_message"][:100] + "..." if len(row["assistant_message"]) > 100 else row["assistant_message"],
                "tokens_used": row["tokens_used"],
                "cost": row["cost"],
                "created_at": row["created_at"],
            })
        
        return conversations
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old data to save space."""
        deleted_rows = 0
        
        # Delete old conversations
        cursor = self._execute("""
        DELETE FROM conversations
        WHERE created_at < datetime('now', ?)
        """, (f"-{days_to_keep} days",))
        deleted_rows += cursor.rowcount
        
        # Delete old tool executions
        cursor = self._execute("""
        DELETE FROM tool_executions
        WHERE created_at < datetime('now', ?)
        """, (f"-{days_to_keep} days",))
        deleted_rows += cursor.rowcount
        
        # Delete old cost tracking
        cursor = self._execute("""
        DELETE FROM cost_tracking
        WHERE created_at < datetime('now', ?)
        """, (f"-{days_to_keep} days",))
        deleted_rows += cursor.rowcount
        
        # Delete old messages
        cursor = self._execute("""
        DELETE FROM messages
        WHERE created_at < datetime('now', ?)
        """, (f"-{days_to_keep} days",))
        deleted_rows += cursor.rowcount
        
        return deleted_rows
    
    def save_message(
        self,
        session_id: str,
        role: str,
        content_raw: str,
        content_summary: Optional[str] = None,
        tags: Optional[List[str]] = None,
        model_id: Optional[str] = None,
        tokens_used: int = 0,
    ) -> str:
        """Save a chat message with optional summary and tags."""
        message_id = str(uuid.uuid4())
        self._execute(
            """
            INSERT INTO messages
            (id, session_id, role, content_raw, content_summary, tags_json, model_id, tokens_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                role,
                content_raw,
                content_summary,
                json.dumps(tags or []),
                model_id,
                tokens_used,
            ),
        )
        
        # Publish event for multi-process sync
        if redis_store.is_connected():
            redis_store.publish_event("memory:message_saved", {
                "message_id": message_id,
                "session_id": session_id,
                "role": role,
                "model_id": model_id
            })
            
        return message_id
    
    def update_message_summary(
        self,
        message_id: str,
        content_summary: str,
    ) -> None:
        """Update the summary for an existing message."""
        self._execute(
            """
            UPDATE messages
            SET content_summary = ?
            WHERE id = ?
            """,
            (content_summary, message_id),
        )
    
    def update_message_tags(
        self,
        message_id: str,
        tags: List[str],
    ) -> None:
        """Update tags for an existing message."""
        self._execute(
            """
            UPDATE messages
            SET tags_json = ?
            WHERE id = ?
            """,
            (json.dumps(tags), message_id),
        )
    
    def get_messages(
        self,
        session_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get messages for a session."""
        cursor = self.connection.cursor()
        cursor.execute("""
        SELECT * FROM (
            SELECT id, role, content_raw, content_summary, tags_json, model_id, tokens_used, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ) ORDER BY created_at ASC
        """, (session_id, limit, offset))
        
        rows = cursor.fetchall()
        messages = []
        
        for row in rows:
            messages.append({
                "id": row["id"],
                "role": row["role"],
                "content_raw": row["content_raw"],
                "content_summary": row["content_summary"],
                "tags": json.loads(row["tags_json"]) if row["tags_json"] else [],
                "model_id": row["model_id"],
                "tokens_used": row["tokens_used"],
                "created_at": row["created_at"],
            })
        
        return messages
    
    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Get all chat sessions with their first message as title."""
        cursor = self.connection.cursor()
        
        # We want to group by session_id and get the earliest user message as the title
        cursor.execute("""
        SELECT session_id, MIN(created_at) as created_at, content_raw as title
        FROM messages
        WHERE role = 'user'
        GROUP BY session_id
        ORDER BY created_at DESC
        """)
        
        rows = cursor.fetchall()
        sessions = []
        for row in rows:
            title = row["title"]
            if len(title) > 40:
                title = title[:37] + "..."
                
            sessions.append({
                "session_id": row["session_id"],
                "title": title,
                "created_at": row["created_at"]
            })
            
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete a chat session and all its messages."""
        try:
            # Delete from messages table
            self._execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            # Delete from conversations table just in case there's old format data
            self._execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
            return True
        except Exception as e:
            print(f"Error deleting session: {e}")
            return False

    def update_message_content(self, message_id: str, new_content: str) -> bool:
        """Update the raw content of a message."""
        try:
            self._execute("UPDATE messages SET content_raw = ? WHERE id = ?", (new_content, message_id))
            return True
        except Exception as e:
            print(f"Error updating message content: {e}")
            return False

    def get_all_memories_with_tags(self) -> List[Dict[str, Any]]:
        """Get all messages that have non-empty tags."""
        cursor = self.connection.cursor()
        cursor.execute("""
        SELECT id, session_id, role, content_raw, tags_json, created_at
        FROM messages
        WHERE tags_json IS NOT NULL AND tags_json != '[]'
        ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        
        memories = []
        for row in rows:
            memories.append({
                "id": row["id"],
                "session_id": row["session_id"],
                "role": row["role"],
                "content": row["content_raw"],
                "tags": json.loads(row["tags_json"]),
                "created_at": row["created_at"],
            })
        return memories
        """Get all chat sessions with their first message as title."""
        cursor = self.connection.cursor()
        
        # We want to group by session_id and get the earliest user message as the title
        cursor.execute("""
        SELECT session_id, MIN(created_at) as created_at, content_raw as title
        FROM messages
        WHERE role = 'user'
        GROUP BY session_id
        ORDER BY created_at DESC
        """)
        
        rows = cursor.fetchall()
        sessions = []
        for row in rows:
            title = row["title"]
            if len(title) > 40:
                title = title[:37] + "..."
                
            sessions.append({
                "session_id": row["session_id"],
                "title": title,
                "created_at": row["created_at"]
            })
            
        return sessions
    
    def get_messages_by_tags(
        self,
        tags: List[str],
        session_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get messages that match any of the given tags."""
        cursor = self.connection.cursor()
        
        # Build tag matching query
        tag_conditions = []
        params = []
        
        for tag in tags:
            tag_conditions.append("tags_json LIKE ?")
            params.append(f'%"{tag}"%')
        
        query = """
        SELECT id, session_id, role, content_raw, content_summary, tags_json, model_id, tokens_used, created_at
        FROM messages
        WHERE ("""
        query += " OR ".join(tag_conditions)
        query += ")"
        
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        messages = []
        for row in rows:
            messages.append({
                "id": row["id"],
                "session_id": row["session_id"],
                "role": row["role"],
                "content_raw": row["content_raw"],
                "content_summary": row["content_summary"],
                "tags": json.loads(row["tags_json"]) if row["tags_json"] else [],
                "model_id": row["model_id"],
                "tokens_used": row["tokens_used"],
                "created_at": row["created_at"],
            })
        
        return messages
    
    def get_recent_summaries(
        self,
        session_id: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get recent message summaries for context building."""
        cursor = self.connection.cursor()
        cursor.execute("""
        SELECT role, content_summary
        FROM messages
        WHERE session_id = ? AND content_summary IS NOT NULL
        ORDER BY created_at DESC
        LIMIT ?
        """, (session_id, limit))
        
        rows = cursor.fetchall()
        summaries = []
        
        for row in rows:
            summaries.append({
                "role": row["role"],
                "content_summary": row["content_summary"],
            })
        
        return summaries
    
    def save_user_memory(self, content: str, tags: List[str] = None) -> str:
        """Save an extracted factual memory."""
        memory_id = str(uuid.uuid4())
        self._execute(
            """
            INSERT INTO user_memories (id, content, tags_json)
            VALUES (?, ?, ?)
            """,
            (memory_id, content, json.dumps(tags or [])),
        )
        return memory_id

    def update_user_memory(self, memory_id: str, new_content: str) -> bool:
        """Update the content of a user memory."""
        try:
            self._execute("UPDATE user_memories SET content = ? WHERE id = ?", (new_content, memory_id))
            return True
        except Exception as e:
            print(f"Error updating user memory: {e}")
            return False

    def delete_user_memory(self, memory_id: str) -> bool:
        """Delete a user memory."""
        try:
            self._execute("DELETE FROM user_memories WHERE id = ?", (memory_id,))
            return True
        except Exception as e:
            print(f"Error deleting user memory: {e}")
            return False

    def get_all_user_memories(self) -> List[Dict[str, Any]]:
        """Get all user memories."""
        cursor = self.connection.cursor()
        cursor.execute("""
        SELECT id, content, tags_json, created_at
        FROM user_memories
        ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        
        memories = []
        for row in rows:
            memories.append({
                "id": row["id"],
                "content": row["content"],
                "tags": json.loads(row["tags_json"]) if row["tags_json"] else [],
                "created_at": row["created_at"],
            })
        return memories

    def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        cursor = self.connection.cursor()
        
        stats = {}
        
        # Count tables
        tables = ["conversations", "tool_executions", "documents", "cost_tracking", "messages"]
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
            stats[f"{table}_count"] = cursor.fetchone()["count"]
        
        # Database size
        cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
        stats["database_size_bytes"] = cursor.fetchone()["size"]
        
        # Most used model
        cursor.execute("""
        SELECT model_id, COUNT(*) as count
        FROM conversations
        GROUP BY model_id
        ORDER BY count DESC
        LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            stats["most_used_model"] = row["model_id"]
            stats["most_used_model_count"] = row["count"]
        
        return stats
    
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
    
    # -----------------------------------------------------------------
    # API Keys & Role Assignments CRUD
    # -----------------------------------------------------------------
    def save_api_key(self, provider: str, key_value: str, label: Optional[str] = None) -> str:
        """Save or update an API key for a provider."""
        key_id = str(uuid.uuid4())
        label = label or f"{provider.title()} API Key"
        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT INTO api_keys (id, provider, label, key_value, is_active, added_at)
            VALUES (?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(provider) DO UPDATE SET
                label = excluded.label,
                key_value = excluded.key_value,
                is_active = 1,
                added_at = CURRENT_TIMESTAMP
        """, (key_id, provider.lower(), label, key_value))
        self.connection.commit()
        return key_id

    def get_api_keys(self) -> List[Dict[str, Any]]:
        """Retrieve all registered API keys."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT id, provider, label, key_value, is_active, added_at FROM api_keys ORDER BY added_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_api_key_by_provider(self, provider: str) -> Optional[str]:
        """Get active API key string for a specific provider. Checks all known aliases."""
        cursor = self.connection.cursor()
        p = provider.lower().strip()
        # Build a set of aliases to check for this provider
        alias_groups = [
            {"mistral", "mistralai", "codestral"},
            {"google", "gemini"},
            {"anthropic", "claude"},
            {"openai"},
            {"groq"},
            {"openrouter"},
        ]
        aliases = {p}
        for group in alias_groups:
            if p in group:
                aliases = group
                break
        placeholders = ",".join("?" for _ in aliases)
        cursor.execute(
            f"SELECT key_value FROM api_keys WHERE provider IN ({placeholders}) AND is_active = 1 ORDER BY added_at DESC LIMIT 1",
            tuple(aliases)
        )
        row = cursor.fetchone()
        return row["key_value"] if row else None

    def delete_api_key(self, provider: str) -> bool:
        """Delete an API key by provider."""
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM api_keys WHERE provider = ?", (provider.lower(),))
        self.connection.commit()
        return cursor.rowcount > 0

    def save_role_assignment(self, role: str, provider: str, model_id: str) -> bool:
        """Save model & provider assignment for a specific role (e.g. reasoning, coding, orchestrator)."""
        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT INTO role_assignments (role, provider, model_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(role) DO UPDATE SET
                provider = excluded.provider,
                model_id = excluded.model_id,
                updated_at = CURRENT_TIMESTAMP
        """, (role.lower(), provider.lower(), model_id))
        self.connection.commit()
        # Sync with Redis if connected
        if redis_store.is_connected():
            redis_store.set_role_model(role.lower(), f"{provider.lower()}:{model_id}")
        return True

    def get_role_assignments(self) -> Dict[str, Dict[str, str]]:
        """Retrieve dictionary of all assigned models & providers per role."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT role, provider, model_id FROM role_assignments")
        rows = cursor.fetchall()
        res = {}
        for row in rows:
            keys = row.keys() if hasattr(row, 'keys') else []
            prov = row["provider"] if "provider" in keys and row["provider"] else "openrouter"
            res[row["role"]] = {"provider": prov, "model_id": row["model_id"]}
        return res

    def save_model_note(self, model_id: str, provider: str, is_favorite: int, notes: str) -> bool:
        """Save or update user note / favorite status for a model."""
        cursor = self.connection.cursor()
        cursor.execute("""
        INSERT INTO model_notes (model_id, provider, is_favorite, notes, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(model_id) DO UPDATE SET
            provider = excluded.provider,
            is_favorite = excluded.is_favorite,
            notes = excluded.notes,
            updated_at = CURRENT_TIMESTAMP
        """, (model_id, provider.lower(), 1 if is_favorite else 0, notes))
        self.connection.commit()
        return True

    def get_model_notes(self) -> Dict[str, Dict[str, Any]]:
        """Fetch all model notes & favorite states as a dictionary keyed by model_id."""
        cursor = self.connection.cursor()
        cursor.execute("SELECT model_id, provider, is_favorite, notes, updated_at FROM model_notes")
        rows = cursor.fetchall()
        res = {}
        for row in rows:
            res[row["model_id"]] = {
                "model_id": row["model_id"],
                "provider": row["provider"],
                "is_favorite": bool(row["is_favorite"]),
                "notes": row["notes"] or "",
                "updated_at": row["updated_at"]
            }
        return res

    def get_model_usage_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get total call counts and last used timestamp for all models."""
        cursor = self.connection.cursor()
        cursor.execute("""
        SELECT model_id, COUNT(*) as call_count, MAX(created_at) as last_used
        FROM messages
        WHERE model_id IS NOT NULL AND model_id != ''
        GROUP BY model_id
        """)
        rows = cursor.fetchall()
        stats = {}
        for row in rows:
            m_id = row["model_id"]
            stats[m_id] = {
                "call_count": row["call_count"],
                "last_used": row["last_used"]
            }
        return stats

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Helper class for session management
class SessionManager:
    """Manages conversation sessions."""
    
    def __init__(self, memory_store: SQLiteMemoryStore):
        self.memory_store = memory_store
        self.current_session_id = str(uuid.uuid4())
        self.session_start = datetime.now()
    
    def new_session(self) -> str:
        """Start a new session."""
        self.current_session_id = str(uuid.uuid4())
        self.session_start = datetime.now()
        return self.current_session_id
    
    def get_session_context(
        self,
        max_messages: int = 10,
        max_tokens: int = 2000,
    ) -> List['Message']:
        """Get conversation context for current session."""
        from src.models.provider_router import Message
        
        conversations = self.memory_store.get_conversation_history(
            self.current_session_id,
            limit=max_messages * 2,  # Get more to filter by tokens
        )
        
        messages = []
        total_tokens = 0
        
        # Add conversations in chronological order (oldest first)
        for conv in reversed(conversations):
            # Estimate tokens (simplified)
            user_tokens = len(conv["user_message"].split())
            assistant_tokens = len(conv["assistant_message"].split())
            message_tokens = user_tokens + assistant_tokens + 20  # Add overhead
            
            if total_tokens + message_tokens > max_tokens:
                break
            
            messages.append(Message(role="user", content=conv["user_message"]))
            messages.append(Message(role="assistant", content=conv["assistant_message"]))
            total_tokens += message_tokens
        
        return messages
    
    def save_conversation(
        self,
        model_id: str,
        user_message: str,
        assistant_message: str,
        tokens_used: int = 0,
        cost: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Save conversation to current session."""
        return self.memory_store.save_conversation(
            session_id=self.current_session_id,
            model_id=model_id,
            user_message=user_message,
            assistant_message=assistant_message,
            tokens_used=tokens_used,
            cost=cost,
            metadata=metadata,
        )
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics for current session."""
        conversations = self.memory_store.get_conversation_history(
            self.current_session_id,
            limit=1000,
        )
        
        total_tokens = sum(c["tokens_used"] for c in conversations)
        total_cost = sum(c["cost"] for c in conversations)
        model_counts = {}
        
        for conv in conversations:
            model = conv["model_id"]
            model_counts[model] = model_counts.get(model, 0) + 1
        
        return {
            "session_id": self.current_session_id,
            "start_time": self.session_start.isoformat(),
            "conversation_count": len(conversations),
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "model_usage": model_counts,
        }