from agents.mcp import MCPServerStdio, MCPServerStreamableHttp, MCPServerSse

def load_mcp_list(config: dict) -> list:
    servers = []
    for name, cfg in config.get("mcp_servers", {}).items():
        transport = cfg["transport"]
        if transport == "stdio":
            servers.append(MCPServerStdio(
                name=name,
                params={
                    "command": cfg["command"],
                    "args": cfg.get("args", []),
                    "env": cfg.get("env"),
                    "cwd": cfg.get("cwd"),
                },
                cache_tools_list=cfg.get("cache_tools_list", True),
                tool_filter=cfg.get("tool_filter"),
                require_approval=cfg.get("require_approval", "never"),
            ))
        elif transport == "streamable_http":
            servers.append(MCPServerStreamableHttp(
                name=name,
                params={
                    "url": cfg["url"],
                    "headers": cfg.get("headers"),
                },
                cache_tools_list=cfg.get("cache_tools_list", True),
                tool_filter=cfg.get("tool_filter"),
                require_approval=cfg.get("require_approval", "never"),
            ))
    return servers