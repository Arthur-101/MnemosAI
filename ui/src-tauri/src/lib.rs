// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use std::process::{Child, Command, Stdio};
// use std::sync::Mutex;
use std::io::{Write, BufRead, BufReader};
use tokio::sync::Mutex as AsyncMutex;
use tauri::{Manager, Emitter};
use serde_json::{json, Value};
use uuid::Uuid;

struct BackendState {
    process: AsyncMutex<Option<Child>>,
    stdin: AsyncMutex<Option<std::process::ChildStdin>>,
    stdout: AsyncMutex<Option<BufReader<std::process::ChildStdout>>>,
}

/// Send a JSON-RPC request to the Python backend and get response
async fn send_json_rpc(
    app_handle: &tauri::AppHandle,
    method: &str,
    params: Value,
    request_id: Option<String>,
) -> Result<Value, String> {
    let state = app_handle.state::<BackendState>();
    let request_id = request_id.unwrap_or_else(|| Uuid::new_v4().to_string());
    
    let request = json!({
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": request_id
    });
    
    let request_str = serde_json::to_string(&request)
        .map_err(|e| format!("Failed to serialize request: {}", e))?;
    
    // Get stdin handle
    let mut stdin_guard = state.stdin.lock().await;
    let stdin = stdin_guard.as_mut()
        .ok_or("Backend stdin not available")?;
    
    // Send request
    stdin.write_all(request_str.as_bytes())
        .map_err(|e| format!("Failed to write to backend: {}", e))?;
    stdin.write_all(b"\n")
        .map_err(|e| format!("Failed to write newline: {}", e))?;
    stdin.flush()
        .map_err(|e| format!("Failed to flush stdin: {}", e))?;
    
    // Get stdout handle and read response
    let mut stdout_guard = state.stdout.lock().await;
    let stdout = stdout_guard.as_mut()
        .ok_or("Backend stdout not available")?;
    
    let mut response_line = String::new();
    let bytes_read = stdout.read_line(&mut response_line)
        .map_err(|e| format!("Failed to read response: {}", e))?;
        
    if bytes_read == 0 {
        return Err("Backend process exited unexpectedly (EOF on stdout)".to_string());
    }
    
    let response: Value = serde_json::from_str(&response_line)
        .map_err(|e| format!("Failed to parse response: {}", e))?;
    
    // Check for JSON-RPC error
    if let Some(error) = response.get("error") {
        let error_msg = error.get("message")
            .and_then(|v| v.as_str())
            .unwrap_or("Unknown error");
        return Err(format!("JSON-RPC error: {}", error_msg));
    }
    
    // Extract result
    response.get("result")
        .cloned()
        .ok_or_else(|| "No result in response".to_string())
}

