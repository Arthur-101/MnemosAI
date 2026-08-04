import { Layout, List, Input, Button, message as antdMessage, Modal, Popconfirm, Typography, Upload, Select, Collapse, Tooltip, Card, Tabs, Tag, Table } from 'antd';
import { open } from '@tauri-apps/plugin-dialog';
import { 
  DeleteOutlined, 
  SettingOutlined, 
  EditOutlined, 
  SaveOutlined, 
  PlusOutlined, 
  InboxOutlined, 
  CodeOutlined, 
  CopyOutlined, 
  CheckOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  RobotOutlined,
  PoweroffOutlined,
  SendOutlined,
  ClearOutlined,
  PaperClipOutlined,
  EyeOutlined,
  FileTextOutlined,
  BulbOutlined,
  KeyOutlined,
  ExperimentOutlined,
  StarOutlined,
  StarFilled,
  SearchOutlined,
  TableOutlined,
  ApiOutlined,
  SyncOutlined,
  DashboardOutlined
} from '@ant-design/icons';
const { Dragger } = Upload;
import { useState, useEffect, useRef } from 'react';
import { invoke, convertFileSrc } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkEmoji from 'remark-emoji';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

const { Header, Content, Footer, Sider } = Layout;

export default function ChatPanel() {
  const [messages, setMessages] = useState<Array<{role: string; content: string; model_id?: string; attachments?: Array<{name: string; path: string; chunkCount?: number}>}>>([]);
  const [sessions, setSessions] = useState<Array<{session_id: string; title: string; created_at: string}>>([]);
  const [input, setInput] = useState('');
  const [sessionId, setSessionId] = useState<string>('');
  const [backendRunning, setBackendRunning] = useState(false);
  const [redisConnected, setRedisConnected] = useState<boolean | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>('auto');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [memories, setMemories] = useState<Array<{id: string, role: string, content: string, tags: string[], created_at: string}>>([]);
  const [backendLogs, setBackendLogs] = useState<string[]>([]);

  // Detect Redis connectivity from backend stderr log stream
  const detectRedisStatus = (logLine: string) => {
    if (logLine.includes('Connected to Redis memory store')) {
      setRedisConnected(true);
    } else if (logLine.includes('Redis connection unavailable') || logLine.includes('Redis auto-start completed, but ping failed')) {
      setRedisConnected(false);
    }
  };
  const [editingMemoryId, setEditingMemoryId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState('');
  const [newMemoryContent, setNewMemoryContent] = useState('');
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  // Role Models & API Keys State
  interface RoleConfig {
    provider: string;
    model_id: string;
  }
  const [roleModels, setRoleModels] = useState<Record<string, RoleConfig>>({
    orchestrator: { provider: 'amd-cloud', model_id: 'amd-cloud/llama-3-8b-instruct' },
    coding: { provider: 'amd-cloud', model_id: 'amd-cloud/qwen-2.5-7b-instruct' },
    reasoning: { provider: 'amd-cloud', model_id: 'amd-cloud/llama-3-8b-instruct' },
    multimodal: { provider: 'amd-cloud', model_id: 'amd-cloud/qwen-2.5-7b-instruct' },
    synthesizer: { provider: 'amd-cloud', model_id: 'amd-cloud/llama-3-8b-instruct' },
    summary: { provider: 'amd-cloud', model_id: 'amd-cloud/qwen-2.5-7b-instruct' }
  });
  const [providerCatalog, setProviderCatalog] = useState<Record<string, Array<{id: string; name: string; cost_label: string; is_active: boolean}>>>({});


  // AMD Cloud & GPU Hardware Telemetry Dials
  const [amdCloudUrl, setAmdCloudUrl] = useState<string>('http://127.0.0.1:8000/v1');
  const [amdCloudKey, setAmdCloudKey] = useState<string>('');
  const [gpuMetrics, setGpuMetrics] = useState<any>({
    gpu_name: 'AMD Radeon Pro V620 (Shared Template)',
    utilization: 0,
    temperature: 0,
    vram_used: 0,
    vram_total: 16384,
    tps: 0,
    driver_version: 'ROCm 6.1',
    status: 'Connecting...'
  });



  // MCP Settings State Hooks
  const [mcpServers, setMcpServers] = useState<any[]>([]);
  const [isMcpModalOpen, setIsMcpModalOpen] = useState(false);
  const [editingMcp, setEditingMcp] = useState<any | null>(null);
  const [selectedLogsServer, setSelectedLogsServer] = useState<string | null>(null);
  const [serverLogs, setServerLogs] = useState<string[]>([]);
  const [logsDrawerOpen, setLogsDrawerOpen] = useState(false);
  
  // MCP Form Hooks
  const [mcpName, setMcpName] = useState('');
  const [mcpCommand, setMcpCommand] = useState('');
  const [mcpArgsStr, setMcpArgsStr] = useState('');
  const [mcpEnvStr, setMcpEnvStr] = useState('');
  const [mcpEnabled, setMcpEnabled] = useState(true);

  const loadProviderModels = async (provider: string) => {
    try {
      const res: any = await invoke('get_available_models', { provider });
      if (Array.isArray(res)) {
        setProviderCatalog(prev => ({ ...prev, [provider]: res }));
      }
    } catch (err) {
      console.error(`Failed to fetch models for ${provider}:`, err);
    }
  };

  const loadRoleModels = async () => {
    try {
      const res: any = await invoke('get_role_models');
      if (res?.role_models) {
        setRoleModels(res.role_models);
      } else if (res) {
        setRoleModels(res);
      }
    } catch (err) {
      console.error('Failed to load role models:', err);
    }
    // Pre-fetch catalogs for all supported providers
    ['amd-cloud', 'local'].forEach(p => loadProviderModels(p));
  };



  const getCleanModelId = (rawModelId: string, provider: string) => {
    if (!rawModelId) return '';
    let m = rawModelId.trim();
    const pPrefix = `${provider.toLowerCase()}:`;
    if (m.toLowerCase().startsWith(pPrefix)) {
      m = m.substring(pPrefix.length);
    }
    if (provider.toLowerCase() !== 'openrouter' && m.toLowerCase().startsWith(`${provider.toLowerCase()}/`)) {
      m = m.substring(provider.length + 1);
    }
    return m;
  };

  const handleProviderChange = async (role: string, newProv: string) => {
    let catalog = providerCatalog[newProv];
    if (!catalog || catalog.length === 0) {
      try {
        const res: any = await invoke('get_available_models', { provider: newProv });
        if (Array.isArray(res)) {
          catalog = res;
          setProviderCatalog(prev => ({ ...prev, [newProv]: res }));
        }
      } catch (e) {
        console.error('Error fetching provider models:', e);
      }
    }
    let targetModels = catalog || [];
    if (role === 'stt') {
      targetModels = targetModels.filter(m => 
        m.id.toLowerCase().includes('whisper') ||
        m.id.toLowerCase().includes('stt') ||
        m.id.toLowerCase().includes('audio') ||
        m.id.toLowerCase().includes('transcribe') ||
        m.name.toLowerCase().includes('speech-to-text') ||
        m.name.toLowerCase().includes('stt')
      );
    } else if (role === 'tts') {
      targetModels = targetModels.filter(m => 
        m.id.toLowerCase().includes('tts') ||
        m.id.toLowerCase().includes('voice') ||
        m.id.toLowerCase().includes('speech') ||
        m.name.toLowerCase().includes('text-to-speech') ||
        m.name.toLowerCase().includes('tts')
      );
    }
    const firstActive = targetModels.find(m => m.is_active)?.id || '';
    handleUpdateRoleModel(role, newProv, firstActive);
  };

  const handleUpdateRoleModel = async (role: string, provider: string, modelId: string) => {
    try {
      await invoke('update_role_model', { role, provider, modelId, model_id: modelId });
      setRoleModels(prev => ({ ...prev, [role]: { provider, model_id: modelId } }));
      antdMessage.success(`Model for [${role}] updated to [${provider.toUpperCase()}] ${modelId || 'None'} (Hot-reloaded!)`);
    } catch (err) {
      antdMessage.error(`Failed to update role model: ${err}`);
    }
  };



  // Lightbox Preview & Image helper
  const [previewImage, setPreviewImage] = useState<{ url: string; title: string; path?: string } | null>(null);

  const isImageFile = (fileNameOrPath: string) => {
    const ext = fileNameOrPath.split('.').pop()?.toLowerCase() || '';
    return ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif', 'svg'].includes(ext);
  };

  const getSafeImageSrc = (att: { dataUrl?: string; path?: string }) => {
    if (att.dataUrl) return att.dataUrl;
    if (att.path) {
      const normalized = att.path.replace(/\\/g, '/');
      return convertFileSrc(normalized);
    }
    return '';
  };

  const handleImageError = (e: React.SyntheticEvent<HTMLImageElement, Event>, filePath?: string) => {
    const target = e.currentTarget;
    if (filePath && !target.dataset.retried) {
      target.dataset.retried = 'true';
      invoke<any>('index_document', { filePath }).then(res => {
        if (res && res.data_url) {
          target.src = res.data_url;
          setPreviewImage(prev => (prev && prev.path === filePath) ? { ...prev, url: res.data_url } : prev);
        }
      }).catch(err => {
        console.warn('Fallback image fetch error:', err);
      });
    }
  };

  // File Attachments & Vector RAG State
  const [attachedFiles, setAttachedFiles] = useState<Array<{ name: string; path: string; chunkCount?: number; dataUrl?: string }>>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const processAndIndexFile = async (filePath: string) => {
    const fileName = filePath.split(/[/\\]/).pop() || filePath;
    antdMessage.loading(`Indexing ${fileName} into ChromaDB vector memory...`, 0);
    try {
      const result = await invoke<any>('index_document', { filePath, file_path: filePath });
      antdMessage.destroy();
      if (result.status === 'success') {
        const newFile = {
          name: fileName,
          path: filePath,
          chunkCount: result.chunk_count,
          dataUrl: result.data_url
        };
        setAttachedFiles(prev => [...prev.filter(f => f.path !== filePath), newFile]);
        antdMessage.success(`Indexed "${fileName}" into Vector DB (${result.chunk_count} chunks, ${result.character_count} chars)!`);
      } else {
        antdMessage.error(`Failed to index file: ${result.error || 'Unknown error'}`);
      }
    } catch (error) {
      antdMessage.destroy();
      antdMessage.error(`Error indexing file: ${error}`);
    }
  };

  const handleFileAttach = async () => {
    try {
      const selected = await open({
        multiple: true,
        filters: [
          {
            name: 'All Supported Files',
            extensions: ['txt', 'py', 'pdf', 'md', 'json', 'csv', 'js', 'ts', 'tsx', 'html', 'css', 'rs', 'log', 'png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif', 'mp3', 'mp4', 'm4a', 'wav', 'aac', 'flac', 'avi', 'mov', 'mkv', 'webm', 'yaml', 'yml']
          },
          {
            name: 'Images',
            extensions: ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif']
          },
          {
            name: 'Audio & Video',
            extensions: ['mp3', 'mp4', 'm4a', 'wav', 'aac', 'flac', 'avi', 'mov', 'mkv', 'webm', 'ogg']
          },
          {
            name: 'All Files (*.*)',
            extensions: ['*']
          }
        ]
      });

      if (!selected) return;
      const paths = Array.isArray(selected) ? selected : [selected];

      for (const filePath of paths) {
        if (typeof filePath === 'string') {
          await processAndIndexFile(filePath);
        }
      }
    } catch (err) {
      console.warn('Tauri dialog fallback:', err);
      fileInputRef.current?.click();
    }
  };

  const handleHTMLFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const filePath = (file as any).path || file.name;
      await processAndIndexFile(filePath);
    }
  };

  // Collapsible panels state
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };
  
  const scrollLogsToBottom = () => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const sendMessage = async () => {
    if ((!input.trim() && attachedFiles.length === 0) || isLoading) return;
    
    const userMessage = input.trim();
    setInput('');

    // Append attached files context to the message payload if present
    const currentAttachments = [...attachedFiles];
    let payloadMessage = userMessage;

    if (currentAttachments.length > 0) {
      const fileNotes = currentAttachments.map(f => `[Attached File: ${f.name} | Path: ${f.path}]`).join('\n');
      if (!userMessage) {
        payloadMessage = `Attached files for context:\n${fileNotes}\n\nPlease analyze the attached file(s).`;
      } else {
        payloadMessage = `${userMessage}\n\n${fileNotes}`;
      }
    }

    setMessages(prev => [...prev, {
      role: 'user',
      content: userMessage || (currentAttachments.length > 0 ? `[Attached ${currentAttachments.length} file(s)]` : ''),
      attachments: currentAttachments
    }]);
    setIsLoading(true);
    setAttachedFiles([]);

    try {
      const response = await invoke<any>('send_chat_message', {
        sessionId: sessionId || 'default',
        session_id: sessionId || 'default',
        message: payloadMessage,
        model: selectedModel === 'auto' ? null : selectedModel,
        model_override: selectedModel === 'auto' ? null : selectedModel
      });

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: response.content || response.reply || response.response || (typeof response === 'string' ? response : ''),
        model_id: response.model || response.model_id || response.model_used
      }]);
      
      await loadSessions();
    } catch (error) {
      antdMessage.error(`Error: ${error}`);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    scrollLogsToBottom();
  }, [backendLogs]);

  const handleCreateSession = async () => {
    try {
      const newSessionId = await invoke<string>('new_session');
      setSessionId(newSessionId);
      setMessages([]);
      await loadSessions();
      antdMessage.success('New chat session started');
    } catch (error) {
      antdMessage.error(`Failed to start new session: ${error}`);
    }
  };

  // Initialize on component mount
  useEffect(() => {
    initializeBackend();
    
    let unlistenLog: (() => void) | undefined;
    let unlistenNewChat: (() => void) | undefined;
    let unlistenToggleEngine: (() => void) | undefined;
    let isMounted = true;

    listen<string>('backend-log', (event) => {
      if (event.payload.startsWith('SUB_AGENT_MSG:')) {
        try {
          const jsonStr = event.payload.replace('SUB_AGENT_MSG:', '');
          const data = JSON.parse(jsonStr);
          const roleUpper = data.role ? data.role.toUpperCase() : '';
          const modelUsed = data.model || data.model_id || '';
          const displayModel = roleUpper && modelUsed && !modelUsed.startsWith(roleUpper)
            ? `${roleUpper} (${modelUsed})`
            : modelUsed || roleUpper || 'sub-agent';

          setMessages(prev => [...prev, {
            role: 'sub_agent',
            content: data.content || data.content_raw || data.reply || data.response || jsonStr || '',
            model_id: displayModel
          }]);
        } catch (e) {
          console.error("Failed to parse sub agent message", e);
        }
        return;
      }
      
      if (!isMounted) return;
      // Detect Redis status from log stream
      detectRedisStatus(event.payload);
      setBackendLogs(prev => {
        if (prev.length > 0 && prev[prev.length - 1] === event.payload) {
          return prev; // Prevent duplicate consecutive logs
        }
        const newLogs = [...prev, event.payload];
        if (newLogs.length > 200) return newLogs.slice(newLogs.length - 200);
        return newLogs;
      });
    }).then(fn => {
      if (!isMounted) {
        fn();
      } else {
        unlistenLog = fn;
      }
    }).catch(err => console.error("Failed to setup log listener", err));
    
    listen('trigger-new-chat', () => {
      if (!isMounted) return;
      handleCreateSession();
    }).then(fn => {
      if (!isMounted) fn();
      else unlistenNewChat = fn;
    });

    listen('trigger-toggle-engine', async () => {
      if (!isMounted) return;
      try {
        const isRunning = await invoke<boolean>('backend_status');
        if (isRunning) {
          await invoke('stop_backend');
          setBackendRunning(false);
          antdMessage.info('AI Engine stopped via System Tray');
        } else {
          await invoke('start_backend');
          setBackendRunning(true);
          antdMessage.success('AI Engine started via System Tray');
        }
      } catch (err) {
        console.error('Failed to toggle backend from tray:', err);
      }
    }).then(fn => {
      if (!isMounted) fn();
      else unlistenToggleEngine = fn;
    });

    return () => {
      isMounted = false;
      if (unlistenLog) unlistenLog();
      if (unlistenNewChat) unlistenNewChat();
      if (unlistenToggleEngine) unlistenToggleEngine();
    };
  }, []);

  // Reload history when sessionId changes
  useEffect(() => {
    if (sessionId) {
      loadChatHistory();
    }
  }, [sessionId]);

  const initializeBackend = async () => {
    try {
      const isRunning = await invoke<boolean>('backend_status');
      setBackendRunning(isRunning);
      
      if (!isRunning) {
        antdMessage.info('Starting AI backend...');
        await invoke('start_backend');
        setBackendRunning(true);
        antdMessage.success('AI backend started');
      }
      
      // Fetch detailed health status to retrieve current Redis status
      try {
        const health = await invoke<any>('get_backend_health');
        if (health && health.redis_connected !== undefined) {
          setRedisConnected(health.redis_connected);
        }
      } catch (err) {
        console.warn('Failed to fetch detailed backend health status:', err);
      }
      
      await loadSessions();
      await loadChatHistory();
    } catch (error) {
      console.error('Failed to initialize backend:', error);
      antdMessage.error('Failed to start AI backend. Please check Python installation and dependencies.');
    }
  };

  const loadSessions = async () => {
    try {
      const sessionsList = await invoke<any[]>('get_all_sessions');
      setSessions(sessionsList);
      
      if (!sessionId && sessionsList.length > 0) {
        setSessionId(sessionsList[0].session_id);
      }
    } catch (error) {
      console.error('Failed to load sessions:', error);
    }
  };

  const loadChatHistory = async () => {
    if (!sessionId) return;
    try {
      const history = await invoke<any[]>('get_chat_history', { sessionId, limit: 100 });
      setMessages(history.map(item => {
        const rawContent = item.content || item.content_raw || item.reply || item.response || '';
        let cleanContent = rawContent;
        const attachments: Array<{ name: string; path: string }> = [];

        if (item.role === 'user' && rawContent.includes('[Attached File:')) {
          const fileRegex = /\[Attached File: ([^\|]+)\| Path: ([^\]]+)\]/g;
          let match;
          while ((match = fileRegex.exec(rawContent)) !== null) {
            attachments.push({ name: match[1].trim(), path: match[2].trim() });
          }
          cleanContent = rawContent.replace(/\n\n\[Attached File: [^\]]+\]/g, '').replace(/\[Attached File: [^\]]+\]/g, '').trim();
        }

        return {
          role: item.role,
          content: cleanContent || rawContent,
          model_id: item.model_id,
          attachments: attachments.length > 0 ? attachments : undefined
        };
      }));
    } catch (error) {
      console.error('Failed to load chat history:', error);
      antdMessage.error(`Failed to load history: ${error}`);
    }
  };



  const handleDeleteSession = async (sId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await invoke('delete_session', { sessionId: sId });
      antdMessage.success('Chat deleted');
      if (sId === sessionId) {
        setSessionId('');
        setMessages([]);
      }
      await loadSessions();
    } catch (error) {
      antdMessage.error(`Failed to delete session: ${error}`);
    }
  };

  const loadMemories = async () => {
    try {
      const res = await invoke<any[]>('get_all_memories');
      setMemories(res || []);
    } catch (error) {
      console.error('Failed to load memories:', error);
    }
  };

  const handleSaveAmdConfig = async () => {
    try {
      await invoke('update_amd_cloud_config', { endpointUrl: amdCloudUrl, apiKey: amdCloudKey });
      antdMessage.success('AMD Radeon Cloud configuration updated successfully!');
    } catch (error) {
      antdMessage.error(`Failed to update AMD configuration: ${error}`);
    }
  };

  useEffect(() => {
    let interval: any;
    if (isSettingsOpen) {
      loadRoleModels();
      loadMemories();
      loadMcpServers();

      // Fetch AMD Cloud configuration
      invoke('get_amd_cloud_config')
        .then((res: any) => {
          if (res) {
            setAmdCloudUrl(res.endpoint_url || 'http://127.0.0.1:8000/v1');
            setAmdCloudKey(res.api_key || '');
          }
        })
        .catch(err => console.error('Failed to load AMD Cloud config:', err));

      // Poll GPU metrics
      const pollGpuMetrics = () => {
        invoke('get_amd_gpu_metrics')
          .then((res: any) => {
            if (res) {
              setGpuMetrics(res);
            }
          })
          .catch(err => console.error('Failed to fetch GPU metrics:', err));
      };

      pollGpuMetrics();
      interval = setInterval(pollGpuMetrics, 1500);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isSettingsOpen]);

  const handleAddMemory = async () => {
    if (!newMemoryContent.trim()) {
      antdMessage.warning('Please enter a memory text to save');
      return;
    }
    try {
      await invoke('add_memory', { content: newMemoryContent.trim() });
      antdMessage.success('Memory saved globally!');
      setNewMemoryContent('');
      await loadMemories();
    } catch (error) {
      antdMessage.error(`Failed to save memory: ${error}`);
    }
  };

  const handleUpdateMemory = async (id: string) => {
    try {
      await invoke('update_memory', { messageId: id, content: editingContent });
      antdMessage.success('Memory updated');
      setEditingMemoryId(null);
      await loadMemories();
    } catch (error) {
      antdMessage.error(`Failed to update memory: ${error}`);
    }
  };

  const handleDeleteMemory = async (id: string) => {
    try {
      await invoke('delete_memory', { memoryId: id });
      antdMessage.success('Memory deleted');
      await loadMemories();
    } catch (error) {
      antdMessage.error(`Failed to delete memory: ${error}`);
    }
  };

  const loadMcpServers = async () => {
    try {
      const res = await invoke<any[]>('get_mcp_servers');
      setMcpServers(res || []);
    } catch (error) {
      console.error('Failed to load MCP servers:', error);
    }
  };

  const handleAddMcpServer = async () => {
    if (!mcpName.trim() || !mcpCommand.trim()) {
      antdMessage.warning('Please enter a server name and command');
      return;
    }
    
    let parsedArgs: string[] = [];
    if (mcpArgsStr.trim()) {
      try {
        parsedArgs = JSON.parse(mcpArgsStr.trim());
        if (!Array.isArray(parsedArgs)) {
          antdMessage.error('Arguments must be a valid JSON array of strings, e.g. ["-y", "pkg"]');
          return;
        }
      } catch (e) {
        antdMessage.error('Invalid arguments JSON array formatting, e.g. ["-y", "pkg"]');
        return;
      }
    }

    let parsedEnv: Record<string, string> = {};
    if (mcpEnvStr.trim()) {
      try {
        parsedEnv = JSON.parse(mcpEnvStr.trim());
        if (typeof parsedEnv !== 'object' || Array.isArray(parsedEnv)) {
          antdMessage.error('Env variables must be a valid JSON object');
          return;
        }
      } catch (e) {
        antdMessage.error('Invalid environment variables JSON object formatting, e.g. {"KEY": "VALUE"}');
        return;
      }
    }

    try {
      const success = await invoke<boolean>('add_mcp_server', {
        name: mcpName.trim(),
        command: mcpCommand.trim(),
        args: parsedArgs,
        env: parsedEnv,
        enabled: mcpEnabled
      });
      if (success) {
        antdMessage.success('MCP server configuration saved!');
        setIsMcpModalOpen(false);
        setEditingMcp(null);
        resetMcpForm();
        loadMcpServers();
      } else {
        antdMessage.error('Failed to save MCP server configuration');
      }
    } catch (error) {
      antdMessage.error(`Error saving MCP server: ${error}`);
    }
  };

  const handleDeleteMcpServer = async (name: string) => {
    try {
      const success = await invoke<boolean>('delete_mcp_server', { name });
      if (success) {
        antdMessage.success(`Deleted MCP server: ${name}`);
        loadMcpServers();
      } else {
        antdMessage.error(`Failed to delete MCP server: ${name}`);
      }
    } catch (error) {
      antdMessage.error(`Error deleting MCP server: ${error}`);
    }
  };

  const loadMcpLogs = async (name: string) => {
    try {
      const logs = await invoke<string[]>('get_mcp_logs', { name });
      setServerLogs(logs || []);
    } catch (error) {
      console.error(`Failed to fetch logs for ${name}:`, error);
    }
  };

  const resetMcpForm = () => {
    setMcpName('');
    setMcpCommand('');
    setMcpArgsStr('');
    setMcpEnvStr('');
    setMcpEnabled(true);
  };

  return (
    <Layout style={{ height: '100vh', width: '100vw', background: '#0b0f19', color: '#f1f5f9' }}>
      {/* Settings Modal */}
      <Modal
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <SettingOutlined style={{ color: '#38bdf8' }} />
            <span style={{ color: '#f8fafc', fontWeight: 600 }}>AgenticAI Settings & System Manager</span>
          </div>
        }
        open={isSettingsOpen}
        onCancel={() => setIsSettingsOpen(false)}
        footer={null}
        width={920}
        styles={{
          mask: { backdropFilter: 'blur(8px)', background: 'rgba(0, 0, 0, 0.7)' },
          body: { background: '#0f172a', color: '#f8fafc', padding: '12px 24px 24px 24px' },
          header: { background: 'transparent', borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }
        }}
      >
        <Tabs
          defaultActiveKey="amd_cloud"
          items={[
            {
              key: 'amd_cloud',
              label: <span><DashboardOutlined style={{ marginRight: '6px' }} />AMD Radeon Cloud & Telemetry</span>,
              children: (
                <div style={{ marginTop: '8px' }}>
                  <Typography.Paragraph type="secondary" style={{ marginBottom: '16px', fontSize: '13px' }}>
                    Configure the AMD Radeon Cloud remote container endpoints or local vLLM/Ollama servers. Telemetry dials track hardware performance in real-time.
                  </Typography.Paragraph>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
                    <Card size="small" title="⚡ Connection Settings" style={{ background: 'rgba(255, 255, 255, 0.03)', borderColor: 'rgba(255, 255, 255, 0.1)' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                        <div>
                          <span style={{ fontSize: '12px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>AMD Radeon Cloud / local API Endpoint URL</span>
                          <Input
                            placeholder="e.g. http://127.0.0.1:8000/v1"
                            value={amdCloudUrl}
                            onChange={e => setAmdCloudUrl(e.target.value)}
                            style={{ background: '#0f172a', color: '#f8fafc', borderColor: '#334155' }}
                          />
                        </div>
                        <div>
                          <span style={{ fontSize: '12px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>Access Token / Container Key</span>
                          <Input.Password
                            placeholder="Optional authentication header key"
                            value={amdCloudKey}
                            onChange={e => setAmdCloudKey(e.target.value)}
                            style={{ background: '#0f172a', color: '#f8fafc', borderColor: '#334155' }}
                          />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
                          <Button
                            type="primary"
                            icon={<SaveOutlined />}
                            onClick={handleSaveAmdConfig}
                            style={{ background: '#0284c7', borderColor: '#0284c7' }}
                          >
                            Save Endpoint
                          </Button>
                        </div>
                      </div>
                    </Card>

                    <Card size="small" title="📊 Live GPU Hardware Dials" style={{ background: 'rgba(255, 255, 255, 0.03)', borderColor: 'rgba(255, 255, 255, 0.1)' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px' }}>
                        <div>
                          <span style={{ color: '#64748b' }}>Active Device:</span>{' '}
                          <Tag color="cyan" style={{ marginLeft: '4px' }}>{gpuMetrics.gpu_name}</Tag>
                        </div>
                        <div>
                          <span style={{ color: '#64748b' }}>Status:</span>{' '}
                          <Tag color={gpuMetrics.status?.includes('Active') ? 'success' : 'warning'} style={{ marginLeft: '4px' }}>
                            {gpuMetrics.status}
                          </Tag>
                        </div>
                        
                        <div style={{ marginTop: '4px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', fontSize: '12px' }}>
                            <span style={{ color: '#cbd5e1' }}>GPU Core Utilization</span>
                            <span style={{ color: '#38bdf8', fontWeight: 600 }}>{gpuMetrics.utilization}%</span>
                          </div>
                          <div style={{ width: '100%', height: '8px', background: '#334155', borderRadius: '4px', overflow: 'hidden' }}>
                            <div style={{ width: `${gpuMetrics.utilization}%`, height: '100%', background: 'linear-gradient(90deg, #38bdf8, #0284c7)', transition: 'width 0.4s ease' }}></div>
                          </div>
                        </div>

                        <div style={{ marginTop: '4px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', fontSize: '12px' }}>
                            <span style={{ color: '#cbd5e1' }}>Dedicated VRAM Allocation</span>
                            <span style={{ color: '#38bdf8', fontWeight: 600 }}>{Math.round(gpuMetrics.vram_used)} MB / {Math.round(gpuMetrics.vram_total)} MB</span>
                          </div>
                          <div style={{ width: '100%', height: '8px', background: '#334155', borderRadius: '4px', overflow: 'hidden' }}>
                            <div style={{ width: `${(gpuMetrics.vram_used / gpuMetrics.vram_total) * 100}%`, height: '100%', background: 'linear-gradient(90deg, #a855f7, #6366f1)', transition: 'width 0.4s ease' }}></div>
                          </div>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '6px', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '8px', fontSize: '12px' }}>
                          <div>
                            <span style={{ color: '#64748b' }}>Core Temp:</span>{' '}
                            <span style={{ color: gpuMetrics.temperature > 70 ? '#f43f5e' : '#22c55e', fontWeight: 600 }}>{gpuMetrics.temperature}°C</span>
                          </div>
                          <div>
                            <span style={{ color: '#64748b' }}>Generation Speed:</span>{' '}
                            <span style={{ color: '#eab308', fontWeight: 600 }}>{gpuMetrics.tps} TPS</span>
                          </div>
                        </div>
                      </div>
                    </Card>
                  </div>
                </div>
              )
            },
            {
              key: 'models',
              label: <span><CodeOutlined style={{ marginRight: '6px' }} />Model Roles Settings</span>,
              children: (
                <div style={{ marginTop: '8px' }}>
                  <Typography.Paragraph type="secondary" style={{ marginBottom: '16px', fontSize: '13px' }}>
                    Configure the model names for each specialized agent role running locally or in your AMD GPU container. You can type any custom model ID or select from templates.
                  </Typography.Paragraph>

                  {/* Role Model Configuration Cards */}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '20px' }}>
                    {[
                      { role: 'orchestrator', label: '⚡ Main Orchestrator', desc: 'Default task classifier & central coordinator' },
                      { role: 'coding', label: '🤖 Coding Sub-Agent', desc: 'Code generator, debugger, and execution specialist' },
                      { role: 'reasoning', label: '💡 Reasoning Sub-Agent', desc: 'Architectural planning, deep logic, and peer-reviewer' },
                      { role: 'multimodal', label: '👁️ Multimodal Specialist', desc: 'Handles vision, audio, and media attachments' },
                      { role: 'synthesizer', label: '🧩 Consensus Synthesizer', desc: 'Merges parallel team contributions into master output' },
                      { role: 'summary', label: '🧠 Background Summarizer & Memory', desc: 'Short-term context compression and factual extraction' }
                    ].map(r => {
                      const roleConfig = roleModels[r.role] || { provider: 'amd-cloud', model_id: '' };
                      const currentProvider = roleConfig.provider || 'amd-cloud';
                      const cleanModelId = getCleanModelId(roleConfig.model_id, currentProvider);

                      let catalogForProvider = providerCatalog[currentProvider] || [];
                      let selectOptions = catalogForProvider.map(m => {
                        const cleanOptVal = getCleanModelId(m.id, currentProvider);
                        return {
                          value: cleanOptVal,
                          label: m.name,
                        };
                      });

                      // Ensure fallback/default templates are available if list is empty
                      if (selectOptions.length === 0) {
                        selectOptions = [
                          { value: 'amd-cloud/llama-3-8b-instruct', label: 'Llama 3 8B Instruct (AMD Cloud Template)' },
                          { value: 'amd-cloud/qwen-2.5-7b-instruct', label: 'Qwen 2.5 Coder 7B (AMD Cloud Template)' },
                          { value: 'amd-cloud/mistral-7b-instruct', label: 'Mistral 7B Instruct (AMD Cloud Template)' }
                        ];
                      }

                      return (
                        <Card key={r.role} size="small" style={{ background: 'rgba(255, 255, 255, 0.03)', borderColor: 'rgba(255, 255, 255, 0.1)', overflow: 'hidden' }}>
                          <div style={{ fontWeight: 600, color: '#f8fafc', marginBottom: '2px', fontSize: '13px' }}>{r.label}</div>
                          <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '8px' }}>{r.desc}</div>
                          
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            <div>
                              <span style={{ fontSize: '11px', color: '#64748b', display: 'block', marginBottom: '4px' }}>Choose Template Model</span>
                              <Select
                                size="small"
                                showSearch
                                style={{ width: '100%' }}
                                value={cleanModelId || undefined}
                                placeholder="Select model template..."
                                onChange={(newModelId) => handleUpdateRoleModel(r.role, currentProvider, newModelId)}
                                options={selectOptions}
                              />
                            </div>
                            <div>
                              <span style={{ fontSize: '11px', color: '#64748b', display: 'block', marginBottom: '4px' }}>Or Type Custom Model ID</span>
                              <Input
                                size="small"
                                placeholder="e.g. llama3:latest / custom-model"
                                value={cleanModelId}
                                onChange={(e) => handleUpdateRoleModel(r.role, currentProvider, e.target.value)}
                                style={{ background: '#0f172a', color: '#f8fafc', borderColor: '#334155', fontSize: '12px' }}
                              />
                            </div>
                          </div>
                        </Card>
                      );
                    })}
                  </div>
                </div>
              )
            },
            {
              key: 'memories',
              label: <span><BulbOutlined /> Memories & Persona</span>,
              children: (
                <div style={{ marginTop: '8px' }}>
                  <Typography.Paragraph type="secondary" style={{ marginBottom: '16px', fontSize: '13px' }}>
                    Global memories are retained across all chat sessions and injected into RAG context assembly. You can add custom global memories or edit/delete existing ones.
                  </Typography.Paragraph>

                  {/* Add Memory Form */}
                  <Card 
                    size="small" 
                    title="Add New Global Memory" 
                    style={{ background: 'rgba(255, 255, 255, 0.03)', borderColor: 'rgba(255, 255, 255, 0.1)', marginBottom: '20px' }}
                  >
                    <Input.TextArea
                      rows={3}
                      placeholder="e.g., Remember that I prefer dark mode, my API port is 8000, and I use Python 3.12."
                      value={newMemoryContent}
                      onChange={e => setNewMemoryContent(e.target.value)}
                      style={{ marginBottom: '12px', background: '#0f172a', color: '#f8fafc', borderColor: '#334155' }}
                    />
                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                      <Button 
                        type="primary" 
                        icon={<PlusOutlined />} 
                        onClick={handleAddMemory}
                        style={{ background: '#0284c7', borderColor: '#0284c7' }}
                      >
                        Save Memory
                      </Button>
                    </div>
                  </Card>

                  {/* Memory List */}
                  <Typography.Text strong style={{ color: '#94a3b8', display: 'block', marginBottom: '8px' }}>
                    Stored Memories ({memories.length})
                  </Typography.Text>

                  <List
                    dataSource={memories}
                    locale={{ emptyText: 'No stored memories found. Add one above or ask the agent to remember something!' }}
                    renderItem={item => (
                      <List.Item
                        style={{ padding: '12px', borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }}
                        actions={[
                          editingMemoryId === item.id ? (
                            <Button icon={<SaveOutlined />} type="link" onClick={() => handleUpdateMemory(item.id)}>Save</Button>
                          ) : (
                            <Button icon={<EditOutlined />} type="link" onClick={() => { setEditingMemoryId(item.id); setEditingContent(item.content); }}>Edit</Button>
                          ),
                          <Popconfirm title="Delete memory?" onConfirm={() => handleDeleteMemory(item.id)}>
                            <Button icon={<DeleteOutlined />} type="link" danger>Delete</Button>
                          </Popconfirm>
                        ]}
                      >
                        {editingMemoryId === item.id ? (
                          <Input.TextArea 
                            value={editingContent} 
                            onChange={e => setEditingContent(e.target.value)} 
                            autoSize={{ minRows: 2, maxRows: 6 }}
                            style={{ background: '#0f172a', color: '#f8fafc' }}
                          />
                        ) : (
                          <div style={{ width: '100%' }}>
                            <div style={{ whiteSpace: 'pre-wrap', color: '#e2e8f0', fontSize: '14px' }}>{item.content}</div>
                            {item.created_at && (
                              <span style={{ fontSize: '11px', color: '#64748b', marginTop: '4px', display: 'block' }}>
                                Added: {new Date(item.created_at).toLocaleString()}
                              </span>
                            )}
                          </div>
                        )}
                      </List.Item>
                    )}
                  />
                </div>
              )
            },
            {
              key: 'mcp',
              label: <span><ApiOutlined /> MCP Servers</span>,
              children: (
                <div style={{ marginTop: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <Typography.Paragraph type="secondary" style={{ margin: 0, fontSize: '13px' }}>
                      Configure stdio-based Model Context Protocol (MCP) servers. Exposed tools are automatically namespaced under `mcp_[server]_[tool]` and available to both orchestrator and sub-agents.
                    </Typography.Paragraph>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <Button 
                        size="small" 
                        icon={<SyncOutlined />} 
                        onClick={loadMcpServers}
                        style={{ background: 'rgba(255, 255, 255, 0.05)', color: '#f8fafc', borderColor: 'rgba(255, 255, 255, 0.1)' }}
                      >
                        Refresh
                      </Button>
                      <Button 
                        type="primary" 
                        size="small" 
                        icon={<PlusOutlined />} 
                        onClick={() => { resetMcpForm(); setEditingMcp(null); setIsMcpModalOpen(true); }}
                        style={{ background: '#0284c7', borderColor: '#0284c7' }}
                      >
                        Add Server
                      </Button>
                    </div>
                  </div>

                  <List
                    dataSource={mcpServers}
                    locale={{ emptyText: 'No MCP servers configured. Add one to extend your agent capabilities!' }}
                    renderItem={server => {
                      const envKeys = Object.keys(server.env || {});
                      return (
                        <Card
                          size="small"
                          style={{
                            background: 'rgba(255, 255, 255, 0.02)',
                            borderColor: 'rgba(255, 255, 255, 0.08)',
                            marginBottom: '12px'
                          }}
                          title={
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{ color: '#38bdf8', fontWeight: 600 }}>{server.name}</span>
                                <Tag color={server.status === 'Active' ? 'success' : server.status === 'Error' ? 'error' : 'default'} style={{ margin: 0, fontSize: '11px' }}>
                                  ● {server.status}
                                </Tag>
                              </div>
                              <div style={{ display: 'flex', gap: '6px' }}>
                                <Button 
                                  size="small"
                                  icon={<FileTextOutlined />}
                                  onClick={() => {
                                    setSelectedLogsServer(server.name);
                                    loadMcpLogs(server.name);
                                    setLogsDrawerOpen(true);
                                  }}
                                  style={{ background: 'rgba(255,255,255,0.05)', color: '#f8fafc', borderColor: 'rgba(255,255,255,0.1)' }}
                                >
                                  Logs
                                </Button>
                                <Button
                                  size="small"
                                  icon={<EditOutlined />}
                                  onClick={() => {
                                    setEditingMcp(server);
                                    setMcpName(server.name);
                                    setMcpCommand(server.command);
                                    setMcpArgsStr(JSON.stringify(server.args));
                                    setMcpEnvStr(JSON.stringify(server.env, null, 2));
                                    setMcpEnabled(server.enabled);
                                    setIsMcpModalOpen(true);
                                  }}
                                  style={{ background: 'rgba(255,255,255,0.05)', color: '#e2e8f0', borderColor: 'rgba(255,255,255,0.1)' }}
                                >
                                  Edit
                                </Button>
                                <Popconfirm
                                  title="Delete this MCP server configuration?"
                                  onConfirm={() => handleDeleteMcpServer(server.name)}
                                  okText="Delete"
                                  cancelText="Cancel"
                                >
                                  <Button size="small" icon={<DeleteOutlined />} danger>
                                    Delete
                                  </Button>
                                </Popconfirm>
                              </div>
                            </div>
                          }
                        >
                          <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '8px' }}>
                            <span style={{ fontWeight: 600, color: '#f8fafc', marginRight: '6px' }}>Command:</span>
                            <span style={{ fontFamily: 'monospace', background: '#0f172a', padding: '2px 6px', borderRadius: '4px' }}>
                              {server.command} {server.args.join(' ')}
                            </span>
                          </div>

                          {envKeys.length > 0 && (
                            <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '12px', display: 'flex', flexWrap: 'wrap', gap: '4px', alignItems: 'center' }}>
                              <span style={{ fontWeight: 600, color: '#f8fafc', marginRight: '4px' }}>Env Keys:</span>
                              {envKeys.map(k => <Tag key={k} color="blue" style={{ fontSize: '10px', margin: 0 }}>{k}</Tag>)}
                            </div>
                          )}

                          {server.error_message && (
                            <div style={{ color: '#ef4444', background: 'rgba(239, 68, 68, 0.08)', padding: '6px 10px', borderRadius: '4px', fontSize: '12px', fontFamily: 'monospace', marginBottom: '12px' }}>
                              Error: {server.error_message}
                            </div>
                          )}

                          {server.status === 'Active' && server.tools.length > 0 ? (
                            <Collapse
                              size="small"
                              style={{ background: 'rgba(0,0,0,0.2)', border: 'none' }}
                              ghost
                              items={[
                                {
                                  key: 'tools',
                                  label: <span style={{ color: '#cbd5e1', fontSize: '12px' }}>🛠️ Discovered Tools ({server.tools.length})</span>,
                                  children: (
                                    <List
                                      size="small"
                                      dataSource={server.tools}
                                      renderItem={(tool: any) => (
                                        <List.Item style={{ padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                          <div style={{ width: '100%' }}>
                                            <Tag color="purple" style={{ fontFamily: 'monospace', fontSize: '11px' }}>
                                              mcp_{server.name}_{tool.name}
                                            </Tag>
                                            <span style={{ color: '#cbd5e1', fontSize: '12px', display: 'block', marginTop: '4px' }}>
                                              {tool.description}
                                            </span>
                                          </div>
                                        </List.Item>
                                      )}
                                    />
                                  )
                                }
                              ]}
                            />
                          ) : (
                            <div style={{ color: '#64748b', fontSize: '11px' }}>
                              {server.status === 'Active' ? 'No tools exposed by this server.' : 'Exposed tools will be listed here when active.'}
                            </div>
                          )}
                        </Card>
                      );
                    }}
                  />
                </div>
              )
            }
          ]}
        />
      </Modal>

      {/* Add / Edit MCP Server Modal */}
      <Modal
        title={editingMcp ? "Edit MCP Server" : "Add MCP Server"}
        open={isMcpModalOpen}
        onOk={handleAddMcpServer}
        onCancel={() => { setIsMcpModalOpen(false); setEditingMcp(null); resetMcpForm(); }}
        okText="Save Config"
        width={540}
        styles={{
          mask: { backdropFilter: 'blur(4px)', background: 'rgba(0, 0, 0, 0.6)' },
          body: { background: '#0f172a', color: '#f8fafc', padding: '16px 20px' },
          header: { background: 'transparent', borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '12px' }}>
          <div>
            <Typography.Text style={{ color: '#cbd5e1', fontSize: '13px', display: 'block', marginBottom: '4px' }}>Server Name</Typography.Text>
            <Input 
              placeholder="e.g. notion" 
              value={mcpName} 
              onChange={e => setMcpName(e.target.value)} 
              disabled={!!editingMcp}
              style={{ background: '#1e293b', color: '#f8fafc', borderColor: '#334155' }}
            />
          </div>

          <div>
            <Typography.Text style={{ color: '#cbd5e1', fontSize: '13px', display: 'block', marginBottom: '4px' }}>Execution Command</Typography.Text>
            <Input 
              placeholder="e.g. npx, uvx, python" 
              value={mcpCommand} 
              onChange={e => setMcpCommand(e.target.value)} 
              style={{ background: '#1e293b', color: '#f8fafc', borderColor: '#334155' }}
            />
          </div>

          <div>
            <Typography.Text style={{ color: '#cbd5e1', fontSize: '13px', display: 'block', marginBottom: '4px' }}>Arguments (JSON Array)</Typography.Text>
            <Input.TextArea 
              rows={2}
              placeholder='e.g. ["-y", "@modelcontextprotocol/server-notion"]' 
              value={mcpArgsStr} 
              onChange={e => setMcpArgsStr(e.target.value)} 
              style={{ background: '#1e293b', color: '#f8fafc', borderColor: '#334155', fontFamily: 'monospace' }}
            />
          </div>

          <div>
            <Typography.Text style={{ color: '#cbd5e1', fontSize: '13px', display: 'block', marginBottom: '4px' }}>Environment Variables (JSON Object)</Typography.Text>
            <Input.TextArea 
              rows={4}
              placeholder='e.g. {&#10;  "NOTION_API_KEY": "secret_..."&#10;}' 
              value={mcpEnvStr} 
              onChange={e => setMcpEnvStr(e.target.value)} 
              style={{ background: '#1e293b', color: '#f8fafc', borderColor: '#334155', fontFamily: 'monospace' }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <input 
              type="checkbox" 
              id="mcp_enabled_checkbox" 
              checked={mcpEnabled} 
              onChange={e => setMcpEnabled(e.target.checked)} 
              style={{ accentColor: '#38bdf8' }}
            />
            <label htmlFor="mcp_enabled_checkbox" style={{ color: '#cbd5e1', fontSize: '13px', cursor: 'pointer' }}>
              Enable server process instantly on save
            </label>
          </div>
        </div>
      </Modal>

      {/* MCP Logs Drawer Modal */}
      <Modal
        title={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginRight: '24px' }}>
            <span style={{ color: '#f8fafc' }}>🔌 Logs for '{selectedLogsServer}'</span>
            <Button 
              size="small" 
              icon={<SyncOutlined />} 
              onClick={() => selectedLogsServer && loadMcpLogs(selectedLogsServer)}
              style={{ background: 'rgba(255,255,255,0.05)', color: '#cbd5e1', borderColor: 'rgba(255,255,255,0.1)' }}
            >
              Reload
            </Button>
          </div>
        }
        open={logsDrawerOpen}
        onCancel={() => setLogsDrawerOpen(false)}
        footer={null}
        width={720}
        styles={{
          mask: { backdropFilter: 'blur(2px)', background: 'rgba(0, 0, 0, 0.5)' },
          body: { background: '#090d16', color: '#f8fafc', padding: '12px' }
        }}
      >
        <div 
          style={{ 
            height: '420px', 
            overflowY: 'auto', 
            background: '#020617', 
            padding: '12px', 
            borderRadius: '6px', 
            fontFamily: 'monospace', 
            fontSize: '11px',
            lineHeight: '1.5',
            color: '#38bdf8',
            border: '1px solid rgba(255,255,255,0.05)'
          }}
        >
          {serverLogs.length === 0 ? (
            <div style={{ color: '#64748b' }}>No logs generated yet.</div>
          ) : (
            serverLogs.map((log, idx) => (
              <div key={idx} style={{ 
                color: log.includes('ERR:') ? '#ef4444' : log.includes('OUT:') ? '#10b981' : '#38bdf8', 
                borderBottom: '1px solid rgba(255,255,255,0.02)',
                paddingBottom: '4px',
                marginBottom: '4px',
                wordBreak: 'break-all',
                whiteSpace: 'pre-wrap'
              }}>
                {log}
              </div>
            ))
          )}
        </div>
      </Modal>

      {/* Upload Modal */}
      <Modal
        title="Upload Files for Context"
        open={isUploadOpen}
        onCancel={() => setIsUploadOpen(false)}
        footer={null}
        width={600}
      >
        <Typography.Paragraph type="secondary">
          Drag files here or click to browse. The path will be inserted into your prompt.
        </Typography.Paragraph>
        <Dragger
          name="file"
          multiple
          beforeUpload={(file) => {
            const f = file as any;
            const filePath = f.path || f.webkitRelativePath || f.name;
            if (filePath) {
              const formattedPath = filePath.includes(' ') ? `"${filePath}"` : filePath;
              setInput(prev => prev + (prev.trim() ? ' ' : '') + formattedPath + ' ');
              antdMessage.success(`${f.name} path added`);
            } else {
              antdMessage.error("Could not retrieve file path.");
            }
            return false;
          }}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">Click or drag file to this area</p>
          <p className="ant-upload-hint">
            Support for code files, PDFs, text, and log files.
          </p>
        </Dragger>
      </Modal>

      {/* Top Application Navigation Header */}
      <Header style={{ 
        background: 'rgba(11, 15, 25, 0.95)', 
        color: '#f8fafc', 
        padding: '0 16px', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'space-between',
        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        backdropFilter: 'blur(16px)',
        height: '56px',
        flexShrink: 0,
        zIndex: 100
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Tooltip title={leftCollapsed ? "Expand Past Chats" : "Collapse Past Chats"}>
            <Button 
              type="text" 
              icon={leftCollapsed ? <MenuUnfoldOutlined style={{ color: '#38bdf8', fontSize: '18px' }} /> : <MenuFoldOutlined style={{ color: '#94a3b8', fontSize: '18px' }} />} 
              onClick={() => setLeftCollapsed(!leftCollapsed)}
            />
          </Tooltip>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '16px', fontWeight: 700, color: '#f8fafc' }}>
            <div style={{ 
              width: 32, 
              height: 32, 
              borderRadius: 8, 
              background: 'linear-gradient(135deg, #0284c7, #2563eb)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 4px 12px rgba(37, 99, 235, 0.35)'
            }}>
              <RobotOutlined style={{ color: '#ffffff', fontSize: '18px' }} />
            </div>
            <span>AgenticAI Studio</span>
            <span style={{ 
              fontSize: '11px', 
              fontWeight: 500, 
              padding: '2px 8px', 
              borderRadius: '12px',
              backgroundColor: backendRunning ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
              color: backendRunning ? '#4ade80' : '#f87171',
              border: `1px solid ${backendRunning ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px'
            }}>
              <span className={backendRunning ? "status-dot-pulsing" : ""} style={{ width: 6, height: 6, borderRadius: '50%', background: backendRunning ? '#22c55e' : '#ef4444' }} />
              {backendRunning ? 'Ready' : 'Offline'}
            </span>
            {/* Redis Status Badge */}
            {backendRunning && (
              <span style={{
                fontSize: '11px',
                fontWeight: 500,
                padding: '2px 8px',
                borderRadius: '12px',
                backgroundColor: redisConnected === null
                  ? 'rgba(100, 116, 139, 0.15)'
                  : redisConnected
                    ? 'rgba(34, 197, 94, 0.12)'
                    : 'rgba(239, 68, 68, 0.12)',
                color: redisConnected === null ? '#94a3b8' : redisConnected ? '#4ade80' : '#f87171',
                border: `1px solid ${redisConnected === null ? 'rgba(100,116,139,0.3)' : redisConnected ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                marginLeft: '4px',
              }}>
                <span style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: redisConnected === null ? '#94a3b8' : redisConnected ? '#22c55e' : '#ef4444',
                }} />
                Redis {redisConnected === null ? '...' : redisConnected ? 'Live' : 'Off'}
              </span>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Tooltip title="Memory Settings">
            <Button 
              type="text" 
              icon={<SettingOutlined style={{ fontSize: '18px', color: '#94a3b8' }} />} 
              onClick={async () => {
                setIsSettingsOpen(true);
                await loadMemories();
                await loadRoleModels();
              }}
            />
          </Tooltip>

          <Tooltip title={rightCollapsed ? "Expand Inspector" : "Collapse Inspector"}>
            <Button 
              type="text" 
              icon={rightCollapsed ? <MenuFoldOutlined style={{ color: '#38bdf8', fontSize: '18px' }} /> : <MenuUnfoldOutlined style={{ color: '#94a3b8', fontSize: '18px' }} />} 
              onClick={() => setRightCollapsed(!rightCollapsed)}
            />
          </Tooltip>
        </div>
      </Header>

      {/* Main Studio Workspace Layout */}
      <Layout style={{ flex: 1, overflow: 'hidden', background: '#0b0f19' }}>
        {/* Left Sider: Past Chats */}
        <Sider 
          width={260} 
          collapsible 
          collapsed={leftCollapsed}
          onCollapse={setLeftCollapsed}
          trigger={null}
          collapsedWidth={0} 
          style={{ 
            background: '#070a12', 
            borderRight: '1px solid rgba(255, 255, 255, 0.08)', 
            overflowY: 'auto',
            transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)'
          }}
        >
          <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px', height: '100%' }}>
            <Button 
              type="primary" 
              block 
              icon={<PlusOutlined />}
              onClick={handleCreateSession}
              style={{
                background: 'linear-gradient(135deg, #2563eb, #0284c7)',
                border: 'none',
                height: '40px',
                borderRadius: '8px',
                fontWeight: 600,
                boxShadow: '0 4px 12px rgba(37, 99, 235, 0.35)'
              }}
            >
              New Chat
            </Button>

            <div style={{ 
              fontSize: '11px', 
              color: '#64748b', 
              textTransform: 'uppercase', 
              fontWeight: 700, 
              letterSpacing: '0.8px',
              marginTop: '4px' 
            }}>
              Past Chats ({sessions.length})
            </div>

            <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {sessions.map(item => {
                const isActive = item.session_id === sessionId;
                return (
                  <div 
                    key={item.session_id}
                    onClick={() => {
                      if (item.session_id !== sessionId) {
                        setSessionId(item.session_id);
                      }
                    }}
                    style={{
                      padding: '10px 12px',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      background: isActive ? 'rgba(37, 99, 235, 0.18)' : 'rgba(255, 255, 255, 0.03)',
                      border: isActive ? '1px solid rgba(56, 189, 248, 0.4)' : '1px solid rgba(255, 255, 255, 0.05)',
                      color: isActive ? '#f8fafc' : '#94a3b8',
                      transition: 'all 0.2s ease',
                      fontSize: '13px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      fontWeight: isActive ? 600 : 400
                    }}
                    title={item.title}
                  >
                    <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flex: 1, marginRight: '8px' }}>
                      {item.title || 'Untitled Chat'}
                    </div>
                    <Popconfirm
                      title="Delete session?"
                      onConfirm={(e) => handleDeleteSession(item.session_id, e as React.MouseEvent)}
                      onCancel={(e) => e?.stopPropagation()}
                      okText="Yes"
                      cancelText="No"
                    >
                      <Button 
                        type="text" 
                        danger 
                        icon={<DeleteOutlined />} 
                        size="small" 
                        onClick={(e) => e.stopPropagation()} 
                        style={{ opacity: isActive ? 1 : 0.4, color: '#f87171' }}
                      />
                    </Popconfirm>
                  </div>
                );
              })}
            </div>
          </div>
        </Sider>

        {/* Center: Conversation View */}
        <Layout style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#0b0f19', overflow: 'hidden' }}>
          <Content style={{ flex: 1, padding: '16px 24px', overflowY: 'auto', display: 'flex', justifyContent: 'center' }}>
            <div style={{ width: '100%', maxWidth: '850px', height: '100%', display: 'flex', flexDirection: 'column' }}>
              <div style={{ flex: 1, overflowY: 'auto', paddingRight: '8px' }}>
                <List
                  itemLayout="vertical"
                  dataSource={messages}
                  renderItem={msg => (
                    <List.Item style={{ border: 'none', padding: '8px 0' }}>
                      <div style={{ 
                        display: 'flex', 
                        justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                        marginBottom: 12 
                      }}>
                        {msg.role !== 'user' && (
                          <div style={{
                            flexShrink: 0,
                            width: 32,
                            height: 32,
                            borderRadius: '50%',
                            background: msg.role === 'sub_agent' ? 'linear-gradient(135deg, #a855f7, #6b21a8)' : 'linear-gradient(135deg, #0284c7, #2563eb)',
                            marginRight: 10,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: '#ffffff',
                            fontSize: 14,
                            boxShadow: '0 4px 10px rgba(0,0,0,0.3)'
                          }}>
                            {msg.role === 'sub_agent' ? '🤖' : 'A'}
                          </div>
                        )}

                        <div style={{ maxWidth: '82%' }}>
                          {/* Attached Files in Chat History (Gemini / ChatGPT Style) */}
                          {msg.role === 'user' && msg.attachments && msg.attachments.length > 0 && (
                            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'flex-end', marginBottom: '8px' }}>
                              {msg.attachments.map((att, attIdx) => {
                                const isImg = isImageFile(att.name || att.path);
                                const imgSrc = getSafeImageSrc(att);
                                return isImg ? (
                                  <div
                                    key={attIdx}
                                    className="attachment-image-thumb"
                                    onClick={(e) => {
                                      const imgEl = e.currentTarget.querySelector('img');
                                      const activeSrc = imgEl?.src || (att as any).dataUrl || getSafeImageSrc(att);
                                      setPreviewImage({ url: activeSrc, title: att.name, path: att.path });
                                    }}
                                    style={{ width: 80, height: 80 }}
                                  >
                                    <img src={imgSrc} alt={att.name} onError={(e) => handleImageError(e, att.path)} />
                                    <div className="zoom-overlay">
                                      <EyeOutlined />
                                    </div>
                                  </div>
                                ) : (
                                  <div
                                    key={attIdx}
                                    className="attachment-card"
                                    onClick={() => setPreviewImage({ url: imgSrc, title: att.name, path: att.path })}
                                    style={{ cursor: 'pointer' }}
                                  >
                                    <FileTextOutlined style={{ fontSize: 16, color: '#38bdf8' }} />
                                    <span style={{ fontSize: '12px', color: '#f8fafc', fontWeight: 500 }}>
                                      {att.name}
                                    </span>
                                  </div>
                                );
                              })}
                            </div>
                          )}

                          <div className="chat-markdown-content" style={{ 
                            background: msg.role === 'user' 
                              ? 'linear-gradient(135deg, #2563eb, #1d4ed8)' 
                              : msg.role === 'sub_agent' 
                              ? 'rgba(147, 51, 234, 0.12)' 
                              : 'rgba(255, 255, 255, 0.05)',
                            border: msg.role === 'sub_agent' 
                              ? '1px dashed rgba(168, 85, 247, 0.4)' 
                              : msg.role === 'user' 
                              ? 'none' 
                              : '1px solid rgba(255, 255, 255, 0.08)',
                            color: '#f8fafc',
                            borderRadius: msg.role === 'user' ? '18px 18px 4px 18px' : '18px 18px 18px 4px', 
                            padding: '12px 16px',
                            overflowX: 'auto',
                            boxShadow: '0 4px 14px rgba(0,0,0,0.25)',
                            fontSize: '14px',
                            lineHeight: 1.5,
                            whiteSpace: 'pre-wrap'
                          }}>
                            {(() => {
                              const messageText = msg.content || (msg as any).content_raw || (msg as any).reply || (msg as any).response || '';
                              return msg.role === 'sub_agent' ? (
                                <Collapse 
                                  size="small" 
                                  ghost 
                                  items={[{
                                    key: '1',
                                    label: <span style={{ fontSize: '12px', color: '#c084fc', fontWeight: 600 }}>View Sub-Agent Details ({msg.model_id || 'Sub-Agent'})</span>,
                                    children: (
                                      <ReactMarkdown 
                                        remarkPlugins={[remarkGfm, remarkEmoji]}
                                        components={{
                                          code({node, inline, className, children, ...props}: any) {
                                            const match = /language-(\w+)/.exec(className || '');
                                            const codeContent = String(children).replace(/\n$/, '');
                                            return !inline && match ? (
                                              <div style={{ position: 'relative' }}>
                                                <Button
                                                  type="text"
                                                  icon={copiedCode === codeContent ? <CheckOutlined style={{ color: '#4ade80' }} /> : <CopyOutlined style={{ color: '#94a3b8' }} />}
                                                  size="small"
                                                  onClick={() => {
                                                    navigator.clipboard.writeText(codeContent);
                                                    setCopiedCode(codeContent);
                                                    setTimeout(() => setCopiedCode(null), 2000);
                                                  }}
                                                  style={{ position: 'absolute', top: 5, right: 5, zIndex: 1, background: 'rgba(15, 23, 42, 0.8)' }}
                                                />
                                                <SyntaxHighlighter
                                                  style={vscDarkPlus as any}
                                                  language={match[1]}
                                                  PreTag="div"
                                                  {...props}
                                                >
                                                  {codeContent}
                                                </SyntaxHighlighter>
                                              </div>
                                            ) : (
                                              <code className={className} style={{background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '4px', color: '#38bdf8'}} {...props}>
                                                {children}
                                              </code>
                                            );
                                          }
                                        }}
                                      >
                                        {messageText}
                                      </ReactMarkdown>
                                    )
                                  }]} 
                                />
                              ) : (
                                <ReactMarkdown 
                                  remarkPlugins={[remarkGfm, remarkEmoji]}
                                  components={{
                                    code({node, inline, className, children, ...props}: any) {
                                      const match = /language-(\w+)/.exec(className || '');
                                      const codeContent = String(children).replace(/\n$/, '');
                                      return !inline && match ? (
                                        <div style={{ position: 'relative' }}>
                                          <Button
                                            type="text"
                                            icon={copiedCode === codeContent ? <CheckOutlined style={{ color: '#4ade80' }} /> : <CopyOutlined style={{ color: '#94a3b8' }} />}
                                            size="small"
                                            onClick={() => {
                                              navigator.clipboard.writeText(codeContent);
                                              setCopiedCode(codeContent);
                                              setTimeout(() => setCopiedCode(null), 2000);
                                            }}
                                            style={{ position: 'absolute', top: 5, right: 5, zIndex: 1, background: 'rgba(15, 23, 42, 0.8)' }}
                                          />
                                          <SyntaxHighlighter
                                            style={vscDarkPlus as any}
                                            language={match[1]}
                                            PreTag="div"
                                            {...props}
                                          >
                                            {codeContent}
                                          </SyntaxHighlighter>
                                        </div>
                                      ) : (
                                        <code className={className} style={{background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '4px', color: '#38bdf8'}} {...props}>
                                          {children}
                                        </code>
                                      );
                                    }
                                  }}
                                >
                                  {messageText}
                                </ReactMarkdown>
                              );
                            })()}
                          </div>
                          {(msg.role === 'assistant' || msg.role === 'sub_agent') && (
                            <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px', textAlign: 'right', display: 'flex', justifyContent: 'flex-end', gap: '8px', alignItems: 'center' }}>
                              {msg.role === 'sub_agent' ? (
                                <>
                                  <span style={{ background: 'rgba(168, 85, 247, 0.15)', color: '#c084fc', padding: '1px 6px', borderRadius: '4px', border: '1px solid rgba(168, 85, 247, 0.3)', fontSize: '10px' }}>
                                    Tool / Sub-Agent
                                  </span>
                                  <span style={{ color: '#38bdf8', fontWeight: 500 }}>
                                    {msg.model_id ? `Role / Model: ${msg.model_id}` : 'System Tool'}
                                  </span>
                                </>
                              ) : (
                                <span>Model: {msg.model_id || 'Orchestrator'}</span>
                              )}
                            </div>
                          )}
                        </div>

                        {msg.role === 'user' && (
                          <div style={{
                            flexShrink: 0,
                            width: 32,
                            height: 32,
                            borderRadius: '50%',
                            background: 'linear-gradient(135deg, #0284c7, #3b82f6)',
                            marginLeft: 10,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: '#ffffff',
                            fontSize: 13,
                            fontWeight: 600
                          }}>
                            U
                          </div>
                        )}
                      </div>
                    </List.Item>
                  )}
                />
                <div ref={messagesEndRef} />
              </div>
            </div>
          </Content>

          {/* Footer Input Toolbar */}
          <Footer style={{ 
            padding: '16px 24px', 
            background: 'rgba(11, 15, 25, 0.95)', 
            borderTop: '1px solid rgba(255, 255, 255, 0.08)', 
            backdropFilter: 'blur(16px)',
            flexShrink: 0 
          }}>
            <input 
              type="file" 
              ref={fileInputRef} 
              onChange={handleHTMLFileSelect} 
              style={{ display: 'none' }} 
              multiple 
            />
            {attachedFiles.length > 0 && (
              <div style={{
                maxWidth: '850px',
                margin: '0 auto 10px auto',
                display: 'flex',
                gap: '10px',
                flexWrap: 'wrap',
                alignItems: 'center',
                padding: '8px 12px',
                background: 'rgba(15, 23, 42, 0.65)',
                borderRadius: '14px',
                border: '1px solid rgba(56, 189, 248, 0.2)',
                backdropFilter: 'blur(12px)'
              }}>
                {attachedFiles.map((file, idx) => {
                  const isImg = isImageFile(file.name || file.path);
                  const imgSrc = getSafeImageSrc(file);
                  return isImg ? (
                    <div
                      key={idx}
                      className="attachment-image-thumb"
                      onClick={(e) => {
                        const imgEl = e.currentTarget.querySelector('img');
                        const activeSrc = imgEl?.src || file.dataUrl || getSafeImageSrc(file);
                        setPreviewImage({ url: activeSrc, title: file.name, path: file.path });
                      }}
                    >
                      <img src={imgSrc} alt={file.name} onError={(e) => handleImageError(e, file.path)} />
                      <div className="zoom-overlay">
                        <EyeOutlined />
                      </div>
                      <button
                        className="attachment-remove-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          setAttachedFiles(prev => prev.filter(f => f.path !== file.path));
                        }}
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <div key={idx} className="attachment-card">
                      <FileTextOutlined style={{ fontSize: 16, color: '#38bdf8' }} />
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span style={{ fontSize: '12px', color: '#f8fafc', fontWeight: 600 }}>{file.name}</span>
                        <span style={{ fontSize: '10px', color: '#94a3b8' }}>{file.chunkCount || 1} chunks</span>
                      </div>
                      <button
                        className="attachment-remove-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          setAttachedFiles(prev => prev.filter(f => f.path !== file.path));
                        }}
                      >
                        ✕
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', maxWidth: '850px', margin: '0 auto', gap: '8px' }}>
              <Select
                value={selectedModel}
                onChange={setSelectedModel}
                style={{ width: 170 }}
                options={[
                  { value: 'auto', label: '⚡ Auto (Orchestrator)' },
                  { value: 'collaborative', label: '🤝 Multi-Model Team' },
                  { value: 'coding', label: '🤖 Coding Specialist' },
                  { value: 'reasoning', label: '💡 Reasoning Specialist' },
                  { value: 'multimodal', label: '👁️ Vision Specialist' },
                ]}
              />
              <Tooltip title="Attach Document / Code File (RAG Vector Memory)">
                <Button
                  icon={<PaperClipOutlined />}
                  onClick={handleFileAttach}
                  disabled={!backendRunning || isLoading}
                />
              </Tooltip>
              <Input.TextArea
                placeholder="Message AgenticAI..."
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if ((input.trim() || attachedFiles.length > 0) && !isLoading) {
                      sendMessage();
                    }
                  }
                }}
                autoSize={{ minRows: 1, maxRows: 6 }}
                style={{ 
                  flex: 1, 
                  background: 'rgba(255, 255, 255, 0.05)', 
                  border: '1px solid rgba(255, 255, 255, 0.1)', 
                  color: '#f8fafc',
                  borderRadius: '8px',
                  resize: 'none',
                  paddingTop: '8px',
                  paddingBottom: '8px'
                }}
                disabled={!backendRunning || isLoading}
              />
              <Button 
                type="primary" 
                icon={<SendOutlined />}
                onClick={sendMessage}
                loading={isLoading}
                disabled={!backendRunning || !input.trim()}
                style={{
                  background: 'linear-gradient(135deg, #2563eb, #0284c7)',
                  border: 'none',
                  borderRadius: '8px',
                  fontWeight: 600
                }}
              >
                Send
              </Button>
            </div>
            <div style={{ textAlign: 'center', marginTop: 8, color: '#64748b', fontSize: '11px' }}>
              © 2026 AgenticAI • Multi-Model Agent System • {backendRunning ? 'AI Ready' : 'AI Offline'}
            </div>
          </Footer>
        </Layout>

        {/* Right Sider: Inspector & Agentic Log */}
        <Sider 
          width={320} 
          collapsible 
          collapsed={rightCollapsed}
          onCollapse={setRightCollapsed}
          trigger={null}
          collapsedWidth={0} 
          style={{ 
            background: '#070a12', 
            borderLeft: '1px solid rgba(255, 255, 255, 0.08)', 
            display: 'flex', 
            flexDirection: 'column',
            transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)'
          }}
        >
          <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', height: '100%', gap: '16px' }}>
            
            {/* Agent Control Panel */}
            <div style={{ 
              background: 'rgba(255, 255, 255, 0.03)', 
              border: '1px solid rgba(255, 255, 255, 0.08)', 
              borderRadius: '10px', 
              padding: '14px' 
            }}>
              <Button 
                block 
                type="primary"
                icon={<PoweroffOutlined />}
                onClick={async () => {
                  try {
                    if (backendRunning) {
                      antdMessage.info('Stopping AI backend...');
                      await invoke('stop_backend');
                      setBackendRunning(false);
                      antdMessage.success('AI backend stopped');
                    } else {
                      antdMessage.info('Starting AI backend...');
                      await invoke('start_backend');
                      setBackendRunning(true);
                      antdMessage.success('AI backend started');
                    }
                  } catch (error) {
                    antdMessage.error(`Failed: ${error}`);
                  }
                }}
                style={{
                  height: '38px',
                  borderRadius: '8px',
                  fontWeight: 600,
                  background: backendRunning 
                    ? 'linear-gradient(135deg, #ef4444, #dc2626)' 
                    : 'linear-gradient(135deg, #22c55e, #16a34a)',
                  border: 'none',
                  boxShadow: backendRunning 
                    ? '0 4px 14px rgba(239, 68, 68, 0.35)' 
                    : '0 4px 14px rgba(34, 197, 94, 0.35)'
                }}
              >
                {backendRunning ? 'Stop Agent Engine' : 'Start Agent Engine'}
              </Button>

              <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                <div style={{ fontSize: '11px', color: '#64748b', fontWeight: 600, textTransform: 'uppercase' }}>
                  Session ID
                </div>
                <div style={{ 
                  fontSize: '11px', 
                  fontFamily: '"Fira Code", monospace', 
                  color: '#38bdf8', 
                  background: 'rgba(15, 23, 42, 0.6)', 
                  padding: '6px 8px', 
                  borderRadius: '6px', 
                  border: '1px solid rgba(56, 189, 248, 0.2)',
                  wordBreak: 'break-all',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}>
                  <span>{sessionId ? `${sessionId.slice(0, 18)}...` : 'No active session'}</span>
                  {sessionId && (
                    <Button 
                      type="text" 
                      size="small"
                      icon={<CopyOutlined style={{ color: '#94a3b8', fontSize: '11px' }} />}
                      onClick={() => {
                        navigator.clipboard.writeText(sessionId);
                        antdMessage.success('Session ID copied');
                      }}
                    />
                  )}
                </div>
              </div>
            </div>

            {/* Agentic Log Section */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>
              <div style={{ 
                fontSize: '11px', 
                color: '#64748b', 
                marginBottom: '8px', 
                fontWeight: 700, 
                textTransform: 'uppercase', 
                letterSpacing: '0.8px',
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'space-between'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <CodeOutlined style={{ color: '#38bdf8' }} />
                  <span>Agent Activity Log</span>
                </div>
                <Button 
                  type="text" 
                  size="small" 
                  icon={<ClearOutlined />}
                  onClick={() => setBackendLogs([])} 
                  style={{ fontSize: '11px', color: '#64748b' }}
                >
                  Clear
                </Button>
              </div>

              <div style={{ 
                flex: 1, 
                background: '#05070f', 
                borderRadius: '8px', 
                padding: '10px', 
                overflowY: 'auto',
                fontFamily: '"Fira Code", "Cascadia Code", monospace',
                fontSize: '11px',
                color: '#cbd5e1',
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                border: '1px solid rgba(255, 255, 255, 0.06)'
              }}>
                {backendLogs.length === 0 ? (
                  <div style={{ color: '#475569', fontStyle: 'italic', padding: '10px', textAlign: 'center' }}>
                    System ready. Agent logs will stream here...
                  </div>
                ) : (
                  backendLogs.map((log, i) => {
                    let color = '#cbd5e1';
                    if (log.includes('ERROR') || log.includes('Failed')) color = '#f87171';
                    else if (log.includes('INFO') || log.includes('DEBUG')) color = '#38bdf8';
                    else if (log.includes('SUCCESS') || log.includes('ready')) color = '#4ade80';

                    return (
                      <div key={i} style={{ marginBottom: '4px', borderBottom: '1px solid rgba(255, 255, 255, 0.03)', paddingBottom: '3px', color }}>
                        {log}
                      </div>
                    );
                  })
                )}
                <div ref={logsEndRef} />
              </div>
            </div>
          </div>
        </Sider>
      </Layout>

      {/* Image Lightbox Zoom Modal (Gemini / ChatGPT Style) */}
      <Modal
        open={!!previewImage}
        footer={null}
        onCancel={() => setPreviewImage(null)}
        centered
        width="auto"
        styles={{
          body: {
            background: 'transparent',
            padding: '10px'
          }
        }}
      >
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '13px', color: '#38bdf8', marginBottom: '12px', fontWeight: 600, fontFamily: '"Fira Code", monospace' }}>
            📄 {previewImage?.title}
          </div>
          <img
            src={previewImage?.url}
            alt={previewImage?.title}
            onError={(e) => handleImageError(e, previewImage?.path)}
            style={{
              maxWidth: '85vw',
              maxHeight: '80vh',
              borderRadius: '12px',
              objectFit: 'contain',
              boxShadow: '0 10px 30px rgba(0,0,0,0.6)'
            }}
          />
        </div>
      </Modal>
    </Layout>
  );
}