#[tauri::command]
async fn start_backend(app_handle: tauri::AppHandle) -> Result<String, String> {
    let state = app_handle.state::<BackendState>();
    let mut process_guard = state.process.lock().await;
    if process_guard.is_some() {
        return Ok("Backend is already running".to_string());
    }
    
    // Robustly find the project root by checking current dir and ancestors
    let mut current_dir = std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."));
    let mut project_root = None;
    
    // Search upwards up to 3 levels to find "src/api/embedded_backend.py"
    for _ in 0..4 {
        if current_dir.join("src/api/embedded_backend.py").exists() {
            project_root = Some(current_dir.clone());
            break;
        }
        if !current_dir.pop() {
            break;
        }
    }
    
    let project_root = project_root.ok_or_else(|| "Could not find project root containing src/api/embedded_backend.py".to_string())?;
    let script_path = project_root.join("src/api/embedded_backend.py");
        
    let python_path_unix = project_root.join(".venv/bin/python");
    let python_path_win = project_root.join(".venv/Scripts/python.exe");
    
    // Use absolute path for Windows to avoid Microsoft Store alias issues
    let python_cmd = if python_path_win.exists() {
        python_path_win.to_str().unwrap()
    } else if python_path_unix.exists() {
        python_path_unix.to_str().unwrap()
    } else {
        if cfg!(windows) { "python" } else { "python3" }
    };
    
    println!("DEBUG: Found Windows Python path: {}", python_path_win.display());
    println!("DEBUG: Does it exist? {}", python_path_win.exists());
    println!("DEBUG: Executing Python command: {}", python_cmd);
    
    // Start the Python embedded backend with stdin/stdout/stderr pipes
    let mut cmd = Command::new(python_cmd);
    cmd.current_dir(&project_root)
        .arg(&script_path)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    
    let mut child = cmd.spawn()
        .map_err(|e| format!("Failed to start backend: {}", e))?;
    
    // Get stdin, stdout, stderr handles
    let stdin = child.stdin.take().ok_or("Failed to get stdin handle")?;
    let stdout = child.stdout.take().ok_or("Failed to get stdout handle")?;
    let stderr = child.stderr.take().ok_or("Failed to get stderr handle")?;
    
    let stdout_reader = BufReader::new(stdout);
    
    // Spawn a task to read stderr and emit events to frontend
    let app_handle_clone = app_handle.clone();
    tokio::spawn(async move {
        use tokio::io::AsyncBufReadExt;
        let mut reader = tokio::io::BufReader::new(tokio::process::ChildStderr::from_std(stderr).expect("Failed to convert stderr"));
        let mut line = String::new();
        while let Ok(bytes) = reader.read_line(&mut line).await {
            if bytes == 0 { break; }
            let _ = app_handle_clone.emit("backend-log", line.clone());
            line.clear();
        }
    });
    
    // Store handles in async mutexes
    *state.stdin.lock().await = Some(stdin);
    *state.stdout.lock().await = Some(stdout_reader);
    *process_guard = Some(child);
    
    // Test connection with a health check via direct JSON-RPC call
    match send_json_rpc(&app_handle, "health", json!({}), None).await {
        Ok(result) => {
            let status = result.get("status")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown");
            if status == "healthy" {
                Ok("Embedded backend started successfully".to_string())
            } else {
                let _ = stop_backend_internal(&app_handle).await;
                Err("Backend started but health check failed".to_string())
            }
        }
        Err(e) => {
            let _ = stop_backend_internal(&app_handle).await;
            Err(format!("Health check failed: {}", e))
        },
    }
}

async fn stop_backend_internal(app_handle: &tauri::AppHandle) -> Result<String, String> {
    let state = app_handle.state::<BackendState>();
    
    // Clear stdin/stdout handles first
    *state.stdin.lock().await = None;
    *state.stdout.lock().await = None;
    
    // Get the child process
    let child_opt = {
        let mut process_guard = state.process.lock().await;
        process_guard.take()
    };
    
    if let Some(mut child) = child_opt {
        let _ = child.kill();
        let _ = child.wait();
        Ok("Backend stopped".to_string())
    } else {
        Err("Backend is not running".to_string())
    }
}

#[tauri::command]
async fn stop_backend(app_handle: tauri::AppHandle) -> Result<String, String> {
    stop_backend_internal(&app_handle).await
}

#[tauri::command]
async fn send_chat_message(
    app_handle: tauri::AppHandle,
    message: String, 
    session_id: Option<String>,
    sessionId: Option<String>,
    model: Option<String>,
    model_override: Option<String>
) -> Result<serde_json::Value, String> {
    let s_id = session_id.or(sessionId);
    let m_override = model_override.or(model);
    let params = json!({
        "message": message,
        "session_id": s_id,
        "model_override": m_override,
        "use_tags": true,
        "use_summaries": true,
        "request_id": Uuid::new_v4().to_string()
    });
    
    let result = send_json_rpc(&app_handle, "chat", params, None).await?;
    Ok(result)
}

#[tauri::command]
async fn index_document(
    app_handle: tauri::AppHandle,
    file_path: Option<String>,
    filePath: Option<String>
) -> Result<serde_json::Value, String> {
    let path = file_path.or(filePath).ok_or("file_path is required")?;
    let params = json!({
        "file_path": path,
        "request_id": Uuid::new_v4().to_string()
    });
    
    let result = send_json_rpc(&app_handle, "index_document", params, None).await?;
    Ok(result)
}

#[tauri::command]
async fn get_chat_history(
    app_handle: tauri::AppHandle,
    session_id: Option<String>, 
    limit: Option<i32>
) -> Result<Vec<serde_json::Value>, String> {
    let limit_val = limit.unwrap_or(100);
    let params = json!({
        "session_id": session_id,
        "limit": limit_val,
        "request_id": Uuid::new_v4().to_string()
    });
    
    let result = send_json_rpc(&app_handle, "history", params, None).await?;
    
    result.get("messages")
        .and_then(|v| v.as_array())
        .map(|arr| arr.clone())
        .ok_or_else(|| "No messages in result".to_string())
}

#[tauri::command]
async fn new_session(app_handle: tauri::AppHandle) -> Result<String, String> {
    let result = send_json_rpc(&app_handle, "new_session", json!({}), None).await?;
    
    result.get("session_id")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .ok_or_else(|| "No session_id in result".to_string())
}

#[tauri::command]
async fn backend_status(app_handle: tauri::AppHandle) -> Result<bool, String> {
    let _state = app_handle.state::<BackendState>();
    
    match send_json_rpc(&app_handle, "health", json!({}), None).await {
        Ok(result) => {
            let status = result.get("status")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown");
            Ok(status == "healthy")
        }
        Err(_) => Ok(false),
    }
}

#[tauri::command]
async fn get_backend_health(app_handle: tauri::AppHandle) -> Result<serde_json::Value, String> {
    send_json_rpc(&app_handle, "health", json!({}), None).await
}

#[tauri::command]
async fn get_all_sessions(app_handle: tauri::AppHandle) -> Result<Vec<serde_json::Value>, String> {
    let result = send_json_rpc(&app_handle, "get_sessions", json!({}), None).await?;
    
    result.get("sessions")
        .and_then(|v| v.as_array())
        .map(|arr| arr.clone())
        .ok_or_else(|| "No sessions in result".to_string())
}

#[tauri::command]
async fn delete_session(
    app_handle: tauri::AppHandle,
    session_id: String
) -> Result<bool, String> {
    let params = json!({
        "session_id": session_id,
        "request_id": Uuid::new_v4().to_string()
    });
    
    let result = send_json_rpc(&app_handle, "delete_session", params, None).await?;
    
    result.get("success")
        .and_then(|v| v.as_bool())
        .ok_or_else(|| "No success flag in result".to_string())
}

#[tauri::command]
async fn get_all_memories(app_handle: tauri::AppHandle) -> Result<Vec<serde_json::Value>, String> {
    let result = send_json_rpc(&app_handle, "get_all_memories", json!({}), None).await?;
    
    result.get("memories")
        .and_then(|v| v.as_array())
        .map(|arr| arr.clone())
        .ok_or_else(|| "No memories in result".to_string())
}

#[tauri::command]
async fn update_memory(
    app_handle: tauri::AppHandle,
    message_id: String,
    content: String
) -> Result<bool, String> {
    let params = json!({
        "message_id": message_id,
        "content": content,
        "request_id": Uuid::new_v4().to_string()
    });
    
    let result = send_json_rpc(&app_handle, "update_memory", params, None).await?;
    
    result.get("success")
        .and_then(|v| v.as_bool())
        .ok_or_else(|| "No success flag in result".to_string())
}

#[tauri::command]
async fn add_memory(
    app_handle: tauri::AppHandle,
    content: String
) -> Result<bool, String> {
    let params = json!({
        "content": content,
        "request_id": Uuid::new_v4().to_string()
    });
    
    let result = send_json_rpc(&app_handle, "add_memory", params, None).await?;
    
    result.get("success")
        .and_then(|v| v.as_bool())
        .ok_or_else(|| "No success flag in result".to_string())
}

#[tauri::command]
async fn delete_memory(
    app_handle: tauri::AppHandle,
    memory_id: String
) -> Result<bool, String> {
    let params = json!({
        "memory_id": memory_id,
        "request_id": Uuid::new_v4().to_string()
    });
    
    let result = send_json_rpc(&app_handle, "delete_memory", params, None).await?;
    
    result.get("success")
        .and_then(|v| v.as_bool())
        .ok_or_else(|| "No success flag in result".to_string())
}

#[tauri::command]
async fn get_amd_cloud_config(app_handle: tauri::AppHandle) -> Result<serde_json::Value, String> {
    let result = send_json_rpc(&app_handle, "get_amd_cloud_config", json!({}), None).await?;
    Ok(result)
}

#[tauri::command]
async fn update_amd_cloud_config(
    app_handle: tauri::AppHandle,
    endpointUrl: String,
    apiKey: String,
) -> Result<serde_json::Value, String> {
    let params = json!({
        "endpoint_url": endpointUrl,
        "api_key": apiKey
    });
    let result = send_json_rpc(&app_handle, "update_amd_cloud_config", params, None).await?;
    Ok(result)
}

#[tauri::command]
async fn get_amd_gpu_metrics(app_handle: tauri::AppHandle) -> Result<serde_json::Value, String> {
    let result = send_json_rpc(&app_handle, "get_amd_gpu_metrics", json!({}), None).await?;
    Ok(result)
}

#[tauri::command]
async fn get_mcp_servers(app_handle: tauri::AppHandle) -> Result<serde_json::Value, String> {
    let result = send_json_rpc(&app_handle, "get_mcp_servers", json!({}), None).await?;
    result.get("servers").cloned().ok_or_else(|| "Failed to fetch MCP servers".to_string())
}

#[tauri::command]
async fn add_mcp_server(
    app_handle: tauri::AppHandle,
    name: String,
    command: String,
    args: Vec<String>,
    env: serde_json::Value,
    enabled: bool,
) -> Result<bool, String> {
    let params = json!({
        "name": name,
        "command": command,
        "args": args,
        "env": env,
        "enabled": enabled,
        "request_id": Uuid::new_v4().to_string()
    });
    let result = send_json_rpc(&app_handle, "add_mcp_server", params, None).await?;
    Ok(result.get("success").and_then(|v| v.as_bool()).unwrap_or(false))
}

#[tauri::command]
async fn delete_mcp_server(app_handle: tauri::AppHandle, name: String) -> Result<bool, String> {
    let params = json!({
        "name": name,
        "request_id": Uuid::new_v4().to_string()
    });
    let result = send_json_rpc(&app_handle, "delete_mcp_server", params, None).await?;
    Ok(result.get("success").and_then(|v| v.as_bool()).unwrap_or(false))
}

#[tauri::command]
async fn get_mcp_logs(app_handle: tauri::AppHandle, name: String) -> Result<Vec<String>, String> {
    let params = json!({
        "name": name,
        "request_id": Uuid::new_v4().to_string()
    });
    let result = send_json_rpc(&app_handle, "get_mcp_logs", params, None).await?;
    let logs = result.get("logs")
        .and_then(|v| v.as_array())
        .map(|arr| arr.iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
        .unwrap_or_else(Vec::new);
    Ok(logs)
}

#[tauri::command]
async fn get_available_models(app_handle: tauri::AppHandle, provider: String) -> Result<serde_json::Value, String> {
    let params = json!({ "provider": provider });
    let result = send_json_rpc(&app_handle, "get_available_models", params, None).await?;
    result.get("models").cloned().ok_or_else(|| "Failed to get available models".to_string())
}

#[tauri::command]
async fn get_role_models(app_handle: tauri::AppHandle) -> Result<serde_json::Value, String> {
    let params = json!({});
    let result = send_json_rpc(&app_handle, "get_role_models", params, None).await?;
    result.get("role_models").cloned().ok_or_else(|| "Failed to get role models".to_string())
}

#[tauri::command]
async fn update_role_model(
    app_handle: tauri::AppHandle,
    role: String,
    provider: String,
    model_id: Option<String>,
    modelId: Option<String>
) -> Result<serde_json::Value, String> {
    let actual_model = model_id.or(modelId).unwrap_or_default();
    let params = json!({
        "role": role,
        "provider": provider,
        "model_id": actual_model,
        "request_id": Uuid::new_v4().to_string()
    });
    let result = send_json_rpc(&app_handle, "update_role_model", params, None).await?;
    Ok(result)
}

#[tauri::command]
async fn get_api_keys(app_handle: tauri::AppHandle) -> Result<Vec<serde_json::Value>, String> {
    let params = json!({});
    let result = send_json_rpc(&app_handle, "get_api_keys", params, None).await?;
    result.get("api_keys")
        .and_then(|v| v.as_array())
        .cloned()
        .ok_or_else(|| "Failed to fetch API keys".to_string())
}

#[tauri::command]
async fn add_api_key(
    app_handle: tauri::AppHandle,
    provider: String,
    key_value: Option<String>,
    keyValue: Option<String>,
    label: Option<String>
) -> Result<serde_json::Value, String> {
    let actual_key = key_value.or(keyValue).unwrap_or_default();
    let params = json!({
        "provider": provider,
        "key_value": actual_key,
        "label": label,
        "request_id": Uuid::new_v4().to_string()
    });
    let result = send_json_rpc(&app_handle, "add_api_key", params, None).await?;
    Ok(result)
}

#[tauri::command]
async fn delete_api_key(
    app_handle: tauri::AppHandle,
    provider: String
) -> Result<serde_json::Value, String> {
    let params = json!({
        "provider": provider,
        "request_id": Uuid::new_v4().to_string()
    });
    let result = send_json_rpc(&app_handle, "delete_api_key", params, None).await?;
    Ok(result)
}

#[tauri::command]
async fn test_api_key(
    app_handle: tauri::AppHandle,
    provider: String,
    key_value: Option<String>,
    keyValue: Option<String>,
    model_id: Option<String>,
    modelId: Option<String>
) -> Result<serde_json::Value, String> {
    let actual_key = key_value.or(keyValue);
    let actual_model = model_id.or(modelId);
    let params = json!({
        "provider": provider,
        "key_value": actual_key,
        "model_id": actual_model,
        "request_id": Uuid::new_v4().to_string()
    });
    let result = send_json_rpc(&app_handle, "test_api_key", params, None).await?;
    Ok(result)
}

#[tauri::command]
async fn get_model_tracker_data(
    app_handle: tauri::AppHandle,
) -> Result<serde_json::Value, String> {
    let params = json!({
        "request_id": Uuid::new_v4().to_string()
    });
    let result = send_json_rpc(&app_handle, "get_model_tracker_data", params, None).await?;
    Ok(result)
}

#[tauri::command]
async fn save_model_note(
    app_handle: tauri::AppHandle,
    modelId: Option<String>,
    model_id: Option<String>,
    provider: String,
    isFavorite: Option<bool>,
    is_favorite: Option<bool>,
    notes: String
) -> Result<serde_json::Value, String> {
    let actual_model = model_id.or(modelId).unwrap_or_default();
    let fav = is_favorite.or(isFavorite).unwrap_or(false);
    let params = json!({
        "model_id": actual_model,
        "provider": provider,
        "is_favorite": if fav { 1 } else { 0 },
        "notes": notes,
        "request_id": Uuid::new_v4().to_string()
    });
    let result = send_json_rpc(&app_handle, "save_model_note", params, None).await?;
    Ok(result)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(BackendState {
            process: AsyncMutex::new(None),
            stdin: AsyncMutex::new(None),
            stdout: AsyncMutex::new(None),
        })
        .setup(|app| {
            let tray_result = (|| -> tauri::Result<()> {
                let status_i = tauri::menu::MenuItem::with_id(app, "status", "🟢 AgenticAI (Engine Active)", false, None::<&str>)?;
                let show_i = tauri::menu::MenuItem::with_id(app, "show", "🖥️  Show Studio Window", true, None::<&str>)?;
                let new_chat_i = tauri::menu::MenuItem::with_id(app, "new_chat", "➕  Start New Chat", true, None::<&str>)?;
                let toggle_i = tauri::menu::MenuItem::with_id(app, "toggle_engine", "⚡  Toggle AI Engine", true, None::<&str>)?;
                let quit_i = tauri::menu::MenuItem::with_id(app, "quit", "❌  Quit AgenticAI", true, None::<&str>)?;

                let sep1 = tauri::menu::PredefinedMenuItem::separator(app)?;
                let sep2 = tauri::menu::PredefinedMenuItem::separator(app)?;

                let menu = tauri::menu::Menu::with_items(app, &[
                    &status_i, &sep1, &show_i, &new_chat_i, &toggle_i, &sep2, &quit_i,
                ])?;

                let mut tray_builder = tauri::tray::TrayIconBuilder::new()
                    .menu(&menu)
                    .tooltip("AgenticAI Studio - Multi-Model AI Ready")
                    .show_menu_on_left_click(false);

                if let Some(icon) = app.default_window_icon() {
                    tray_builder = tray_builder.icon(icon.clone());
                }

                tray_builder
                    .on_menu_event(|app, event| match event.id.as_ref() {
                        "quit" => { std::process::exit(0); }
                        "show" => {
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                        "new_chat" => {
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.show();
                                let _ = window.set_focus();
                                let _ = window.emit("trigger-new-chat", ());
                            }
                        }
                        "toggle_engine" => {
                            if let Some(window) = app.get_webview_window("main") {
                                let _ = window.emit("trigger-toggle-engine", ());
                            }
                        }
                        _ => {}
                    })
                    .on_tray_icon_event(|tray, event| {
                        if let tauri::tray::TrayIconEvent::Click {
                            button: tauri::tray::MouseButton::Left,
                            button_state: tauri::tray::MouseButtonState::Up,
                            ..
                        } = event {
                            let app = tray.app_handle();
                            if let Some(window) = app.get_webview_window("main") {
                                if window.is_visible().unwrap_or(false) {
                                    let _ = window.hide();
                                } else {
                                    let _ = window.show();
                                    let _ = window.set_focus();
                                }
                            }
                        }
                    })
                    .build(app)?;

                Ok(())
            })();

            if let Err(e) = tray_result {
                eprintln!("WARNING: Tray icon setup failed (non-fatal): {:?}", e);
            }

            let app_handle_for_show = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                tokio::time::sleep(tokio::time::Duration::from_millis(1000)).await;
                if let Some(window) = app_handle_for_show.get_webview_window("main") {
                    let _ = window.center();
                    let _ = window.unminimize();
                    let _ = window.set_skip_taskbar(false);
                    let _ = window.set_always_on_top(true);
                    let _ = window.show();
                    let _ = window.set_focus();

                    #[cfg(target_os = "windows")]
                    {
                        if let Ok(hwnd) = window.hwnd() {
                            unsafe {
                                windows_sys::Win32::UI::WindowsAndMessaging::ShowWindow(
                                    hwnd.0 as _,
                                    windows_sys::Win32::UI::WindowsAndMessaging::SW_RESTORE,
                                );
                                windows_sys::Win32::UI::WindowsAndMessaging::SetForegroundWindow(
                                    hwnd.0 as _,
                                );
                            }
                        }
                    }
                }
                tokio::time::sleep(tokio::time::Duration::from_millis(1500)).await;
                if let Some(window) = app_handle_for_show.get_webview_window("main") {
                    let _ = window.set_always_on_top(false);
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            start_backend,
            stop_backend,
            send_chat_message,
            get_chat_history,
            new_session,
            backend_status,
            get_backend_health,
            get_amd_cloud_config,
            update_amd_cloud_config,
            get_amd_gpu_metrics,
            get_all_sessions,
            delete_session,
            get_all_memories,
            add_memory,
            update_memory,
            delete_memory,
            index_document,
            get_available_models,
            get_role_models,
            update_role_model,
            get_api_keys,
            add_api_key,
            delete_api_key,
            test_api_key,
            get_model_tracker_data,
            save_model_note,
            get_mcp_servers,
            add_mcp_server,
            delete_mcp_server,
            get_mcp_logs,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
